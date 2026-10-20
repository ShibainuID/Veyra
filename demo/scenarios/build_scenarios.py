"""Build the simulated camera replay scenarios (plan Section 3: `demo/scenarios/*.json`).

Run from the repo root: `python demo/scenarios/build_scenarios.py`. Output is deterministic (seeded random) and
committed, so the replay, the movement rule, and the frontend overlay all read the same tracks. Every scenario is
labeled `source: "simulated"`: these are synthetic tracks, not detections from real footage.

Movement model: a centroid walks with a smoothly drifting heading and short grazing pauses, bouncing off the frame
edges; a stationary animal keeps only a small positional jitter. Bounding boxes are normalized `[x, y, w, h]` and
always stay inside the frame. Frames are sampled at `fps`; windows of `window_s` align to scenario time 0.
"""

import json
import math
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
DURATION_S = 180
FPS = 2
WINDOW_S = 30
WALK_SPEED = 0.014  # normalized frame units per second
MARGIN = 0.02


def _round(value: float) -> float:
    return round(value, 4)


class Walker:
    """One animal's centroid. `speed_scale(t)` scales walking speed (1 = normal, ~0 = stationary)."""

    def __init__(self, rng: random.Random, x: float, y: float, w: float, h: float, heading: float) -> None:
        self.rng, self.x, self.y, self.w, self.h, self.heading = rng, x, y, w, h, heading
        self.pause_until = -1.0
        self.next_pause = rng.uniform(10, 16)

    def step(self, t: float, dt: float, speed_scale: float, jitter: float = 0.0006) -> list[float]:
        rng = self.rng
        if t >= self.next_pause and speed_scale > 0.3:
            self.pause_until = t + rng.uniform(3, 5)
            self.next_pause = self.pause_until + rng.uniform(12, 18)
        grazing = t < self.pause_until
        speed = WALK_SPEED * speed_scale * (0.12 if grazing else rng.uniform(0.85, 1.15))
        self.heading += rng.gauss(0, 0.18)
        nx = self.x + math.cos(self.heading) * speed * dt
        ny = self.y + math.sin(self.heading) * speed * dt * 0.6  # perspective: less vertical travel
        half_w, half_h = self.w / 2 + MARGIN, self.h / 2 + MARGIN
        if not half_w <= nx <= 1 - half_w:
            self.heading = math.pi - self.heading
            nx = min(max(nx, half_w), 1 - half_w)
        if not half_h <= ny <= 1 - half_h:
            self.heading = -self.heading
            ny = min(max(ny, half_h), 1 - half_h)
        self.x, self.y = nx, ny
        cx = min(max(nx + rng.gauss(0, jitter), half_w), 1 - half_w)
        cy = min(max(ny + rng.gauss(0, jitter), half_h), 1 - half_h)
        return [_round(cx - self.w / 2), _round(cy - self.h / 2), _round(self.w), _round(self.h)]


def _times(start: float, end: float) -> list[float]:
    first, last = round(start * FPS), round(end * FPS)
    return [i / FPS for i in range(first, last)]


def _frames(walker: Walker, start: float, end: float, speed_scale, visibility) -> list[dict]:
    frames = []
    for t in _times(start, end):
        bbox = walker.step(t, 1 / FPS, speed_scale(t))
        vis = min(1.0, max(0.0, visibility(t) + walker.rng.uniform(-0.03, 0.03)))
        frames.append({"t": t, "bbox": bbox, "visibility": _round(vis)})
    return frames


def _match(t: float, animal_id: str, inliers: int, quality: float) -> dict:
    return {"t": t, "type": "muzzle_match", "candidate_animal_id": animal_id, "inliers": inliers, "quality": quality}


def _scenario(scenario_id: str, label: str, description: str, camera_id: str, tracks: list[dict]) -> dict:
    return {"id": scenario_id, "label": label, "description": description, "camera_id": camera_id,
            "source": "simulated", "duration_s": DURATION_S, "fps": FPS, "window_s": WINDOW_S, "clip": None,
            "tracks": tracks}


def _steady(t: float) -> float:
    return 1.0


def _clear(t: float) -> float:
    return 0.88


