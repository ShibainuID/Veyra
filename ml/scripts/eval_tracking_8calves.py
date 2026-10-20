"""Tracking and identity-handoff evaluation on 8-Calves (real barn CCTV, identities per frame).

A2  detection: zero-shot COCO YOLO (animal classes) against the ground-truth boxes.
A3  tracking: ByteTrack, BoT-SORT, and BoT-SORT with re-ID; MOTA, IDF1, ID switches.
A4  handoff policy: identities are locked to tracks at the first frame (as the scan zone would do),
    then every later ground-truth box is counted as correct, wrong, or uncertain under two rules:
      naive   - an identity follows its track number forever;
      policy  - an identity is dropped when its track disappears for more than GAP frames or its box
                overlaps another detection above OVERLAP IoU (PRD: no confident identity through a switch).

usage: python scripts/eval_tracking_8calves.py [--frames 12000] [--model yolov8m.pt]
"""

import argparse
import json
import time
from pathlib import Path

import motmetrics as mm
import numpy as np
import pandas as pd
import yaml
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml/data/raw/eight_calves/extracted"
RESULTS = ROOT / "ml/results"
RUNS = ROOT / "ml/runs/tracking_8calves"
COCO_ANIMALS = list(range(15, 24))
MATCH_IOU = 0.5
GAP = 10
OVERLAP = 0.3
DEVICE = "mps" if __import__("torch").backends.mps.is_available() else ("cuda" if __import__("torch").cuda.is_available() else "cpu")


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU between xyxy boxes a (n,4) and b (m,4)."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x0 = np.maximum(a[:, None, 0], b[None, :, 0])
    y0 = np.maximum(a[:, None, 1], b[None, :, 1])
    x1 = np.minimum(a[:, None, 2], b[None, :, 2])
    y1 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    area = lambda r: (r[:, 2] - r[:, 0]) * (r[:, 3] - r[:, 1])  # noqa: E731
    return inter / (area(a)[:, None] + area(b)[None, :] - inter + 1e-9)


def load_ground_truth(frames: int, width: int, height: int) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    # frame_id starts at 1; tracker frames start at 0.
    df = pd.read_pickle(next(DATA.rglob("*.pkl")))
    df = df.assign(frame_id=df["frame_id"] - 1)
    df = df[df["frame_id"] < frames]
    gt = {}
    for fid, g in df.groupby("frame_id"):
        cx, cy, w, h = (g[c].to_numpy(float) for c in ("x", "y", "w", "h"))
        boxes = np.stack([(cx - w / 2) * width, (cy - h / 2) * height, (cx + w / 2) * width, (cy + h / 2) * height], 1)
        gt[int(fid)] = (g["tracklet_id"].to_numpy(int), boxes)
    return gt


def tracker_config(name: str) -> str:
    if name != "botsort_reid":
        return f"{name}.yaml"
    import ultralytics

    cfg = yaml.safe_load((Path(ultralytics.__file__).parent / "cfg/trackers/botsort.yaml").read_text())
    cfg.update(with_reid=True, model="auto")
    path = RUNS / "botsort_reid.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return str(path)


def run_tracker(video: Path, model_name: str, tracker: str, frames: int) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    cache = RUNS / f"{tracker}_{Path(model_name).stem}_{frames}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return z["tracks"].item()
    model = YOLO(model_name)
    # COCO weights: keep the animal classes; a fine-tuned single-class detector keeps everything.
    classes = COCO_ANIMALS if len(model.names) > 1 else None
    out, t0 = {}, time.time()
    for fid, r in enumerate(model.track(source=str(video), tracker=tracker_config(tracker), classes=classes,
                                        conf=0.25, persist=True, stream=True, verbose=False,
                                        device=DEVICE)):
        if fid >= frames:
            break
        if r.boxes.id is None:
            out[fid] = (np.zeros(0, int), np.zeros((0, 4)))
        else:
            out[fid] = (r.boxes.id.cpu().numpy().astype(int), r.boxes.xyxy.cpu().numpy())
        if fid % 2000 == 0:
            print(f"  {tracker}: frame {fid} ({time.time() - t0:.0f}s)", flush=True)
    np.savez(cache, tracks=np.array(out, dtype=object))
    return out


