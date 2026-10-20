"""Critical verification for the Agent Wallet: approval, idempotent execution, ledger, and activation."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from domain import clock
from persistence.db import SessionLocal
from persistence.models import Alert, Animal, AuditEvent, Policy, WalletEntry
from tests.support import MANAGER, OPERATOR, OTHER_FARM, VET

API = "/api/v1"
SARI = "animal-demo-001"
START_BALANCE = 978638
SARI_PREMIUM = 8736


@pytest.fixture
def sari(client):
    response = client.post(f"{API}/demo/reset", params={"scenario": "post-enrollment"}, headers=MANAGER)
    assert response.status_code == 200, response.text
    return client


def propose(client, headers=OPERATOR, **body):
    return client.post(f"{API}/agent/actions", json=body, headers=headers)


def propose_ok(client, **body) -> dict:
    response = propose(client, **body)
    assert response.status_code == 201, response.text
    return response.json()


def decide(client, action, decision="approve", headers=MANAGER, **overrides):
    body = {"decision": decision, "payload_hash": action["payload_hash"], "version": action["version"], **overrides}
    return client.post(f"{API}/agent/actions/{action['id']}/decision", json=body, headers=headers)


def execute(client, action_id, key="key-1", headers=MANAGER):
    extra = {"Idempotency-Key": key} if key is not None else {}
    return client.post(f"{API}/agent/actions/{action_id}/execute", headers={**headers, **extra})


def approved(client, **body) -> dict:
    action = propose_ok(client, **body)
    response = decide(client, action)
    assert response.status_code == 200, response.text
    return response.json()


def run(client, key="key-1", **body) -> dict:
    action = approved(client, **body)
    response = execute(client, action["id"], key)
    assert response.status_code == 200, response.text
    return response.json()


def apply_basic(client) -> dict:
    executed = run(client, key="app-key", action_type="POLICY_APPLICATION", animal_id=SARI,
                   product_id="basic-mortality")
    assert executed["status"] == "succeeded"
    return executed


def application_id(client) -> str:
    policy = sari_policy()
    return policy.application_id


def sari_policy() -> Policy:
    with SessionLocal() as session:
        return session.scalars(select(Policy).where(Policy.animal_id == SARI)).one()


def set_demo(client, payment_mode="succeed", insurer_activation="confirm"):
    response = client.put(f"{API}/demo/settings", headers=MANAGER,
                          json={"payment_mode": payment_mode, "insurer_activation": insurer_activation})
    assert response.status_code == 200, response.text


def wallet(client) -> dict:
    return client.get(f"{API}/wallet", headers=MANAGER).json()


def entries(action_id, entry_type) -> list[WalletEntry]:
    with SessionLocal() as session:
        return session.scalars(select(WalletEntry).where(WalletEntry.action_id == action_id,
                                                         WalletEntry.entry_type == entry_type)).all()


def events(event_type) -> list[AuditEvent]:
    with SessionLocal() as session:
        return session.scalars(select(AuditEvent).where(AuditEvent.event_type == event_type)).all()


def error_code(response) -> str:
    return response.json()["error"]["code"]


def payment_body(client) -> dict:
    return {"action_type": "PREMIUM_PAYMENT", "policy_application_id": application_id(client)}


# Full flow ---------------------------------------------------------------------------------------------------

def test_full_flow_application_payment_then_separate_activation(sari):
    recommendation = sari.post(f"{API}/animals/{SARI}/insurance-recommendations", headers=OPERATOR).json()
    basic = next(r for r in recommendation["results"] if r["product_id"] == "basic-mortality")
    assert basic["outcome"] == "eligible"

    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality",
                        rationale="Cheapest eligible cover")
    assert action["status"] == "pending_approval" and action["version"] == 1
    payload = action["payload"]
    assert payload["premium_minor"] == basic["premium_minor"] == SARI_PREMIUM
    assert payload["insured_value_minor"] == 249600 and payload["deductible_minor"] == 24960
    assert payload["disclosed_fields"] == ["animal_id", "breed", "sex", "age_range", "weight_range",
                                           "valuation_range", "identity_reference"]
    assert payload["evidence_manifest_version"] == action["evidence_manifest"]["version"] == 1
    assert {i["type"] for i in action["evidence_manifest"]["items"]} >= {"identity_reference", "valuation"}
    assert action["review"]["recipient"] == "Sandbox Mutual"
    assert action["proposed_by_type"] == "agent" and action["proposed_by_id"] == "user-operator"
    assert action["expires_at"].endswith("Z")

    approve = decide(sari, action)
    assert approve.status_code == 200 and approve.json()["status"] == "approved"
    executed = execute(sari, action["id"], "app-key").json()
    assert executed["status"] == "succeeded"
    assert executed["execution"]["provider_receipt"]["status"] == "accepted"
    policy = sari_policy()
    assert policy.status == "awaiting_payment" and policy.premium_minor == SARI_PREMIUM

    pay = propose_ok(sari, **payment_body(sari))
    assert pay["payload"]["amount_minor"] == SARI_PREMIUM and pay["payload"]["mode"] == "sandbox"
    assert pay["review"]["balance_after_minor"] == START_BALANCE - SARI_PREMIUM
    decide(sari, pay)
    paid = execute(sari, pay["id"], "pay-key").json()
    assert paid["status"] == "succeeded"
    assert paid["execution"]["provider_receipt"]["payment_ref"].startswith("SBX-PAY-")

    policy = sari_policy()
    assert policy.status == "active"
    assert policy.activation_receipt["activated"] is True and policy.effective_date == clock.now().date()
    assert wallet(sari)["available_minor"] == START_BALANCE - SARI_PREMIUM
    assert wallet(sari)["held_minor"] == 0
    assert len(entries(pay["id"], "debit")) == 1

    # Agent proposal, human decision, provider result, and insurer activation are separate events.
    with SessionLocal() as session:
        trail = session.scalars(select(AuditEvent).where(AuditEvent.animal_id == SARI)
                                .order_by(AuditEvent.created_at)).all()
    pay_events = [(e.event_type, e.actor_type) for e in trail if e.data.get("action_id") == pay["id"]]
    assert pay_events == [("action.proposed", "agent"), ("action.approved", "user"), ("action.executed", "provider")]
    activated = [e for e in trail if e.event_type == "policy.activated"]
    assert len(activated) == 1 and activated[0].actor_type == "provider"

    passport = sari.get(f"{API}/animals/{SARI}/passport", headers=MANAGER).json()
    titles = [line["title"] for line in passport["passbook"]["lines"]]
    assert "Policy active · Basic Mortality & Accident" in titles
    assert "Premium payment paid" in titles
    stamps = {line["title"]: line["stamp"] for line in passport["passbook"]["lines"]}
    assert stamps["Premium payment approved"]["kind"] == "approved"


# Approval rules ----------------------------------------------------------------------------------------------

def test_operator_decision_is_forbidden_even_when_operator_proposed(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    response = decide(sari, action, headers=OPERATOR)
    assert response.status_code == 403 and error_code(response) == "FORBIDDEN_ROLE"
    assert execute(sari, action["id"], headers=OPERATOR).status_code == 403


def test_declined_action_cannot_execute(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    assert decide(sari, action, "decline", note="Not now").json()["status"] == "declined"
    response = execute(sari, action["id"])
    assert response.status_code == 409 and error_code(response) == "APPROVAL_REQUIRED"


def test_pending_action_cannot_execute(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    assert error_code(execute(sari, action["id"])) == "APPROVAL_REQUIRED"


def test_expired_action_cannot_be_approved_or_executed(sari):
    pending = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    later = clock.now() + timedelta(minutes=31)
    clock.set_now(lambda: later)
    response = decide(sari, pending)
    assert response.status_code == 409 and error_code(response) == "ACTION_EXPIRED"
    assert sari.get(f"{API}/agent/actions/{pending['id']}", headers=MANAGER).json()["status"] == "expired"
    assert [e.data["action_id"] for e in events("action.expired")] == [pending["id"]]

    clock.reset()
    action = approved(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    later = clock.now() + timedelta(minutes=31)
    clock.set_now(lambda: later)
    response = execute(sari, action["id"])
    assert response.status_code == 409 and error_code(response) == "ACTION_EXPIRED"
    assert sari.get(f"{API}/agent/actions/{action['id']}", headers=MANAGER).json()["status"] == "expired"


def test_wrong_hash_or_version_is_stale(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    response = decide(sari, action, payload_hash="0" * 64)
    assert response.status_code == 409 and error_code(response) == "APPROVAL_STALE"
    assert error_code(decide(sari, action, version=2)) == "APPROVAL_STALE"
    assert decide(sari, action).status_code == 200


def test_reproposing_supersedes_the_pending_action(sari):
    first = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    second = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    assert (second["version"], second["supersedes_id"]) == (2, first["id"])
    old = sari.get(f"{API}/agent/actions/{first['id']}", headers=MANAGER).json()
    assert (old["status"], old["cancel_reason"]) == ("cancelled", "superseded")
    assert error_code(decide(sari, old)) == "INVALID_STATE"


def test_cancel_by_operator(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    response = sari.post(f"{API}/agent/actions/{action['id']}/cancel", headers=OPERATOR)
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert error_code(sari.post(f"{API}/agent/actions/{action['id']}/cancel", headers=OPERATOR)) == "INVALID_STATE"


def test_ineligible_or_unknown_product_cannot_be_proposed(sari):
    unknown = propose(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="mortality-theft")
    assert unknown.status_code == 409 and error_code(unknown) == "INVALID_STATE"
    assert unknown.json()["error"]["details"]["outcome"] == "unknown"
    ineligible = propose(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="dairy-health-plus")
    assert ineligible.json()["error"]["details"]["outcome"] == "ineligible"
    assert propose(sari, headers=VET, action_type="POLICY_APPLICATION", animal_id=SARI,
                   product_id="basic-mortality").status_code == 403


def test_unconfirmed_animal_is_refused(sari):
    with SessionLocal() as session:
        session.get(Animal, SARI).identity_status = "pending_review"
        session.commit()
    response = propose(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    assert response.status_code == 409 and error_code(response) == "IDENTITY_UNCONFIRMED"


def test_cross_farm_action_access_is_not_found(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    assert sari.get(f"{API}/agent/actions/{action['id']}", headers=OTHER_FARM).status_code == 404
    assert decide(sari, action, headers=OTHER_FARM).status_code == 404
    assert execute(sari, action["id"], headers=OTHER_FARM).status_code == 404
    assert sari.get(f"{API}/agent/actions", headers=OTHER_FARM).json()["items"] == []
    other = propose(sari, headers=OTHER_FARM, action_type="POLICY_APPLICATION", animal_id=SARI,
                    product_id="basic-mortality")
    assert other.status_code == 404


def test_list_filters(sari):
    action = propose_ok(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    listed = sari.get(f"{API}/agent/actions", params={"status": "pending_approval", "animal_id": SARI},
                      headers=VET).json()["items"]
    assert [a["id"] for a in listed] == [action["id"]]
    assert sari.get(f"{API}/agent/actions", params={"status": "approved"}, headers=VET).json()["items"] == []


# Idempotent execution ----------------------------------------------------------------------------------------

def test_missing_idempotency_key_is_400(sari):
    action = approved(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    response = execute(sari, action["id"], key=None)
    assert response.status_code == 400 and error_code(response) == "IDEMPOTENCY_KEY_REQUIRED"


def test_same_key_returns_same_execution_and_one_debit(sari):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    first = execute(sari, pay["id"], "pay-key").json()
    second = execute(sari, pay["id"], "pay-key").json()
    assert first["execution"]["id"] == second["execution"]["id"]
    assert second["status"] == "succeeded"
    assert len(entries(pay["id"], "debit")) == 1
    assert wallet(sari)["available_minor"] == START_BALANCE - SARI_PREMIUM


def test_new_key_after_success_is_duplicate(sari):
    executed = apply_basic(sari)
    response = execute(sari, executed["id"], "another-key")
    assert response.status_code == 409 and error_code(response) == "DUPLICATE_EXECUTION"


def test_key_reused_for_another_action_is_duplicate(sari):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    response = execute(sari, pay["id"], "app-key")
    assert error_code(response) == "DUPLICATE_EXECUTION"


# Payments ----------------------------------------------------------------------------------------------------

def test_withheld_activation_stays_pending_until_activation_check(sari):
    apply_basic(sari)
    set_demo(sari, insurer_activation="withhold")
    paid = run(sari, key="pay-key", **payment_body(sari))
    assert paid["status"] == "succeeded"
    policy = sari_policy()
    assert policy.status == "paid_pending_activation" and policy.effective_date is None
    assert len(events("policy.activation_pending")) == 1 and events("policy.activated") == []

    set_demo(sari, insurer_activation="confirm")
    assert sari.post(f"{API}/policies/{policy.id}/activation-check", headers=OPERATOR).status_code == 403
    response = sari.post(f"{API}/policies/{policy.id}/activation-check", headers=MANAGER)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active" and response.json()["effective_date"] is not None
    assert len(events("policy.activated")) == 1


def test_payment_decline_fails_and_releases_hold(sari):
    apply_basic(sari)
    set_demo(sari, payment_mode="fail")
    failed = run(sari, key="pay-key", **payment_body(sari))
    assert failed["status"] == "failed"
    assert failed["execution"]["error"]["code"] == "SANDBOX_DECLINED"
    assert wallet(sari)["available_minor"] == START_BALANCE and wallet(sari)["held_minor"] == 0
    assert len(entries(failed["id"], "hold")) == len(entries(failed["id"], "release")) == 1
    assert entries(failed["id"], "debit") == []
    assert sari_policy().status == "awaiting_payment"


def test_payment_timeout_is_unknown_then_reconciles_with_one_debit(sari):
    apply_basic(sari)
    set_demo(sari, payment_mode="timeout")
    unknown = run(sari, key="pay-key", **payment_body(sari))
    assert unknown["status"] == "unknown" and unknown["execution"]["status"] == "unknown"
    assert wallet(sari)["held_minor"] == SARI_PREMIUM
    assert sari_policy().status == "awaiting_payment"

    retry = execute(sari, unknown["id"], "pay-key").json()
    assert retry["status"] == "succeeded" and retry["execution"]["id"] == unknown["execution"]["id"]
    assert len(entries(unknown["id"], "debit")) == 1
    assert wallet(sari)["available_minor"] == START_BALANCE - SARI_PREMIUM and wallet(sari)["held_minor"] == 0
    assert sari_policy().status == "active"
    again = execute(sari, unknown["id"], "pay-key").json()
    assert again["status"] == "succeeded" and len(entries(unknown["id"], "debit")) == 1
    statuses = [e.data["status"] for e in events("action.executed") if e.data["action_id"] == unknown["id"]]
    assert statuses == ["unknown", "succeeded"]


def test_insufficient_funds_is_refused(sari):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    with SessionLocal() as session:
        session.add(WalletEntry(id="wal-drain", farm_id="farm-wahyu", entry_type="debit",
                                amount_minor=START_BALANCE - 100, currency="USD", description="drain"))
        session.commit()
    response = execute(sari, pay["id"], "pay-key")
    assert response.status_code == 409 and error_code(response) == "INSUFFICIENT_SANDBOX_FUNDS"
    assert response.json()["error"]["details"] == {"available_minor": 100, "amount_minor": SARI_PREMIUM}
    assert sari.get(f"{API}/agent/actions/{pay['id']}", headers=MANAGER).json()["status"] == "approved"


def test_new_valuation_after_approving_payment_is_stale(sari):
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    valuation = sari.post(f"{API}/animals/{SARI}/valuations", headers=MANAGER, json={
        "weight_basis": "override", "weight_low_kg": 500, "weight_high_kg": 540, "unit_price_minor_per_kg": 520,
        "price_source": "Demo reference price", "price_date": "2026-10-01"})
    assert valuation.status_code == 201
    response = execute(sari, pay["id"], "pay-key")
    assert response.status_code == 409 and error_code(response) == "APPROVAL_STALE"
    assert response.json()["error"]["details"]["changed_fields"] == ["evidence_manifest_version"]
    action = sari.get(f"{API}/agent/actions/{pay['id']}", headers=MANAGER).json()
    assert (action["status"], action["cancel_reason"]) == ("cancelled", "approval_stale")
    assert wallet(sari)["held_minor"] == 0


def test_payment_needs_an_accepted_application(sari):
    response = propose(sari, action_type="PREMIUM_PAYMENT", policy_application_id="app-missing")
    assert response.status_code == 404


# Insurer notification ----------------------------------------------------------------------------------------

def _alert(animal_id, alert_id="alr-test"):
    now = clock.now()
    with SessionLocal() as session:
        session.add(Alert(id=alert_id, farm_id="farm-wahyu", kind="reduced_movement", animal_id=animal_id,
                          camera_id="cam-pen-a", window_start=now - timedelta(minutes=3),
                          window_end=now - timedelta(minutes=1),
                          rule={"name": "reduced_movement_v1", "threshold": 0.6, "score": 0.22, "baseline": 0.81,
                                "source": "simulated"}, status="open", notes=[]))
        session.commit()
    return alert_id


def test_notification_for_insured_animal(client):
    alert_id = _alert("animal-demo-002")
    executed = run(client, key="ntf-key", action_type="INSURER_NOTIFICATION", alert_id=alert_id)
    assert executed["status"] == "succeeded"
    assert executed["execution"]["provider_receipt"]["notification_ref"].startswith("SBX-NTF-")
    summary = executed["payload"]["summary"]
    assert "Reduced movement alert for Bima (animal-demo-002) on camera cam-pen-a" in summary
    assert "score 0.22" in summary and "baseline 0.81" in summary


def test_notification_requires_alert_with_animal_and_active_policy(client):
    unassigned = _alert(None, "alr-unassigned")
    response = propose(client, action_type="INSURER_NOTIFICATION", alert_id=unassigned)
    assert response.status_code == 409 and error_code(response) == "INVALID_STATE"
    uninsured = _alert("animal-demo-004", "alr-uninsured")
    assert error_code(propose(client, action_type="INSURER_NOTIFICATION", alert_id=uninsured)) == "INVALID_STATE"