def healthy() -> dict:
    rng = random.Random(1001)
    sari = Walker(rng, 0.30, 0.55, 0.22, 0.17, 0.3)
    bima = Walker(rng, 0.68, 0.45, 0.24, 0.18, 2.6)
    return _scenario(
        "healthy", "Healthy herd · Pen A",
        "Sari and Bima are identified by muzzle and keep moving normally. No alert is expected.", "cam-pen-a",
        [{"track_key": "t-01", "frames": _frames(sari, 0, DURATION_S, _steady, _clear),
          "events": [_match(4, "animal-demo-001", 23, 0.86)]},
         {"track_key": "t-02", "frames": _frames(bima, 0, DURATION_S, _steady, _clear),
          "events": [_match(9, "animal-demo-002", 31, 0.9)]}])


def anomaly() -> dict:
    rng = random.Random(2002)
    sari = Walker(rng, 0.32, 0.52, 0.22, 0.17, 0.1)
    bima = Walker(rng, 0.70, 0.48, 0.24, 0.18, 3.0)

    def slowing(t: float) -> float:
        if t < 60:
            return 1.0
        if t < 85:
            return 0.75
        if t < 90:
            return 0.75 - (t - 85) * 0.14
        return 0.02

    return _scenario(
        "anomaly", "Reduced movement · Pen A",
        "Sari moves normally for the first minute, then her tracked movement drops by more than 70% from 90 s while "
        "she stays clearly visible. One reduced-movement alert is expected.", "cam-pen-a",
        [{"track_key": "t-01", "frames": _frames(sari, 0, DURATION_S, slowing, _clear),
          "events": [_match(4, "animal-demo-001", 23, 0.86)]},
         {"track_key": "t-02", "frames": _frames(bima, 0, DURATION_S, _steady, _clear),
          "events": [_match(9, "animal-demo-002", 31, 0.9)]}])


def lost_identity() -> dict:
    rng = random.Random(3003)
    bima = Walker(rng, 0.40, 0.50, 0.24, 0.18, 0.4)

    def occluding(t: float) -> float:
        return 0.88 if t < 64 else max(0.5, 0.88 - (t - 64) * 0.07)

    bima_frames = _frames(bima, 0, 70, _steady, occluding)
    stranger = Walker(rng, bima.x, bima.y, 0.24, 0.18, bima.heading)

    def obscured(t: float) -> float:
        return 0.45 if t < 120 else 0.82

    return _scenario(
        "lost_identity", "Lost identity · Pen B",
        "Bima is identified at 5 s and lost behind the trough at 70 s. A new track appears at 75 s with no muzzle "
        "match: it stays unassigned, and its low-visibility window raises an observation-quality warning on the "
        "track, never on an animal.", "cam-pen-b",
        [{"track_key": "t-03", "frames": bima_frames,
          "events": [_match(5, "animal-demo-002", 28, 0.88), {"t": 70, "type": "track_lost", "reason": "occlusion"}]},
         {"track_key": "t-14", "frames": _frames(stranger, 75, DURATION_S, _steady, obscured), "events": []}])


SCENARIOS = (healthy, anomaly, lost_identity)


def _dumps(scenario: dict) -> str:
    """Readable and diff-friendly: one frame or event per line."""
    compact = {"separators": (", ", ": ")}
    head = {k: v for k, v in scenario.items() if k != "tracks"}
    lines = ["{"] + [f"  {json.dumps(k)}: {json.dumps(v, **compact)}," for k, v in head.items()] + ['  "tracks": [']
    for i, track in enumerate(scenario["tracks"]):
        lines.append(f'    {{"track_key": {json.dumps(track["track_key"])}, "frames": [')
        lines += [f"      {json.dumps(f, **compact)}," for f in track["frames"]]
        lines[-1] = lines[-1].rstrip(",")
        lines.append("    ], \"events\": [")
        lines += [f"      {json.dumps(e, **compact)}," for e in track["events"]]
        if track["events"]:
            lines[-1] = lines[-1].rstrip(",")
        lines.append("    ]}" + ("," if i < len(scenario["tracks"]) - 1 else ""))
    lines += ["  ]", "}"]
    text = "\n".join(lines) + "\n"
    assert json.loads(text) == scenario
    return text


def main() -> None:
    for build in SCENARIOS:
        scenario = build()
        path = OUT_DIR / f"{scenario['id']}.json"
        path.write_text(_dumps(scenario), encoding="utf-8", newline="\n")
        print(f"wrote {path.name}: {sum(len(t['frames']) for t in scenario['tracks'])} frames")


if __name__ == "__main__":
    main()
