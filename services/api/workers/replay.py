"""Camera replay runner (`demo/scenarios`; association and movement rules).

A replay steps through a simulated scenario and feeds every frame and event through the same ingest function the
internal `POST /cameras/{id}/observations` endpoint uses, so association, observations, and alerts are produced
exactly as for a live camera. 

- A replay is recorded footage that ends no later than now: `observed_at = anchor + t`, where the anchor is
  `started_at − duration` at speed 0, `started_at − duration × (1 − 1/speed)` at speed ≥ 1, and `started_at` below
  speed 1. No observation is ever stamped after the moment it is ingested, so "last seen" is always in the past.
- Speed 0 ingests the whole scenario synchronously, inside the request that started it.
- Speed > 0 runs a daemon thread that ingests one simulated second per commit and waits `1 / speed` real seconds
  between batches (no transaction is held while waiting).
- Camera events (`scenario["events"]`, today only `zone_scan`) go through `association.zone_scan`, the same handoff
  the observation feed uses; at one instant, frames come first, then track events, then camera events.
- A `zone_scan` that names a `muzzle_image` (repo-relative) is not pre-decided: when the replay starts, the real
  muzzle matcher compares that image with the farm's enrolled muzzles, and its verified match (or none) becomes the
  scan's animal. `inliers` are the matcher's verified points and `quality` the matched embedding's cosine.
- The movement rule runs for every track as each window closes, on the observations attributed to the track's
  animal (an associated track) or on all of the track's frames (quality warnings on an unassigned track).
- Only one replay runs per farm and camera: starting another stops the previous one (status `stopped`). Starts on
  one camera are serialized by a lock, and a runner stops by itself once its row is no longer `running`.
- A demo reset stops every replay thread first (`register_reset_hook`), so a reset never races a writer.
"""

import json
import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from config import Settings
from domain import alerts as alert_rules
from domain import audit, clock, movement
from adapters.perception import Perception, guide_box_crop
from domain.association import ObservationInput, ZoneScanInput, ingest, zone_scan
from domain.errors import DomainError
from domain.ids import new_id
from persistence.db import SessionLocal, read_session, writer_scope
from persistence.lifecycle import register_reset_hook
from persistence.models import Alert, Camera, Observation, Replay, Track

logger = logging.getLogger("veyra.replay")

REPLAY_ACTOR = ("system", "replay")
STATUSES = ("running", "finished", "failed", "stopped")
JOIN_TIMEOUT_S = 5.0


# --- scenarios -------------------------------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _read_scenario(path: Path, mtime: float) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def real_scan(settings: Settings, farm_id: str, image: Path, perception: Perception | None = None) -> dict:
    """The real muzzle matcher on a scan image against the farm's enrolled muzzles: `{animal_id, inliers, quality,
    source}`, with `animal_id` None unless one animal verifies. Never raises: an unreadable image or a missing
    matcher is a scan that names no animal."""
    import tempfile

    import cv2

    from workers.enrollment_job import gallery_refs

    perception = perception or Perception()
    none = {"animal_id": None, "inliers": None, "quality": None, "source": "simulated"}
    frame = cv2.imread(str(image))
    if frame is None or not perception.capabilities.get("muzzle"):
        return none
    with read_session() as session:
        refs = gallery_refs(session, farm_id)
    with tempfile.TemporaryDirectory() as work:
        crop = Path(work) / "zone_scan_crop.jpg"
        cv2.imwrite(str(crop), guide_box_crop(frame))
        identity = perception.identify(crop, refs, None)
    if identity.get("fallback"):
        return none
    best = max(identity.get("candidates") or [], key=lambda c: c.get("inliers") or 0, default=None)
    matched = identity.get("animal_id") if identity.get("outcome") == "candidate" else None
    chosen = next((c for c in identity.get("candidates") or [] if c.get("animal_id") == matched), best)
    return {"animal_id": matched, "inliers": chosen.get("inliers") if chosen else None,
            "quality": round(float(chosen["cosine"]), 2) if chosen and matched else None,
            "source": identity.get("source") or "prototype"}


