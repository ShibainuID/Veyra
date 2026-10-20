"""Perception capability probe and facade (PRD Sections 4.1-4.3; plan Section 1: capability facade).

A capability is available when the prototype adapter's dependencies import and its model is present.
Anything unavailable falls back to labeled fixtures. Age is always available: it is fixture-based.

`Perception` is the only door from the API to the ML team's adapters. Each step (views, identity, weight,
age) picks the prototype adapter when its capability is available and falls back to the labeled fixture on
its own, so one enrollment can mix sources; every result carries `source` (`prototype`, `simulated`, or
`documented`) and `method_version`. The ML modules are imported lazily inside the methods: the video worker
imports torch and open_clip at module top, so fixture mode must never import it.
"""

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from config import Settings, get_settings

MUZZLE_MODEL = Path(__file__).resolve().parents[1] / "models" / "muzzle_embed_v1.onnx"
MIN_MODEL_BYTES = 1_000_000  # an un-pulled Git LFS pointer is ~130 bytes

CAPABILITIES = ("video", "muzzle", "weight", "age")
REQUIRED_VIEWS = ("muzzle", "teeth", "body")
# Unknown samples: views assigned at these shares of the video duration (no view classifier in fixture mode).
EVEN_SPLIT = {"muzzle": 0.2, "teeth": 0.5, "body": 0.8}
# The capture screen's muzzle guide box (services/api/README.md "Capture assumptions"); the crop uses exactly it.
MUZZLE_GUIDE_WIDTH = 0.9
MUZZLE_GUIDE_ASPECT = 1.18
YOLO_WEIGHTS = "yolov8x-seg.pt"
FIXTURE_VIEWS_VERSION = "fixture_views_v1"
SAMPLES_FILE = "enrollment_samples.json"
AGE_FILE = "age_estimates.json"

logger = logging.getLogger("veyra.perception")


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


def effective_capabilities(settings: Settings | None = None) -> dict[str, bool]:
    """What the facade will actually use: `fixture` disables every prototype, `prototype` and `auto` probe.

    `prototype` asks for the ML pipeline explicitly, so each capability it cannot provide is logged; the step
    still falls back to its fixture rather than failing the enrollment.
    """
    settings = settings or get_settings()
    if settings.perception_mode == "fixture":
        return {name: name == "age" for name in CAPABILITIES}
    probed = probe_capabilities()
    if settings.perception_mode == "prototype":
        for name in CAPABILITIES:
            if not probed[name]:
                logger.warning("perception_mode=prototype but the %s capability is unavailable; using fixtures", name)
    return probed


@dataclass(frozen=True)
class GalleryRef:
    """One registered muzzle crop of a confirmed animal: the matcher's gallery entry."""

    animal_id: str
    media_id: str
    path: Path


# Process-wide caches. Models are heavy to load; gallery references are keyed by media id, which is immutable.
_lock = threading.Lock()
_muzzle_identifier = None
_yolo = None
_video_models = None
_reference_cache: dict[str, object] = {}


def clear_caches() -> None:
    global _muzzle_identifier, _yolo, _video_models
    with _lock:
        _muzzle_identifier = _yolo = _video_models = None
        _reference_cache.clear()


def _get_muzzle_identifier():
    global _muzzle_identifier
    with _lock:
        if _muzzle_identifier is None:
            from adapters.muzzle import MuzzleIdentifier

            _muzzle_identifier = MuzzleIdentifier(MUZZLE_MODEL)
        return _muzzle_identifier


def _get_yolo():
    global _yolo
    with _lock:
        if _yolo is None:
            from ultralytics import YOLO

            _yolo = YOLO(YOLO_WEIGHTS)
        return _yolo


def _get_video_models():
    global _video_models
    detector = _get_yolo()
    with _lock:
        if _video_models is None:
            from workers.video_enrollment import Models

            _video_models = Models.load(detector)
        return _video_models


def load_samples(settings: Settings | None = None) -> dict:
    path = (settings or get_settings()).fixtures_dir / SAMPLES_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def guide_box_crop(frame):
    """The muzzle guide box: 90% of the frame width at a 1.18 aspect ratio, centred (same box as the ML worker)."""
    h, w = frame.shape[:2]
    cw = int(MUZZLE_GUIDE_WIDTH * w)
    ch = min(h, int(cw / MUZZLE_GUIDE_ASPECT))
    cw = min(cw, int(ch * MUZZLE_GUIDE_ASPECT))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return frame[y0:y0 + ch, x0:x0 + cw]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _missing_view_reasons(views: dict) -> list[str]:
    return [f"{view}_view_missing" for view in REQUIRED_VIEWS if view not in views]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


