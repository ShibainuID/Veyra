"""Camera replay, monitoring endpoints, and the PRD's identity and movement verification (replay speed 0)."""

import time
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from config import get_settings
from domain import clock
from persistence.db import read_session
from persistence.models import Alert, AuditEvent, Observation, Replay
from tests.support import ASSESSOR, MANAGER, OPERATOR, OTHER_FARM, VET
from workers import replay as replays

API = "/api/v1"
SERVICE = {"X-Service-Token": "demo-worker-token"}


@pytest.fixture
def farm(client):
    assert client.post(f"{API}/demo/reset?scenario=post-enrollment", headers=MANAGER).status_code == 200
    return client


def _start(client, scenario: str, headers=OPERATOR) -> dict:
    """Speed 0 runs inside the request and answers 200 `finished`; a threaded replay answers 202 `running`."""
    response = client.post(f"{API}/demo/replays/{scenario}/start", headers=headers)
    assert response.status_code in (200, 202), response.text
    body = response.json()
    assert (response.status_code, body["status"]) in ((200, "finished"), (202, "running"))
    return body


def _alerts(client, **params) -> list[dict]:
    response = client.get(f"{API}/alerts", headers=OPERATOR, params=params)
    assert response.status_code == 200
    return response.json()["items"]


def _replay_alerts(client, replay_id: str) -> list[dict]:
    return client.get(f"{API}/replays/{replay_id}", headers=VET).json()["alerts"]


def test_scenarios_list_carries_track_data_and_cameras(farm):
    body = farm.get(f"{API}/demo/replays", headers=ASSESSOR).json()
    assert [s["id"] for s in body["scenarios"]] == ["anomaly", "crowded_scan", "healthy", "lost_identity", "veo_barn"]
    anomaly = body["scenarios"][0]
    assert (anomaly["camera_name"], anomaly["source"], len(anomaly["tracks"][0]["frames"])) == (
        "Pen A · feed line", "simulated", 360)
    assert anomaly["events"][0]["type"] == "zone_scan"  # Sari: identified in the scan zone
    assert anomaly["tracks"][1]["events"][0]["type"] == "muzzle_match"  # Bima: by a muzzle match on her track
    assert {c["id"] for c in body["cameras"]} == {"cam-pen-a", "cam-pen-b", "cam-pen-c"}
    assert farm.get(f"{API}/demo/replays").status_code == 401


def test_only_managers_and_operators_start_replays(farm):
    assert farm.post(f"{API}/demo/replays/healthy/start", headers=VET).status_code == 403
    assert farm.post(f"{API}/demo/replays/nope/start", headers=OPERATOR).status_code == 404
    assert farm.post(f"{API}/demo/replays/healthy/start", headers=OTHER_FARM).status_code == 404


