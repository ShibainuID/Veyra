"""Perception facade: capability selection per mode, per-step fallback, and the prototype adapters' arguments.

The ML modules are replaced with fakes at their import targets (`sys.modules` entries or module attributes), so
these tests prove which adapter the facade calls and with what, without torch or a YOLO download.
"""

import json
import logging
import sys
import threading
import time
import types
from pathlib import Path

import cv2
import numpy as np
import pytest

import adapters.muzzle
import adapters.weight
from adapters import perception
from adapters.perception import GalleryRef, Perception, effective_capabilities, guide_box_crop, probe_capabilities
from config import get_settings
from tests.video_support import DOMINANT_CHANNEL, dominant_channel, textured_image, write_enrollment_video

ALL = {"video": True, "muzzle": True, "weight": True, "age": True}
NONE = {"video": False, "muzzle": False, "weight": False, "age": True}


@pytest.fixture(autouse=True)
def fresh_caches():
    perception.clear_caches()
    yield
    perception.clear_caches()


@pytest.fixture
def video(tmp_path) -> Path:
    return write_enrollment_video(tmp_path / "enroll.mp4")


def _mode(monkeypatch, mode: str):
    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", mode)
    get_settings.cache_clear()
    return get_settings()


# ----- effective capabilities ---------------------------------------------------------------------------------


def test_fixture_mode_disables_every_prototype(monkeypatch):
    monkeypatch.setattr(perception, "probe_capabilities", lambda: dict(ALL))

    assert effective_capabilities(_mode(monkeypatch, "fixture")) == NONE


def test_auto_mode_uses_the_probe(monkeypatch):
    probed = {"video": False, "muzzle": True, "weight": False, "age": True}
    monkeypatch.setattr(perception, "probe_capabilities", lambda: dict(probed))

    assert effective_capabilities(_mode(monkeypatch, "auto")) == probed


def test_prototype_mode_logs_each_unavailable_capability(monkeypatch, caplog):
    monkeypatch.setattr(perception, "probe_capabilities", lambda: dict(NONE))

    with caplog.at_level(logging.WARNING, logger="veyra.perception"):
        caps = effective_capabilities(_mode(monkeypatch, "prototype"))

    assert caps == NONE
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert all(name in logged for name in ("video", "muzzle", "weight"))


def test_perception_snapshots_effective_capabilities(monkeypatch):
    monkeypatch.setattr(perception, "probe_capabilities", lambda: dict(ALL))
    _mode(monkeypatch, "auto")

    assert Perception().capabilities == ALL


# ----- fixture paths ------------------------------------------------------------------------------------------


def test_fixture_views_read_frames_at_the_sample_times(video, tmp_path):
    manifest = Perception(NONE).extract_views(video, tmp_path / "out", "sample-enrollment-001")

    assert manifest["processing_mode"] == "fixture"
    assert manifest["source"] == "simulated" and manifest["method_version"]
    assert manifest["review_reasons"] == [] and manifest["review_required"] is False
    assert manifest["video"]["duration_s"] == pytest.approx(7.0, abs=0.1)
    assert len(manifest["video"]["sha256"]) == 64
    assert {name: spec["time_s"] for name, spec in manifest["views"].items()} == pytest.approx(
        {"muzzle": 1.5, "teeth": 3.2, "body": 6.0}, abs=0.05)
    for name, spec in manifest["views"].items():
        frame = cv2.imread(spec["path"])
        assert frame is not None and dominant_channel(frame) == DOMINANT_CHANNEL[name]
    crop = cv2.imread(manifest["views"]["muzzle"]["crop_path"])
    expected = guide_box_crop(np.zeros((240, 320, 3), np.uint8))
    assert crop.shape == expected.shape
    assert crop.shape[1] / crop.shape[0] == pytest.approx(1.18, abs=0.02)


def test_unknown_sample_splits_the_video_and_says_so(video, tmp_path):
    manifest = Perception(NONE).extract_views(video, tmp_path / "out", None)

    assert set(manifest["views"]) == {"muzzle", "teeth", "body"}
    assert manifest["views"]["muzzle"]["time_s"] == pytest.approx(1.4, abs=0.05)
    assert manifest["review_reasons"] == ["fixture_view_assignment"]


def test_sample_without_a_muzzle_view_reports_it_missing(video, tmp_path):
    manifest = Perception(NONE).extract_views(video, tmp_path / "out", "sample-enrollment-unclear")

    assert set(manifest["views"]) == {"teeth", "body"}
    assert "muzzle_view_missing" in manifest["review_reasons"]
    assert manifest["checks"]["required_views_present"] is False


