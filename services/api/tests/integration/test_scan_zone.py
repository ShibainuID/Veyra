"""Scan-zone handoff through the replays and the observation feed, the Veo footage scenario, and the footage route."""

import pytest
from sqlalchemy import select

from config import get_settings
from persistence.db import read_session
from persistence.models import AuditEvent, Observation
from routes import demo as demo_routes
from tests.support import MANAGER, OPERATOR, OTHER_FARM, VET

API = "/api/v1"
SERVICE = {"X-Service-Token": "demo-worker-token"}
ZONE = [[0.4781, 0.6611], [0.7021, 0.6611], [0.7021, 0.8463], [0.4781, 0.8463]]


@pytest.fixture
def farm(client):
    assert client.post(f"{API}/demo/reset?scenario=post-enrollment", headers=MANAGER).status_code == 200
    return client


def _run(client, scenario: str) -> dict:
    started = client.post(f"{API}/demo/replays/{scenario}/start", headers=OPERATOR)
    assert started.status_code == 200, started.text
    replay = client.get(f"{API}/replays/{started.json()['replay_id']}", headers=VET).json()
    assert replay["status"] == "finished"
    return replay


def test_cameras_and_scenarios_expose_the_calibrated_scan_zone(farm):
    cameras = {c["id"]: c for c in farm.get(f"{API}/cameras", headers=VET).json()["items"]}
    zone = cameras["cam-pen-a"]["scan_zone"]
    assert (zone["polygon"], zone["label"], zone["source"]) == (ZONE, "Gate scan zone", "prototype")
    assert cameras["cam-pen-b"]["scan_zone"] is None and cameras["cam-pen-c"]["scan_zone"] is None
    scenarios = {s["id"]: s for s in farm.get(f"{API}/demo/replays", headers=VET).json()["scenarios"]}
    assert scenarios["healthy"]["scan_zone"]["polygon"] == ZONE
    assert scenarios["lost_identity"]["scan_zone"] is None
    assert scenarios["crowded_scan"]["events"] == [
        {"t": 3.0, "type": "zone_scan", "animal_id": "animal-demo-001", "inliers": 31, "quality": 0.88,
         "muzzle_image": None}]


def test_healthy_replay_identifies_sari_through_the_scan_zone(farm):
    replay = _run(farm, "healthy")
    assert replay["scan_zone"]["polygon"] == ZONE
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    sari = tracks["t-01"]
    assert (sari["animal_id"], sari["association_status"], sari["association_method"]) == (
        "animal-demo-001", "associated", "zone_handoff")
    evidence = sari["association_evidence"]
    assert (evidence["tracks_in_zone"], evidence["inliers"], evidence["quality"]) == (1, 31, 0.88)
    assert (tracks["t-02"]["association_method"], tracks["t-02"]["animal_id"]) == ("muzzle_match", "animal-demo-002")
    passport = farm.get(f"{API}/animals/animal-demo-001/passport", headers=VET).json()
    lines = passport["passbook"]["lines"] if isinstance(passport["passbook"], dict) else passport["passbook"]
    identified = [line for line in lines if line["title"] == "Identified on camera Pen A · feed line"]
    assert identified and identified[0]["detail"].startswith("Scanned alone in the scan zone · muzzle scan 31")


def test_crowded_scan_identifies_nobody_and_raises_no_animal_alert(farm):
    before = {a["id"] for a in farm.get(f"{API}/alerts", headers=VET).json()["items"]}
    replay = _run(farm, "crowded_scan")
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    assert set(tracks) == {"t-21", "t-22"}
    for track in tracks.values():
        assert (track["association_status"], track["animal_id"]) == ("uncertain", None)
        evidence = track["association_evidence"]
        assert (evidence["tracks_in_zone"], evidence["reason"]) == (2, "multiple_tracks_in_zone")
        assert evidence["message"] == "2 animals in the scan zone — scan one animal at a time."
    assert replay["alerts"] == []
    after = farm.get(f"{API}/alerts", headers=VET).json()["items"]
    assert [a for a in after if a["id"] not in before and a["animal_id"] is not None] == []
    with read_session() as session:
        attributed = session.scalars(select(Observation).where(
            Observation.track_id.in_([t["id"] for t in tracks.values()]), Observation.animal_id.is_not(None))).all()
        scan = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "camera.zone_scan"))
    assert attributed == []
    assert (scan.data["outcome"], scan.data["tracks_in_zone"], scan.animal_id) == ("crowded", 2, None)
    assert farm.get(f"{API}/animals/animal-demo-001/observations", headers=VET).json()["last_observation"] is None


