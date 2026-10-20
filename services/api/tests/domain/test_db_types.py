from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import StatementError

from persistence.db import SessionLocal, init_db
from persistence.models import AuditEvent, Farm


@pytest.fixture
def session():
    init_db()
    with SessionLocal() as session:
        session.add(Farm(id="farm-t", name="Test Farm"))
        session.commit()
        yield session


def _event(created_at: datetime) -> AuditEvent:
    return AuditEvent(id="evt-1", farm_id="farm-t", actor_type="system", actor_id="test", event_type="test",
                      subject_type="farm", subject_id="farm-t", data={}, created_at=created_at)


def test_utc_datetime_round_trip_is_aware_utc(session):
    jakarta = datetime(2026, 10, 20, 16, 30, tzinfo=timezone(timedelta(hours=7)))
    session.add(_event(jakarta))
    session.commit()
    session.expunge_all()

    loaded = session.get(AuditEvent, "evt-1")

    assert loaded.created_at.tzinfo is UTC
    assert loaded.created_at == datetime(2026, 10, 20, 9, 30, tzinfo=UTC)


def test_utc_datetime_rejects_naive(session):
    session.add(_event(datetime(2026, 10, 20, 9, 30)))
    with pytest.raises(StatementError, match="naive"):
        session.commit()