def with_real_scans(settings: Settings, farm_id: str, scenario: dict) -> dict:
    """The scenario with each `muzzle_image` zone scan decided by the real matcher (see the module docstring)."""
    events = scenario.get("events") or []
    if not any(e.get("muzzle_image") for e in events):
        return scenario
    resolved = []
    for event in events:
        if event.get("type") == "zone_scan" and event.get("muzzle_image"):
            result = real_scan(settings, farm_id, settings.repo_root / event["muzzle_image"])
            event = {**event, **{k: result[k] for k in ("animal_id", "inliers", "quality")},
                     "scan_source": result["source"]}
        resolved.append(event)
    return {**scenario, "events": resolved}


def scenario_ids(settings: Settings) -> list[str]:
    return sorted(path.stem for path in settings.scenarios_dir.glob("*.json"))


def load_scenario(settings: Settings, scenario_id: str) -> dict:
    path = settings.scenarios_dir / f"{scenario_id}.json"
    if scenario_id not in scenario_ids(settings) or not path.is_file():
        raise DomainError("NOT_FOUND", "Scenario not found.", {"scenario_id": scenario_id})
    return _read_scenario(path, path.stat().st_mtime)


def list_scenarios(settings: Settings) -> list[dict]:
    return [load_scenario(settings, scenario_id) for scenario_id in scenario_ids(settings)]


# --- running replays -------------------------------------------------------------------------------------------


@dataclass
class _Run:
    replay_id: str
    farm_id: str
    camera_id: str
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    progress_s: float = 0.0


_runs: dict[str, _Run] = {}
_runs_lock = threading.Lock()


def _stop_runs(predicate) -> list[str]:
    with _runs_lock:
        runs = [run for run in _runs.values() if predicate(run)]
    for run in runs:
        run.stop.set()
    for run in runs:
        if run.thread is not None and run.thread is not threading.current_thread():
            run.thread.join(JOIN_TIMEOUT_S)
            if run.thread.is_alive():
                logger.warning("Replay %s did not stop within %ss", run.replay_id, JOIN_TIMEOUT_S)
    return [run.replay_id for run in runs]


def stop_all() -> list[str]:
    """Stop every replay thread and wait for each to exit (the demo reset hook)."""
    return _stop_runs(lambda run: True)


register_reset_hook(stop_all)


def active_progress(replay_id: str) -> float | None:
    with _runs_lock:
        run = _runs.get(replay_id)
    return None if run is None else run.progress_s


def is_running_thread(replay_id: str) -> bool:
    with _runs_lock:
        run = _runs.get(replay_id)
    return bool(run and run.thread and run.thread.is_alive())


def footage_anchor(started_at: datetime, speed: float, duration_s: float) -> datetime:
    """Scenario time 0 in observation time: the replay is footage that ends no later than its ingest."""
    if speed == 0:
        return started_at - timedelta(seconds=duration_s)
    if speed >= 1:
        return started_at - timedelta(seconds=duration_s * (1 - 1 / speed))
    return started_at


CAMERA_EVENT = 2


def _items(scenario: dict) -> list[tuple[float, int, str, dict]]:
    """Frames and events in scenario order; at the same instant every frame comes before the track events, and
    those before the camera's own events (a scan sees the frames of its instant)."""
    items = []
    for track in scenario["tracks"]:
        items += [(frame["t"], 0, track["track_key"], frame) for frame in track["frames"]]
        items += [(event["t"], 1, track["track_key"], event) for event in track["events"]]
    items += [(event["t"], CAMERA_EVENT, "", event) for event in scenario.get("events", [])]
    return sorted(items, key=lambda item: (item[0], item[1], item[2]))