def test_veo_barn_replays_the_real_tracker_run_without_inventing_identity(farm):
    scenarios = {s["id"]: s for s in farm.get(f"{API}/demo/replays", headers=VET).json()["scenarios"]}
    veo = scenarios["veo_barn"]
    assert (veo["source"], veo["clip"], veo["camera_id"], veo["duration_s"]) == (
        "prototype", "/api/v1/demo/footage/video_cctv.mp4", "cam-pen-a", 8)
    assert veo["footage"]["label"] == "Pen A camera footage"
    assert veo["events"][0]["muzzle_image"] == "demo/media/veo/references/09_hp_muzzle.png"
    assert veo["footage"]["kind"] == "ai_generated" and veo["footage"]["tracker"] == "yolov8x+botsort_reid"
    assert len(veo["tracks"]) == 13 and veo["tracks"][10]["track_key"] == "veo-11"
    first = veo["tracks"][0]["frames"][0]
    assert first["t"] == 0.0 and all(0 <= v <= 1 for v in first["bbox"])

    replay = _run(farm, "veo_barn")
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    assert len(tracks) == 13
    assert all(t["animal_id"] is None and t["association_status"] == "unassigned" for t in tracks.values())
    heifer = tracks["veo-11"]["association_evidence"]
    assert (heifer["event"], heifer["tracks_in_zone"], heifer["reason"]) == (
        "zone_scan", 1, "candidate_not_registered")
    with read_session() as session:
        rows = session.scalars(select(Observation).where(
            Observation.track_id.in_([t["id"] for t in tracks.values()]))).all()
    assert len(rows) == sum(len(t["frames"]) for t in veo["tracks"])
    assert all(row.animal_id is None for row in rows)
    assert replay["alerts"] == []


def test_the_observation_feed_takes_zone_scans(farm):
    url = f"{API}/cameras/cam-pen-a/observations"
    frame = {"track_key": "gate-1", "observed_at": "2026-10-20T09:00:00Z", "bbox": [0.52, 0.68, 0.12, 0.1],
             "visibility": 0.9}
    assert farm.post(url, json=frame, headers=SERVICE).status_code == 201
    scan = {"event": "zone_scan", "observed_at": "2026-10-20T09:00:00.400Z", "candidate_animal_id": "animal-demo-006",
            "inliers": 24, "quality": 0.8}
    body = farm.post(url, json=scan, headers=SERVICE).json()
    assert body["handoff"]["outcome"] == "associated" and body["handoff"]["track_keys"] == ["gate-1"]
    assert (body["track"]["animal_id"], body["track"]["association_method"]) == ("animal-demo-006", "zone_handoff")
    assert body["observation"]["event"] == "zone_scan"

    empty = farm.post(url, json={**scan, "observed_at": "2026-10-20T09:00:05Z"}, headers=SERVICE).json()
    assert (empty["handoff"]["outcome"], empty["observation"], empty["track"]) == ("no_track", None, None)
    assert farm.post(url, json={"event": "frame", "observed_at": "2026-10-20T09:00:06Z"},
                     headers=SERVICE).status_code == 422
    no_zone = farm.post(f"{API}/cameras/cam-pen-b/observations", json=scan, headers=SERVICE)
    assert no_zone.status_code == 422
    assert farm.post(url, json=scan).status_code == 401


# --- footage -----------------------------------------------------------------------------------------------------


