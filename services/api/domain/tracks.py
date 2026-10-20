"""Track rules for barn cameras (PRD M07, M08, Section 4.5): scan-zone handoff, identity continuity, movement.

Pure functions with no database or model imports, so the worker, the tests, and the offline evaluation on
real footage (`ml/scripts/tune_handoff_policy.py`) all run the same rules. Boxes are pixel xyxy and times are
seconds from the start of a recording.

Tracks wire format (perception output, worker payloads, replay fixtures):
    {"width": 800, "height": 600, "fps": 20, "source": "prototype", "method_version": "...",
     "frames": [[t_s, [[track_id, x0, y0, x1, y1, conf], ...]], ...]}
"""

import math
from dataclasses import dataclass

# Handoff and continuity policy. `max_gap_s` and the crowding values were selected on 10 minutes of real barn
# footage (8-Calves) with zero wrong identities as the first criterion; see ml/results/handoff_policy.md.
POLICY = {
    "version": "handoff_v2",
    # A scan hands over identity only if exactly one track dwells in the zone around the scan time.
    "zone_window_s": 10.0,
    "zone_dwell_s": 2.0,
    # Identity is dropped when the track is missing longer than this, or overlaps another animal for too long.
    "max_gap_s": 1.0,
    "crowd_iou": 0.6,
    "crowd_s": 0.25,
}

# Movement is measured on samples at this rate, which suppresses detector jitter between consecutive frames.
SAMPLE_HZ = 1.0
WINDOW_S = 60.0


