"""Build the simulated camera replay scenarios (plan Section 3: `demo/scenarios/*.json`).

Run from the repo root: `python demo/scenarios/build_scenarios.py`. Output is deterministic (seeded random) and
committed, so the replay, the movement rule, and the frontend overlay all read the same tracks. Every scenario is
labeled `source: "simulated"`: `healthy`, `anomaly`, `lost_identity`, and `crowded_scan` are synthetic tracks, and
`veo_barn` is a real tracker's output on AI-generated (Google Veo) footage, never a real farm.

Identity starts from a scan-zone handoff (`events: [{"type": "zone_scan", ...}]`, a camera event) or a muzzle match on
the track itself (a track event); see services/api/domain/association.py.

Movement model: a centroid walks with a smoothly drifting heading and short grazing pauses, bouncing off the frame
edges; a stationary animal keeps only a small positional jitter. Bounding boxes are normalized `[x, y, w, h]` and
always stay inside the frame. Frames are sampled at `fps`; windows of `window_s` align to scenario time 0.
"""

import json
import math
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
VEO_DIR = OUT_DIR.parent / "media" / "veo"
DURATION_S = 180
CROWDED_S = 90
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


def _zone_scan(t: float, animal_id: str | None, inliers: int | None, quality: float | None) -> dict:
    """A muzzle scan made in the camera's scan zone (a camera event, not a track's): the replay hands the identity to
    the one track inside the zone at `t`, or to none (demo/fixtures/herd.json carries cam-pen-a's zone)."""
    return {"t": t, "type": "zone_scan", "animal_id": animal_id, "inliers": inliers, "quality": quality}


# cam-pen-a's scan zone (demo/fixtures/herd.json), calibrated by the ML teammate on the Veo CCTV footage.
ZONE = ((0.4781, 0.6611), (0.7021, 0.8463))  # top-left, bottom-right
ZONE_CENTRE = ((ZONE[0][0] + ZONE[1][0]) / 2, (ZONE[0][1] + ZONE[1][1]) / 2)


def _scenario(scenario_id: str, label: str, description: str, camera_id: str, tracks: list[dict],
              events: list[dict] | None = None, duration_s: float = DURATION_S) -> dict:
    return {"id": scenario_id, "label": label, "description": description, "camera_id": camera_id,
            "source": "simulated", "duration_s": duration_s, "fps": FPS, "window_s": WINDOW_S, "clip": None,
            "events": events or [], "tracks": tracks}


def _steady(t: float) -> float:
    return 1.0


def _clear(t: float) -> float:
    return 0.88


SARI_SCAN = _zone_scan(3, "animal-demo-001", 31, 0.88)  # Sari, alone in the scan zone at 3 s


def healthy() -> dict:
    rng = random.Random(1001)
    sari = Walker(rng, ZONE_CENTRE[0], ZONE_CENTRE[1], 0.22, 0.17, -2.4)  # starts in the scan zone, walks out
    bima = Walker(rng, 0.68, 0.45, 0.24, 0.18, 2.6)
    return _scenario(
        "healthy", "Healthy herd · Pen A",
        "Sari is scanned alone in the scan zone at 3 s, so her identity passes to her camera track; Bima is "
        "identified by a muzzle match at 9 s. Both keep moving normally. No alert is expected.", "cam-pen-a",
        [{"track_key": "t-01", "frames": _frames(sari, 0, DURATION_S, _steady, _clear), "events": []},
         {"track_key": "t-02", "frames": _frames(bima, 0, DURATION_S, _steady, _clear),
          "events": [_match(9, "animal-demo-002", 31, 0.9)]}],
        events=[SARI_SCAN])


def anomaly() -> dict:
    rng = random.Random(2002)
    sari = Walker(rng, ZONE_CENTRE[0], ZONE_CENTRE[1], 0.22, 0.17, -2.6)
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
        "Sari is identified alone in the scan zone at 3 s and moves normally for the first minute, then her tracked "
        "movement drops by more than 70% from 90 s while she stays clearly visible. One reduced-movement alert is "
        "expected.", "cam-pen-a",
        [{"track_key": "t-01", "frames": _frames(sari, 0, DURATION_S, slowing, _clear), "events": []},
         {"track_key": "t-02", "frames": _frames(bima, 0, DURATION_S, _steady, _clear),
          "events": [_match(9, "animal-demo-002", 31, 0.9)]}],
        events=[SARI_SCAN])


