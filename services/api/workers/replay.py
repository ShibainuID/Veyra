"""Camera replay runner (plan Section 3: `demo/scenarios`, Section 4: association and movement rules).

A replay steps through a simulated scenario and feeds every frame and event through the same ingest function the
internal `POST /cameras/{id}/observations` endpoint uses, so association, observations, and alerts are produced
exactly as for a live camera. `observed_at = started_at + t`.

- Speed 0 ingests the whole scenario synchronously, inside the request that started it.
- Speed > 0 runs a daemon thread that ingests one simulated second per commit and waits `1 / speed` real seconds
  between batches (no transaction is held while waiting).
- The movement rule runs for every track as each window closes.
- Only one replay runs per farm and camera: starting another stops the previous one (status `stopped`).
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
from domain.association import ObservationInput, ingest
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


def _items(scenario: dict) -> list[tuple[float, int, str, dict]]:
    """Frames and events in scenario order; at the same instant a track's frame comes before its events."""
    items = []
    for track in scenario["tracks"]:
        items += [(frame["t"], 0, track["track_key"], frame) for frame in track["frames"]]
        items += [(event["t"], 1, track["track_key"], event) for event in track["events"]]
    return sorted(items, key=lambda item: (item[0], item[1], item[2]))


class _Replayer:
    """The state of one replay as it steps: last frame per track, track start and loss times, and the baselines."""

    def __init__(self, run: _Run, scenario: dict, started_at: datetime, speed: float) -> None:
        self.run, self.scenario, self.started_at, self.speed = run, scenario, started_at, speed
        self.window_s = scenario["window_s"]
        self.fps = scenario["fps"]
        self.items = _items(scenario)
        self.last_frame: dict[str, dict] = {}
        self.first_seen_s: dict[str, float] = {}
        self.lost_at_s: dict[str, float] = {}
        self.baselines: dict[tuple[str, str], movement.WindowStats] = {}
        self.pending_windows = movement.windows(scenario["duration_s"], self.window_s)

    def at(self, t: float) -> datetime:
        return self.started_at + timedelta(seconds=t)

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

    def ingest_batch(self, start_s: float, end_s: float) -> None:
        batch = [item for item in self.items if start_s <= item[0] < end_s]
        if not batch:
            return
        with SessionLocal() as session:
            for t, kind, track_key, entry in batch:
                ingest(session, farm_id=self.run.farm_id, camera_id=self.run.camera_id,
                       item=self._observation(t, kind, track_key, entry), replay_id=self.run.replay_id,
                       actor=REPLAY_ACTOR)
            session.commit()

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
            rows = session.scalars(select(Observation).where(
                Observation.track_id == track.id, Observation.event == "frame",
                Observation.observed_at >= self.at(start_s), Observation.observed_at < self.at(end_s))).all()
            samples = [movement.Sample((row.observed_at - self.started_at).total_seconds(), row.bbox, row.visibility)
                       for row in rows]
            stats = movement.window_stats(samples, start_s=start_s, window_s=self.window_s, fps=self.fps)
            associated = track.association_status == "associated"
            key = (track.animal_id, track.camera_id)
            assessment = movement.assess(stats, associated=associated,
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
        """Ingest and evaluate second by second; False if stopped."""
        steps = math.ceil(self.scenario["duration_s"])
        for second in range(steps):
            if self.run.stop.is_set():
                return False
            self.ingest_batch(second, second + 1)
            self.run.progress_s = float(second + 1)
            self.evaluate_closed_windows(second + 1)
            if self.speed > 0 and self.run.stop.wait(1 / self.speed):
                return False
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


def _execute(run: _Run, scenario: dict, started_at: datetime, speed: float) -> None:
    try:
        completed = _Replayer(run, scenario, started_at, speed).run_steps()
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


def _execute_in_own_scope(run: _Run, scenario: dict, started_at: datetime, speed: float) -> None:
    """The replay thread gets its own writer slot, never the slot of the request that started it."""
    with writer_scope():
        _execute(run, scenario, started_at, speed)


def start(settings: Settings, *, farm_id: str, actor: tuple[str, str], scenario_id: str) -> Replay:
    """Create the replay and run it (synchronously at speed 0, else on a daemon thread). Returns the row as it was
    created. The caller must not hold a writing session."""
    scenario = load_scenario(settings, scenario_id)
    camera_id = scenario["camera_id"]
    with read_session() as session:
        camera = session.get(Camera, camera_id)
        if camera is None or camera.farm_id != farm_id:
            raise DomainError("NOT_FOUND", "This scenario's camera is not on your farm.", {"camera_id": camera_id})
    _stop_runs(lambda run: run.farm_id == farm_id and run.camera_id == camera_id)
    speed = float(settings.replay_speed)
    now = clock.now()
    with SessionLocal() as session:
        previous = session.scalars(select(Replay.id).where(Replay.farm_id == farm_id, Replay.camera_id == camera_id,
                                                           Replay.status == "running")).all()
        if previous:
            session.execute(update(Replay).where(Replay.id.in_(previous), Replay.status == "running")
                            .values(status="stopped", finished_at=now).execution_options(synchronize_session=False))
            for replay_id in previous:
                audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1],
                             event_type="replay.stopped", subject_type="replay", subject_id=replay_id,
                             data={"reason": "superseded"})
        replay = Replay(id=new_id("rpl"), farm_id=farm_id, scenario_id=scenario_id, camera_id=camera_id,
                        status="running", speed=speed, started_at=now, finished_at=None)
        session.add(replay)
        session.flush()
        audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="replay.started",
                     subject_type="replay", subject_id=replay.id,
                     data={"scenario_id": scenario_id, "camera_id": camera_id, "speed": speed,
                           "source": scenario.get("source", "simulated"), "superseded": list(previous)})
        session.commit()
    run = _Run(replay_id=replay.id, farm_id=farm_id, camera_id=camera_id)
    with _runs_lock:
        _runs[replay.id] = run
    if speed == 0:
        _execute(run, scenario, now, speed)
    else:
        run.thread = threading.Thread(target=_execute_in_own_scope, args=(run, scenario, now, speed), daemon=True,
                                      name=f"replay-{replay.id}")
        run.thread.start()
    return replay


def progress_of(replay: Replay, scenario_duration: float, session: Session) -> float:
    active = active_progress(replay.id)
    if active is not None:
        return active
    if replay.status == "finished":
        return float(scenario_duration)
    last = session.scalar(select(func.max(Track.last_seen)).where(Track.replay_id == replay.id))
    return 0.0 if last is None else min(float(scenario_duration), (last - replay.started_at).total_seconds())
