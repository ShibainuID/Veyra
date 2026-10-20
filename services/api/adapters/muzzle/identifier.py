"""Muzzle identity adapter: embedding shortlist + SIFT/RANSAC verification (see models/MODEL_CARD.md).

Outcomes follow PRD Section 4.1 step 2 and M03:
- `candidate`: one registered animal passes geometric verification.
- `new`: no registered animal passes; the operator may register a new animal after review.
- `uncertain`: the crop is unusable, or two different animals pass verification with similar support.
Every result is a candidate for human review, never an automatic identity decision.
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "muzzle_embed_v1.onnx"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
IMG_SIZE = 224
SHORTLIST = 5
ACCEPT_INLIERS = 5
# A second animal within this share of the best inlier count makes the result ambiguous.
AMBIGUITY_RATIO = 0.8
SIFT_MAX_SIDE = 480
SIFT_FEATURES = 800
SIFT_RATIO = 0.75
MIN_KEYPOINTS = 8


@dataclass
class Reference:
    image_id: str
    embedding: np.ndarray
    keypoints: np.ndarray
    descriptors: np.ndarray


@dataclass
class Gallery:
    animals: dict[str, list[Reference]] = field(default_factory=dict)

    def add(self, animal_id: str, ref: Reference) -> None:
        self.animals.setdefault(animal_id, []).append(ref)

    def centroids(self) -> tuple[list[str], np.ndarray]:
        ids = list(self.animals)
        if not ids:
            return [], np.zeros((0, 512), dtype=np.float32)
        c = np.stack([np.mean([r.embedding for r in self.animals[a]], axis=0) for a in ids])
        return ids, c / np.linalg.norm(c, axis=1, keepdims=True)


class MuzzleIdentifier:
    def __init__(self, model_path: Path = MODEL_PATH):
        # The ONNX session is thread-safe; OpenCV SIFT/CLAHE/matcher objects are created per call because they are not.
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    def embed(self, crops_bgr: list[np.ndarray]) -> np.ndarray:
        batch = []
        for img in crops_bgr:
            rgb = cv2.cvtColor(cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            batch.append(((rgb.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1))
        return self.session.run(None, {"image": np.stack(batch).astype(np.float32)})[0]

    def sift_features(self, crop_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        scale = SIFT_MAX_SIDE / max(gray.shape)
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        kps, desc = cv2.SIFT_create(nfeatures=SIFT_FEATURES).detectAndCompute(clahe.apply(gray), None)
        if desc is None or len(kps) < MIN_KEYPOINTS:
            return None
        return np.float32([k.pt for k in kps]), desc

    def reference(self, image_id: str, crop_bgr: np.ndarray) -> Reference | None:
        feats = self.sift_features(crop_bgr)
        if feats is None:
            return None
        return Reference(image_id, self.embed([crop_bgr])[0], *feats)

    def inliers(self, a: tuple[np.ndarray, np.ndarray], b: Reference) -> int:
        pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(a[1], b.descriptors, k=2)
        good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < SIFT_RATIO * n.distance]
        if len(good) < MIN_KEYPOINTS:
            return 0
        src = a[0][[m.queryIdx for m in good]]
        dst = b.keypoints[[m.trainIdx for m in good]]
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        return 0 if mask is None else int(mask.sum())

    def identify(self, crop_bgr: np.ndarray, gallery: Gallery) -> dict:
        base = {"source": "prototype", "method_version": "muzzle_hybrid_v1", "accept_inliers": ACCEPT_INLIERS}
        feats = self.sift_features(crop_bgr)
        if feats is None:
            return {**base, "outcome": "uncertain", "reason": "insufficient_quality", "candidates": []}
        ids, centroids = gallery.centroids()
        if not ids:
            return {**base, "outcome": "new", "reason": "empty_gallery", "candidates": []}

        cos = centroids @ self.embed([crop_bgr])[0]
        shortlist = np.argsort(-cos)[:SHORTLIST]
        candidates = sorted(
            ({"animal_id": ids[i], "cosine": round(float(cos[i]), 4),
              "inliers": max(self.inliers(feats, r) for r in gallery.animals[ids[i]])} for i in shortlist),
            key=lambda c: (c["inliers"], c["cosine"]), reverse=True,
        )
        passing = [c for c in candidates if c["inliers"] > ACCEPT_INLIERS]
        if not passing:
            return {**base, "outcome": "new", "reason": "no_verified_match", "candidates": candidates}
        if len(passing) > 1 and passing[1]["inliers"] >= AMBIGUITY_RATIO * passing[0]["inliers"]:
            return {**base, "outcome": "uncertain", "reason": "ambiguous_match", "candidates": candidates}
        return {**base, "outcome": "candidate", "reason": None, "animal_id": passing[0]["animal_id"],
                "candidates": candidates}

    def check_duplicate(self, crop_bgr: np.ndarray, gallery: Gallery) -> dict:
        """Before registering a new animal: flag a possible duplicate when any registered animal verifies."""
        result = self.identify(crop_bgr, gallery)
        duplicate = result["outcome"] in ("candidate", "uncertain") and result["reason"] != "insufficient_quality"
        return {**result, "possible_duplicate": duplicate}
