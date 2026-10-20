"""Phase 3 CCTV: scan-zone handoff, observations, reduced-movement alerts, evidence packs, review, demo replays."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from domain import replays
from domain.evidence import canonical_sha256
from main import create_app
from persistence.models import Animal

API = "/api/v1"
START = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
ZONE = [[0.02, 0.70], [0.22, 0.70], [0.22, 0.98], [0.02, 0.98]]


def scenario(**overrides) -> dict:
    """A short replay fixture: 90 minutes, two animals, optional reduced movement from minute 60 for the first."""
    params = {"label": "test", "duration_s": 5400, "tracks": 2, "seed": 3, **overrides}
    return {"camera": {"name": "Test camera", "location": None}, "scan_zone": {"name": "Scan", "polygon": ZONE},
            "scenarios": {"test": params}}


ANOMALY = {"anomaly": {"track": 0, "from_s": 3600, "activity_factor": 0.05, "speed_factor": 0.5}}


def make_animal(client, headers, worker, cow: str) -> str:
    e = client.post(f"{API}/enrollments", json={"sample_key": "sample-enrollment-001"}, headers=headers).json()
    client.post(f"{API}/enrollments/{e['id']}/video", headers=headers, files={"file": ("cow.mp4", f"COW:{cow}".encode())})
    client.post(f"{API}/enrollments/{e['id']}/process", headers=headers)
    worker()
    r = client.post(f"{API}/enrollments/{e['id']}/confirm", json={"decision": "new_animal"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["animal_id"]


@pytest.fixture
def farm(client, make_user, worker):
    """Manager, operator, veterinarian, camera worker; one confirmed animal; a camera with a scan zone."""
    manager, mgr = make_user("manager")
    _, op = make_user("operator", farm_id=manager.farm_id)
    _, vet = make_user("veterinarian", farm_id=manager.farm_id)
    _, svc = make_user("service", farm_id=manager.farm_id)
    animal = make_animal(client, op, worker, "bella")
    camera = client.post(f"{API}/cameras", json={"name": "Barn A"}, headers=mgr).json()
    zone = client.post(f"{API}/cameras/{camera['id']}/zones", json={"name": "Scan crate", "polygon": ZONE}, headers=mgr)
    assert zone.status_code == 201, zone.text
    return {"farm_id": manager.farm_id, "mgr": mgr, "op": op, "vet": vet, "svc": svc, "animal": animal,
            "camera": camera["id"], "zone": zone.json()["id"]}


def scan(client, f, animal: str, at: datetime):
    return client.post(f"{API}/cameras/{f['camera']}/scans",
                       json={"zone_id": f["zone"], "animal_id": animal, "scanned_at": at.isoformat()}, headers=f["op"])


def post_tracks(client, f, worker, tracks: dict) -> dict:
    r = client.post(f"{API}/cameras/{f['camera']}/observations", json={"started_at": START.isoformat(), "tracks": tracks},
                    headers=f["svc"])
    assert r.status_code == 202, r.text
    worker()
    return client.get(f"{API}/cameras/{f['camera']}/recordings/{r.json()['recording_id']}", headers=f["op"]).json()


def replay(f, client, worker, **overrides):
    r = replays.generate("test", scenario(**overrides))
    assert scan(client, f, f["animal"], START + timedelta(seconds=r.scans[0][1])).status_code == 201
    return post_tracks(client, f, worker, r.tracks)


def test_scan_handoff_links_track_and_updates_passport(client, farm, worker):
    rec = replay(farm, client, worker)
    assert rec["status"] == "processed" and rec["source"] == "simulated"
    assert [(link["status"], link["track_id"]) for link in rec["links"]] == [("confirmed", "1")]
    assert rec["summary"]["decisions"][0]["decision"] == "within_baseline"

    obs = client.get(f"{API}/animals/{farm['animal']}/observations", headers=farm["op"]).json()
    assert len(obs["observations"]) > 60 and {o["track_id"] for o in obs["observations"]} == {"1"}
    assert obs["health"]["status"] == "normal"
    passport = client.get(f"{API}/animals/{farm['animal']}/passport", headers=farm["op"]).json()
    assert passport["last_observed"]["track_id"] == "1"
    assert passport["health"]["status"] == "normal" and passport["open_alerts"] == []
    assert client.get(f"{API}/alerts", headers=farm["op"]).json() == []
    actions = {h["action"] for h in passport["history"]}
    assert {"camera.zone_scan_recorded", "camera.identity_confirmed"} <= actions


def test_reduced_movement_raises_alert_with_evidence_pack(client, farm, worker):
    rec = replay(farm, client, worker, **ANOMALY)
    decision = rec["summary"]["decisions"][0]
    assert decision["decision"] == "reduced_movement_alert" and decision["ratio"] < 0.5

    alerts = client.get(f"{API}/alerts", headers=farm["op"]).json()
    assert [(a["kind"], a["status"], a["display_id"]) for a in alerts] == [("reduced_movement", "open", "animal-001")]
    alert = client.get(f"{API}/alerts/{alerts[0]['id']}", headers=farm["op"]).json()
    pack = alert["evidence"]
    assert pack["version"] == 1 and pack["manifest_sha256"] == canonical_sha256(pack["manifest"])
    m = pack["manifest"]
    assert "not a diagnosis" in m["statement"] and m["source"] == "simulated"
    assert m["identity_links"][0]["method"] == "scan_zone_handoff"
    assert m["identity_links"][0]["scan"]["scanned_at"]
    assert len(m["observations"]) >= 15 and m["rule"]["ratio"] < m["rule"]["ratio_threshold"]
    assert [x["role"] for x in m["media"]] == ["tracks"]
    assert m["completeness"] == {"identity_confirmed": True, "clip_attached": False, "veterinary_assessment": False}

    health = client.get(f"{API}/animals/{farm['animal']}/passport", headers=farm["op"]).json()["health"]
    assert health["status"] == "needs_inspection" and health["open_alert_ids"] == [alert["id"]]
    listed = client.get(f"{API}/animals", params={"has_open_alert": True}, headers=farm["op"]).json()
    assert [a["id"] for a in listed] == [farm["animal"]]


def test_alert_review_keeps_findings_apart_and_versions_evidence(client, farm, worker):
    replay(farm, client, worker, **ANOMALY)
    alert_id = client.get(f"{API}/alerts", headers=farm["op"]).json()[0]["id"]
    url = f"{API}/alerts/{alert_id}"

    r = client.patch(url, json={"status": "acknowledged", "notes": "Checked pen, calling vet."}, headers=farm["op"])
    assert r.status_code == 200 and r.json()["evidence"]["version"] == 2
    health = client.get(f"{API}/animals/{farm['animal']}/passport", headers=farm["op"]).json()["health"]
    assert health["status"] == "under_review"

    finding = {"finding": "condition_observed", "details": "Mild lameness, left hind."}
    r = client.patch(url, json={"assessment": finding}, headers=farm["op"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    r = client.patch(url, json={"status": "resolved", "assessment": finding}, headers=farm["vet"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "resolved" and body["assessment"]["finding"] == "condition_observed"
    m = body["evidence"]["manifest"]
    assert m["version"] == 3 and m["veterinary_assessment"]["details"] == finding["details"]
    assert m["review"]["notes"] == "Checked pen, calling vet."
    assert client.patch(url, json={"notes": "again"}, headers=farm["op"]).status_code == 409

    versions = client.get(f"{url}/evidence", headers=farm["op"]).json()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert len({v["manifest_sha256"] for v in versions}) == 3
    health = client.get(f"{API}/animals/{farm['animal']}/passport", headers=farm["op"]).json()["health"]
    assert health["status"] == "veterinary_reviewed" and health["last_assessment"]["finding"] == "condition_observed"


def test_uncertain_handoff_never_attaches_identity(client, farm, worker):
    rec = replay(farm, client, worker, duration_s=900, crowded_scan=True)
    assert [(link["status"], link["reason"], link["track_id"]) for link in rec["links"]] == [
        ("uncertain", "multiple_tracks_in_zone", None)]
    assert set(rec["links"][0]["candidates"]) == {"1", replays.INTRUDER_ID}
    obs = client.get(f"{API}/animals/{farm['animal']}/observations", headers=farm["op"]).json()
    assert obs["observations"] == [] and obs["health"]["status"] == "not_monitored"
    passport = client.get(f"{API}/animals/{farm['animal']}/passport", headers=farm["op"]).json()
    assert passport["last_observed"] is None


def test_one_track_cannot_carry_two_animals(client, farm, worker):
    second = make_animal(client, farm["op"], worker, "daisy")
    r = replays.generate("test", scenario(duration_s=900))
    at = START + timedelta(seconds=r.scans[0][1])
    assert scan(client, farm, farm["animal"], at).status_code == 201
    assert scan(client, farm, second, at + timedelta(seconds=1)).status_code == 201
    rec = post_tracks(client, farm, worker, r.tracks)
    assert [(link["status"], link["reason"]) for link in rec["links"]] == [("confirmed", None),
                                                                           ("uncertain", "track_already_linked")]


def test_recording_upload_runs_tracker_and_attaches_clip(client, farm, worker):
    r = replays.generate("test", scenario(**ANOMALY))
    scan(client, farm, farm["animal"], START + timedelta(seconds=r.scans[0][1]))
    up = client.post(f"{API}/cameras/{farm['camera']}/recordings", headers=farm["op"],
                     data={"started_at": START.isoformat()},
                     files={"file": ("barn.mp4", json.dumps(r.tracks).encode(), "video/mp4")})
    assert up.status_code == 202, up.text
    worker()
    rec = client.get(f"{API}/cameras/{farm['camera']}/recordings/{up.json()['recording_id']}", headers=farm["op"]).json()
    assert rec["status"] == "processed" and rec["tracks_media_id"] and rec["video_media_id"]
    alert = client.get(f"{API}/alerts", headers=farm["op"]).json()[0]
    assert len(alert["evidence_media_ids"]) == 1
    m = client.get(f"{API}/alerts/{alert['id']}", headers=farm["op"]).json()["evidence"]["manifest"]
    assert [x["role"] for x in m["media"]] == ["clip", "recording_video", "tracks"]
    assert m["completeness"]["clip_attached"] is True


def test_scan_needs_a_confirmed_animal(client, farm, db):
    with db.sessions() as s:
        pending = Animal(farm_id=farm["farm_id"], display_id="animal-099", identity_status="pending_review")
        s.add(pending)
        s.commit()
        pending_id = str(pending.id)
    r = scan(client, farm, pending_id, START)
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDENTITY_UNCONFIRMED"


def test_worker_observations_are_service_only_and_validated(client, farm):
    url = f"{API}/cameras/{farm['camera']}/observations"
    body = {"started_at": START.isoformat(), "tracks": {"width": 800, "height": 600, "frames": []}}
    assert client.post(url, json=body, headers=farm["mgr"]).status_code == 403
    bad = {"started_at": START.isoformat(), "tracks": {"frames": [[1, []]]}}
    r = client.post(url, json=bad, headers=farm["svc"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_alerts_and_cameras_are_farm_scoped(client, farm, worker, make_user):
    replay(farm, client, worker, **ANOMALY)
    alert_id = client.get(f"{API}/alerts", headers=farm["op"]).json()[0]["id"]
    _, other = make_user("manager")
    assert client.get(f"{API}/alerts", headers=other).json() == []
    assert client.get(f"{API}/alerts/{alert_id}", headers=other).status_code == 404
    assert client.patch(f"{API}/alerts/{alert_id}", json={"status": "acknowledged"}, headers=other).status_code == 404
    assert client.get(f"{API}/cameras/{farm['camera']}/zones", headers=other).status_code == 404


def test_demo_replay_is_hidden_unless_demo_mode(client, farm):
    r = client.post(f"{API}/demo/replays/anomaly/start", json={}, headers=farm["mgr"])
    assert r.status_code == 404


def test_demo_anomaly_replay_end_to_end(settings, db, farm, worker):
    demo = TestClient(create_app(replace(settings, demo_mode=True), db))
    assert demo.post(f"{API}/demo/replays/nope/start", json={}, headers=farm["mgr"]).status_code == 404
    r = demo.post(f"{API}/demo/replays/anomaly/start", json={}, headers=farm["mgr"])
    assert r.status_code == 202, r.text
    assert r.json()["source"] == "simulated" and r.json()["animal_ids"] == [farm["animal"]]
    worker()
    alerts = demo.get(f"{API}/alerts", headers=farm["op"]).json()
    assert [(a["kind"], a["source"], a["animal_id"]) for a in alerts] == [("reduced_movement", "simulated", farm["animal"])]
