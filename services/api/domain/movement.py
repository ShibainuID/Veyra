"""The transparent movement rule (plan Section 4: movement rule).

Per track and per window (`window_s`, aligned to scenario time 0):
- speed = the mean centroid displacement per second between consecutive frames, in normalized frame units;
- the window is usable when mean visibility is at least `min_visibility` and frame coverage is at least
  `min_coverage` of the frames expected at the scenario fps.

The baseline is the first usable window for the same animal and camera within one replay. A usable window of an
associated track raises `reduced_movement` when `speed < baseline × (1 − threshold)`. A window that is not usable
raises an `observation_quality` warning: on the animal when the track is associated, otherwise on the track.
Alerts are deduped by a cooldown per (animal or track, camera, kind) measured on observation time.

Alerts never diagnose: they say tracked movement was lower than this animal's own earlier window and recommend an
inspection. Everything here is pure; `workers/replay.py` loads the samples and writes the alerts.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo

REDUCED_MOVEMENT_RULE = "reduced_movement_v1"
OBSERVATION_QUALITY_RULE = "observation_quality_v1"
RULE_TEXT = "reduced tracked movement versus this animal's earlier window"
QUALITY_TEXT = "observation quality too low to assess movement in this window"
NOT_A_DIAGNOSIS = "Inspection recommended; this is not a diagnosis."


@dataclass(frozen=True)
class MovementConfig:
    threshold: float = 0.6
    min_visibility: float = 0.6
    min_coverage: float = 0.7
    cooldown: timedelta = field(default=timedelta(minutes=10))


DEFAULT_CONFIG = MovementConfig()


@dataclass(frozen=True)
class Sample:
    t: float  # seconds (scenario time or seconds since the replay started)
    bbox: Sequence[float]  # [x, y, w, h], normalized 0–1
    visibility: float


@dataclass(frozen=True)
class WindowStats:
    start_s: float
    end_s: float
    frames: int
    expected_frames: int
    coverage: float
    mean_visibility: float | None
    speed: float | None
    usable: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    outcome: str  # "baseline" | "normal" | "reduced_movement" | "observation_quality" | "unassessed"
    subject: str  # "animal" | "track"
    score: float | None = None  # reduced movement: fractional drop versus the baseline (0.78 = 78% lower)
    baseline_speed: float | None = None

    @property
    def raises_alert(self) -> bool:
        return self.outcome in ("reduced_movement", "observation_quality")


def centroid(bbox: Sequence[float]) -> tuple[float, float]:
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def speed(samples: Sequence[Sample]) -> float | None:
    """Mean centroid displacement per second over consecutive frames; None with fewer than two frames."""
    ordered = sorted(samples, key=lambda s: s.t)
    rates = []
    for a, b in zip(ordered, ordered[1:]):
        dt = b.t - a.t
        if dt <= 0:
            continue
        (ax, ay), (bx, by) = centroid(a.bbox), centroid(b.bbox)
        rates.append(math.hypot(bx - ax, by - ay) / dt)
    return sum(rates) / len(rates) if rates else None


def windows(duration_s: float, window_s: float) -> list[tuple[float, float]]:
    count = int(duration_s // window_s)
    return [(i * window_s, (i + 1) * window_s) for i in range(count)]


def window_stats(samples: Iterable[Sample], *, start_s: float, window_s: float, fps: float,
                 config: MovementConfig = DEFAULT_CONFIG) -> WindowStats:
    end_s = start_s + window_s
    inside = [s for s in samples if start_s <= s.t < end_s]
    expected = max(1, round(window_s * fps))
    coverage = min(1.0, len(inside) / expected)
    mean_visibility = sum(s.visibility for s in inside) / len(inside) if inside else None
    reasons = []
    if mean_visibility is None or mean_visibility < config.min_visibility:
        reasons.append("low_visibility")
    if coverage < config.min_coverage:
        reasons.append("low_coverage")
    return WindowStats(start_s=start_s, end_s=end_s, frames=len(inside), expected_frames=expected,
                       coverage=round(coverage, 4),
                       mean_visibility=None if mean_visibility is None else round(mean_visibility, 4),
                       speed=speed(inside), usable=not reasons, reasons=tuple(reasons))


def window_applies(*, first_seen_s: float, lost_at_s: float | None, start_s: float, end_s: float,
                   frame_interval_s: float) -> bool:
    """A track is assessed for a window only if it existed when the window opened and was not lost before it
    closed: a track that starts or ends mid-window has a partial window by construction, not a quality problem."""
    if first_seen_s > start_s + frame_interval_s / 2:
        return False
    return lost_at_s is None or lost_at_s >= end_s


def assess(stats: WindowStats, *, associated: bool, baseline: WindowStats | None,
           partial_association: bool = False, config: MovementConfig = DEFAULT_CONFIG) -> Assessment:
    """`stats` of an associated track count only the observations attributed to its animal. When the track was
    associated partway through the window (`partial_association`), a window too short to be usable is skipped:
    the gap comes from when identity was confirmed, not from observation quality."""
    subject = "animal" if associated else "track"
    if not stats.usable:
        if associated and partial_association:
            return Assessment("unassessed", subject)
        return Assessment("observation_quality", subject)
    if not associated or stats.speed is None:
        return Assessment("unassessed", subject)
    if baseline is None or not baseline.speed:
        return Assessment("baseline", subject, baseline_speed=stats.speed)
    drop = 1 - stats.speed / baseline.speed
    if stats.speed < baseline.speed * (1 - config.threshold):
        return Assessment("reduced_movement", subject, score=round(drop, 4), baseline_speed=baseline.speed)
    return Assessment("normal", subject, score=round(drop, 4), baseline_speed=baseline.speed)


def in_cooldown(previous_window_ends: Iterable[datetime], window_end: datetime,
                config: MovementConfig = DEFAULT_CONFIG) -> bool:
    """True when an alert of the same (animal or track, camera, kind) ended within the cooldown of this window,
    before or after it (replays of the same scenario overlap in observation time)."""
    return any(abs(window_end - previous) < config.cooldown for previous in previous_window_ends)


def rule_json(assessment: Assessment, stats: WindowStats, window_s: float,
              config: MovementConfig = DEFAULT_CONFIG) -> dict:
    common = {"window_s": window_s, "mean_visibility": stats.mean_visibility, "coverage": stats.coverage,
              "speed": None if stats.speed is None else round(stats.speed, 6), "source": "simulated"}
    if assessment.outcome == "reduced_movement":
        return {"name": REDUCED_MOVEMENT_RULE, "text": RULE_TEXT, "threshold": config.threshold,
                "score": assessment.score, "baseline": round(assessment.baseline_speed, 6), **common}
    return {"name": OBSERVATION_QUALITY_RULE, "text": QUALITY_TEXT, "threshold": config.min_visibility,
            "min_coverage": config.min_coverage, "score": stats.mean_visibility, "baseline": None,
            "reasons": list(stats.reasons), **common}


def _hhmm(at: datetime, zone: tzinfo = UTC) -> str:
    # Seconds too: a 30 s window inside one minute would otherwise read 09:31–09:31.
    return at.astimezone(zone).strftime("%H:%M:%S")


def alert_summary(*, kind: str, rule: dict, camera_name: str, window_start: datetime, window_end: datetime,
                  animal_name: str | None = None, track_key: str | None = None, zone: tzinfo = UTC) -> str:
    """A plain, deterministic sentence for the alert drawer, the passbook, and the assistant.

    Times print in `zone` (the asker's offset for the assistant; UTC elsewhere, which the web app
    restates in the viewer's local time from the structured window)."""
    span = f"({_hhmm(window_start, zone)}–{_hhmm(window_end, zone)} {window_start.astimezone(zone).tzname()})"
    if kind == "reduced_movement":
        score = rule.get("score") or 0
        who = f"{animal_name}'s" if animal_name else "this animal's"
        return (f"Movement {round(score * 100)}% below {who} earlier window on {camera_name} {span}. "
                f"{NOT_A_DIAGNOSIS}")
    subject = animal_name or (f"unidentified track {track_key}" if track_key else "an unidentified track")
    detail = []
    if rule.get("mean_visibility") is not None and "low_visibility" in rule.get("reasons", ["low_visibility"]):
        detail.append(f"mean visibility {round(rule['mean_visibility'] * 100)}%")
    if "low_coverage" in rule.get("reasons", []) and rule.get("coverage") is not None:
        detail.append(f"frame coverage {round(rule['coverage'] * 100)}%")
    why = f": {', '.join(detail)}" if detail else ""
    return (f"Observation quality too low to assess movement for {subject} on {camera_name} {span}{why}. "
            f"Check the camera view; this is not a diagnosis.")