class _Replayer:
    """The state of one replay as it steps: last frame per track, track start and loss times, and the baselines."""

    def __init__(self, run: _Run, scenario: dict, anchor: datetime, speed: float) -> None:
        self.run, self.scenario, self.anchor, self.speed = run, scenario, anchor, speed
        self.window_s = scenario["window_s"]
        self.fps = scenario["fps"]
        self.items = _items(scenario)
        self.last_frame: dict[str, dict] = {}
        self.first_seen_s: dict[str, float] = {}
        self.lost_at_s: dict[str, float] = {}
        self.baselines: dict[tuple[str, str], movement.WindowStats] = {}
        self.pending_windows = movement.windows(scenario["duration_s"], self.window_s)

    def at(self, t: float) -> datetime:
        return self.anchor + timedelta(seconds=t)

    def _observation(self, t: float, kind: int, track_key: str, entry: dict) -> ObservationInput:
        if kind == 0:
            self.last_frame[track_key] = entry
            self.first_seen_s.setdefault(track_key, t)
            return ObservationInput(track_key=track_key, observed_at=self.at(t), bbox=entry["bbox"],
                                    visibility=entry["visibility"])
        frame = self.last_frame.get(track_key) or {"bbox": [0.0, 0.0, 0.0, 0.0], "visibility": 0.0}
        self.first_seen_s.setdefault(track_key, t)
        if entry["type"] == "track_lost":
            self.lost_at_s.setdefault(track_key, t)
            return ObservationInput(track_key=track_key, observed_at=self.at(t), bbox=frame["bbox"],
                                    visibility=frame["visibility"], event="track_lost", reason=entry.get("reason"))
        return ObservationInput(track_key=track_key, observed_at=self.at(t), bbox=frame["bbox"],
                                visibility=frame["visibility"], event="muzzle_match",
                                candidate_animal_id=entry.get("candidate_animal_id"), inliers=entry.get("inliers"),
                                quality=entry.get("quality"))

    def ingest_batch(self, start_s: float, end_s: float) -> bool:
        """Ingest one batch; False (and nothing written) once the replay row is no longer running."""
        batch = [item for item in self.items if start_s <= item[0] < end_s]
        with SessionLocal() as session:
            if session.scalar(select(Replay.status).where(Replay.id == self.run.replay_id)) != "running":
                self.run.stop.set()
                return False
            source = self.scenario.get("source", "simulated")
            for t, kind, track_key, entry in batch:
                if kind == CAMERA_EVENT:
                    if entry["type"] == "zone_scan":
                        zone_scan(session, farm_id=self.run.farm_id, camera_id=self.run.camera_id,
                                  scan=ZoneScanInput(observed_at=self.at(t), animal_id=entry.get("animal_id"),
                                                     inliers=entry.get("inliers"), quality=entry.get("quality")),
                                  replay_id=self.run.replay_id, actor=REPLAY_ACTOR,
                                  source=entry.get("scan_source", source))
                    continue
                ingest(session, farm_id=self.run.farm_id, camera_id=self.run.camera_id,
                       item=self._observation(t, kind, track_key, entry), replay_id=self.run.replay_id,
                       actor=REPLAY_ACTOR, source=source)
            session.commit()
        return True

    def evaluate_closed_windows(self, now_s: float) -> None:
        closed = [w for w in self.pending_windows if w[1] <= now_s]
        if not closed:
            return
        self.pending_windows = [w for w in self.pending_windows if w[1] > now_s]
        with SessionLocal() as session:
            for start_s, end_s in closed:
                self._evaluate(session, start_s, end_s)
            session.commit()

    def _evaluate(self, session: Session, start_s: float, end_s: float) -> None:
        tracks = session.scalars(select(Track).where(Track.replay_id == self.run.replay_id)
                                 .order_by(Track.first_seen, Track.track_key)).all()
        for track in tracks:
            first_s = self.first_seen_s.get(track.track_key)
            if first_s is None or not movement.window_applies(
                    first_seen_s=first_s, lost_at_s=self.lost_at_s.get(track.track_key), start_s=start_s,
                    end_s=end_s, frame_interval_s=1 / self.fps):
                continue
            if track.association_status == "uncertain":
                continue
            associated = track.association_status == "associated"
            query = select(Observation).where(
                Observation.track_id == track.id, Observation.event == "frame",
                Observation.observed_at >= self.at(start_s), Observation.observed_at < self.at(end_s))
            partial = False
            if associated:
                # Only what was attributed to this animal at ingest counts toward its movement.
                attributed = (Observation.track_id == track.id, Observation.association_status == "associated",
                              Observation.animal_id == track.animal_id)
                query = query.where(*attributed[1:])
                since = session.scalar(select(func.min(Observation.observed_at)).where(*attributed))
                partial = since is None or since > self.at(start_s + 0.5 / self.fps)
            samples = [movement.Sample((row.observed_at - self.anchor).total_seconds(), row.bbox, row.visibility)
                       for row in session.scalars(query).all()]
            stats = movement.window_stats(samples, start_s=start_s, window_s=self.window_s, fps=self.fps)
            key = (track.animal_id, track.camera_id)
            assessment = movement.assess(stats, associated=associated, partial_association=partial,
                                         baseline=self.baselines.get(key) if associated else None)
            if assessment.outcome == "baseline":
                self.baselines[key] = stats
            if not assessment.raises_alert:
                continue
            baseline = self.baselines.get(key) if assessment.outcome == "reduced_movement" else None
            alert_rules.create(
                session, farm_id=self.run.farm_id, kind=assessment.outcome, camera_id=track.camera_id, track=track,
                animal_id=track.animal_id if associated else None, window_start=self.at(start_s),
                window_end=self.at(end_s), rule=movement.rule_json(assessment, stats, self.window_s),
                clip={"scenario_id": self.scenario["id"], "camera_id": track.camera_id, "start_s": start_s,
                      "end_s": end_s, "video": self.scenario.get("clip")},
                baseline_start=self.at(baseline.start_s) if baseline else None,
                baseline_end=self.at(baseline.end_s) if baseline else None, actor=REPLAY_ACTOR)

    def run_steps(self) -> bool:
        """Ingest and evaluate second by second; False if stopped. A threaded replay waits before each batch, so the
        batch for simulated second k (frames up to k + 0.5) is ingested only once its footage has been "recorded"
        (with the anchor, no observation is ever stamped after its ingest)."""
        steps = math.ceil(self.scenario["duration_s"])
        for second in range(steps):
            if self.run.stop.is_set():
                return False
            if self.speed > 0 and self.run.stop.wait(1 / self.speed):
                return False
            if not self.ingest_batch(second, second + 1):
                return False
            self.run.progress_s = float(second + 1)
            self.evaluate_closed_windows(second + 1)
        return True