def test_anomaly_replay_raises_exactly_one_reduced_movement_alert_for_sari(farm):
    started = _start(farm, "anomaly")
    assert (started["scenario_id"], started["speed"], started["duration_s"], started["status"]) == (
        "anomaly", 0.0, 180, "finished")

    replay = farm.get(f"{API}/replays/{started['replay_id']}", headers=VET).json()
    assert (replay["status"], replay["progress_s"]) == ("finished", 180)
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    assert (tracks["t-01"]["animal_id"], tracks["t-01"]["association_status"]) == ("animal-demo-001", "associated")
    assert tracks["t-02"]["animal_id"] == "animal-demo-002"

    alerts = _alerts(farm, kind="reduced_movement")
    assert len(alerts) == 1
    alert = alerts[0]
    assert (alert["animal_id"], alert["animal_name"], alert["camera_id"], alert["status"]) == (
        "animal-demo-001", "Sari", "cam-pen-a", "open")
    assert alert["track_id"] == tracks["t-01"]["id"]
    assert alert["rule"]["name"] == "reduced_movement_v1" and alert["rule"]["threshold"] == 0.6
    assert alert["rule"]["score"] > 0.7 and alert["rule"]["source"] == "simulated"
    assert alert["clip"] == {"scenario_id": "anomaly", "camera_id": "cam-pen-a", "start_s": 90, "end_s": 120,
                             "video": None}
    anchor = replay["anchor_at"]
    assert alert["baseline_start"] == anchor and alert["window_start"] > anchor
    assert alert["baseline_end"] < alert["window_start"] < alert["window_end"] <= replay["started_at"]
    assert alert["summary"].startswith("Movement ") and "below Sari's earlier window on Pen A · feed line" in \
        alert["summary"] and alert["summary"].endswith("this is not a diagnosis.")
    assert [a["id"] for a in _replay_alerts(farm, started["replay_id"])] == [alert["id"]]
    assert _alerts(farm, kind="observation_quality", animal_id="animal-demo-001") == []

    with read_session() as session:
        events = session.scalars(select(AuditEvent).where(AuditEvent.subject_id.in_(
            [alert["id"], started["replay_id"]]))).all()
    assert sorted(e.event_type for e in events) == ["alert.created", "replay.finished", "replay.started"]
    created = next(e for e in events if e.event_type == "alert.created")
    assert (created.animal_id, created.actor_type) == ("animal-demo-001", "system")


def test_anomaly_rerun_within_cooldown_does_not_duplicate_but_later_run_does(farm):
    """Dedupe semantics: the cooldown is per (animal, camera, kind) on observation time across replays, so a rerun
    within 10 minutes adds no alert, and a rerun more than 10 minutes later raises a new one."""
    _start(farm, "anomaly")
    second = _start(farm, "anomaly")
    assert len(_alerts(farm, kind="reduced_movement")) == 1
    assert _replay_alerts(farm, second["replay_id"]) == []

    clock.set_now(lambda: clock._system_now() + timedelta(minutes=11))
    third = _start(farm, "anomaly")
    assert len(_alerts(farm, kind="reduced_movement")) == 2
    assert len(_replay_alerts(farm, third["replay_id"])) == 1


def test_healthy_replay_raises_no_alert(farm):
    before = _alerts(farm)
    started = _start(farm, "healthy")
    assert _alerts(farm) == before
    tracks = farm.get(f"{API}/replays/{started['replay_id']}", headers=VET).json()["tracks"]
    assert {(t["track_key"], t["animal_id"]) for t in tracks} == {("t-01", "animal-demo-001"),
                                                                 ("t-02", "animal-demo-002")}


def test_lost_identity_track_never_becomes_bima(farm):
    started = _start(farm, "lost_identity")
    replay = farm.get(f"{API}/replays/{started['replay_id']}", headers=VET).json()
    tracks = {t["track_key"]: t for t in replay["tracks"]}
    assert (tracks["t-03"]["association_status"], tracks["t-03"]["animal_id"]) == ("uncertain", None)
    assert tracks["t-03"]["association_evidence"]["previous_animal_id"] == "animal-demo-002"
    t14 = tracks["t-14"]
    assert (t14["association_status"], t14["animal_id"]) == ("unassigned", None)

    with read_session() as session:
        on_t14 = session.scalars(select(Observation).where(Observation.track_id == t14["id"])).all()
    assert on_t14 and all(o.animal_id is None and o.association_status == "unassigned" for o in on_t14)

    warnings = _replay_alerts(farm, started["replay_id"])
    assert [(a["kind"], a["animal_id"], a["track_id"], a["track_key"]) for a in warnings] == [
        ("observation_quality", None, t14["id"], "t-14")]
    assert warnings[0]["clip"]["start_s"] == 90 and warnings[0]["rule"]["reasons"] == ["low_visibility"]
    assert "unidentified track t-14" in warnings[0]["summary"]

    bima = farm.get(f"{API}/animals/animal-demo-002/observations", headers=VET).json()
    last = bima["last_observation"]
    assert last["camera_id"] == "cam-pen-b" and last["association_status"] == "associated"
    with read_session() as session:
        assert session.get(Observation, last["id"]).track_id == tracks["t-03"]["id"]
    assert all(o["track_id"] != t14["id"] for o in bima["recent"])
    assert all(o["animal_id"] == "animal-demo-002" for o in bima["recent"])