def detection_metrics(gt, pred) -> dict:
    tp = fp = fn = 0
    for fid, (_, gb) in gt.items():
        pb = pred.get(fid, (None, np.zeros((0, 4))))[1]
        m = iou_matrix(gb, pb) >= MATCH_IOU
        matched_gt = matched_pred = 0
        used = set()
        for i in range(len(gb)):
            j = next((j for j in np.argsort(-iou_matrix(gb[i:i + 1], pb)[0]) if m[i, j] and j not in used), None)
            if j is not None:
                used.add(j)
                matched_gt += 1
        matched_pred = len(used)
        tp += matched_gt
        fn += len(gb) - matched_gt
        fp += len(pb) - matched_pred
    return {"precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1)}


def mot_metrics(gt, pred) -> dict:
    acc = mm.MOTAccumulator(auto_id=True)
    for fid in sorted(gt):
        gid, gb = gt[fid]
        pid, pb = pred.get(fid, (np.zeros(0, int), np.zeros((0, 4))))
        dist = 1 - iou_matrix(gb, pb)
        dist[dist > 1 - MATCH_IOU] = np.nan
        acc.update(gid.tolist(), pid.tolist(), dist)
    s = mm.metrics.create().compute(acc, metrics=["mota", "idf1", "num_switches", "num_fragmentations", "mostly_tracked"])
    return {k: float(v) for k, v in s.iloc[0].items()}


def handoff(gt, pred, policy: bool) -> dict:
    """Lock identities at the first frame, then score every later ground-truth box."""
    first = min(gt)
    gid0, gb0 = gt[first]
    pid0, pb0 = pred[first]
    locks: dict[int, int] = {}
    ious = iou_matrix(gb0, pb0)
    for i, calf in enumerate(gid0):
        j = int(np.argmax(ious[i])) if ious.shape[1] else -1
        if j >= 0 and ious[i, j] >= MATCH_IOU:
            locks[int(pid0[j])] = int(calf)
    last_seen = {t: first for t in locks}
    counts = {"correct": 0, "wrong": 0, "uncertain": 0, "not_detected": 0}
    first_error: dict[int, int] = {}
    for fid in sorted(gt):
        if fid == first:
            continue
        pid, pb = pred.get(fid, (np.zeros(0, int), np.zeros((0, 4))))
        present = set(int(t) for t in pid)
        if policy:
            for t in list(locks):
                if t in present and fid - last_seen[t] > GAP:
                    locks.pop(t)
            overlap = iou_matrix(pb, pb)
            np.fill_diagonal(overlap, 0)
            for k, t in enumerate(pid):
                if int(t) in locks and overlap.shape[0] and overlap[k].max() > OVERLAP:
                    locks.pop(int(t))
        for t in present:
            last_seen[t] = fid
        gid, gb = gt[fid]
        ious = iou_matrix(gb, pb)
        for i, calf in enumerate(gid):
            j = int(np.argmax(ious[i])) if ious.shape[1] else -1
            if j < 0 or ious[i, j] < MATCH_IOU:
                counts["not_detected"] += 1
                continue
            assigned = locks.get(int(pid[j]))
            if assigned is None:
                counts["uncertain"] += 1
            elif assigned == calf:
                counts["correct"] += 1
            else:
                counts["wrong"] += 1
                first_error.setdefault(int(calf), fid)
    total = sum(counts.values())
    seconds = {c: (f - first) / 20 for c, f in first_error.items()}
    return {**{k: v / total for k, v in counts.items()}, "locked_at_start": len(locks) if not policy else None,
            "median_seconds_to_first_wrong": float(np.median(list(seconds.values()))) if seconds else None,
            "calves_ever_wrong": len(seconds)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=12000)
    ap.add_argument("--model", default="yolov8m.pt")
    args = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    video = next(DATA.rglob("*.mp4"))
    import cv2

    cap = cv2.VideoCapture(str(video))
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    gt = load_ground_truth(args.frames, width, height)
    report = {"video": video.name, "frames": args.frames, "seconds": args.frames / 20, "model": args.model,
              "resolution": [width, height], "match_iou": MATCH_IOU, "policy": {"gap_frames": GAP, "overlap_iou": OVERLAP}}
    for tracker in ("bytetrack", "botsort", "botsort_reid"):
        print(f"running {tracker}", flush=True)
        pred = run_tracker(video, args.model, tracker, args.frames)
        report[tracker] = {"detection": detection_metrics(gt, pred), "mot": mot_metrics(gt, pred),
                           "handoff_naive": handoff(gt, pred, policy=False),
                           "handoff_policy": handoff(gt, pred, policy=True)}
        print(json.dumps(report[tracker], indent=1), flush=True)
    out = RESULTS / f"tracking_8calves_{Path(args.model).stem}_{args.frames}.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
