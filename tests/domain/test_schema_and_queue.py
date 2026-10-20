"""Database-level guarantees that later workflows rely on."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from domain import jobs
from persistence.models import AgentAction, Animal, Execution


def _action(s, farm_id) -> AgentAction:
    animal = Animal(farm_id=farm_id, display_id=f"animal-{uuid.uuid4().hex[:6]}")
    s.add(animal)
    s.flush()
    action = AgentAction(farm_id=farm_id, lineage_id=uuid.uuid4(), action_type="PREMIUM_PAYMENT", animal_id=animal.id,
                         payload={"amount_minor": 250000}, payload_sha256="0" * 64, evidence_manifest_version=1,
                         status="approved", proposed_by="agent", expires_at=datetime.now(UTC) + timedelta(hours=1))
    s.add(action)
    s.flush()
    return action


def test_only_one_live_execution_per_action(db, make_user):
    user, _ = make_user()
    with db.sessions() as s:
        action = _action(s, user.farm_id)
        s.add(Execution(farm_id=user.farm_id, action_id=action.id, idempotency_key="k1", status="executing"))
        s.commit()
        s.add(Execution(farm_id=user.farm_id, action_id=action.id, idempotency_key="k2", status="executing"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_failed_execution_allows_a_retry(db, make_user):
    user, _ = make_user()
    with db.sessions() as s:
        action = _action(s, user.farm_id)
        s.add(Execution(farm_id=user.farm_id, action_id=action.id, idempotency_key="k1", status="failed"))
        s.add(Execution(farm_id=user.farm_id, action_id=action.id, idempotency_key="k2", status="executing"))
        s.commit()


def test_idempotency_key_is_unique_per_farm(db, make_user):
    user, _ = make_user()
    with db.sessions() as s:
        a1, a2 = _action(s, user.farm_id), _action(s, user.farm_id)
        s.add(Execution(farm_id=user.farm_id, action_id=a1.id, idempotency_key="same", status="failed"))
        s.commit()
        s.add(Execution(farm_id=user.farm_id, action_id=a2.id, idempotency_key="same", status="executing"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_status_check_constraint_rejects_unknown_values(db, make_user):
    user, _ = make_user()
    with db.sessions() as s:
        s.add(Animal(farm_id=user.farm_id, display_id="animal-x", identity_status="probably"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_two_workers_never_claim_the_same_job(db, make_user):
    user, _ = make_user()
    with db.sessions() as s:
        jobs.enqueue(s, user.farm_id, "echo", {}, user.id)
        s.commit()
    with db.sessions() as s1, db.sessions() as s2:
        # s1 locks the only queued row inside an open transaction; s2 must skip it.
        from sqlalchemy import select

        from persistence.models import Job
        locked = s1.scalars(select(Job).where(Job.status == "queued").with_for_update(skip_locked=True)).first()
        assert locked is not None
        assert jobs.claim_next(s2) is None
        s1.rollback()
