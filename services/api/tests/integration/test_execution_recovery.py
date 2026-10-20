"""Stranded executions: a crash between claiming an execution and applying its result must be recoverable."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from adapters.sandbox import payment
from domain import actions, clock
from domain.auth import Principal
from main import create_app
from persistence.db import SessionLocal
from persistence.models import ActionExecution, Animal, AuditEvent
from tests.integration.test_financial_flow import (
    SARI, SARI_PREMIUM, START_BALANCE, apply_basic, approved, entries, error_code, execute, payment_body, propose,
    propose_ok, sari, sari_policy, wallet,
)

__all__ = ["sari"]  # the fixture is imported for use here
MANAGER_PRINCIPAL = Principal(user_id="user-manager", farm_id="farm-wahyu", role="manager", name="W. Santoso")


def _execution(action_id) -> ActionExecution:
    with SessionLocal() as session:
        return session.scalars(select(ActionExecution).where(ActionExecution.action_id == action_id)).one()


def _status(client, action_id) -> str:
    from tests.support import MANAGER

    return client.get(f"/api/v1/agent/actions/{action_id}", headers=MANAGER).json()["status"]


def test_charge_landed_but_apply_crashed_reconciles_on_same_key(sari, monkeypatch):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    real_finish = actions._finish
    calls = {"n": 0}

    def crash_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database is locked")
        return real_finish(*args, **kwargs)

    monkeypatch.setattr(actions, "_finish", crash_once)
    with pytest.raises(RuntimeError):
        actions.execute(MANAGER_PRINCIPAL, pay["id"], "pay-key")
    assert _execution(pay["id"]).status == "executing" and wallet(sari)["held_minor"] == SARI_PREMIUM

    retry = execute(sari, pay["id"], "pay-key").json()

    assert retry["status"] == "succeeded" and retry["execution"]["status"] == "succeeded"
    assert len(entries(pay["id"], "debit")) == 1
    assert wallet(sari)["available_minor"] == START_BALANCE - SARI_PREMIUM and wallet(sari)["held_minor"] == 0
    assert sari_policy().status == "active"
    assert error_code(execute(sari, pay["id"], "other-key")) == "DUPLICATE_EXECUTION"


def test_recordless_executing_waits_for_lease_then_fails_and_releases(sari, monkeypatch):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))

    def crash(*args, **kwargs):
        raise RuntimeError("process died before calling the provider")

    monkeypatch.setattr(actions, "_call_provider", crash)
    with pytest.raises(RuntimeError):
        actions.execute(MANAGER_PRINCIPAL, pay["id"], "pay-key")
    monkeypatch.undo()

    inside = execute(sari, pay["id"], "pay-key").json()
    assert inside["status"] == "executing" and wallet(sari)["held_minor"] == SARI_PREMIUM

    later = clock.now() + actions.EXECUTION_LEASE + timedelta(seconds=1)
    clock.set_now(lambda: later)
    after = execute(sari, pay["id"], "pay-key").json()

    assert after["status"] == "failed" and after["execution"]["error"]["code"] == "PROVIDER_NO_RECORD"
    assert wallet(sari)["held_minor"] == 0 and wallet(sari)["available_minor"] == START_BALANCE
    assert entries(pay["id"], "debit") == []
    clock.reset()
    assert propose(sari, **payment_body(sari)).status_code == 201


def test_provider_error_is_unknown_then_recordless_reconcile_fails_and_releases(sari, monkeypatch):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))

    def broken(*args, **kwargs):
        raise ConnectionError("sandbox unreachable")

    monkeypatch.setattr(payment, "charge", broken)
    first = execute(sari, pay["id"], "pay-key").json()
    assert first["status"] == "unknown" and first["execution"]["error"]["code"] == "PROVIDER_ERROR"
    assert wallet(sari)["held_minor"] == SARI_PREMIUM
    monkeypatch.undo()

    retry = execute(sari, pay["id"], "pay-key").json()

    assert retry["status"] == "failed" and retry["execution"]["error"]["code"] == "PROVIDER_NO_RECORD"
    assert wallet(sari)["held_minor"] == 0 and wallet(sari)["available_minor"] == START_BALANCE
    assert sari_policy().status == "awaiting_payment"
    assert propose(sari, **payment_body(sari)).status_code == 201


def test_timeout_records_provider_timeout_code(sari):
    from tests.integration.test_financial_flow import run, set_demo

    apply_basic(sari)
    set_demo(sari, payment_mode="timeout")
    unknown = run(sari, key="pay-key", **payment_body(sari))
    assert unknown["execution"]["error"]["code"] == "PROVIDER_TIMEOUT"


def test_startup_marks_orphaned_executions_unknown(sari, app, monkeypatch):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    monkeypatch.setattr(actions, "_call_provider", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("killed")))
    with pytest.raises(RuntimeError):
        actions.execute(MANAGER_PRINCIPAL, pay["id"], "pay-key")
    monkeypatch.undo()

    with TestClient(create_app()) as restarted:  # the lifespan runs startup recovery
        assert _status(restarted, pay["id"]) == "unknown"
        assert _execution(pay["id"]).status == "unknown"
        with SessionLocal() as session:
            event = session.scalars(select(AuditEvent).where(
                AuditEvent.event_type == "action.execution_orphaned")).one()
        assert event.actor_type == "system" and event.data["action_id"] == pay["id"]
        retry = execute(restarted, pay["id"], "pay-key").json()
        assert retry["status"] == "failed"  # the provider was never called
        assert wallet(restarted)["held_minor"] == 0


def test_identity_lost_after_approval_is_identity_unconfirmed(sari):
    action = approved(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    with SessionLocal() as session:
        session.get(Animal, SARI).identity_status = "pending_review"
        session.commit()

    response = execute(sari, action["id"])

    assert response.status_code == 409 and error_code(response) == "IDENTITY_UNCONFIRMED"
    assert _status(sari, action["id"]) == "cancelled"


def test_revise_reproposes_from_the_action_references(sari):
    from tests.support import MANAGER, OPERATOR, VET

    first = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality",
                       rationale="Cheapest eligible cover")
    response = sari.post(f"/api/v1/agent/actions/{first['id']}/revise", headers=OPERATOR)

    assert response.status_code == 201, response.text
    revised = response.json()
    assert (revised["version"], revised["supersedes_id"], revised["status"]) == (2, first["id"], "pending_approval")
    assert revised["payload"]["product_id"] == "basic-mortality" and revised["rationale"] == "Cheapest eligible cover"
    assert _status(sari, first["id"]) == "cancelled"
    assert sari.post(f"/api/v1/agent/actions/{revised['id']}/revise", headers=VET).status_code == 403

    later = clock.now() + timedelta(minutes=31)
    clock.set_now(lambda: later)
    expired = sari.post(f"/api/v1/agent/actions/{revised['id']}/revise", headers=MANAGER).json()
    assert (expired["version"], expired["supersedes_id"]) == (3, revised["id"])
    clock.reset()


def test_revise_refuses_executed_actions(sari):
    from tests.support import OPERATOR

    executed = apply_basic(sari)
    response = sari.post(f"/api/v1/agent/actions/{executed['id']}/revise", headers=OPERATOR)
    assert response.status_code == 409 and error_code(response) == "INVALID_STATE"