def test_known_sample_without_video_gives_views_without_frames(tmp_path):
    manifest = Perception(NONE).extract_views(None, tmp_path / "out", "sample-enrollment-001")

    assert manifest["views"]["muzzle"] == {"frame_id": None, "time_s": 1.5, "path": None, "crop_path": None}
    assert manifest["views"]["body"]["path"] is None
    assert not (tmp_path / "out").exists()


def test_unreadable_video_is_flagged(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")

    manifest = Perception(NONE).extract_views(bad, tmp_path / "out", None)

    assert "video_unreadable" in manifest["review_reasons"]
    assert manifest["views"] == {}


def test_fixture_identity_and_duplicate_flag():
    facade = Perception(NONE)

    new = facade.identify(None, [], "sample-enrollment-001")
    dup = facade.identify(None, [], "sample-enrollment-dup")
    unclear = facade.identify(None, [], "sample-enrollment-unclear")
    unknown = facade.identify(None, [], None)

    assert (new["outcome"], new["possible_duplicate"], new["source"]) == ("new", False, "simulated")
    assert (dup["outcome"], dup["animal_id"], dup["possible_duplicate"]) == ("candidate", "animal-demo-002", True)
    assert (unclear["outcome"], unclear["possible_duplicate"]) == ("uncertain", False)
    assert unknown == {"source": "simulated", "method_version": "none", "outcome": "uncertain",
                       "reason": "perception_unavailable", "candidates": [], "possible_duplicate": False,
                       "review_required": True}


def test_fixture_weight_and_unavailable_weight():
    facade = Perception(NONE)

    weight = facade.weight(None, "sample-enrollment-001")
    missing = facade.weight(None, None)

    assert (weight["range_low"], weight["range_high"], weight["source"]) == (480.0, 560.0, "simulated")
    assert missing["review_required"] is True and missing["review_reason"] == "weight_unavailable"
    assert missing["source"] == "simulated" and "method_version" in missing


def test_age_is_the_ml_fixture():
    age = Perception(NONE).age("sample-enrollment-001", ["frame_0076"])

    assert (age["range_low"], age["range_high"], age["source"]) == (24, 30, "simulated")
    assert age["evidence_frame_ids"] == ["frame_0076"]


# ----- prototype selection with fakes -------------------------------------------------------------------------


class FakeYOLO:
    instances: list = []

    def __init__(self, weights):
        self.weights = weights
        FakeYOLO.instances.append(self)


@pytest.fixture
def fake_ultralytics(monkeypatch):
    FakeYOLO.instances = []
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    return FakeYOLO


@pytest.fixture
def fake_video_worker(monkeypatch, fake_ultralytics):
    calls = {}

    class Models:
        @classmethod
        def load(cls, detector):
            calls["detector"] = detector
            return "models"

    def process_video(video_path, out_dir, models, marker_cm=15.0):
        calls.update(video_path=video_path, out_dir=out_dir, models=models)
        if "raise" in calls:
            raise calls["raise"]
        return {"processing_mode": "prototype", "method_version": "video_enrollment_v1",
                "video": {"path": str(video_path), "sha256": "abc", "duration_s": np.float64(7.0)},
                "views": {"muzzle": {"frame_id": "frame_0006", "time_s": np.float32(1.5), "path": "m.jpg",
                                     "crop_path": "c.jpg", "box": np.array([1.0, 2.0])}},
                "checks": {"required_views_present": np.bool_(False)}, "review_required": True,
                "review_reasons": ["marker_not_detected"]}

    module = types.ModuleType("workers.video_enrollment")
    module.Models, module.process_video = Models, process_video
    monkeypatch.setitem(sys.modules, "workers.video_enrollment", module)
    return calls


def test_video_prototype_selected_only_when_capable(video, tmp_path, fake_video_worker):
    out = tmp_path / "out"

    fixture = Perception({**ALL, "video": False}).extract_views(video, out, "sample-enrollment-001")
    assert fixture["processing_mode"] == "fixture" and fake_video_worker == {}

    manifest = Perception(ALL).extract_views(video, out, "sample-enrollment-001")

    assert fake_video_worker["video_path"] == video
    assert fake_video_worker["out_dir"] == out
    assert fake_video_worker["models"] == "models"
    assert fake_video_worker["detector"].weights == perception.YOLO_WEIGHTS
    assert manifest["processing_mode"] == "prototype" and manifest["source"] == "prototype"
    assert "path" not in manifest["video"]
    assert manifest["review_reasons"] == ["marker_not_detected", "teeth_view_missing", "body_view_missing"]


def test_video_prototype_import_failure_falls_back(video, tmp_path, monkeypatch, fake_ultralytics):
    monkeypatch.setitem(sys.modules, "workers.video_enrollment", None)  # import raises ImportError

    manifest = Perception(ALL).extract_views(video, tmp_path / "out", "sample-enrollment-001")

    assert manifest["processing_mode"] == "fixture"
    assert manifest["fallback"] == {"from": "prototype", "reason": "prototype_unavailable"}
    assert set(manifest["views"]) == {"muzzle", "teeth", "body"}


@pytest.fixture
def fake_identifier(monkeypatch):
    calls = {"references": [], "check": []}

    class FakeIdentifier:
        def __init__(self, model_path):
            calls["model_path"] = model_path

        def reference(self, image_id, crop_bgr):
            calls["references"].append((image_id, crop_bgr.shape))
            return f"ref:{image_id}"

        def check_duplicate(self, crop_bgr, gallery):
            calls["check"].append((crop_bgr.shape, {a: list(r) for a, r in gallery.animals.items()}))
            return {"source": "prototype", "method_version": "muzzle_hybrid_v1", "outcome": "candidate",
                    "reason": None, "animal_id": "animal-demo-002", "candidates": [], "possible_duplicate": True}

    monkeypatch.setattr(adapters.muzzle, "MuzzleIdentifier", FakeIdentifier)
    return calls


def _image(path: Path, size=(118, 100)) -> Path:
    cv2.imwrite(str(path), textured_image(size=size))
    return path


def test_muzzle_prototype_gets_the_crop_and_the_gallery(tmp_path, fake_identifier):
    crop = _image(tmp_path / "crop.jpg")
    refs = [GalleryRef("animal-demo-002", "media-a", _image(tmp_path / "a.jpg")),
            GalleryRef("animal-demo-002", "media-b", _image(tmp_path / "b.jpg")),
            GalleryRef("animal-demo-003", "media-c", _image(tmp_path / "c.jpg"))]

    first = Perception(ALL).identify(crop, refs, "sample-enrollment-001")
    Perception(ALL).identify(crop, refs, "sample-enrollment-001")

    assert first["source"] == "prototype" and first["possible_duplicate"] is True
    assert fake_identifier["model_path"] == perception.MUZZLE_MODEL
    shape, gallery = fake_identifier["check"][0]
    assert shape == (100, 118, 3)
    assert gallery == {"animal-demo-002": ["ref:media-a", "ref:media-b"], "animal-demo-003": ["ref:media-c"]}
    assert [image_id for image_id, _ in fake_identifier["references"]] == ["media-a", "media-b", "media-c"]  # cached
    assert first["gallery"] == {"animals": 2, "references": 3, "unusable_references": 0,
                                "pending_animals": 0}


def test_muzzle_prototype_skipped_without_a_crop_or_capability(tmp_path, fake_identifier):
    crop = _image(tmp_path / "crop.jpg")

    no_crop = Perception(ALL).identify(None, [], "sample-enrollment-dup")
    no_cap = Perception({**ALL, "muzzle": False}).identify(crop, [], "sample-enrollment-dup")
    unknown = Perception(ALL).identify(None, [], None)

    assert fake_identifier["check"] == []
    assert no_crop["source"] == no_cap["source"] == "simulated"
    assert unknown["reason"] == "no_muzzle_crop"


def test_weight_prototype_gets_the_body_frame(tmp_path, monkeypatch, fake_ultralytics):
    calls = {}

    def fake_estimate(image_bgr, model, marker_cm=15.0, tape_heart_girth_cm=None):
        calls.update(shape=image_bgr.shape, model=model)
        return {"source": "prototype", "method_version": "weight_side_view_v2", "range_low": 400.0,
                "range_high": 450.0, "unit": "kg", "review_required": False, "review_reason": None}

    monkeypatch.setattr(adapters.weight, "estimate_weight", fake_estimate)
    body = _image(tmp_path / "body.jpg", size=(320, 240))

    skipped = Perception({**ALL, "weight": False}).weight(body, "sample-enrollment-001")
    result = Perception(ALL).weight(body, "sample-enrollment-001")

    assert skipped["source"] == "simulated"
    assert calls["shape"] == (240, 320, 3) and calls["model"].weights == perception.YOLO_WEIGHTS
    assert (result["source"], result["range_low"]) == ("prototype", 400.0)


def test_weight_prototype_reuses_the_video_marker_scale(tmp_path, monkeypatch, fake_ultralytics):
    calls = {}

    def fake_estimate(image_bgr, model, marker_cm=15.0, tape_heart_girth_cm=None, scale_override=None):
        calls.update(marker_cm=marker_cm, scale_override=scale_override)
        return {"source": "prototype", "range_low": 400.0, "range_high": 450.0, "unit": "kg"}

    monkeypatch.setattr(adapters.weight, "estimate_weight", fake_estimate)
    scale = {"marker_id": 7, "px_per_cm": 8.25, "marker_cm": 12.0}

    Perception(ALL).weight(_image(tmp_path / "body.jpg"), "sample-enrollment-001", scale=scale)

    assert calls == {"marker_cm": 12.0, "scale_override": scale}


def test_yolo_weights_come_from_settings(tmp_path, monkeypatch, fake_ultralytics):
    calls = {}

    def fake_estimate(image_bgr, model, marker_cm=15.0, tape_heart_girth_cm=None):
        calls["weights"] = model.weights
        return {"source": "prototype", "range_low": 400.0, "range_high": 450.0, "unit": "kg"}

    monkeypatch.setattr(adapters.weight, "estimate_weight", fake_estimate)
    monkeypatch.setenv("VEYRA_YOLO_WEIGHTS", str(tmp_path / "models" / "yolov8x-seg.pt"))
    get_settings.cache_clear()

    Perception(ALL).weight(_image(tmp_path / "body.jpg"), "sample-enrollment-001")

    assert calls["weights"] == str(tmp_path / "models" / "yolov8x-seg.pt")


def test_weight_prototype_error_falls_back_to_the_fixture(tmp_path, monkeypatch, fake_ultralytics):
    def broken(*args, **kwargs):
        raise RuntimeError("segmentation failed")

    monkeypatch.setattr(adapters.weight, "estimate_weight", broken)

    result = Perception(ALL).weight(_image(tmp_path / "body.jpg"), "sample-enrollment-001")

    assert result["source"] == "simulated" and result["range_low"] == 480.0
    assert result["fallback"] == {"from": "prototype", "reason": "prototype_error"}
    assert "segmentation failed" not in json.dumps(result)


def test_steps_fall_back_independently(video, tmp_path, fake_identifier):
    facade = Perception({**NONE, "muzzle": True})
    manifest = facade.extract_views(video, tmp_path / "out", "sample-enrollment-001")

    identity = facade.identify(Path(manifest["views"]["muzzle"]["crop_path"]), [], "sample-enrollment-001")
    weight = facade.weight(Path(manifest["views"]["body"]["path"]), "sample-enrollment-001")

    assert (manifest["source"], identity["source"], weight["source"]) == ("simulated", "prototype", "simulated")


# ----- the real matcher ---------------------------------------------------------------------------------------


@pytest.mark.skipif(not probe_capabilities()["muzzle"], reason="muzzle model or onnxruntime not available")
def test_real_muzzle_identifier_on_a_synthetic_crop(tmp_path):
    crop = _image(tmp_path / "crop.jpg", size=(236, 200))
    facade = Perception({**NONE, "muzzle": True})

    empty = facade.identify(crop, [], None)
    again = facade.identify(crop, [GalleryRef("animal-demo-009", "media-self", crop)], None)

    assert empty["source"] == "prototype" and empty["method_version"] == "muzzle_hybrid_v1"
    assert empty["outcome"] in ("new", "uncertain")
    assert empty["possible_duplicate"] is False
    # The same crop registered in the gallery verifies against itself: the matcher really ran.
    assert again["outcome"] == "candidate" and again["animal_id"] == "animal-demo-009"
    assert again["possible_duplicate"] is True


# ----- hardening: JSON-safe results, prototype guards, model lock, pending gallery ---------------------------


def test_prototype_views_are_plain_json(video, tmp_path, fake_video_worker):
    manifest = Perception(ALL).extract_views(video, tmp_path / "out", None, video_sha256="stored-hash")

    json.dumps(manifest)
    assert type(manifest["views"]["muzzle"]["time_s"]) is float
    assert manifest["views"]["muzzle"]["box"] == [1.0, 2.0]
    assert manifest["checks"]["required_views_present"] is False
    assert manifest["video"]["sha256"] == "stored-hash"


def test_prototype_weight_with_numpy_values_is_plain_json(tmp_path, monkeypatch, fake_ultralytics):
    def numpy_estimate(image_bgr, model, marker_cm=15.0, tape_heart_girth_cm=None):
        return {"source": "prototype", "method_version": "weight_side_view_v2", "range_low": np.float64(480.5),
                "range_high": np.float32(530.0), "unit": "kg", "review_required": np.bool_(False),
                "review_reason": None, "flags": [],
                "landmarks_px": {"withers": (np.int64(10), np.int64(20)), "front_is_left": np.bool_(True),
                                 "trunk_x": (np.int32(3), np.int32(300))},
                "measurements": [{"name": "withers_height", "value": np.float64(121.4)}],
                "mask_area": np.array([[1, 2], [3, 4]])}

    monkeypatch.setattr(adapters.weight, "estimate_weight", numpy_estimate)

    result = Perception(ALL).weight(_image(tmp_path / "body.jpg"), None)

    json.dumps(result)
    assert result["landmarks_px"]["front_is_left"] is True
    assert result["landmarks_px"]["withers"] == [10, 20]
    assert result["review_required"] is False and type(result["range_low"]) is float
    assert result["mask_area"] == [[1, 2], [3, 4]]


def test_prototype_identity_with_numpy_values_is_plain_json(tmp_path, monkeypatch):
    class NumpyIdentifier:
        def __init__(self, model_path):
            pass

        def reference(self, image_id, crop_bgr):
            return image_id

        def check_duplicate(self, crop_bgr, gallery):
            return {"source": "prototype", "method_version": "muzzle_hybrid_v1", "outcome": "new",
                    "reason": "no_verified_match", "possible_duplicate": np.bool_(False),
                    "candidates": [{"animal_id": "animal-demo-002", "cosine": np.float32(0.41),
                                    "inliers": np.int64(2)}]}

    monkeypatch.setattr(adapters.muzzle, "MuzzleIdentifier", NumpyIdentifier)
    refs = [GalleryRef("animal-demo-002", "media-a", _image(tmp_path / "a.jpg"))]

    result = Perception(ALL).identify(_image(tmp_path / "crop.jpg"), refs, None)

    json.dumps(result)
    assert result["possible_duplicate"] is False
    assert type(result["candidates"][0]["inliers"]) is int


def test_long_video_skips_the_prototype(video, tmp_path, monkeypatch, fake_video_worker):
    monkeypatch.setattr(perception, "MAX_PROTOTYPE_SECONDS", 5.0)

    manifest = Perception(ALL).extract_views(video, tmp_path / "out", "sample-enrollment-001")

    assert "video_path" not in fake_video_worker
    assert manifest["processing_mode"] == "fixture"
    assert manifest["fallback"] == {"from": "prototype", "reason": "video_too_large"}


def test_video_prototype_error_falls_back_without_exposing_the_message(video, tmp_path, fake_video_worker, caplog):
    fake_video_worker["raise"] = ValueError("secret internal detail")

    with caplog.at_level(logging.ERROR, logger="veyra.perception"):
        manifest = Perception(ALL).extract_views(video, tmp_path / "out", "sample-enrollment-001")

    assert manifest["fallback"] == {"from": "prototype", "reason": "prototype_error"}
    assert "secret internal detail" not in json.dumps(manifest)
    assert any("secret internal detail" in (r.exc_text or "") or r.exc_info for r in caplog.records)
    assert set(manifest["views"]) == {"muzzle", "teeth", "body"}


def test_fixture_views_reuse_the_stored_hash(video, tmp_path):
    manifest = Perception(NONE).extract_views(video, tmp_path / "out", None, video_sha256="stored-hash")

    assert manifest["video"]["sha256"] == "stored-hash"


def test_shared_model_inference_is_serialized(tmp_path, monkeypatch, fake_ultralytics):
    active, peak = [0], [0]
    guard = threading.Lock()

    def slow_estimate(image_bgr, model, marker_cm=15.0, tape_heart_girth_cm=None):
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with guard:
            active[0] -= 1
        return {"source": "prototype", "method_version": "weight_side_view_v2", "range_low": 1.0,
                "range_high": 2.0, "unit": "kg", "review_required": False, "review_reason": None}

    monkeypatch.setattr(adapters.weight, "estimate_weight", slow_estimate)
    body = _image(tmp_path / "body.jpg")
    threads = [threading.Thread(target=Perception(ALL).weight, args=(body, None)) for _ in range(4)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak[0] == 1
    assert len(fake_ultralytics.instances) == 1  # one shared model, loaded once


def test_pending_gallery_animals_are_labeled(tmp_path, fake_identifier):
    refs = [GalleryRef("animal-demo-002", "media-a", _image(tmp_path / "a.jpg"), "pending_review")]

    result = Perception(ALL).identify(_image(tmp_path / "crop.jpg"), refs, None)

    assert result["animal_id"] == "animal-demo-002" and result["animal_identity_status"] == "pending_review"
    assert result["gallery"]["pending_animals"] == 1