@dataclass(frozen=True)
class Box:
    track_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0

    @property
    def center(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2

    @property
    def diagonal(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


@dataclass(frozen=True)
class Frame:
    t: float
    boxes: tuple[Box, ...]

    def get(self, track_id: str) -> Box | None:
        return next((b for b in self.boxes if b.track_id == track_id), None)


@dataclass(frozen=True)
class Tracks:
    width: int
    height: int
    fps: float
    frames: tuple[Frame, ...]
    source: str
    method_version: str

    @property
    def duration_s(self) -> float:
        return self.frames[-1].t if self.frames else 0.0

    def track_ids(self) -> list[str]:
        return sorted({b.track_id for f in self.frames for b in f.boxes})


class TracksFormatError(ValueError):
    pass


def parse_tracks(data: dict) -> Tracks:
    try:
        frames = []
        last_t = -math.inf
        for t, boxes in data["frames"]:
            t = float(t)
            if t < last_t:
                raise TracksFormatError("frame times must not decrease")
            last_t = t
            frames.append(Frame(t, tuple(Box(str(b[0]), *map(float, b[1:5]), float(b[5]) if len(b) > 5 else 1.0)
                                         for b in boxes)))
        return Tracks(int(data["width"]), int(data["height"]), float(data.get("fps") or 0), tuple(frames),
                      str(data.get("source", "prototype")), str(data.get("method_version", "unknown")))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TracksFormatError):
            raise
        raise TracksFormatError(f"invalid tracks payload: {exc}") from exc


def iou(a: Box, b: Box) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    union = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - inter
    return inter / union if union > 0 else 0.0


def point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


@dataclass(frozen=True)
class Handoff:
    status: str
    track_id: str | None
    reason: str | None
    candidates: tuple[str, ...]
    linked_from_t: float | None


def resolve_handoff(tracks: Tracks, zone: list[list[float]], scan_t: float, policy: dict = POLICY) -> Handoff:
    """Which track, if any, carries the identity scanned in `zone` (normalised polygon) at `scan_t`."""
    poly = [(x * tracks.width, y * tracks.height) for x, y in zone]
    window = [f for f in tracks.frames if abs(f.t - scan_t) <= policy["zone_window_s"]]
    dwell: dict[str, float] = {}
    first_in: dict[str, float] = {}
    for prev, cur in zip(window, window[1:]):
        for box in cur.boxes:
            if point_in_polygon(*box.center, poly):
                dwell[box.track_id] = dwell.get(box.track_id, 0.0) + (cur.t - prev.t)
                first_in.setdefault(box.track_id, cur.t)
    candidates = tuple(sorted(t for t, d in dwell.items() if d >= policy["zone_dwell_s"]))
    if not candidates:
        return Handoff("unresolved", None, "no_track_in_zone", (), None)
    if len(candidates) > 1:
        return Handoff("uncertain", None, "multiple_tracks_in_zone", candidates, None)
    return Handoff("confirmed", candidates[0], None, candidates, first_in[candidates[0]])


class LinkFollower:
    """Keeps an identity on one track until the policy stops trusting it. A released identity is never re-attached."""

    def __init__(self, track_id: str, t0: float, policy: dict = POLICY):
        self.track_id = track_id
        self.policy = policy
        self.last_seen = t0
        self.crowd_since: float | None = None
        self.released_at: float | None = None
        self.reason: str | None = None

    @property
    def active(self) -> bool:
        return self.released_at is None

    def _release(self, t: float, reason: str) -> None:
        self.released_at, self.reason = t, reason

    def update(self, frame: Frame) -> bool:
        if not self.active:
            return False
        mine = frame.get(self.track_id)
        if frame.t - self.last_seen > self.policy["max_gap_s"]:
            self._release(self.last_seen, "track_lost")
            return False
        if mine is None:
            return True
        self.last_seen = frame.t
        crowded = any(iou(mine, b) > self.policy["crowd_iou"] for b in frame.boxes if b.track_id != self.track_id)
        if not crowded:
            self.crowd_since = None
        elif self.crowd_since is None:
            self.crowd_since = frame.t
        elif frame.t - self.crowd_since >= self.policy["crowd_s"]:
            # The identity is untrusted from the start of the overlap, not from when the rule fired.
            self._release(self.crowd_since, "crowding")
        return self.active


def follow_link(tracks: Tracks, track_id: str, t0: float, policy: dict = POLICY) -> tuple[float | None, str | None]:
    """Return (release time, reason) for an identity attached to `track_id` at `t0`, or (None, None) if it held."""
    follower = LinkFollower(track_id, t0, policy)
    for frame in tracks.frames:
        if frame.t >= t0 and not follower.update(frame):
            break
    if follower.active and tracks.duration_s - follower.last_seen > policy["max_gap_s"]:
        return follower.last_seen, "track_lost"
    return follower.released_at, follower.reason


def movement_windows(tracks: Tracks, track_id: str, window_s: float = WINDOW_S, sample_hz: float = SAMPLE_HZ) -> list[dict]:
    """Per-window movement of one track, in body diagonals per visible minute, with visibility and confidence.

    Displacement is normalised by the box diagonal so the score does not depend on distance to the camera.
    Windows without the track are omitted; partly visible windows report `visible_fraction` so callers can
    ignore unusable ones instead of reading low visibility as low movement.
    """
    step = 1.0 / sample_hz
    samples: list[tuple[float, Box]] = []
    next_t = -math.inf
    for frame in tracks.frames:
        box = frame.get(track_id)
        if box is not None and frame.t >= next_t:
            samples.append((frame.t, box))
            next_t = frame.t + step * 0.999
    windows: dict[int, list[tuple[float, Box]]] = {}
    for t, box in samples:
        windows.setdefault(int(t // window_s), []).append((t, box))
    out = []
    for k, rows in sorted(windows.items()):
        moved = 0.0
        for (t0, a), (t1, b) in zip(rows, rows[1:]):
            if t1 - t0 <= 1.5 * step:
                (ax, ay), (bx, by) = a.center, b.center
                moved += math.hypot(bx - ax, by - ay) / max((a.diagonal + b.diagonal) / 2, 1.0)
        visible_s = len(rows) * step
        out.append({"start_s": k * window_s, "end_s": (k + 1) * window_s,
                    "visible_fraction": round(min(visible_s / window_s, 1.0), 4),
                    "movement_score": round(moved / (visible_s / 60.0), 4),
                    "mean_conf": round(sum(b.conf for _, b in rows) / len(rows), 4)})
    return out