def _finish(replay_id: str, farm_id: str, status: str, data: dict | None = None) -> None:
    with SessionLocal() as session:
        result = session.execute(update(Replay).where(Replay.id == replay_id, Replay.status == "running")
                                 .values(status=status, finished_at=clock.now())
                                 .execution_options(synchronize_session=False))
        if result.rowcount == 1:
            audit.record(session, farm_id=farm_id, actor_type=REPLAY_ACTOR[0], actor_id=REPLAY_ACTOR[1],
                         event_type=f"replay.{status}", subject_type="replay", subject_id=replay_id, data=data)
        session.commit()


def _alert_count(replay_id: str) -> int:
    with read_session() as session:
        tracks = select(Track.id).where(Track.replay_id == replay_id)
        return session.scalar(select(func.count()).select_from(Alert).where(Alert.track_id.in_(tracks))) or 0


def _execute(run: _Run, scenario: dict, anchor: datetime, speed: float) -> None:
    try:
        completed = _Replayer(run, scenario, anchor, speed).run_steps()
        if completed and not run.stop.is_set():
            _finish(run.replay_id, run.farm_id, "finished",
                    {"scenario_id": scenario["id"], "alerts": _alert_count(run.replay_id)})
    except Exception:
        logger.exception("Replay %s failed", run.replay_id)
        if not run.stop.is_set():
            try:
                _finish(run.replay_id, run.farm_id, "failed", {"scenario_id": scenario["id"]})
            except Exception:
                logger.exception("Could not mark replay %s failed", run.replay_id)
    finally:
        with _runs_lock:
            _runs.pop(run.replay_id, None)


