"""Enrollment hardening: restart recovery, stale duplicate checks, unverified links, retry supersession, upload
handling, numpy-safe prototype results, and generic error messages."""

import json
import sys
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import adapters.weight
import routes.enrollments as enrollment_routes
from adapters import perception
from adapters.perception import probe_capabilities
from config import get_settings
from domain import enrollment as enrollments
from domain.auth import Principal
from main import create_app
from persistence.db import SessionLocal, read_session
from persistence.media import media_path
from persistence.models import Animal, Enrollment, Job, Media
from tests.integration.test_enrollment_flow import API, SARI, _confirm, _create, _process, _reviewed, _upload
from tests.support import OPERATOR
from tests.video_support import write_enrollment_video
from workers import jobs

OPERATOR_PRINCIPAL = Principal(user_id="user-operator", farm_id="farm-wahyu", role="operator", name="A. Pratama")


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory) -> bytes:
    return write_enrollment_video(tmp_path_factory.mktemp("video") / "enroll.mp4").read_bytes()


@pytest.fixture(autouse=True)
def fresh_perception():
    perception.clear_caches()
    yield
    perception.clear_caches()


def _stuck_in_processing(client) -> tuple[str, str]:
    """An enrollment whose job was enqueued but never ran, as after a crash."""
    created = _create(client, "sample-enrollment-001")
    with SessionLocal() as session:
        job = enrollments.start_processing(session, OPERATOR_PRINCIPAL, created["id"])
        session.commit()
        return created["id"], job.id


def _detail(client, enrollment_id) -> dict:
    return client.get(f"{API}/enrollments/{enrollment_id}", headers=OPERATOR).json()


# ----- 2. stuck in processing ---------------------------------------------------------------------------------


def test_restart_fails_interrupted_jobs_and_their_enrollments(client, app):
    enrollment_id, job_id = _stuck_in_processing(client)
    assert _detail(client, enrollment_id)["status"] == "processing"

    with TestClient(create_app()):  # a new process starting on the same database
        pass

    detail = _detail(client, enrollment_id)
    assert detail["status"] == "failed" and detail["review_reasons"] == ["processing_interrupted"]
    job = client.get(f"{API}/jobs/{job_id}", headers=OPERATOR).json()
    assert job["status"] == "failed" and job["error"]["code"] == "interrupted"
    assert client.post(f"{API}/enrollments/{enrollment_id}/retry", headers=OPERATOR).status_code == 201


def test_processing_can_be_retried_and_the_late_job_cannot_save(client):
    enrollment_id, job_id = _stuck_in_processing(client)

    retry = client.post(f"{API}/enrollments/{enrollment_id}/retry", headers=OPERATOR)

    assert retry.status_code == 201
    old = _detail(client, enrollment_id)
    assert old["status"] == "failed" and "superseded_by_retry" in old["review_reasons"]
    jobs.submit(job_id)  # the old job finally runs: its guarded save finds the enrollment no longer processing
    assert client.get(f"{API}/jobs/{job_id}", headers=OPERATOR).json()["status"] == "failed"
    assert _detail(client, enrollment_id)["status"] == "failed"


# ----- 3. stale duplicate check -------------------------------------------------------------------------------


def test_two_enrollments_of_the_same_new_cow(client, video_bytes):
    first = _reviewed(client, video_bytes, "sample-enrollment-001")
    second = _reviewed(client, video_bytes, "sample-enrollment-001")  # both checked against the same herd
    assert _confirm(client, first["id"], SARI).status_code == 200

    stale = _confirm(client, second["id"], SARI)

    assert stale.status_code == 422
    details = stale.json()["error"]["details"]
    assert details["override_required"] == ["herd_changed_since_processing"]
    assert details["changed_animal_ids"] == ["animal-demo-001"]

    linked = _confirm(client, second["id"], {"decision": "link_existing", "link_to": "animal-demo-001",
                                             "override_note": "Same cow filmed twice."})
    assert linked.status_code == 200
    with read_session() as session:
        assert session.scalars(select(Animal.id).where(Animal.name == "Sari")).all() == ["animal-demo-001"]


