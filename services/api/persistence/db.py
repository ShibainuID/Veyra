"""Engine, sessions, and the declarative base (plan Section 2).

The engine is built lazily and cached per `database_url`, so nothing connects at import time and a test
with a fresh data dir gets a fresh database. Callers own the transaction: `get_session` never commits.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator

from config import get_settings


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
    type_annotation_map = {datetime: UTCDateTime, dict: JSON, list: JSON}


_engines: dict[str, Engine] = {}


def _sqlite_pragmas(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    url = get_settings().database_url
    engine = _engines.get(url)
    if engine is None:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(url, connect_args={"check_same_thread": False})
            event.listen(engine, "connect", _sqlite_pragmas)
        else:
            engine = create_engine(url)
        _engines[url] = engine
    return engine


def reset_engine() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def SessionLocal() -> Session:
    return Session(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency. The route commits; an exception rolls back."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    import persistence.models  # noqa: F401  (registers the tables on Base.metadata)

    get_settings().media_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(get_engine())


def drop_all() -> None:
    import persistence.models  # noqa: F401

    Base.metadata.drop_all(get_engine())
