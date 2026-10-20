"""Incidents, claim checklists, and claim submission through the Agent Wallet."""

from datetime import timedelta

from sqlalchemy import select

from domain import clock
from persistence.db import SessionLocal
from persistence.models import Alert, AuditEvent, Claim, Policy
from tests.integration.test_financial_flow import approved, decide, error_code, execute, propose, propose_ok
from tests.support import ASSESSOR, MANAGER, OPERATOR, OTHER_FARM, VET

API = "/api/v1"
BIMA = "animal-demo-002"  # seeded active basic-mortality policy: insured 270400, deductible 27040


def _alert(animal_id=BIMA, alert_id="alr-bima"):
    now = clock.now()
    with SessionLocal() as session:
        session.add(Alert(id=alert_id, farm_id="farm-wahyu", kind="reduced_movement", animal_id=animal_id,
                          camera_id="cam-pen-a", window_start=now - timedelta(minutes=3),
                          window_end=now - timedelta(minutes=1), rule={"name": "reduced_movement_v1"},
                          status="open", notes=[]))
        session.commit()
    return alert_id


def _incident(client, animal_id=BIMA, kind="accidental_injury", headers=OPERATOR, **extra):
    occurred = clock.isoformat((clock.now() - timedelta(hours=2)).replace(microsecond=0))
    body = {"animal_id": animal_id, "kind": kind, "occurred_at": occurred,
            "description": "Left hind lameness found at the morning check after a reduced-movement alert.",
            "estimated_loss_minor": 60000, "facts": {"location": "Pen A"}, **extra}
    return client.post(f"{API}/incidents", json=body, headers=headers)


def _draft(client, incident_id, headers=OPERATOR):
    return client.post(f"{API}/claims/drafts", json={"incident_id": incident_id}, headers=headers)


def _finding(client, incident_id, finding_type="vet_assessment", headers=VET):
    return client.post(f"{API}/incidents/{incident_id}/findings", headers=headers,
                       json={"summary": "Soft-tissue injury of the left hind; no fracture.", "finding_type": finding_type})


def _ready_claim(client) -> dict:
    incident = _incident(client, linked_alert_ids=[_alert()]).json()
    claim = _draft(client, incident["id"]).json()
    assert _finding(client, incident["id"]).status_code == 201
    patched = client.patch(f"{API}/claims/{claim['id']}", json={"declaration_confirmed": True}, headers=MANAGER)
    assert patched.status_code == 200, patched.text
    return patched.json()


def test_incident_links_active_policy_and_keeps_fields_distinct(client):
    response = _incident(client, linked_alert_ids=[_alert()])
    assert response.status_code == 201, response.text
    incident = response.json()
    assert incident["policy_id"] is not None and incident["linked_alert_ids"] == ["alr-bima"]
    assert incident["occurred_at"].endswith("Z")
    finding = _finding(client, incident["id"]).json()["professional_findings"][0]
    assert (finding["finding_type"], finding["author_id"], finding["author_role"]) == (
        "vet_assessment", "user-vet", "vet")
    fetched = client.get(f"{API}/incidents/{incident['id']}", headers=ASSESSOR).json()
    assert fetched["reported_by"] == "user-operator" and fetched["reported_by_name"]
    assert fetched["description"].startswith("Left hind") and fetched["facts"] == {"location": "Pen A"}
    with SessionLocal() as session:
        types = session.scalars(select(AuditEvent.event_type).where(AuditEvent.subject_id == incident["id"])).all()
    assert types == ["incident.recorded", "incident.finding_added"]


def test_incident_roles_and_scope(client):
    assert _incident(client, headers=VET).status_code == 403
    assert _incident(client, animal_id="animal-other-001").status_code == 404
    incident = _incident(client).json()
    assert _finding(client, incident["id"], headers=OPERATOR).status_code == 403
    assert _finding(client, incident["id"], headers=MANAGER).status_code == 403
    assert _finding(client, incident["id"]).status_code == 201
    assert client.get(f"{API}/incidents/{incident['id']}", headers=OTHER_FARM).status_code == 404
    other_alert = _alert(animal_id="animal-demo-003", alert_id="alr-melati")
    assert _incident(client, linked_alert_ids=[other_alert]).status_code == 422


def test_claim_needs_an_active_policy_covering_the_peril(client):
    uninsured = _incident(client, animal_id="animal-demo-004").json()
    response = _draft(client, uninsured["id"])
    assert response.status_code == 409 and error_code(response) == "INVALID_STATE"
    illness = _incident(client, kind="illness").json()  # basic-mortality covers accidental_injury and death only
    assert error_code(_draft(client, illness["id"])) == "INVALID_STATE"


def test_alert_alone_cannot_create_a_claim(client):
    response = client.post(f"{API}/claims/drafts", json={"incident_id": _alert()}, headers=OPERATOR)
    assert response.status_code == 404


def test_draft_checklist_and_illustrative_payout(client):
    incident = _incident(client).json()
    claim = _draft(client, incident["id"]).json()
    assert claim["status"] == "draft" and claim["claimed_amount_minor"] == 60000
    status = {item["key"]: item["status"] for item in claim["checklist"]}
    assert status == {"identity_reference": "present", "active_policy": "present", "incident_facts": "present",
                      "farmer_declaration": "missing", "observation_evidence": "missing", "vet_assessment": "missing"}
    assert claim["missing"] == ["farmer_declaration", "observation_evidence", "vet_assessment"]
    payout = claim["illustrative_payout"]
    assert payout["amount_minor"] == 60000 - 27040 and payout["illustrative"] is True
    again = _draft(client, incident["id"]).json()
    assert again["id"] == claim["id"]
    assert client.get(f"{API}/claims", headers=ASSESSOR).json()["items"][0]["id"] == claim["id"]


