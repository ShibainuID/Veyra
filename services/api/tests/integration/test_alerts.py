"""Alert listing and review (PRD verification: operator acknowledges, vet adds notes, transitions validated)."""

import pytest
from sqlalchemy import select

from persistence.db import read_session
from persistence.models import AuditEvent
from tests.support import ASSESSOR, MANAGER, OPERATOR, OTHER_FARM, VET

API = "/api/v1"


@pytest.fixture
def alert_id(client):
    assert client.post(f"{API}/demo/reset?scenario=post-enrollment", headers=MANAGER).status_code == 200
    assert client.post(f"{API}/demo/replays/anomaly/start", headers=OPERATOR).status_code == 202
    items = client.get(f"{API}/alerts", headers=OPERATOR, params={"kind": "reduced_movement"}).json()["items"]
    return items[0]["id"]


def _patch(client, alert_id, body, headers):
    return client.patch(f"{API}/alerts/{alert_id}", json=body, headers=headers)


def test_alert_list_is_farm_scoped_newest_first_and_filterable(client, alert_id):
    items = client.get(f"{API}/alerts", headers=ASSESSOR).json()["items"]
    assert [a["kind"] for a in items] == ["reduced_movement", "observation_quality"]
    seeded = items[1]
    assert (seeded["animal_name"], seeded["camera_name"]) == ("Gatot", "Pen B · water trough")
    assert "Gatot" in seeded["summary"] and "mean visibility 41%" in seeded["summary"]
    assert [a["id"] for a in client.get(f"{API}/alerts", headers=VET,
                                        params={"animal_id": "animal-demo-001"}).json()["items"]] == [alert_id]
    assert client.get(f"{API}/alerts", headers=VET, params={"status": "resolved"}).json()["items"] == []
    assert client.get(f"{API}/alerts", headers=VET, params={"kind": "bogus"}).status_code == 422
    assert client.get(f"{API}/alerts", headers=OTHER_FARM).json()["items"] == []
    assert client.get(f"{API}/alerts/{alert_id}", headers=VET).json()["id"] == alert_id


def test_other_farm_cannot_see_or_review_the_alert(client, alert_id):
    assert client.get(f"{API}/alerts/{alert_id}", headers=OTHER_FARM).status_code == 404
    assert _patch(client, alert_id, {"status": "acknowledged"}, OTHER_FARM).status_code == 404


def test_operator_acknowledges_vet_adds_assessment_and_resolution_needs_a_note(client, alert_id):
    assert _patch(client, alert_id, {"status": "acknowledged"}, ASSESSOR).status_code == 403
    assert _patch(client, alert_id, {"status": "resolved", "note": "early"}, OPERATOR).json()["error"]["code"] == \
        "INVALID_STATE"

    acked = _patch(client, alert_id, {"status": "acknowledged"}, OPERATOR)
    assert acked.status_code == 200 and acked.json()["status"] == "acknowledged"
    again = _patch(client, alert_id, {"status": "acknowledged"}, MANAGER)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "INVALID_STATE")

    noted = _patch(client, alert_id, {"note": "Mild left hind lameness on inspection."}, VET).json()
    note = noted["notes"][0]
    assert (note["kind"], note["role"], note["author"], note["text"]) == (
        "assessment", "vet", "user-vet", "Mild left hind lameness on inspection.")
    assert noted["status"] == "acknowledged"
    assert _patch(client, alert_id, {"status": "resolved", "note": "vet cannot"}, VET).status_code == 403

    no_note = _patch(client, alert_id, {"status": "resolved"}, OPERATOR)
    assert (no_note.status_code, no_note.json()["error"]["code"]) == (422, "VALIDATION_FAILED")
    assert _patch(client, alert_id, {}, OPERATOR).status_code == 422

    resolved = _patch(client, alert_id, {"status": "resolved", "note": "Inspected and rested."}, OPERATOR).json()
    assert resolved["status"] == "resolved"
    assert [(n["kind"], n["role"]) for n in resolved["notes"]] == [("assessment", "vet"), ("review", "operator")]
    assert _patch(client, alert_id, {"status": "acknowledged"}, MANAGER).json()["error"]["code"] == "INVALID_STATE"

    with read_session() as session:
        events = session.scalars(select(AuditEvent).where(AuditEvent.subject_id == alert_id)
                                 .order_by(AuditEvent.created_at)).all()
    assert [(e.event_type, e.actor_id) for e in events] == [
        ("alert.created", "replay"), ("alert.acknowledged", "user-operator"), ("alert.note_added", "user-vet"),
        ("alert.resolved", "user-operator")]
    assert all(e.animal_id == "animal-demo-001" for e in events)

    lines = client.get(f"{API}/animals/animal-demo-001/passport", headers=VET).json()["passbook"]
    lines = lines["lines"] if isinstance(lines, dict) else lines
    by_title = {line["title"]: line for line in lines}
    assert by_title["Assessment note"]["detail"] == "Mild left hind lameness on inspection."
    assert by_title["Alert resolved"]["stamp"]["kind"] == "confirmed"
    assert by_title["Alert acknowledged"]["stamp"]["by"] == "A. Pratama"
    assert by_title["Alert · reduced movement"]["detail"].endswith("this is not a diagnosis.")


def test_vet_may_acknowledge_with_an_assessment(client, alert_id):
    body = _patch(client, alert_id, {"status": "acknowledged", "note": "Will examine at 10:00."}, VET).json()
    assert body["status"] == "acknowledged" and body["notes"][0]["kind"] == "assessment"
