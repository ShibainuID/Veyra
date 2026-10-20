import threading
import time

import pytest
from sqlalchemy import delete, func, insert, select, text, update

from persistence.db import SessionLocal, init_db, read_session
from persistence.models import Farm


@pytest.fixture(autouse=True)
def schema():
    init_db()


def _farm_count(session) -> int:
    return session.scalar(select(func.count()).select_from(Farm))


def _write_one(farm_id: str) -> None:
    with SessionLocal() as session:
        session.add(Farm(id=farm_id, name=farm_id))
        session.commit()


def test_second_writer_in_the_same_thread_fails_at_once():
    with SessionLocal() as outer:
        _farm_count(outer)
        started = time.monotonic()
        with SessionLocal() as inner:
            with pytest.raises(RuntimeError, match="already holds a writing transaction"):
                _farm_count(inner)
        assert time.monotonic() - started < 2
        outer.add(Farm(id="farm-outer", name="Outer"))
        outer.commit()

    _write_one("farm-after-commit")
    with read_session() as session:
        assert _farm_count(session) == 2


@pytest.mark.parametrize("finish", ["rollback", "close"])
def test_writer_slot_is_released_when_the_transaction_ends(finish):
    session = SessionLocal()
    _farm_count(session)
    getattr(session, finish)()

    _write_one("farm-next")
    session.close()


def test_writer_slot_is_released_when_another_thread_closes_the_session():
    session = SessionLocal()
    _farm_count(session)
    closer = threading.Thread(target=session.close)
    closer.start()
    closer.join(5)

    _write_one("farm-after-cross-thread-close")


def test_reading_while_holding_a_writer_is_allowed():
    with SessionLocal() as writer:
        _farm_count(writer)
        with read_session() as reader:
            assert _farm_count(reader) == 0
        writer.add(Farm(id="farm-writer", name="Writer"))
        writer.commit()


def test_writers_in_other_threads_still_wait_their_turn():
    errors: list[Exception] = []

    def other() -> None:
        try:
            _write_one("farm-other-thread")
        except Exception as exc:
            errors.append(exc)

    with SessionLocal() as session:
        _farm_count(session)
        thread = threading.Thread(target=other)
        thread.start()
        time.sleep(0.1)
        session.add(Farm(id="farm-main-thread", name="Main"))
        session.commit()
    thread.join(10)

    assert errors == []
    with read_session() as session:
        assert _farm_count(session) == 2


@pytest.mark.parametrize("statement", [
    lambda: insert(Farm).values(id="farm-core", name="Core"),
    lambda: update(Farm).values(name="Renamed"),
    lambda: delete(Farm),
    lambda: Farm.__table__.insert().values(id="farm-table", name="Table"),
    lambda: Farm.__table__.delete(),
], ids=["orm-insert", "orm-update", "orm-delete", "table-insert", "table-delete"])
def test_read_session_rejects_core_dml(statement):
    _write_one("farm-existing")

    with read_session() as reader:
        with pytest.raises(RuntimeError, match="read-only"):
            reader.execute(statement())

    with read_session() as session:
        assert session.scalars(select(Farm.id)).all() == ["farm-existing"]


def test_read_session_still_runs_selects_and_text():
    with read_session() as reader:
        assert reader.execute(text("SELECT 1")).scalar() == 1
        assert _farm_count(reader) == 0