def test_footage_route_streams_allow_listed_clips_with_range(farm):
    path = demo_routes.footage_dir() / "video_cctv.mp4"
    whole = farm.get(f"{API}/demo/footage/video_cctv.mp4")  # no sign-in: a <video> element cannot send one
    assert whole.status_code == 200
    assert whole.headers["content-type"] == "video/mp4"
    assert int(whole.headers["content-length"]) == path.stat().st_size > 1_000_000
    assert whole.headers["accept-ranges"] == "bytes"
    assert "AI-generated" in whole.headers["x-veyra-provenance"]
    part = farm.get(f"{API}/demo/footage/video_cctv.mp4", headers={"Range": "bytes=0-1023"})
    assert part.status_code == 206 and len(part.content) == 1024
    assert part.headers["content-range"] == f"bytes 0-1023/{path.stat().st_size}"
    assert part.content == path.read_bytes()[:1024]
    for name in ("video_hp.mp4", "video_cctv_tracked.mp4"):
        assert farm.get(f"{API}/demo/footage/{name}", headers={"Range": "bytes=0-15"}).status_code == 206


@pytest.mark.parametrize("name", ["nope.mp4", "VEO_PROMPTS.md", "..%2Fout%2Ftracks.json", "run_report.json",
                                  "references"])
def test_footage_route_refuses_unknown_names(farm, name):
    response = farm.get(f"{API}/demo/footage/{name}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_footage_route_is_hidden_outside_demo_mode(client, monkeypatch):
    monkeypatch.setenv("VEYRA_DEMO_MODE", "0")
    get_settings.cache_clear()
    assert client.get(f"{API}/demo/footage/video_cctv.mp4").status_code == 404


def test_footage_route_reports_an_unpulled_lfs_pointer(farm, monkeypatch, tmp_path):
    (tmp_path / "video_cctv.mp4").write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\n")
    monkeypatch.setattr(demo_routes, "footage_dir", lambda: tmp_path)
    response = farm.get(f"{API}/demo/footage/video_cctv.mp4")
    assert response.status_code == 404 and "git lfs pull" in response.json()["error"]["message"]


def test_other_farms_see_no_scan_zone_of_ours(farm):
    assert farm.get(f"{API}/cameras", headers=OTHER_FARM).json()["items"] == []


def test_veo_barn_scan_is_decided_by_the_real_matcher(farm, monkeypatch):
    """With Sari's muzzle in the gallery and the matcher verifying her, the scanned heifer's track becomes Sari."""
    import adapters.muzzle
    from adapters import perception
    from tests.integration.test_identity_checks import _attach_reference

    calls = []

    class FakeIdentifier:
        def __init__(self, model_path):
            pass

        def reference(self, image_id, crop_bgr):
            return f"ref:{image_id}"

        def check_duplicate(self, crop_bgr, gallery):
            calls.append(sorted(gallery.animals))
            return {"source": "prototype", "method_version": "muzzle_hybrid_v1", "outcome": "candidate",
                    "reason": None, "animal_id": "animal-demo-001", "possible_duplicate": True,
                    "candidates": [{"animal_id": "animal-demo-001", "inliers": 312, "cosine": 0.93}]}

    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "auto")
    monkeypatch.setattr(perception, "probe_capabilities",
                        lambda: {"video": False, "muzzle": True, "weight": False, "age": True})
    monkeypatch.setattr(adapters.muzzle, "MuzzleIdentifier", FakeIdentifier)
    get_settings.cache_clear()
    perception.clear_caches()
    try:
        _attach_reference("animal-demo-001")
        replay = _run(farm, "veo_barn")
    finally:
        perception.clear_caches()
    assert calls == [["animal-demo-001"]]
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    assert tracks["veo-11"]["animal_id"] == "animal-demo-001"
    evidence = tracks["veo-11"]["association_evidence"]
    assert (evidence["event"], evidence["inliers"], evidence["quality"]) == ("zone_scan", 312, 0.93)
    assert all(t["animal_id"] is None for key, t in tracks.items() if key != "veo-11")
