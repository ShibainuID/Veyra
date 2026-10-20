"""Engine, sessions, and the declarative base (plan Section 2).

The engine is built lazily and cached per `database_url`, so nothing connects at import time and a test
with a fresh data dir gets a fresh database. Callers own the transaction: `get_session` never commits.

SQLite transactions are real: pysqlite's own transaction handling is turned off and SQLAlchemy emits
`BEGIN` itself (the documented pysqlite recipe), so a session reads one snapshot and `begin_nested()`
savepoints roll back with their outer transaction. Two kinds of session:
- `SessionLocal()` / `get_session` (writing) start with `BEGIN IMMEDIATE`, taking the write lock before the
  first read. Writers run one at a time; a second writer waits for the first to finish, up to the 15 s busy
  timeout, and then fails with "database is locked". A deferred transaction that read and then tried to
  write after another commit would instead fail at once, which is why writing sessions are immediate.
- `read_session()` / `get_read_session` (read-only) start with a deferred `BEGIN`: they read a WAL snapshot,
  never block writers, and raise if asked to flush changes or to execute an INSERT, UPDATE, or DELETE.

A thread holds at most one writing transaction: starting a second one while the first is open raises
`RuntimeError` at once instead of waiting on itself until the busy timeout. The slot is released when that
transaction commits, rolls back, or its connection returns to the pool, from whichever thread does it.

JSON columns track in-place changes to the top-level dict or list (`notes.append(...)` is saved), but not
changes nested deeper; reassign the attribute for those. A JSON `None` is stored as SQL `NULL`.

Session rules (the API runs as a single uvicorn worker process):
- GET routes and other read-only work use the read session; anything that writes uses the writing session.
- One session per request, job, or thread; never share a session across threads, and never open a writing
  session while the same thread holds another one (the guard above raises).
- Keep writing transactions short: never hold one across slow calls (perception, sandbox providers). Commit
  first, call, then open a new session to record the result.
- Make state transitions guarded updates, `UPDATE ... WHERE id = :id AND status = :expected`, and check the
  rowcount instead of reading the status and then writing it.
- Do not use `begin_nested()` to recover from an `IntegrityError`; roll back the whole session and start over.
"""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState, Session
from sqlalchemy.sql.dml import UpdateBase
from sqlalchemy.types import TypeDecorator

from config import get_settings

SQLITE_BUSY_TIMEOUT_S = 15
_BEGIN_OPTION = "sqlite_begin"
_WRITER_KEY = "veyra_writer_slot"
_READ_ONLY = "read_session() is read-only; use SessionLocal() to write"


class UTCDateTime(TypeDecorator):
    """Stores naive UTC (SQLite drops tzinfo) and returns aware UTC. Naive input is a bug, so it raises."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use domain.clock.now()")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map = {
        datetime: UTCDateTime,
        dict: MutableDict.as_mutable(JSON(none_as_null=True)),
        list: MutableList.as_mutable(JSON(none_as_null=True)),
    }


_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def _sqlite_connect(dbapi_connection, connection_record) -> None:
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class _WriterSlot:
    """Whether one thread holds a writing transaction. The holding connection keeps a reference, so the slot
    is released wherever that transaction ends."""

    held = False


_threads = threading.local()


def _thread_slot() -> _WriterSlot:
    slot = getattr(_threads, "writer", None)
    if slot is None:
        slot = _threads.writer = _WriterSlot()
    return slot


def _sqlite_begin(connection) -> None:
    mode = connection.get_execution_options().get(_BEGIN_OPTION, "IMMEDIATE")
    if mode != "IMMEDIATE":
        connection.exec_driver_sql(f"BEGIN {mode}")
        return
    slot = _thread_slot()
    if slot.held:
        raise RuntimeError("this thread already holds a writing transaction; commit or close that session before "
                           "opening another writing session, or read with read_session()")
    connection.exec_driver_sql("BEGIN IMMEDIATE")
    slot.held = True
    connection.info[_WRITER_KEY] = slot


def _release_writer(info: dict) -> None:
    slot = info.pop(_WRITER_KEY, None)
    if slot is not None:
        slot.held = False


def _on_transaction_end(connection) -> None:
    _release_writer(connection.info)


def _on_checkin(dbapi_connection, connection_record) -> None:
    if connection_record is not None:
        _release_writer(connection_record.info)


def _create_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return create_engine(url)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_S})
    event.listen(engine, "connect", _sqlite_connect)
    event.listen(engine, "begin", _sqlite_begin)
    event.listen(engine, "commit", _on_transaction_end)
    event.listen(engine, "rollback", _on_transaction_end)
    event.listen(engine, "checkin", _on_checkin)
    return engine


def get_engine() -> Engine:
    url = get_settings().database_url
    with _engines_lock:
        if url not in _engines:
            _engines[url] = _create_engine(url)
        return _engines[url]


def reset_engine() -> None:
    with _engines_lock:
        for engine in _engines.values():
            engine.dispose()
        _engines.clear()


def SessionLocal() -> Session:
    """A writing session: each transaction starts with `BEGIN IMMEDIATE`. The caller commits."""
    return Session(bind=get_engine(), expire_on_commit=False)


class _ReadSession(Session):
    def flush(self, objects=None) -> None:
        if self.new or self.dirty or self.deleted:
            raise RuntimeError(_READ_ONLY)
        super().flush(objects)


@event.listens_for(_ReadSession, "do_orm_execute")
def _refuse_dml(state: ORMExecuteState) -> None:
    if isinstance(state.statement, UpdateBase):
        raise RuntimeError(_READ_ONLY)


def read_session() -> Session:
    """A read-only session on a deferred transaction: a consistent snapshot that never blocks writers."""
    return _ReadSession(bind=get_engine().execution_options(**{_BEGIN_OPTION: "DEFERRED"}), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency for routes that write. The route commits; an exception rolls back."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_read_session() -> Iterator[Session]:
    """FastAPI dependency for routes that only read."""
    with read_session() as session:
        yield session


def init_db() -> None:
    import persistence.models  # noqa: F401  (registers the tables on Base.metadata)

    get_settings().media_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(get_engine())


def drop_all() -> None:
    import persistence.models  # noqa: F401

    Base.metadata.drop_all(get_engine())
