import threading
import time

import pytest
from sqlalchemy import func, select

from persistence.db import SessionLocal, init_db, read_session
from persistence.models import Farm


@pytest.fixture(autouse=True)
def schema():
    init_db()


def _farm_count(session) -> int:
    return session.scalar(select(func.count()).select_from(Farm))


def _in_thread(target) -> tuple[threading.Thread, list[Exception]]:
    errors: list[Exception] = []

    def run() -> None:
        try:
            target()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, errors


def _insert_farm(farm_id: str) -> None:
    with SessionLocal() as session:
        session.add(Farm(id=farm_id, name=farm_id))
        session.commit()


def test_read_then_write_survives_a_concurrent_writer():
    with SessionLocal() as session:
        before = _farm_count(session)
        writer, errors = _in_thread(lambda: _insert_farm("farm-other-writer"))
        time.sleep(0.1)
        session.add(Farm(id="farm-reader-writer", name="Reader"))
        session.commit()
    writer.join(10)

    assert errors == []
    with read_session() as session:
        assert _farm_count(session) == before + 2


def test_writing_sessions_serialize_read_modify_write():
    first_holds_lock = threading.Event()
    seen_by_second: list[int] = []

    def first() -> None:
        with SessionLocal() as session:
            count = _farm_count(session)
            first_holds_lock.set()
            time.sleep(0.2)
            session.add(Farm(id=f"farm-{count}", name="First"))
            session.commit()

    def second() -> None:
        first_holds_lock.wait(5)
        with SessionLocal() as session:
            count = _farm_count(session)
            seen_by_second.append(count)
            session.add(Farm(id=f"farm-{count}", name="Second"))
            session.commit()

    threads = [_in_thread(first), _in_thread(second)]
    for thread, _ in threads:
        thread.join(10)

    assert [error for _, errors in threads for error in errors] == []
    assert seen_by_second == [1]


def test_read_session_sees_a_snapshot_and_does_not_block_writers():
    with read_session() as reader:
        before = _farm_count(reader)
        started = time.monotonic()
        _insert_farm("farm-while-reading")

        assert time.monotonic() - started < 2
        assert _farm_count(reader) == before
        reader.rollback()
        assert _farm_count(reader) == before + 1


def test_read_session_refuses_to_write():
    with read_session() as reader:
        reader.add(Farm(id="farm-sneaky", name="Sneaky"))
        with pytest.raises(RuntimeError, match="read-only"):
            reader.flush()


def test_outer_rollback_discards_savepoint_writes():
    with SessionLocal() as session:
        _farm_count(session)
        with session.begin_nested():
            session.add(Farm(id="farm-nested", name="Nested"))
        session.rollback()

    with read_session() as session:
        assert session.get(Farm, "farm-nested") is None