def _execute_in_own_scope(run: _Run, scenario: dict, anchor: datetime, speed: float) -> None:
    """The replay thread gets its own writer slot, never the slot of the request that started it."""
    with writer_scope():
        _execute(run, scenario, anchor, speed)


_start_locks: dict[tuple[str, str], threading.Lock] = {}


def _start_lock(farm_id: str, camera_id: str) -> threading.Lock:
    with _runs_lock:
        return _start_locks.setdefault((farm_id, camera_id), threading.Lock())


def start(settings: Settings, *, farm_id: str, actor: tuple[str, str], scenario_id: str) -> Replay:
    """Create the replay and run it: synchronously at speed 0, else on a daemon thread. Returns the replay row as it
    stands afterwards (`finished` or `failed` at speed 0, `running` otherwise). The caller must not hold a writing
    session. Starts on one camera are serialized: stopping the previous replay, creating the new row, and
    registering its runner happen under one lock."""
    scenario = load_scenario(settings, scenario_id)
    camera_id = scenario["camera_id"]
    with read_session() as session:
        camera = session.get(Camera, camera_id)
        if camera is None or camera.farm_id != farm_id:
            raise DomainError("NOT_FOUND", "This scenario's camera is not on your farm.", {"camera_id": camera_id})
    scenario = with_real_scans(settings, farm_id, scenario)
    speed = float(settings.replay_speed)
    with _start_lock(farm_id, camera_id):
        _stop_runs(lambda run: run.farm_id == farm_id and run.camera_id == camera_id)
        now = clock.now()
        with SessionLocal() as session:
            previous = session.scalars(select(Replay.id).where(
                Replay.farm_id == farm_id, Replay.camera_id == camera_id, Replay.status == "running")).all()
            if previous:
                session.execute(update(Replay).where(Replay.id.in_(previous), Replay.status == "running")
                                .values(status="stopped", finished_at=now)
                                .execution_options(synchronize_session=False))
                for replay_id in previous:
                    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1],
                                 event_type="replay.stopped", subject_type="replay", subject_id=replay_id,
                                 data={"reason": "superseded"})
            replay = Replay(id=new_id("rpl"), farm_id=farm_id, scenario_id=scenario_id, camera_id=camera_id,
                            status="running", speed=speed, started_at=now, finished_at=None)
            session.add(replay)
            session.flush()
            audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1],
                         event_type="replay.started", subject_type="replay", subject_id=replay.id,
                         data={"scenario_id": scenario_id, "camera_id": camera_id, "speed": speed,
                               "source": scenario.get("source", "simulated"), "superseded": list(previous)})
            session.commit()
        run = _Run(replay_id=replay.id, farm_id=farm_id, camera_id=camera_id)
        anchor = footage_anchor(now, speed, scenario["duration_s"])
        with _runs_lock:
            _runs[replay.id] = run
        if speed > 0:
            run.thread = threading.Thread(target=_execute_in_own_scope, args=(run, scenario, anchor, speed),
                                          daemon=True, name=f"replay-{replay.id}")
            run.thread.start()
    if speed == 0:
        _execute(run, scenario, anchor, speed)
    with read_session() as session:
        return session.get(Replay, replay.id) or replay


def anchor_of(replay: Replay, scenario_duration: float) -> datetime:
    return footage_anchor(replay.started_at, replay.speed, scenario_duration)


def progress_of(replay: Replay, scenario_duration: float, session: Session) -> float:
    active = active_progress(replay.id)
    if active is not None:
        return active
    if replay.status == "finished":
        return float(scenario_duration)
    last = session.scalar(select(func.max(Track.last_seen)).where(Track.replay_id == replay.id))
    if last is None:
        return 0.0
    elapsed = (last - anchor_of(replay, scenario_duration)).total_seconds()
    return max(0.0, min(float(scenario_duration), elapsed))
