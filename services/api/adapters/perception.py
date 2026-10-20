"""Real perception backed by the muzzle, weight, and enrollment-video adapters. Models load on first use."""

import json
from functools import cached_property
from pathlib import Path

import cv2
import numpy as np

from adapters.muzzle import Gallery, MuzzleIdentifier, Reference
from adapters.muzzle.identifier import MODEL_PATH
from adapters.weight import estimate_weight
from domain.perception import GalleryReference


def to_jsonable(obj):
    """Convert numpy scalars and arrays in adapter output to plain Python values for JSONB storage."""

    def convert(o):
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f"{type(o).__name__} is not JSON serialisable")

    return json.loads(json.dumps(obj, default=convert))


class RealPerception:
    model_version = f"muzzle_hybrid_v1:{MODEL_PATH.name}"

    def __init__(self, yolo_weights: str):
        self.yolo_weights = yolo_weights

    @cached_property
    def detector(self):
        from ultralytics import YOLO

        return YOLO(self.yolo_weights)

    @cached_property
    def video_models(self):
        from workers.video_enrollment import Models

        return Models.load(self.detector)

    @cached_property
    def muzzle(self) -> MuzzleIdentifier:
        return MuzzleIdentifier()

    def process_video(self, video_path: Path, out_dir: Path, marker_cm: float) -> dict:
        from workers.video_enrollment import process_video

        return to_jsonable(process_video(video_path, out_dir, self.video_models, marker_cm=marker_cm))

    def save_reference_features(self, crop_path: Path, features_path: Path) -> list[float] | None:
        ref = self.muzzle.reference(crop_path.name, cv2.imread(str(crop_path)))
        if ref is None:
            return None
        features_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(features_path, keypoints=ref.keypoints, descriptors=ref.descriptors)
        return [float(x) for x in ref.embedding]

    def identify(self, crop_path: Path, gallery: list[GalleryReference]) -> dict:
        g = Gallery()
        for entry in gallery:
            z = np.load(entry.features_path)
            g.add(str(entry.animal_id), Reference(str(entry.reference_id), np.asarray(entry.embedding, dtype=np.float32),
                                                  z["keypoints"], z["descriptors"]))
        return to_jsonable(self.muzzle.check_duplicate(cv2.imread(str(crop_path)), g))

    def estimate_weight(self, body_frame_path: Path, scale: dict, tape_heart_girth_cm: float | None) -> dict:
        image = cv2.imread(str(body_frame_path))
        return to_jsonable(estimate_weight(image, self.detector, marker_cm=scale.get("marker_cm") or 15.0,
                                           tape_heart_girth_cm=tape_heart_girth_cm, scale_override=scale))