def test_sari_is_last_seen_on_pen_a_after_the_anomaly(farm):
    assert farm.get(f"{API}/animals/animal-demo-001/observations", headers=VET).json()["last_observation"] is None
    _start(farm, "anomaly")
    body = farm.get(f"{API}/animals/animal-demo-001/observations", headers=VET).json()
    last = body["last_observation"]
    assert (last["camera_id"], last["camera_name"], last["association_status"]) == (
        "cam-pen-a", "Pen A · feed line", "associated")
    assert [t["track_key"] for t in body["tracks"]] == ["t-01"]
    assert len(body["recent"]) == 50 and body["quality_summary"]["low_visibility"] == 0
    assert farm.get(f"{API}/animals/animal-demo-001/observations", headers=OTHER_FARM).status_code == 404

    passport = farm.get(f"{API}/animals/animal-demo-001/passport", headers=VET).json()
    titles = [line["title"] for line in passport["passbook"]["lines"]] if isinstance(passport["passbook"], dict) \
        else [line["title"] for line in passport["passbook"]]
    assert "Identified on camera Pen A · feed line" in titles and "Alert · reduced movement" in titles


def test_cameras_show_map_coordinates_and_last_observation(farm):
    items = {c["id"]: c for c in farm.get(f"{API}/cameras", headers=ASSESSOR).json()["items"]}
    assert (items["cam-pen-a"]["map_x"], items["cam-pen-a"]["map_y"]) == (0.22, 0.30)
    assert items["cam-pen-a"]["last_observation"]["animal_id"] == "animal-demo-002"
    _start(farm, "lost_identity")
    pen_b = farm.get(f"{API}/cameras", headers=ASSESSOR).json()["items"][1]
    assert pen_b["id"] == "cam-pen-b"
    assert (pen_b["last_observation"]["animal_id"], pen_b["last_observation"]["association_status"]) == (
        None, "unassigned")
    assert farm.get(f"{API}/cameras", headers=OTHER_FARM).json()["items"] == []


def _observation(**overrides) -> dict:
    body = {"track_key": "ext-1", "observed_at": "2026-10-20T09:00:00Z", "bbox": [0.1, 0.1, 0.2, 0.2],
            "visibility": 0.9}
    return {**body, **overrides}


def test_observation_feed_requires_the_service_token(farm):
    url = f"{API}/cameras/cam-pen-c/observations"
    assert farm.post(url, json=_observation()).status_code == 401
    assert farm.post(url, json=_observation(), headers={"X-Service-Token": "wrong"}).status_code == 401
    assert farm.post(url, json=_observation(), headers=MANAGER).status_code == 401

    created = farm.post(url, json=_observation(), headers=SERVICE)
    assert created.status_code == 201, created.text
    assert created.json()["track"]["association_status"] == "unassigned"

    matched = farm.post(url, headers=SERVICE, json=_observation(
        observed_at="2026-10-20T09:00:01Z", event="muzzle_match", candidate_animal_id="animal-demo-006", inliers=19,
        quality=0.8)).json()
    assert (matched["observation"]["animal_id"], matched["track"]["association_method"]) == (
        "animal-demo-006", "muzzle_match")
    assert farm.post(f"{API}/cameras/cam-nope/observations", json=_observation(), headers=SERVICE).status_code == 404
    assert farm.post(url, json=_observation(bbox=[0.1, 0.2]), headers=SERVICE).status_code == 422
    with read_session() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "track.associated",
                                                        AuditEvent.animal_id == "animal-demo-006"))
    assert (event.actor_type, event.actor_id) == ("system", "service-worker")