def test_stale_check_can_be_overridden_or_rerun(client):
    first = _reviewed(client, None, "sample-enrollment-001")
    second = _reviewed(client, None, "sample-enrollment-001")
    assert _confirm(client, first["id"], SARI).status_code == 200

    retry = client.post(f"{API}/enrollments/{second['id']}/retry", headers=OPERATOR).json()
    _process(client, retry["id"])

    rerun = _confirm(client, retry["id"], {**SARI, "animal": {**SARI["animal"], "name": "Sari II"}})
    assert rerun.status_code == 200  # the re-run check saw the current herd


# ----- 4. unverified link -------------------------------------------------------------------------------------


def test_link_to_an_animal_the_matcher_did_not_verify_needs_a_note(client):
    detail = _reviewed(client, None, "sample-enrollment-001")  # identity outcome: new

    refused = _confirm(client, detail["id"], {"decision": "link_existing", "link_to": "animal-demo-002"})
    linked = _confirm(client, detail["id"], {"decision": "link_existing", "link_to": "animal-demo-002",
                                             "override_note": "Ear tag 002 read in the yard."})

    assert refused.status_code == 422
    assert refused.json()["error"]["details"]["override_required"] == ["unverified_link"]
    assert linked.status_code == 200
    decision = linked.json()["decision"]
    assert decision["overrides"] == ["unverified_link"] and decision["matches_candidate"] is False


def test_link_to_another_animal_than_the_candidate_needs_a_note(client):
    detail = _reviewed(client, None, "sample-enrollment-dup")  # candidate: animal-demo-002

    response = _confirm(client, detail["id"], {"decision": "link_existing", "link_to": "animal-demo-003"})

    assert response.status_code == 422
    assert response.json()["error"]["details"]["candidate_animal_id"] == "animal-demo-002"


# ----- 9. retry from review supersedes ------------------------------------------------------------------------


def test_retry_from_review_supersedes_the_original(client):
    detail = _reviewed(client, None, "sample-enrollment-001")

    new = client.post(f"{API}/enrollments/{detail['id']}/retry", headers=OPERATOR).json()

    old = _detail(client, detail["id"])
    assert old["status"] == "rejected"
    assert old["decision"]["reject_reason"] == "superseded_by_retry"
    assert old["decision"]["superseded_by"] == new["id"]
    assert _confirm(client, detail["id"], SARI).status_code == 409


# ----- 5 + 11. uploads ----------------------------------------------------------------------------------------


def test_reupload_replaces_the_previous_video(client, video_bytes):
    created = _create(client)
    assert _upload(client, created["id"], video_bytes).status_code == 200
    with read_session() as session:
        first = session.get(Enrollment, created["id"]).video_media_id
        first_path = media_path(session.get(Media, first))
    assert first_path.is_file()

    assert _upload(client, created["id"], video_bytes + b"\x00").status_code == 200

    with read_session() as session:
        enrollment = session.get(Enrollment, created["id"])
        assert session.get(Media, first) is None
        current = session.get(Media, enrollment.video_media_id)
    assert enrollment.video_media_id != first and not first_path.exists()
    assert media_path(current).stat().st_size == len(video_bytes) + 1
    assert len(current.sha256) == 64


def test_upload_hash_matches_the_bytes(client, video_bytes):
    import hashlib

    created = _create(client)
    _upload(client, created["id"], video_bytes)

    with read_session() as session:
        media = session.get(Media, session.get(Enrollment, created["id"]).video_media_id)
    assert media.sha256 == hashlib.sha256(video_bytes).hexdigest() and media.bytes == len(video_bytes)
    assert not list((get_settings().data_dir / "uploads").glob("*"))  # the spool was moved, not copied


def test_oversize_upload_is_refused_from_its_content_length(client, video_bytes, monkeypatch):
    monkeypatch.setattr(enrollments, "MAX_VIDEO_BYTES", 1000)
    monkeypatch.setattr(enrollment_routes, "MULTIPART_OVERHEAD", 100)

    def never(*args, **kwargs):
        raise AssertionError("the body should not be spooled")

    monkeypatch.setattr(enrollment_routes, "_spool", never)
    created = _create(client)

    response = _upload(client, created["id"], video_bytes)

    assert response.status_code == 422
    assert response.json()["error"]["details"]["max_bytes"] == 1000


