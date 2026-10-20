"""Enrollment video processing (PRD Section 4.1 steps 1-2, M02).

One continuous video should show the muzzle, the open mouth with teeth, and the whole body from the
side with the scale marker. The worker samples frames, labels each frame's view with CLIP zero-shot
prompts, checks the body view with a cow detector, looks for scene cuts, picks the best frame per
view, and writes a manifest. It reports evidence consistency only: a continuous capture does not prove
ownership, liveness, or absence of substitution.
"""

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import open_clip
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.weight import marker_px_per_cm  # noqa: E402

SAMPLE_FPS = 4.0
VIEW_PROMPTS = {
    "muzzle": "a close-up photo of a cow's nose and nostrils",
    "teeth": "a close-up photo of a cow's open mouth showing its teeth",
    "body": "a photo of a whole cow standing, seen from the side",
    "other": "a photo of a barn, the ground, the sky, or a blurry image",
}
# Side versus rear or front views is decided by the cow detector's box aspect ratio, not by prompts:
# rear-view prompts captured side views in testing.
REQUIRED_VIEWS = ("muzzle", "teeth", "body")
MIN_VIEW_PROB = 0.5
CUT_CORRELATION = 0.5
MIN_COW_CONF = 0.4
BODY_MIN_WIDTH = 0.4
BODY_MIN_ASPECT = 1.2
# The capture screen shows a muzzle guide box this wide, with the framing of the training crops
# (width/height ~1.18). Tight centre crops lost most of the embedding similarity in testing.
MUZZLE_GUIDE_WIDTH = 0.9
MUZZLE_GUIDE_ASPECT = 1.18
COCO_COW = 19


@dataclass
class Models:
    clip: torch.nn.Module
    preprocess: object
    text: torch.Tensor
    detector: object

    @classmethod
    def load(cls, detector) -> "Models":
        clip, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
        clip.eval()
        with torch.no_grad():
            text = clip.encode_text(open_clip.get_tokenizer("ViT-B-32")(list(VIEW_PROMPTS.values())))
        return cls(clip, preprocess, text / text.norm(dim=-1, keepdim=True), detector)


def sample_frames(video_path: Path, fps: float = SAMPLE_FPS) -> tuple[list[tuple[float, np.ndarray]], float]:
    cap = cv2.VideoCapture(str(video_path))
    native = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(native / fps))
    frames, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            frames.append((i / native, frame))
        i += 1
    cap.release()
    return frames, i / native


def sharpness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1]))), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def color_histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def view_probabilities(frames: list[np.ndarray], models: Models) -> np.ndarray:
    probs = []
    for s in range(0, len(frames), 32):
        x = torch.stack([models.preprocess(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))) for f in frames[s:s + 32]])
        with torch.no_grad():
            img = models.clip.encode_image(x)
        img = img / img.norm(dim=-1, keepdim=True)
        probs.append((100 * img @ models.text.T).softmax(-1).numpy())
    return np.concatenate(probs)


def cow_boxes(frame: np.ndarray, detector) -> list[dict]:
    r = detector.predict(frame, classes=[COCO_COW], conf=MIN_COW_CONF, verbose=False)[0]
    h, w = frame.shape[:2]
    out = []
    for (x0, y0, x1, y1), conf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
        out.append({"box": [float(x0), float(y0), float(x1), float(y1)], "conf": float(conf),
                    "inside_frame": bool(x0 > 2 and y0 > 2 and x1 < w - 3 and y1 < h - 3),
                    "width_frac": float((x1 - x0) / w), "aspect": float((x1 - x0) / max(y1 - y0, 1))})
    return out


def is_full_side_body(boxes: list[dict]) -> bool:
    big = [b for b in boxes if b["width_frac"] >= BODY_MIN_WIDTH]
    return len(big) == 1 and big[0]["inside_frame"] and big[0]["aspect"] >= BODY_MIN_ASPECT


def muzzle_crop(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    cw = int(MUZZLE_GUIDE_WIDTH * w)
    ch = min(h, int(cw / MUZZLE_GUIDE_ASPECT))
    cw = min(cw, int(ch * MUZZLE_GUIDE_ASPECT))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return frame[y0:y0 + ch, x0:x0 + cw]


def process_video(video_path: Path, out_dir: Path, models: Models, marker_cm: float = 15.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, duration = sample_frames(video_path)
    if not frames:
        return {"processing_mode": "prototype", "review_required": True, "review_reasons": ["video_unreadable"]}
    images = [f for _, f in frames]
    probs = view_probabilities(images, models)
    names = list(VIEW_PROMPTS)
    sharp = np.array([sharpness(f) for f in images])
    hists = [color_histogram(f) for f in images]
    cuts = [round(frames[i][0], 2) for i in range(1, len(frames))
            if cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_CORREL) < CUT_CORRELATION]

    labels, body_checks = [], {}
    for i, p in enumerate(probs):
        label = names[int(p.argmax())] if p.max() >= MIN_VIEW_PROB else "other"
        if label == "body":
            boxes = cow_boxes(images[i], models.detector)
            body_checks[i] = boxes
            if not is_full_side_body(boxes):
                label = "other"
        labels.append(label)

    views, reasons = {}, []
    for view in REQUIRED_VIEWS:
        idx = [i for i, l in enumerate(labels) if l == view]
        if not idx:
            reasons.append(f"{view}_view_missing")
            continue
        norm = sharp[idx] / sharp[idx].max()
        best = idx[int(np.argmax(probs[idx, names.index(view)] * norm))]
        frame_id = f"frame_{best:04d}"
        path = out_dir / f"{view}_{frame_id}.jpg"
        cv2.imwrite(str(path), images[best])
        views[view] = {"frame_id": frame_id, "time_s": round(frames[best][0], 2), "view_prob": round(float(probs[best, names.index(view)]), 3),
                       "sharpness": round(float(sharp[best]), 1), "frames_with_view": len(idx), "path": str(path)}
        if view == "muzzle":
            crop_path = out_dir / f"muzzle_crop_{frame_id}.jpg"
            cv2.imwrite(str(crop_path), muzzle_crop(images[best]))
            views[view]["crop_path"] = str(crop_path)
        if view == "body":
            views[view]["cow_boxes"] = body_checks[best]
            marker = marker_px_per_cm(images[best], marker_cm)
            views[view]["scale_reference"] = marker
            if marker is None:
                reasons.append("marker_not_detected")

    if cuts:
        reasons.append("scene_cut_detected")
    if any(len([b for b in boxes if b["width_frac"] >= BODY_MIN_WIDTH]) > 1 for boxes in body_checks.values()):
        reasons.append("multiple_cows_in_body_view")
    present = [v for v in REQUIRED_VIEWS if v in views]
    order = [views[v]["time_s"] for v in present]
    if order != sorted(order):
        reasons.append("views_out_of_guided_order")

    manifest = {
        "processing_mode": "prototype",
        "method_version": "video_enrollment_v1",
        "video": {"path": str(video_path), "sha256": hashlib.sha256(video_path.read_bytes()).hexdigest(),
                  "duration_s": round(duration, 2), "sampled_frames": len(frames), "sample_fps": SAMPLE_FPS},
        "views": views,
        "checks": {"required_views_present": not any(r.endswith("_view_missing") for r in reasons),
                   "scene_cuts_s": cuts, "view_counts": {n: labels.count(n) for n in names}},
        "review_required": bool(reasons),
        "review_reasons": reasons,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest
