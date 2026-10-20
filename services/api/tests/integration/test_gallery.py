"""Camera muzzle gallery sync: the cloud tells each pen camera which enrolled animals it should recognise."""

from sqlalchemy import select

from persistence.db import read_session
from persistence.models import AuditEvent
from tests.integration.test_enrollment_flow import SARI, _confirm, _reviewed
from tests.support import MANAGER, OPERATOR, OTHER_FARM, VET

API = "/api/v1"
SERVICE = {"X-Service-Token": "demo-worker-token"}


def _gallery(client, camera_id="cam-pen-a", headers=SERVICE):
    return client.get(f"{API}/cameras/{camera_id}/gallery", headers=headers)


def _ack(client, version, camera_id="cam-pen-a", headers=SERVICE):
    return client.post(f"{API}/cameras/{camera_id}/gallery/ack", json={"version": version}, headers=headers)


def _status(client, camera_id="cam-pen-a", headers=MANAGER) -> dict:
    cameras = client.get(f"{API}/cameras", headers=headers).json()["items"]
    return next(c for c in cameras if c["id"] == camera_id)["gallery"]


def test_gallery_lists_the_confirmed_herd(client):
    response = _gallery(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["camera_id"] == "cam-pen-a" and body["farm_id"] == "farm-wahyu"
    names = [a["name"] for a in body["animals"]]
    assert names == ["Bima", "Melati", "Gatot", "Dewi", "Rama"]
    assert all(len(a["references"]) == 1 and a["references"][0]["view"] == "muzzle" for a in body["animals"])
    assert body["animals"][0]["references"][0]["media_url"] is None  # seeded: footage not attached
    assert body["source"] == "simulated"
    assert body["version"] == 10  # five animals + five muzzle references
    assert _gallery(client, headers=MANAGER).json()["version"] == 10


def test_gallery_needs_the_service_token_or_a_manager(client):
    assert _gallery(client, headers={}).status_code == 401
    assert _gallery(client, headers={"X-Service-Token": "wrong"}).status_code == 401
    assert _gallery(client, headers=OPERATOR).status_code == 403
    assert _gallery(client, headers=VET).status_code == 403
    assert _gallery(client, headers=OTHER_FARM).status_code == 404  # another farm's camera
    assert _gallery(client, camera_id="cam-missing").status_code == 404
    assert _ack(client, 10, headers={}).status_code == 401
    assert _ack(client, 10, headers=MANAGER).status_code == 401  # the ack is the camera worker's alone


def test_ack_brings_the_camera_in_sync(client):
    before = _status(client)
    assert before == {"current_version": 10, "synced_version": None, "synced_at": None, "in_sync": False,
                      "source": None}

    response = _ack(client, 10)

    assert response.status_code == 200, response.text
    assert response.json()["gallery"]["in_sync"] is True
    after = _status(client)
    assert after["synced_version"] == 10 and after["in_sync"] is True and after["synced_at"].endswith("Z")
    assert _status(client, "cam-pen-b")["in_sync"] is False
    with read_session() as session:
        event = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "camera.gallery_synced")).one()
    assert (event.actor_type, event.actor_id, event.subject_id, event.data["version"]) == (
        "system", "camera-worker", "cam-pen-a", 10)
    assert _ack(client, 11).status_code == 422  # a version that does not exist yet


def test_version_changes_after_an_enrollment_is_confirmed(client, tmp_path):
    from tests.video_support import write_enrollment_video

    _ack(client, 10)
    video = write_enrollment_video(tmp_path / "enroll.mp4").read_bytes()
    detail = _reviewed(client, video, "sample-enrollment-001")
    assert _confirm(client, detail["id"], SARI).status_code == 200

    gallery = _gallery(client).json()
    assert gallery["version"] == 12
    sari = next(a for a in gallery["animals"] if a["name"] == "Sari")
    assert sari["identity_status"] == "confirmed" and sari["references"][0]["media_url"]
    stale = _status(client)
    assert (stale["current_version"], stale["synced_version"], stale["in_sync"]) == (12, 10, False)
    assert _ack(client, 12).json()["gallery"]["in_sync"] is True


def test_publish_simulates_the_camera_acks(client):
    assert client.post(f"{API}/cameras/gallery/publish", headers=OPERATOR).status_code == 403
    response = client.post(f"{API}/cameras/gallery/publish", headers=MANAGER)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 10 and body["source"] == "simulated"
    assert body["acknowledged"] == ["cam-pen-a", "cam-pen-b", "cam-pen-c"]
    assert all(status["in_sync"] and status["source"] == "simulated" for status in body["cameras"].values())
    assert _status(client, "cam-pen-c")["in_sync"] is True
    # Another farm's cameras are untouched and its manager sees only its own.
    other = client.get(f"{API}/cameras", headers=OTHER_FARM).json()["items"]
    assert all(c["gallery"]["synced_version"] is None for c in other)
    with read_session() as session:
        types = session.scalars(select(AuditEvent.event_type).where(AuditEvent.event_type.like("camera.%"))).all()
    assert types.count("camera.gallery_published") == 1 and types.count("camera.gallery_synced") == 3