def test_human_track_review_is_audited_and_role_checked(farm):
    started = _start(farm, "lost_identity")
    t14 = next(t for t in farm.get(f"{API}/replays/{started['replay_id']}", headers=VET).json()["tracks"]
               if t["track_key"] == "t-14")
    url = f"{API}/tracks/{t14['id']}"
    body = {"animal_id": "animal-demo-002", "note": "Ear tag 002 read at the trough"}
    assert farm.patch(url, json=body, headers=VET).status_code == 403
    assert farm.patch(url, json=body, headers=OTHER_FARM).status_code == 404
    assert farm.patch(url, json={"animal_id": "animal-other-001"}, headers=OPERATOR).status_code == 404

    reviewed = farm.patch(url, json=body, headers=OPERATOR)
    assert reviewed.status_code == 200, reviewed.text
    track = reviewed.json()
    assert (track["animal_id"], track["animal_name"], track["association_method"]) == (
        "animal-demo-002", "Bima", "human_review")
    with read_session() as session:
        earlier = session.scalar(select(func.count()).select_from(Observation).where(
            Observation.track_id == t14["id"], Observation.animal_id.is_not(None)))
        event = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "track.associated",
                                                        AuditEvent.subject_id == t14["id"]))
    assert earlier == 0  # never retroactive
    assert (event.actor_id, event.animal_id, event.data["note"]) == (
        "user-operator", "animal-demo-002", "Ear tag 002 read at the trough")

    unassigned = farm.patch(url, json={"animal_id": None}, headers=MANAGER).json()
    assert (unassigned["association_status"], unassigned["animal_id"]) == ("unassigned", None)
    with read_session() as session:
        assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "track.unassigned")) is not None


def test_reset_stops_a_threaded_replay_cleanly(farm, monkeypatch):
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", "4")
    get_settings.cache_clear()
    started = _start(farm, "anomaly")
    assert started["speed"] == 4.0
    deadline = time.monotonic() + 5
    while replays.active_progress(started["replay_id"]) in (None, 0.0) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert replays.is_running_thread(started["replay_id"])
    with read_session() as session:
        assert session.get(Replay, started["replay_id"]).status == "running"

    assert farm.post(f"{API}/demo/reset?scenario=post-enrollment", headers=MANAGER).status_code == 200

    assert not replays.is_running_thread(started["replay_id"])
    assert replays.active_progress(started["replay_id"]) is None
    with read_session() as session:
        count = session.scalar(select(func.count()).select_from(Observation))
        assert session.scalar(select(func.count()).select_from(Replay)) == 0
    time.sleep(0.6)
    with read_session() as session:
        assert session.scalar(select(func.count()).select_from(Observation)) == count


def test_starting_a_replay_stops_the_running_one_on_that_camera(farm, monkeypatch):
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", "4")
    get_settings.cache_clear()
    first = _start(farm, "healthy")
    second = _start(farm, "anomaly")
    try:
        assert not replays.is_running_thread(first["replay_id"])
        with read_session() as session:
            assert session.get(Replay, first["replay_id"]).status == "stopped"
            assert session.get(Replay, second["replay_id"]).status == "running"
        assert farm.get(f"{API}/replays/{first['replay_id']}", headers=VET).json()["status"] == "stopped"
    finally:
        replays.stop_all()


def _latest_observation_time():
    with read_session() as session:
        return session.scalar(select(func.max(Observation.observed_at)))


@pytest.mark.parametrize("scenario", ["healthy", "anomaly", "lost_identity"])
def test_instant_replay_is_footage_that_ends_before_now(farm, scenario):
    started = _start(farm, scenario)
    replay = farm.get(f"{API}/replays/{started['replay_id']}", headers=VET).json()
    assert replay["anchor_at"] < replay["started_at"]
    latest = _latest_observation_time()
    assert latest <= clock.now()
    assert clock.isoformat(latest) < replay["started_at"]
    with read_session() as session:
        alert_ends = session.scalars(select(Alert.window_end)).all()
    assert all(end <= clock.now() for end in alert_ends)


