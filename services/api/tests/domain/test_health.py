"""Health status per animal: a deterministic monitoring state from records, one test per status."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from domain.health import classify

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
RECENT = NOW - timedelta(hours=2)
STALE = NOW - timedelta(hours=30)


def alert(kind="reduced_movement", status="open", notes=(), hours_ago=3):
    at = NOW - timedelta(hours=hours_ago)
    return SimpleNamespace(kind=kind, status=status, notes=list(notes), window_start=at, updated_at=at)


VET_NOTE = {"kind": "assessment", "role": "vet", "text": "Sound on all four legs."}
REVIEW_NOTE = {"kind": "review", "role": "operator", "text": "Back to normal grazing."}


def test_open_reduced_movement_needs_inspection():
    first = alert(hours_ago=5)
    result = classify([alert(hours_ago=1), first], RECENT, NOW)
    assert result["status"] == "needs_inspection" and result["since"] == first.window_start
    assert "diagnos" not in result["reason"].lower()


def test_acknowledged_alert_is_under_review():
    result = classify([alert(status="acknowledged")], RECENT, NOW)
    assert result["status"] == "under_review"


def test_open_observation_quality_alert_is_an_observation_gap():
    assert classify([alert(kind="observation_quality")], RECENT, NOW)["status"] == "observation_gap"


def test_stale_last_observation_is_an_observation_gap():
    result = classify([], STALE, NOW)
    assert result["status"] == "observation_gap" and result["since"] == STALE


def test_latest_alert_resolved_with_vet_assessment_is_vet_reviewed():
    resolved = alert(status="resolved", notes=[VET_NOTE, REVIEW_NOTE])
    assert classify([resolved], RECENT, NOW)["status"] == "veterinary_reviewed"
    without_vet = alert(status="resolved", notes=[REVIEW_NOTE])
    assert classify([without_vet], RECENT, NOW)["status"] == "normal"


def test_recent_observation_without_open_alerts_is_normal():
    result = classify([], RECENT, NOW)
    assert result["status"] == "normal" and result["since"] == RECENT


def test_no_associated_observation_is_not_monitored():
    result = classify([], None, NOW)
    assert result == {"status": "not_monitored", "reason": result["reason"], "since": None}


def test_herd_list_and_passport_carry_health(client):
    from tests.support import MANAGER

    items = client.get("/api/v1/animals", headers=MANAGER).json()["items"]
    assert items and all(item["health"]["status"] for item in items)
    passport = client.get(f"/api/v1/animals/{items[0]['id']}/passport", headers=MANAGER).json()
    assert passport["animal"]["health"] == items[0]["health"]


def test_health_status_reads_records_like_the_herd_list(client):
    from domain.health import health_status
    from persistence.db import read_session
    from persistence.models import Animal
    from tests.support import MANAGER

    items = client.get("/api/v1/animals", headers=MANAGER).json()["items"]
    with read_session() as session:
        for item in items:
            result = health_status(session, session.get(Animal, item["id"]))
            assert result["status"] == item["health"]["status"]