def crowded_scan() -> dict:
    """Two cows stand in the scan zone when Sari's muzzle is scanned: nobody can say which track is Sari."""
    rng = random.Random(4004)
    sari = Walker(rng, ZONE_CENTRE[0] - 0.05, ZONE_CENTRE[1] - 0.03, 0.2, 0.15, -2.5)
    other = Walker(rng, ZONE_CENTRE[0] + 0.06, ZONE_CENTRE[1] + 0.04, 0.2, 0.15, -0.6)
    return _scenario(
        "crowded_scan", "Crowded scan · Pen A",
        "Sari's muzzle is scanned at 3 s while a second cow stands in the scan zone with her. With two animals in the "
        "zone the camera cannot tell which track is Sari, so neither track is identified: both are uncertain and "
        "no animal-specific alert can follow. Scan one animal at a time.", "cam-pen-a",
        [{"track_key": "t-21", "frames": _frames(sari, 0, CROWDED_S, _steady, _clear), "events": []},
         {"track_key": "t-22", "frames": _frames(other, 0, CROWDED_S, _steady, _clear), "events": []}],
        events=[SARI_SCAN], duration_s=CROWDED_S)


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


VEO_CLIP = "/api/v1/demo/footage/video_cctv.mp4"
VEO_LABEL = "AI-generated footage (Veo) — not a real farm"
VEO_SCAN_S = 4.0  # the muzzle scan in the phone video (VEO_PROMPTS.md: scan time ~4 s on the shared timeline)


def veo_barn() -> dict:
    """The ML teammate's real tracker run (`demo/media/veo/out/tracks.json`, yolov8x + BoT-SORT re-ID) on the
    AI-generated CCTV clip, converted to the scenario format with its timing kept: pixel xyxy boxes become normalized
    xywh, and the detector confidence stands in for visibility.

    Identity is never invented. The heifer scanned in the zone at ~4 s was enrolled on the teammate's own backend
    from `video_hp.mp4` (run_report.json: a new animal, empty gallery); she is not one of this farm's animals, so the
    scan names no registered animal and every track stays unassigned. The scan still shows the zone rule: track 11
    is the only animal in the zone at that moment."""
    tracks_data = json.loads((VEO_DIR / "out" / "tracks.json").read_text(encoding="utf-8"))
    report = json.loads((VEO_DIR / "out" / "run_report.json").read_text(encoding="utf-8"))
    assert [tuple(p) for p in report["zone"][::2]] == list(ZONE), "the Veo run's zone must be cam-pen-a's zone"
    width, height = tracks_data["width"], tracks_data["height"]
    frames: dict[str, list[dict]] = {}
    for t, boxes in tracks_data["frames"]:
        for track_id, x0, y0, x1, y1, conf in boxes:
            x0, x1 = max(0.0, x0 / width), min(1.0, x1 / width)
            y0, y1 = max(0.0, y0 / height), min(1.0, y1 / height)
            frames.setdefault(track_id, []).append(
                {"t": round(t, 3), "bbox": [_round(x0), _round(y0), _round(x1 - x0), _round(y1 - y0)],
                 "visibility": _round(conf)})
    last_t = tracks_data["frames"][-1][0]
    sample_hz = round((len(tracks_data["frames"]) - 1) / last_t, 2)
    linked = {link["track_id"] for link in report["recording"]["links"] if link["status"] == "confirmed"}
    assert linked == {"11"}, "the teammate's run linked its scan to track 11"
    return {
        "id": "veo_barn", "label": "Veo barn · AI-generated CCTV",
        "description": "A real tracker run on AI-generated CCTV footage: twelve heifers, one of them alone in the scan "
                       "zone when her muzzle is scanned at 4 s. She was enrolled on another system, not on this farm, "
                       "so the scan names no registered animal and no track is identified. Nothing here is a real "
                       "farm.",
        "camera_id": "cam-pen-a", "source": "simulated", "duration_s": math.ceil(last_t), "fps": sample_hz,
        "window_s": WINDOW_S, "clip": VEO_CLIP,
        "footage": {"label": VEO_LABEL, "generator": "Google Veo", "kind": "ai_generated",
                    "tracker": tracks_data["method_version"], "tracks": "demo/media/veo/out/tracks.json",
                    "prompts": "demo/media/veo/VEO_PROMPTS.md"},
        "events": [_zone_scan(VEO_SCAN_S, None, None, None)],
        "tracks": [{"track_key": f"veo-{track_id}", "frames": frames[track_id], "events": []}
                   for track_id in sorted(frames, key=int)],
    }


SCENARIOS = (healthy, anomaly, lost_identity, crowded_scan, veo_barn)


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
