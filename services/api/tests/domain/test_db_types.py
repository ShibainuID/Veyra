from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError

from persistence.db import SessionLocal, init_db
from persistence.models import (
    ActionExecution, AgentAction, Alert, AuditEvent, Camera, Farm, ProviderRecord, Replay, Track,
)


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


def _alert(session, **overrides) -> Alert:
    session.add(Camera(id="cam-t", farm_id="farm-t", name="Cam", location="Pen", map_x=0.1, map_y=0.2))
    session.flush()
    now = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)
    alert = Alert(id="alr-t", farm_id="farm-t", kind="observation_quality", camera_id="cam-t", window_start=now,
                  window_end=now, rule={"name": "r"}, clip=None, status="open", **overrides)
    session.add(alert)
    session.commit()
    return alert


def test_json_none_is_sql_null(session):
    _alert(session)
    session.expunge_all()

    assert session.scalars(select(Alert.id).where(Alert.clip.is_(None))).all() == ["alr-t"]


def test_in_place_json_mutation_is_persisted(session):
    alert = _alert(session, notes=[])
    alert.notes.append({"by": "user-vet", "text": "checked"})
    alert.rule["score"] = 0.4
    session.commit()

    with SessionLocal() as other:
        loaded = other.get(Alert, "alr-t")
        assert loaded.notes == [{"by": "user-vet", "text": "checked"}]
        assert loaded.rule == {"name": "r", "score": 0.4}


def _action(session) -> None:
    now = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)
    for action_id in ("act-1", "act-2"):
        session.add(AgentAction(id=action_id, farm_id="farm-t", action_type="PREMIUM_PAYMENT", payload={},
                                payload_hash="h", status="approved", proposed_by_type="user", proposed_by_id="u",
                                expires_at=now))
    session.flush()
    session.add(ActionExecution(id="exe-1", action_id="act-1", idempotency_key="key-1", status="executing",
                                provider_id="sandbox-pay"))
    session.commit()


@pytest.mark.parametrize(("action_id", "key"), [("act-1", "key-2"), ("act-2", "key-1")])
def test_action_execution_uniques(session, action_id, key):
    _action(session)
    session.add(ActionExecution(id="exe-2", action_id=action_id, idempotency_key=key, status="executing",
                                provider_id="sandbox-pay"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_provider_record_unique_per_operation_and_key(session):
    def record(record_id: str) -> ProviderRecord:
        return ProviderRecord(id=record_id, provider="sandbox-pay", operation="charge", idempotency_key="k",
                              request={}, response={})

    session.add(record("prv-1"))
    session.commit()
    session.add(record("prv-2"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_track_key_unique_per_replay_and_camera(session):
    _alert(session)
    now = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)
    session.add(Replay(id="rep-1", farm_id="farm-t", scenario_id="healthy", camera_id="cam-t", status="running",
                       speed=1.0))
    session.flush()
    for track_id in ("trk-1", "trk-2"):
        session.add(Track(id=track_id, replay_id="rep-1", camera_id="cam-t", track_key="t-1",
                          association_status="unassigned", first_seen=now, last_seen=now))
    with pytest.raises(IntegrityError):
        session.commit()
