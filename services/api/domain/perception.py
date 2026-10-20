"""Boundary between domain logic and the perception adapters.

Domain code depends only on this protocol, so it never imports torch, OpenCV, or ONNX Runtime.
The real implementation (`adapters.perception.RealPerception`) loads models lazily in the worker;
tests install a deterministic fake with `set_perception`.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class GalleryReference:
    animal_id: uuid.UUID
    reference_id: uuid.UUID
    embedding: list[float]
    features_path: Path


class Perception(Protocol):
    model_version: str

    def process_video(self, video_path: Path, out_dir: Path, marker_cm: float) -> dict:
        """Enrollment manifest: best frame per view, muzzle crop, scale reference, checks, review reasons."""

    def save_reference_features(self, crop_path: Path, features_path: Path) -> list[float] | None:
        """Write SIFT features for a muzzle crop and return its embedding, or None when the crop is unusable."""

    def identify(self, crop_path: Path, gallery: list[GalleryReference]) -> dict:
        """Muzzle identity result: outcome candidate/new/uncertain, candidates, possible_duplicate."""

    def estimate_weight(self, body_frame_path: Path, scale: dict, tape_heart_girth_cm: float | None) -> dict:
        """Weight adapter output for the body frame."""


_override: Perception | None = None
_default: Perception | None = None


def set_perception(perception: Perception | None) -> None:
    global _override
    _override = perception


def get_perception(yolo_weights: str) -> Perception:
    global _default
    if _override is not None:
        return _override
    if _default is None:
        from adapters.perception import RealPerception

        _default = RealPerception(yolo_weights)
    return _default
