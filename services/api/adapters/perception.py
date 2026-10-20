"""Perception capability probe (PRD Sections 4.1-4.3; plan Section 1: capability facade).

A capability is available when the prototype adapter's dependencies import and its model is present.
Anything unavailable falls back to labeled fixtures. Age is always available: it is fixture-based.
"""

from importlib.util import find_spec
from pathlib import Path

MUZZLE_MODEL = Path(__file__).resolve().parents[1] / "models" / "muzzle_embed_v1.onnx"
MIN_MODEL_BYTES = 1_000_000  # an un-pulled Git LFS pointer is ~130 bytes


def _has(*modules: str) -> bool:
    return all(find_spec(name) is not None for name in modules)


def probe_capabilities(model_path: Path = MUZZLE_MODEL) -> dict[str, bool]:
    model_ready = model_path.is_file() and model_path.stat().st_size > MIN_MODEL_BYTES
    return {
        "video": _has("torch", "open_clip", "ultralytics", "cv2"),
        "muzzle": _has("cv2", "onnxruntime") and model_ready,
        "weight": _has("ultralytics", "cv2"),
        "age": True,
    }