def test_threaded_replay_never_stamps_an_observation_after_its_ingest(farm, monkeypatch):
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", "20")
    get_settings.cache_clear()
    started = _start(farm, "healthy")
    assert started["anchor_at"] < started["started_at"]
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            latest = _latest_observation_time()
            assert latest <= clock.now()
            time.sleep(0.1)
    finally:
        replays.stop_all()


def test_assistant_reports_a_past_last_seen_time_after_a_replay(farm):
    _start(farm, "anomaly")
    body = farm.post(f"{API}/assistant/query", json={"text": "Where was Sari last seen?"}, headers=VET).json()
    observed = next(f["value"] for f in body["facts"] if f["label"] == "Last observed at")
    assert observed <= clock.isoformat(clock.now())
    assert "(just now)" in body["answer"] or "min ago" in body["answer"]


def _walk_frames(start: float, end: float, speed_per_s: float, fps: int = 2) -> list[dict]:
    frames, x, direction = [], 0.3, 1
    for i in range(round(start * fps), round(end * fps)):
        step = speed_per_s / fps
        if not 0.05 <= x + direction * step <= 0.7:
            direction = -direction
        x += direction * step
        frames.append({"t": i / fps, "bbox": [round(x, 5), 0.4, 0.2, 0.2], "visibility": 0.9})
    return frames


def test_movement_uses_only_observations_attributed_to_the_animal(farm, monkeypatch):
    """Bima's track is matched at 40 s. Before that the (unidentified) track runs fast; afterwards it walks at a steady
    speed. Counting the unattributed frames would make the 30-60 s window a fast baseline and raise a false
    reduced-movement alert; attributing only Bima's own frames skips that partial window and finds no change."""
    scenario = {"id": "late_match", "label": "Late match", "description": "test", "camera_id": "cam-pen-a",
                "source": "simulated", "duration_s": 120, "fps": 2, "window_s": 30, "clip": None,
                "tracks": [{"track_key": "t-late",
                            "frames": _walk_frames(0, 40, 0.05) + _walk_frames(40, 120, 0.008),
                            "events": [{"t": 40, "type": "muzzle_match", "candidate_animal_id": "animal-demo-002",
                                        "inliers": 25, "quality": 0.9}]}]}
    real = replays.load_scenario
    monkeypatch.setattr(replays, "load_scenario",
                        lambda settings, scenario_id: scenario if scenario_id == "late_match" else real(settings,
                                                                                                        scenario_id))
    started = _start(farm, "late_match")
    replay = farm.get(f"{API}/replays/{started['replay_id']}", headers=VET).json()
    assert replay["tracks"][0]["animal_id"] == "animal-demo-002"
    assert replay["alerts"] == []  # no reduced movement and no quality warning on Bima for the partial window


def test_concurrent_starts_on_one_camera_leave_one_running_replay(farm, monkeypatch):
    monkeypatch.setenv("VEYRA_REPLAY_SPEED", "4")
    get_settings.cache_clear()
    import threading as _threading

    results, errors = [], []

    def start(scenario):
        try:
            results.append(replays.start(get_settings(), farm_id="farm-wahyu", actor=("user", "user-operator"),
                                         scenario_id=scenario).id)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    workers = [_threading.Thread(target=start, args=(name,)) for name in ("healthy", "anomaly", "healthy")]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
        assert errors == [] and len(results) == 3
        with read_session() as session:
            statuses = dict(session.execute(select(Replay.id, Replay.status)).all())
        assert sorted(statuses.values()) == ["running", "stopped", "stopped"]
        running = [rid for rid, status in statuses.items() if status == "running"]
        assert [rid for rid in results if replays.is_running_thread(rid)] == running
    finally:
        replays.stop_all()
