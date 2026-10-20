"""Explicit reconcile of an `unknown` action, and alert review invalidating an insurer-notification approval."""

from tests.integration.test_financial_flow import (
    API, SARI_PREMIUM, START_BALANCE, _alert, apply_basic, approved, entries, error_code, execute, payment_body,
    run, sari, sari_policy, set_demo, wallet,
)
from tests.support import MANAGER, OPERATOR, VET

__all__ = ["sari"]  # the fixture is imported for use here


def reconcile(client, action_id, headers=MANAGER):
    return client.post(f"{API}/agent/actions/{action_id}/reconcile", headers=headers)


def test_timeout_then_explicit_reconcile_succeeds_with_one_debit(sari):
    apply_basic(sari)
    set_demo(sari, payment_mode="timeout")
    unknown = run(sari, key="pay-key", **payment_body(sari))
    assert unknown["status"] == "unknown" and wallet(sari)["held_minor"] == SARI_PREMIUM

    forbidden = reconcile(sari, unknown["id"], headers=OPERATOR)
    assert forbidden.status_code == 403 and error_code(forbidden) == "FORBIDDEN_ROLE"

    response = reconcile(sari, unknown["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "succeeded" and body["execution"]["id"] == unknown["execution"]["id"]
    assert body["execution"]["idempotency_key"] == "pay-key" and body["execution"]["provider_receipt"]
    assert len(entries(unknown["id"], "debit")) == 1
    assert wallet(sari)["available_minor"] == START_BALANCE - SARI_PREMIUM and wallet(sari)["held_minor"] == 0
    assert sari_policy().status == "active"

    again = reconcile(sari, unknown["id"])
    assert again.status_code == 409 and error_code(again) == "INVALID_STATE"
    assert len(entries(unknown["id"], "debit")) == 1


def test_reconcile_on_a_non_unknown_action_is_invalid_state(sari):
    action = approved(sari, action_type="POLICY_APPLICATION", animal_id="animal-demo-001",
                      product_id="basic-mortality")
    response = reconcile(sari, action["id"])
    assert response.status_code == 409 and error_code(response) == "INVALID_STATE"
    assert reconcile(sari, "act-missing").status_code == 404


def _review(client, alert_id, headers, **body):
    response = client.patch(f"{API}/alerts/{alert_id}", json=body, headers=headers)
    assert response.status_code == 200, response.text


def test_acknowledging_the_alert_after_approval_makes_the_notification_stale(client):
    alert_id = _alert("animal-demo-002")
    action = approved(client, action_type="INSURER_NOTIFICATION", alert_id=alert_id)
    _review(client, alert_id, OPERATOR, status="acknowledged")
    response = execute(client, action["id"], "ntf-key")
    assert response.status_code == 409 and error_code(response) == "APPROVAL_STALE"
    assert response.json()["error"]["details"]["changed_fields"] == ["evidence_manifest_version"]


def test_vet_assessment_after_approval_makes_the_notification_stale(client):
    alert_id = _alert("animal-demo-002")
    action = approved(client, action_type="INSURER_NOTIFICATION", alert_id=alert_id)
    _review(client, alert_id, VET, note="Walked the pen; mild lameness on the left hind.")
    response = execute(client, action["id"], "ntf-key")
    assert response.status_code == 409 and error_code(response) == "APPROVAL_STALE"
    fresh = run(client, key="ntf-key-2", action_type="INSURER_NOTIFICATION", alert_id=alert_id)
    assert fresh["status"] == "succeeded"
