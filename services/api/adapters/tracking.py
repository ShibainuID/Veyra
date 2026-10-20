"""Barn camera tracking adapter: fine-tuned calf detector + BoT-SORT with re-ID (ml/results/tracking_8calves.md).

The tracker runs on every frame so BoT-SORT keeps its motion and appearance state, but boxes are emitted at
`EMIT_HZ` to keep the tracks file small; `domain.tracks` samples movement at 1 Hz anyway.
"""

import tempfile
from pathlib import Path

import cv2
import yaml

EMIT_HZ = 5.0
CONF = 0.25
IMG_SIZE = 800
# COCO animal classes (cat..giraffe). With a COCO detector only these are kept, so people are never tracked.
COCO_ANIMALS = list(range(15, 24))


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _tracker_config(directory: Path) -> str:
    import ultralytics

    cfg = yaml.safe_load((Path(ultralytics.__file__).parent / "cfg/trackers/botsort.yaml").read_text())
    cfg.update(with_reid=True, model="auto")
    path = directory / "botsort_reid.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return str(path)


def track_video(video_path: Path, weights: str, emit_hz: float = EMIT_HZ) -> dict:
    from ultralytics import YOLO

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if width == 0 or height == 0:
        raise ValueError("video could not be read")
    every = max(1, round(fps / emit_hz))
    model = YOLO(weights)
    # The fine-tuned detector has one class (calf); a COCO detector is restricted to animals.
    classes = COCO_ANIMALS if len(model.names) > 1 else None
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        stream = model.track(source=str(video_path), tracker=_tracker_config(Path(tmp)), conf=CONF, imgsz=IMG_SIZE,
                             classes=classes, persist=True, stream=True, verbose=False, device=_device())
        for i, r in enumerate(stream):
            if i % every:
                continue
            boxes = []
            if r.boxes.id is not None:
                for tid, xyxy, conf in zip(r.boxes.id.int().tolist(), r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
                    boxes.append([str(tid), *(round(v, 1) for v in xyxy), round(conf, 3)])
            frames.append([round(i / fps, 3), boxes])
    return {"width": width, "height": height, "fps": fps, "source": "prototype",
            "method_version": f"{Path(weights).stem}+botsort_reid", "frames": frames}


def extract_clip(video_path: Path, out_path: Path, start_s: float, end_s: float, track_id: str, tracks: dict) -> bool:
    """Write [start_s, end_s] as MP4, drawing the animal's box from the nearest emitted tracks frame."""
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
    boxes = {round(t, 1): b for t, frame in tracks["frames"] for b in frame if b[0] == track_id}
    times = sorted(boxes)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    written = 0
    t = start_s
    while t <= end_s:
        ok, image = cap.read()
        if not ok:
            break
        if times:
            nearest = min(times, key=lambda x: abs(x - t))
            if abs(nearest - t) <= 1.0:
                _, x0, y0, x1, y1, *_ = boxes[nearest]
                cv2.rectangle(image, (int(x0), int(y0)), (int(x1), int(y1)), (0, 200, 255), 2)
                cv2.putText(image, f"track {track_id}", (int(x0), max(int(y0) - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 200, 255), 1)
        writer.write(image)
        written += 1
        t += 1.0 / fps
    writer.release()
    cap.release()
    if not written:
        out_path.unlink(missing_ok=True)
    return written > 0
