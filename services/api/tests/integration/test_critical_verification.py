"""The critical verification checks, one test per check, in one place.

Each test states the check it verifies and reuses the flows and helpers of the detailed suites
(test_financial_flow, test_claims, test_replay, test_assistant_api).
"""

from datetime import timedelta

from sqlalchemy import select

from domain import clock
from persistence.db import read_session
from persistence.models import Alert, Observation
from tests.integration.test_assistant_api import _ask, _facts
from tests.integration.test_claims import _alert as _bima_alert
from tests.integration.test_claims import _draft, _finding, _incident
from tests.integration.test_financial_flow import (
    API, SARI_PREMIUM, apply_basic, approved, decide, entries, error_code, events, execute, payment_body,
    propose, propose_ok, run, sari, sari_policy, set_demo, wallet,
)
from tests.integration.test_replay import _start
from tests.support import MANAGER, OPERATOR

__all__ = ["sari"]  # the fixture is imported for use here

SARI = "animal-demo-001"


def _application(client) -> dict:
    return propose_ok(client, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")


def test_duplicate_execution_is_rejected(sari):
    """Reject duplicate execution and prevent operator-role approvals (duplicate execution)."""
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    first = execute(sari, pay["id"], "pay-key").json()
    again = execute(sari, pay["id"], "pay-key").json()
    assert first["status"] == "succeeded" and again["execution"]["id"] == first["execution"]["id"]
    other_key = execute(sari, pay["id"], "pay-key-2")
    assert other_key.status_code == 409 and error_code(other_key) == "DUPLICATE_EXECUTION"
    assert len(entries(pay["id"], "debit")) == 1 and entries(pay["id"], "debit")[0].amount_minor == SARI_PREMIUM


def test_operator_cannot_approve(sari):
    """Reject duplicate execution and prevent operator-role approvals (operator approvals)."""
    action = _application(sari)
    response = decide(sari, action, headers=OPERATOR)
    assert response.status_code == 403 and error_code(response) == "FORBIDDEN_ROLE"
    assert sari.get(f"{API}/agent/actions/{action['id']}", headers=MANAGER).json()["status"] == "pending_approval"
    assert execute(sari, action["id"], headers=OPERATOR).status_code == 403


def test_execution_blocked_after_declined_approval(sari):
    """Block execution after declined, expired, or stale approval (declined)."""
    action = _application(sari)
    assert decide(sari, action, "decline", note="Not this season").json()["status"] == "declined"
    response = execute(sari, action["id"])
    assert response.status_code == 409 and error_code(response) == "APPROVAL_REQUIRED"
    assert events("action.executed") == []


def test_execution_blocked_after_expired_approval(sari):
    """Block execution after declined, expired, or stale approval (expired)."""
    action = approved(sari, action_type="POLICY_APPLICATION", animal_id=SARI, product_id="basic-mortality")
    later = clock.now() + timedelta(minutes=31)
    clock.set_now(lambda: later)
    response = execute(sari, action["id"])
    assert response.status_code == 409 and error_code(response) == "ACTION_EXPIRED"
    assert sari.get(f"{API}/agent/actions/{action['id']}", headers=MANAGER).json()["status"] == "expired"
    assert events("action.executed") == []


def test_execution_blocked_after_stale_approval(sari):
    """Block execution after declined, expired, or stale approval (stale)."""
    apply_basic(sari)
    pay = approved(sari, **payment_body(sari))
    valuation = sari.post(f"{API}/animals/{SARI}/valuations", headers=MANAGER, json={
        "weight_basis": "override", "weight_low_kg": 500, "weight_high_kg": 540, "unit_price_minor_per_kg": 520,
        "price_source": "Demo reference price", "price_date": "2026-10-01"})
    assert valuation.status_code == 201, valuation.text
    response = execute(sari, pay["id"], "pay-key")
    assert response.status_code == 409 and error_code(response) == "APPROVAL_STALE"
    assert entries(pay["id"], "debit") == [] and wallet(sari)["held_minor"] == 0


def test_unresolved_track_does_not_inherit_a_passport(sari):
    """Confirm an unresolved track cannot silently inherit an animal's passport."""
    started = _start(sari, "lost_identity")
    replay = sari.get(f"{API}/replays/{started['replay_id']}", headers=MANAGER).json()
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    lost, new = tracks["t-03"], tracks["t-14"]
    assert (lost["association_status"], lost["animal_id"]) == ("uncertain", None)
    assert (new["association_status"], new["animal_id"]) == ("unassigned", None)
    with read_session() as session:
        on_new = session.scalars(select(Observation).where(Observation.track_id == new["id"])).all()
        new_alerts = session.scalars(select(Alert).where(Alert.track_id == new["id"])).all()
    assert on_new and all(o.animal_id is None for o in on_new)
    assert all(a.animal_id is None for a in new_alerts)
    assert all(o["track_id"] != new["id"]
               for o in sari.get(f"{API}/animals/animal-demo-002/observations", headers=MANAGER).json()["recent"])


def test_payment_success_does_not_activate_coverage_by_itself(sari):
    """Confirm payment success does not independently activate coverage."""
    apply_basic(sari)
    set_demo(sari, insurer_activation="withhold")
    paid = run(sari, key="pay-key", **payment_body(sari))
    assert paid["status"] == "succeeded" and len(entries(paid["id"], "debit")) == 1
    policy = sari_policy()
    assert policy.status == "paid_pending_activation" and policy.effective_date is None
    assert events("policy.activated") == []


def test_claim_missing_a_required_item_is_blocked_and_the_reason_kept(client):
    """Block a claim missing a configured required item; preserve the reason."""
    incident = _incident(client, linked_alert_ids=[_bima_alert()]).json()
    claim = _draft(client, incident["id"]).json()
    client.patch(f"{API}/claims/{claim['id']}", json={"declaration_confirmed": True}, headers=MANAGER)
    response = propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert response.status_code == 409 and error_code(response) == "EVIDENCE_INCOMPLETE"
    assert response.json()["error"]["details"]["missing"] == ["vet_assessment"]
    stored = client.get(f"{API}/claims/{claim['id']}", headers=MANAGER).json()
    assert stored["status"] == "draft" and stored["blocked_reason"]["missing"] == ["vet_assessment"]


def test_observed_behavior_farmer_report_and_professional_findings_stay_distinct(client):
    """Keep observed behavior, farmer-reported incident, and confirmed professional findings distinct."""
    alert_id = _bima_alert()
    incident = _incident(client, linked_alert_ids=[alert_id]).json()
    assert _finding(client, incident["id"]).status_code == 201
    stored = client.get(f"{API}/incidents/{incident['id']}", headers=MANAGER).json()
    # Farmer report: the operator's own words and facts.
    assert stored["reported_by"] == "user-operator" and stored["description"].startswith("Left hind")
    # Professional finding: a separate list, authored by the vet.
    [finding] = stored["professional_findings"]
    assert (finding["finding_type"], finding["author_role"]) == ("vet_assessment", "vet")
    assert finding["summary"] not in stored["description"]
    # Observed behavior: the camera alert stays its own record, only linked by id.
    assert stored["linked_alert_ids"] == [alert_id]
    alert = client.get(f"{API}/alerts/{alert_id}", headers=MANAGER).json()
    assert alert["kind"] == "reduced_movement" and alert["notes"] == []


def test_location_query_returns_last_seen_or_missing_evidence(sari):
    """Return last-seen time or missing evidence for unsupported location queries."""
    seen = _ask(sari, "Where was Bima last seen?")
    assert seen["intent"] == "location_lookup" and seen["missing"] == []
    assert _facts(seen)["Last observed on"][2] == "cam-pen-a"
    unseen = _ask(sari, "Where is Dewi?")
    assert unseen["missing"] == ["last_observation"] and unseen["facts"] == []
    assert "No camera observation is on record" in unseen["answer"]
