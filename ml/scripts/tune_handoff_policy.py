"""Tune the identity continuity policy in services/api/domain/tracks.py on real barn footage (8-Calves).

Uses the cached tracker output of eval_tracking_8calves.py (fine-tuned detector + BoT-SORT re-ID). Identities are
locked to tracks at the start of a segment, as a scan-zone handoff would do, then followed with `LinkFollower`.
Each labelled calf box afterwards is correct, wrong, uncertain (no identity), or not detected.

The video is cut into two five-minute segments with fresh locks at the start of each. The first segment has no
identity swap, so it cannot separate safe from unsafe policies on its own; selection therefore uses both segments
and there is no held-out estimate. The rule is safety first: the policy whose worse segment has the fewest wrong
identities, then the one whose worse segment keeps the most correct identities.

usage: python scripts/tune_handoff_policy.py [--model calf_detector_v1] [--tracker botsort_reid]
"""

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain.tracks import POLICY, Box, Frame, LinkFollower  # noqa: E402
from eval_tracking_8calves import MATCH_IOU, RUNS, iou_matrix, load_ground_truth  # noqa: E402

FPS = 20
SEGMENTS = {"minutes_0_5": (0, 6000), "minutes_5_10": (6000, 12000)}
GRID = {"max_gap_s": [0.5, 1.0, 2.0, 5.0], "crowd_iou": [0.3, 0.4, 0.5, 0.6, 0.7],
        "crowd_s": [0.25, 0.5, 0.75, 1.0, 2.0, 1e9]}


def to_frames(pred: dict) -> dict[int, Frame]:
    return {fid: Frame(fid / FPS, tuple(Box(str(int(t)), *map(float, b)) for t, b in zip(ids, boxes)))
            for fid, (ids, boxes) in pred.items()}


def score(gt: dict, pred: dict, frames: dict[int, Frame], start: int, end: int, policy: dict | None) -> dict:
    """policy=None keeps every lock forever (naive)."""
    gid0, gb0 = gt[start]
    pid0, pb0 = pred[start]
    ious = iou_matrix(gb0, pb0)
    locks: dict[str, int] = {}
    followers: dict[str, LinkFollower] = {}
    for i, calf in enumerate(gid0):
        j = int(np.argmax(ious[i])) if ious.shape[1] else -1
        if j >= 0 and ious[i, j] >= MATCH_IOU:
            track = str(int(pid0[j]))
            locks[track] = int(calf)
            if policy is not None:
                followers[track] = LinkFollower(track, start / FPS, policy)
    counts = dict.fromkeys(("correct", "wrong", "uncertain", "not_detected"), 0)
    for fid in range(start + 1, end):
        if fid not in gt:
            continue
        frame = frames.get(fid, Frame(fid / FPS, ()))
        for track, follower in followers.items():
            if track in locks and not follower.update(frame):
                locks.pop(track)
        gid, gb = gt[fid]
        pid, pb = pred.get(fid, (np.zeros(0, int), np.zeros((0, 4))))
        m = iou_matrix(gb, pb)
        for i, calf in enumerate(gid):
            j = int(np.argmax(m[i])) if m.shape[1] else -1
            if j < 0 or m[i, j] < MATCH_IOU:
                counts["not_detected"] += 1
                continue
            assigned = locks.get(str(int(pid[j])))
            counts["uncertain" if assigned is None else "correct" if assigned == calf else "wrong"] += 1
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="calf_detector_v1")
    ap.add_argument("--tracker", default="botsort_reid")
    args = ap.parse_args()
    pred = np.load(RUNS / f"{args.tracker}_{args.model}_12000.npz", allow_pickle=True)["tracks"].item()
    frames = to_frames(pred)
    gt = load_ground_truth(12000, 800, 600)

    def both(policy):
        return {name: score(gt, pred, frames, *span, policy) for name, span in SEGMENTS.items()}

    rows = []
    for values in itertools.product(*GRID.values()):
        segs = both({**POLICY, **dict(zip(GRID, values))})
        rows.append({**dict(zip(GRID, values)), "worst_wrong": max(r["wrong"] for r in segs.values()),
                     "worst_correct": min(r["correct"] for r in segs.values()), "segments": segs})
    rows.sort(key=lambda r: (round(r["worst_wrong"], 4), -r["worst_correct"]))
    best = {k: rows[0][k] for k in GRID}
    report = {
        "tracker": args.tracker, "model": args.model, "segments_frames": SEGMENTS, "grid": GRID,
        "selection": "min worst-segment wrong (4 dp), then max worst-segment correct; selected on all 10 minutes",
        "chosen": best, "top10": rows[:10],
        "results": {
            "naive": both(None),
            "chosen_policy": both({**POLICY, **best}),
            "previous_policy_v1": both({**POLICY, "max_gap_s": 0.5, "crowd_iou": 0.3, "crowd_s": 0.0}),
        },
    }
    out = ROOT / "ml/results/handoff_policy.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps({"chosen": best, "results": report["results"]}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
