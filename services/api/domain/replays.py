"""Deterministic camera replay scenarios for the demo (PRD M07, M08, Section 7 seed data).

Each scenario generates tracks in the `domain.tracks` wire format at 1 Hz, plus the times at which each animal is
scanned in the scan zone. Animals walk out of the scan zone to their own area of the pen, then alternate between
resting and short walking bouts. An anomaly lowers one animal's chance of starting a bout and its walking speed
from a given time. Everything produced here is labelled `simulated`.
"""

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

WIDTH, HEIGHT = 800, 600
BOX_W, BOX_H = 110, 70
PEN = (200, 30, 790, 570)
START_WALK, STOP_WALK = 0.03, 0.25
WALK_PX_S, TRANSFER_PX_S = 25.0, 40.0
JITTER_PX = 1.0
SCAN_SPACING_S, ZONE_HOLD_S, SCAN_OFFSET_S = 30.0, 8.0, 4.0
INTRUDER_ID = "99"


@dataclass(frozen=True)
class Replay:
    name: str
    label: str
    tracks: dict
    # (track index, scan time in seconds) for each animal the scenario hands over through the scan zone.
    scans: list[tuple[int, float]]


def load_fixture(fixtures_root: Path) -> dict:
    return json.loads((fixtures_root / "replays.json").read_text())


def _zone_center(polygon: list[list[float]]) -> tuple[float, float]:
    return (sum(x for x, _ in polygon) / len(polygon) * WIDTH, sum(y for _, y in polygon) / len(polygon) * HEIGHT)


def _cells(n: int) -> list[tuple[float, float, float, float]]:
    cols = math.ceil(math.sqrt(n * (PEN[2] - PEN[0]) / (PEN[3] - PEN[1])))
    rows = math.ceil(n / cols)
    w, h = (PEN[2] - PEN[0]) / cols, (PEN[3] - PEN[1]) / rows
    return [(PEN[0] + (i % cols) * w, PEN[1] + (i // cols) * h, PEN[0] + (i % cols + 1) * w, PEN[1] + (i // cols + 1) * h)
            for i in range(n)]


def _box(track_id: str, cx: float, cy: float) -> list:
    return [track_id, round(cx - BOX_W / 2, 1), round(cy - BOX_H / 2, 1), round(cx + BOX_W / 2, 1),
            round(cy + BOX_H / 2, 1), 0.9]


def _path(rng: random.Random, duration: int, appear: float, zone: tuple[float, float],
          cell: tuple[float, float, float, float], anomaly: dict | None) -> dict[int, tuple[float, float]]:
    lo_x, lo_y = cell[0] + BOX_W / 2, cell[1] + BOX_H / 2
    hi_x, hi_y = cell[2] - BOX_W / 2, cell[3] - BOX_H / 2
    home = ((lo_x + hi_x) / 2, (lo_y + hi_y) / 2)
    x, y = zone
    walking, heading = False, 0.0
    out = {}
    for t in range(int(appear), duration + 1):
        if t < appear + ZONE_HOLD_S:
            out[t] = (zone[0] + rng.uniform(-JITTER_PX, JITTER_PX), zone[1] + rng.uniform(-JITTER_PX, JITTER_PX))
            continue
        if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
            dx, dy = home[0] - x, home[1] - y
            d = math.hypot(dx, dy)
            step = min(TRANSFER_PX_S, d)
            x, y = x + dx / d * step, y + dy / d * step
            out[t] = (x, y)
            continue
        slow = anomaly is not None and t >= anomaly["from_s"]
        p_start = START_WALK * (anomaly["activity_factor"] if slow else 1.0)
        speed = WALK_PX_S * (anomaly["speed_factor"] if slow else 1.0)
        if walking and rng.random() < STOP_WALK:
            walking = False
        elif not walking and rng.random() < p_start:
            walking, heading = True, rng.uniform(0, 2 * math.pi)
        if walking:
            nx, ny = x + math.cos(heading) * speed, y + math.sin(heading) * speed
            if not (lo_x <= nx <= hi_x and lo_y <= ny <= hi_y):
                heading += math.pi
                nx, ny = min(max(nx, lo_x), hi_x), min(max(ny, lo_y), hi_y)
            x, y = nx, ny
        out[t] = (x + rng.uniform(-JITTER_PX, JITTER_PX), y + rng.uniform(-JITTER_PX, JITTER_PX))
    return out


def generate(name: str, fixture: dict) -> Replay:
    scenario = fixture["scenarios"].get(name)
    if scenario is None:
        raise KeyError(name)
    rng = random.Random(scenario["seed"])
    duration, n = int(scenario["duration_s"]), int(scenario["tracks"])
    zone = _zone_center(fixture["scan_zone"]["polygon"])
    anomaly = scenario.get("anomaly")
    paths, scans = {}, []
    for i, cell in enumerate(_cells(n)):
        appear = 5.0 + SCAN_SPACING_S * i
        paths[str(i + 1)] = _path(rng, duration, appear, zone, cell,
                                  anomaly if anomaly and anomaly["track"] == i else None)
        scans.append((i, appear + SCAN_OFFSET_S))
    if scenario.get("crowded_scan"):
        # A second, unscanned animal shares the scan zone with the first animal, then leaves the view.
        paths[INTRUDER_ID] = {t: (zone[0] + 25, zone[1] - 10) for t in range(5, 5 + int(ZONE_HOLD_S) + 4)}
    frames = [[float(t), [_box(tid, *path[t]) for tid, path in paths.items() if t in path]] for t in range(duration + 1)]
    tracks = {"width": WIDTH, "height": HEIGHT, "fps": 1.0, "source": "simulated", "method_version": f"replay:{name}",
              "frames": frames}
    return Replay(name, scenario["label"], tracks, scans)