def test_failed_attach_leaves_no_media_file(client, video_bytes, monkeypatch):
    created = _create(client)

    def broken(*args, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(enrollments, "attach_video", broken)
    with pytest.raises(RuntimeError):
        _upload(client, created["id"], video_bytes)

    assert not list((get_settings().media_dir / "farm-wahyu").glob("*.mp4"))


# ----- 1. numpy prototype results through the job -------------------------------------------------------------


def test_numpy_weight_result_is_stored(client, video_bytes, monkeypatch):
    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "auto")
    monkeypatch.setattr(perception, "probe_capabilities",
                        lambda: {"video": False, "muzzle": False, "weight": True, "age": True})
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=lambda weights: object()))

    def numpy_estimate(image_bgr, model, marker_cm=15.0, tape_heart_girth_cm=None):
        return {"source": "prototype", "method_version": "weight_side_view_v2", "range_low": np.float64(470.0),
                "range_high": np.float64(540.0), "point_kg": np.float32(505.0), "unit": "kg",
                "review_required": np.bool_(False), "review_reason": None,
                "landmarks_px": {"front_is_left": np.bool_(True), "withers": (np.int64(1), np.int64(2))}}

    monkeypatch.setattr(adapters.weight, "estimate_weight", numpy_estimate)
    get_settings.cache_clear()

    detail = _reviewed(client, video_bytes, "sample-enrollment-001")

    weight = detail["estimates"]["weight"]
    assert weight["source"] == "prototype" and weight["landmarks_px"]["front_is_left"] is True
    assert _confirm(client, detail["id"], SARI).status_code == 200


# ----- 10. generic error messages -----------------------------------------------------------------------------


def test_processing_errors_are_generic(client, monkeypatch):
    def broken(self, *args, **kwargs):
        raise RuntimeError("C:\\secret\\path exploded")

    monkeypatch.setattr(perception.Perception, "extract_views", broken)
    created = _create(client, "sample-enrollment-001")

    job = _process(client, created["id"])

    detail = _detail(client, created["id"])
    job_out = client.get(f"{API}/jobs/{job['job_id']}", headers=OPERATOR).json()
    assert detail["status"] == "failed" and detail["review_reasons"] == ["processing_failed"]
    assert "secret" not in json.dumps(detail) and "secret" not in json.dumps(job_out)
    assert job_out["error"]["code"] == "INTERNAL_ERROR"


# ----- 8. pending animals stay in the gallery -----------------------------------------------------------------


@pytest.mark.skipif(not probe_capabilities()["muzzle"], reason="muzzle model or onnxruntime not available")
def test_pending_animal_is_flagged_when_enrolled_again(client, video_bytes, monkeypatch):
    first = _reviewed(client, video_bytes, None)  # fixture mode, unknown sample: identity uncertain
    confirmed = _confirm(client, first["id"], {**SARI, "override_note": "No matcher on this device."})
    pending_id = confirmed.json()["animal_id"]
    with read_session() as session:
        assert session.get(Animal, pending_id).identity_status == "pending_review"

    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "auto")
    monkeypatch.setattr(perception, "probe_capabilities",
                        lambda: {"video": False, "muzzle": True, "weight": False, "age": True})
    get_settings.cache_clear()
    again = _reviewed(client, video_bytes, None)

    identity = again["identity"]
    assert identity["source"] == "prototype" and identity["outcome"] == "candidate"
    assert identity["animal_id"] == pending_id and identity["animal_identity_status"] == "pending_review"
    assert identity["possible_duplicate"] is True and identity["gallery"]["pending_animals"] == 1


def test_jobs_table_has_no_stuck_rows_after_sync_processing(client):
    _reviewed(client, None, "sample-enrollment-001")

    with read_session() as session:
        statuses = set(session.scalars(select(Job.status)))
    assert statuses == {"succeeded"}