def test_declaration_is_manager_only(client):
    claim = _draft(client, _incident(client).json()["id"]).json()
    response = client.patch(f"{API}/claims/{claim['id']}", json={"declaration_confirmed": True}, headers=OPERATOR)
    assert response.status_code == 403


def test_claim_missing_vet_assessment_is_evidence_incomplete_and_kept(client):
    incident = _incident(client, linked_alert_ids=[_alert()]).json()
    claim = _draft(client, incident["id"]).json()
    client.patch(f"{API}/claims/{claim['id']}", json={"declaration_confirmed": True}, headers=MANAGER)

    response = propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])

    assert response.status_code == 409 and error_code(response) == "EVIDENCE_INCOMPLETE"
    assert response.json()["error"]["details"]["missing"] == ["vet_assessment"]
    stored = client.get(f"{API}/claims/{claim['id']}", headers=MANAGER).json()
    assert stored["blocked_reason"]["missing"] == ["vet_assessment"]
    assert stored["status"] == "draft"
    with SessionLocal() as session:
        blocked = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "claim.blocked")).one()
    assert blocked.actor_type == "agent"


def test_complete_claim_submits_to_assessment_pending(client):
    claim = _ready_claim(client)
    assert claim["status"] == "ready" and claim["missing"] == [] and claim["blocked_reason"] is None

    action = approved(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert action["payload"]["declaration_confirmed"] is True
    assert action["payload"]["claimed_amount_minor"] == 60000
    assert {i["type"] for i in action["evidence_manifest"]["items"]} >= {
        "identity_reference", "policy", "incident", "professional_finding", "alert", "farmer_declaration"}
    executed = execute(client, action["id"], "claim-key").json()
    assert executed["status"] == "succeeded"
    assert executed["execution"]["provider_receipt"]["assessment_status"] == "assessment_pending"

    submitted = client.get(f"{API}/claims/{claim['id']}", headers=ASSESSOR).json()
    assert (submitted["status"], submitted["assessment_status"]) == ("assessment_pending", "assessment_pending")
    assert submitted["receipt"]["claim_ref"].startswith("SBX-CLM-")
    assert submitted["evidence_manifest_id"] == action["evidence_manifest"]["id"]
    passport = client.get(f"{API}/animals/{BIMA}/passport", headers=MANAGER).json()
    titles = [line["title"] for line in passport["passbook"]["lines"]]
    assert "Claim submitted · assessment pending" in titles
    assert error_code(propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])) == "INVALID_STATE"


def test_new_finding_after_approval_makes_claim_submission_stale(client):
    claim = _ready_claim(client)
    action = approved(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    _finding(client, claim["incident_id"], finding_type="vet_health_record")
    response = execute(client, action["id"], "claim-key")
    assert error_code(response) == "APPROVAL_STALE"
    with SessionLocal() as session:
        assert session.get(Claim, claim["id"]).status == "ready"


def test_claim_submission_decision_is_manager_only(client):
    claim = _ready_claim(client)
    action = propose_ok(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert decide(client, action, headers=OPERATOR).status_code == 403


def test_incident_in_the_future_is_rejected(client):
    future = clock.isoformat(clock.now() + timedelta(hours=1))
    response = _incident(client, occurred_at=future)
    assert response.status_code == 422 and error_code(response) == "VALIDATION_FAILED"


def test_incident_before_cover_cannot_be_claimed(client):
    incident = _incident(client, occurred_at="2019-01-01T00:00:00Z").json()
    assert incident["policy_id"] is None  # the active policy did not cover that date
    response = _draft(client, incident["id"])
    assert response.status_code == 409 and error_code(response) == "INVALID_STATE"


def test_cover_moved_after_approval_blocks_submission(client):
    claim = _ready_claim(client)
    action = approved(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    with SessionLocal() as session:
        policy = session.get(Policy, claim["policy_id"])
        policy.effective_date = clock.now().date() + timedelta(days=1)
        session.commit()

    assert error_code(execute(client, action["id"], "claim-key")) == "APPROVAL_STALE"
    response = propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert error_code(response) == "EVIDENCE_INCOMPLETE"
    assert response.json()["error"]["details"]["missing"] == ["active_policy"]


def test_a_finding_added_after_the_declaration_completes_the_checklist(client):
    incident = _incident(client, linked_alert_ids=[_alert()]).json()
    claim = _draft(client, incident["id"]).json()
    client.patch(f"{API}/claims/{claim['id']}", json={"declaration_confirmed": True}, headers=MANAGER)
    assert _finding(client, incident["id"]).status_code == 201
    fresh = client.get(f"{API}/claims/{claim['id']}", headers=MANAGER).json()
    status = {item["key"]: item["status"] for item in fresh["checklist"]}
    assert status["vet_assessment"] == "present" and status["farmer_declaration"] == "present"
    declaration = next(item for item in fresh["checklist"] if item["key"] == "farmer_declaration")
    assert declaration["detail"].startswith("Confirmed by ")
