import threading
import time

import pytest
from sqlalchemy import func, select

from persistence.db import SessionLocal, immediate_session, init_db
from persistence.models import Farm


@pytest.fixture(autouse=True)
def schema():
    init_db()


def _farm_count(session) -> int:
    return session.scalar(select(func.count()).select_from(Farm))


def test_read_transaction_sees_a_stable_snapshot():
    with SessionLocal() as reader, SessionLocal() as writer:
        before = _farm_count(reader)
        writer.add(Farm(id="farm-race", name="Race"))
        writer.commit()

        assert _farm_count(reader) == before
        reader.rollback()
        assert _farm_count(reader) == before + 1


def test_outer_rollback_discards_savepoint_writes():
    with SessionLocal() as session:
        _farm_count(session)
        with session.begin_nested():
            session.add(Farm(id="farm-nested", name="Nested"))
        session.rollback()

    with SessionLocal() as session:
        assert session.get(Farm, "farm-nested") is None


def test_immediate_sessions_serialize_read_modify_write():
    first_holds_lock = threading.Event()
    seen_by_second: list[int] = []
    errors: list[Exception] = []

    def first() -> None:
        try:
            with immediate_session() as session:
                count = _farm_count(session)
                first_holds_lock.set()
                time.sleep(0.2)
                session.add(Farm(id=f"farm-{count}", name="First"))
                session.commit()
        except Exception as exc:
            errors.append(exc)
            first_holds_lock.set()

    def second() -> None:
        first_holds_lock.wait(5)
        try:
            with immediate_session() as session:
                count = _farm_count(session)
                seen_by_second.append(count)
                session.add(Farm(id=f"farm-{count}", name="Second"))
                session.commit()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert errors == []
    assert seen_by_second == [1]
    with SessionLocal() as session:
        assert _farm_count(session) == 2