class Perception:
    """The facade. Construct one per job: it snapshots the effective capabilities and the sample fixtures."""

    def __init__(self, capabilities: dict[str, bool] | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.capabilities = capabilities if capabilities is not None else effective_capabilities(self.settings)
        self.samples = load_samples(self.settings)

    def _sample(self, sample_key: str | None) -> dict | None:
        return self.samples.get(sample_key) if sample_key else None

    # ----- views -------------------------------------------------------------------------------------------

    def extract_views(self, video_path: Path | None, out_dir: Path, sample_key: str | None) -> dict:
        """Best frame per required view, a muzzle crop, checks, and review reasons (the ML manifest's shape)."""
        out_dir = Path(out_dir)
        if video_path is not None and self.capabilities.get("video"):
            try:
                return self._prototype_views(Path(video_path), out_dir)
            except (ImportError, OSError) as exc:
                logger.warning("video prototype unavailable (%s); extracting fixture views", exc)
                manifest = self._fixture_views(Path(video_path), out_dir, sample_key)
                manifest["fallback"] = {"from": "prototype", "error": f"{type(exc).__name__}: {exc}"}
                return manifest
        if video_path is not None:
            return self._fixture_views(Path(video_path), out_dir, sample_key)
        return self._sample_views(sample_key)

    def _prototype_views(self, video_path: Path, out_dir: Path) -> dict:
        from workers.video_enrollment import process_video

        manifest = process_video(video_path, out_dir, _get_video_models())
        manifest.setdefault("processing_mode", "prototype")
        manifest.setdefault("method_version", "video_enrollment_v1")
        manifest.setdefault("views", {})
        manifest.setdefault("checks", {})
        manifest["source"] = "prototype"
        reasons = list(manifest.get("review_reasons") or [])
        reasons += [r for r in _missing_view_reasons(manifest["views"]) if r not in reasons]
        manifest["review_reasons"] = reasons
        manifest["review_required"] = bool(reasons)
        video = manifest.get("video") or {}
        video.pop("path", None)  # a worker-local temp path, meaningless once the frames are stored as media
        manifest["video"] = video
        return manifest

    def _fixture_base(self, reasons: list[str], views: dict, view_assignment: str, video: dict | None) -> dict:
        reasons = _dedupe(reasons + _missing_view_reasons(views))
        return {
            "processing_mode": "fixture",
            "source": "simulated",
            "method_version": FIXTURE_VIEWS_VERSION,
            "video": video,
            "views": views,
            "checks": {"required_views_present": all(v in views for v in REQUIRED_VIEWS),
                       "view_assignment": view_assignment},
            "review_required": bool(reasons),
            "review_reasons": reasons,
        }

    def _sample_views(self, sample_key: str | None) -> dict:
        """No footage: the sample's view times without frames, so a demo runs without a video."""
        sample = self._sample(sample_key)
        if sample is None:
            return self._fixture_base(["video_missing"], {}, "none", None)
        views = {name: {"frame_id": None, "time_s": spec["time_s"], "path": None}
                 | ({"crop_path": None} if name == "muzzle" else {})
                 for name, spec in sample["views"].items()}
        return self._fixture_base(["footage_not_attached"], views, "sample_fixture", None)

    def _fixture_views(self, video_path: Path, out_dir: Path, sample_key: str | None) -> dict:
        """Frames read with cv2 at the sample's view times (or 20/50/80% of the video for unknown samples)."""
        import cv2

        sample = self._sample(sample_key)
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames, wanted, reasons = {}, {}, []
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if not cap.isOpened() or fps <= 0 or count <= 0:
            cap.release()
            fallback = self._sample_views(sample_key)
            fallback["review_reasons"] = _dedupe(["video_unreadable"] + fallback["review_reasons"])
            fallback["review_required"] = True
            fallback["video"] = {"sha256": _sha256(video_path), "duration_s": None}
            return fallback
        duration = count / fps
        if sample is not None:
            times = {name: spec["time_s"] for name, spec in sample["views"].items()}
            assignment = "sample_fixture"
        else:
            times = {name: share * duration for name, share in EVEN_SPLIT.items()}
            assignment = "even_split"
            reasons.append("fixture_view_assignment")
        for name, t in times.items():
            wanted.setdefault(min(count - 1, max(0, round(t * fps))), []).append(name)

        index = 0
        last = max(wanted)
        while index <= last:
            ok, frame = cap.read()
            if not ok:
                break
            if index in wanted:
                frames[index] = frame
            index += 1
        cap.release()

        out_dir.mkdir(parents=True, exist_ok=True)
        views = {}
        for idx, names in sorted(wanted.items()):
            frame = frames.get(idx)
            if frame is None:
                continue  # past the last decodable frame: reported as `<view>_view_missing`
            frame_id = f"frame_{idx:04d}"
            for name in names:
                path = out_dir / f"{name}_{frame_id}.jpg"
                cv2.imwrite(str(path), frame)
                view = {"frame_id": frame_id, "time_s": round(idx / fps, 2), "path": str(path)}
                if name == "muzzle":
                    crop_path = out_dir / f"muzzle_crop_{frame_id}.jpg"
                    cv2.imwrite(str(crop_path), guide_box_crop(frame))
                    view["crop_path"] = str(crop_path)
                views[name] = view
        video = {"sha256": _sha256(video_path), "duration_s": round(duration, 2), "fps": round(fps, 3),
                 "frames": count}
        return self._fixture_base(reasons, views, assignment, video)

    # ----- identity ----------------------------------------------------------------------------------------

    def identify(self, crop_path: Path | None, gallery_refs: list[GalleryRef], sample_key: str | None) -> dict:
        """Identity candidate plus the duplicate check, always with `possible_duplicate`. Never a decision."""
        if crop_path is not None and self.capabilities.get("muzzle"):
            try:
                return self._prototype_identity(Path(crop_path), gallery_refs)
            except Exception as exc:  # a broken model or unreadable crop must not fail the enrollment
                logger.exception("muzzle prototype failed; using the fixture identity")
                result = self._fixture_identity(sample_key, matcher=False)
                result["fallback"] = {"from": "prototype", "error": f"{type(exc).__name__}: {exc}"}
                return result
        return self._fixture_identity(sample_key, matcher=bool(self.capabilities.get("muzzle")))

    def _prototype_identity(self, crop_path: Path, gallery_refs: list[GalleryRef]) -> dict:
        import cv2
        from adapters.muzzle import Gallery

        identifier = _get_muzzle_identifier()
        crop = cv2.imread(str(crop_path))
        if crop is None:
            raise OSError(f"muzzle crop is unreadable: {crop_path.name}")
        gallery = Gallery()
        skipped = 0
        for ref in gallery_refs:
            reference = _reference_cache.get(ref.media_id)
            if reference is None:
                image = cv2.imread(str(ref.path))
                reference = identifier.reference(ref.media_id, image) if image is not None else None
                if reference is None:
                    skipped += 1
                    continue
                _reference_cache[ref.media_id] = reference
            gallery.add(ref.animal_id, reference)
        result = dict(identifier.check_duplicate(crop, gallery))
        result.setdefault("source", "prototype")
        result.setdefault("method_version", "muzzle_hybrid_v1")
        result["gallery"] = {"animals": len(gallery.animals), "references": len(gallery_refs) - skipped,
                             "unusable_references": skipped}
        return result

    def _fixture_identity(self, sample_key: str | None, matcher: bool) -> dict:
        sample = self._sample(sample_key)
        if sample is not None:
            identity = json.loads(json.dumps(sample["identity"]))
            identity.setdefault("source", "simulated")
            identity.setdefault("method_version", "muzzle_hybrid_v1")
            identity["possible_duplicate"] = identity["outcome"] in ("candidate", "uncertain") and \
                identity.get("reason") != "insufficient_quality"
            return identity
        return {"source": "simulated", "method_version": "none", "outcome": "uncertain",
                "reason": "no_muzzle_crop" if matcher else "perception_unavailable", "candidates": [],
                "possible_duplicate": False, "review_required": True}

    # ----- weight ------------------------------------------------------------------------------------------

    def weight(self, body_frame_path: Path | None, sample_key: str | None) -> dict:
        if body_frame_path is not None and self.capabilities.get("weight"):
            try:
                return self._prototype_weight(Path(body_frame_path))
            except Exception as exc:
                logger.exception("weight prototype failed; using the fixture weight")
                result = self._fixture_weight(sample_key)
                result["fallback"] = {"from": "prototype", "error": f"{type(exc).__name__}: {exc}"}
                return result
        return self._fixture_weight(sample_key)

    def _prototype_weight(self, body_frame_path: Path) -> dict:
        import cv2
        from adapters.weight import estimate_weight

        image = cv2.imread(str(body_frame_path))
        if image is None:
            raise OSError(f"body frame is unreadable: {body_frame_path.name}")
        result = dict(estimate_weight(image, _get_yolo()))
        result.setdefault("source", "prototype")
        result.setdefault("method_version", "weight_side_view_v2")
        result.setdefault("unit", "kg")
        result.setdefault("range_low", None)
        result.setdefault("range_high", None)
        return result

    def _fixture_weight(self, sample_key: str | None) -> dict:
        sample = self._sample(sample_key)
        if sample is not None and sample.get("weight"):
            weight = json.loads(json.dumps(sample["weight"]))
            weight.setdefault("source", "simulated")
            return weight
        return {"source": "simulated", "method_version": "none", "range_low": None, "range_high": None,
                "unit": "kg", "review_required": True, "review_reason": "weight_unavailable"}

    # ----- age ---------------------------------------------------------------------------------------------

    def age(self, sample_key: str | None, teeth_frame_ids: list[str], documented_birth_date=None,
            observed_on=None) -> dict:
        from adapters.age import estimate_age

        return estimate_age(sample_key or "", teeth_frame_ids, documented_birth_date=documented_birth_date,
                            observed_on=observed_on, fixtures_path=self.settings.fixtures_dir / AGE_FILE)
