"""Deterministic stand-in for the perception adapters.

A test video's bytes contain `COW:<name>`; that name plays the role of the muzzle pattern. Extra tokens
control the manifest: `CUT` adds a scene cut, `NOTEETH` drops the teeth view, `NOMARKER` drops the scale
marker, `NOMUZZLE` drops the muzzle view, and `CRASH` raises to exercise job failure.
"""

import re
from pathlib import Path

from domain.perception import GalleryReference


class FakePerception:
    model_version = "fake_muzzle_v1"

    def process_video(self, video_path: Path, out_dir: Path, marker_cm: float) -> dict:
        content = video_path.read_text()
        if "CRASH" in content:
            raise RuntimeError("simulated perception failure")
        cow = re.search(r"COW:(\w+)", content).group(1)
        out_dir.mkdir(parents=True, exist_ok=True)
        views, reasons = {}, []
        wanted = [v for v in ("muzzle", "teeth", "body") if f"NO{v.upper()}" not in content]
        for i, view in enumerate(wanted):
            frame = out_dir / f"{view}_frame_{i:04d}.jpg"
            frame.write_text(f"{view} of {cow}")
            views[view] = {"frame_id": f"frame_{i:04d}", "time_s": float(i), "view_prob": 0.99, "path": str(frame)}
        if "muzzle" in views:
            crop = out_dir / "muzzle_crop.jpg"
            crop.write_text(cow)
            views["muzzle"]["crop_path"] = str(crop)
        if "body" in views:
            views["body"]["scale_reference"] = None if "NOMARKER" in content else {"marker_id": 7, "px_per_cm": 5.0,
                                                                                    "marker_cm": marker_cm}
            if "NOMARKER" in content:
                reasons.append("marker_not_detected")
        reasons += [f"{v}_view_missing" for v in ("muzzle", "teeth", "body") if v not in views]
        if "CUT" in content:
            reasons.append("scene_cut_detected")
        return {"processing_mode": "prototype", "method_version": "fake_video_v1", "video": {"path": str(video_path)},
                "views": views, "checks": {"scene_cuts_s": [1.0] if "CUT" in content else []},
                "review_required": bool(reasons), "review_reasons": reasons}

    def save_reference_features(self, crop_path: Path, features_path: Path) -> list[float] | None:
        features_path.parent.mkdir(parents=True, exist_ok=True)
        features_path.write_text(crop_path.read_text())
        return [float(len(crop_path.read_text()))]

    def identify(self, crop_path: Path, gallery: list[GalleryReference]) -> dict:
        cow = crop_path.read_text()
        matches = sorted({str(g.animal_id) for g in gallery if g.features_path.read_text() == cow})
        base = {"source": "prototype", "method_version": "fake_muzzle_v1"}
        if not matches:
            return {**base, "outcome": "new", "reason": "no_verified_match", "candidates": [], "possible_duplicate": False}
        candidates = [{"animal_id": m, "inliers": 100} for m in matches]
        if len(matches) > 1:
            return {**base, "outcome": "uncertain", "reason": "ambiguous_match", "candidates": candidates,
                    "possible_duplicate": True}
        return {**base, "outcome": "candidate", "reason": None, "animal_id": matches[0], "candidates": candidates,
                "possible_duplicate": True}

    def estimate_weight(self, body_frame_path: Path, scale: dict, tape_heart_girth_cm: float | None) -> dict:
        return {"source": "prototype", "method_version": "fake_weight_v1", "range_low": 480.0, "range_high": 560.0,
                "unit": "kg", "review_required": False, "review_reason": None}
