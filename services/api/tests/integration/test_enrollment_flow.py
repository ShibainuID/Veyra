"""Enrollment end to end in fixture mode with synchronous jobs: create → upload → process → review → decide."""

from pathlib import Path

import pytest
from sqlalchemy import select

from adapters import perception
from adapters.perception import probe_capabilities
from config import get_settings
from persistence.db import read_session
from persistence.models import Animal, AnimalReference, AuditEvent, Enrollment, Estimate, Media
from tests.support import MANAGER, OPERATOR, OTHER_FARM, VET
from tests.video_support import write_enrollment_video

API = "/api/v1"


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory) -> bytes:
    return write_enrollment_video(tmp_path_factory.mktemp("video") / "enroll.mp4").read_bytes()


def _create(client, sample_key=None, headers=OPERATOR) -> dict:
    body = {"sample_key": sample_key} if sample_key else {}
    response = client.post(f"{API}/enrollments", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, enrollment_id, data, filename="enroll.mp4", content_type="video/mp4", headers=OPERATOR):
    return client.put(f"{API}/enrollments/{enrollment_id}/video", files={"file": (filename, data, content_type)},
                      headers=headers)


def _process(client, enrollment_id, headers=OPERATOR) -> dict:
    response = client.post(f"{API}/enrollments/{enrollment_id}/process", headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def _reviewed(client, video_bytes, sample_key, headers=OPERATOR) -> dict:
    created = _create(client, sample_key, headers)
    if video_bytes is not None:
        assert _upload(client, created["id"], video_bytes, headers=headers).status_code == 200
    _process(client, created["id"], headers)
    detail = client.get(f"{API}/enrollments/{created['id']}", headers=headers).json()
    assert detail["status"] == "review", detail
    return detail


def _confirm(client, enrollment_id, body, headers=OPERATOR):
    return client.post(f"{API}/enrollments/{enrollment_id}/confirm", json=body, headers=headers)


def _events(subject_id=None, animal_id=None) -> list[str]:
    with read_session() as session:
        query = select(AuditEvent.event_type)
        if subject_id:
            query = query.where(AuditEvent.subject_id == subject_id)
        if animal_id:
            query = query.where(AuditEvent.animal_id == animal_id)
        return list(session.scalars(query))


SARI = {"decision": "register_new",
        "animal": {"name": "Sari", "breed": "Bali cattle", "breed_category": "beef", "sex": "F"}}


def test_create_returns_the_upload_target(client):
    created = _create(client, "sample-enrollment-001")

    assert created["status"] == "created"
    assert created["upload"] == {"method": "PUT", "url": f"/api/v1/enrollments/{created['id']}/video"}
    assert "enrollment.created" in _events(created["id"])


def test_unknown_sample_key_is_rejected(client):
    response = client.post(f"{API}/enrollments", json={"sample_key": "sample-nope"}, headers=OPERATOR)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_full_flow_registers_sari(client, video_bytes):
    created = _create(client, "sample-enrollment-001")
    upload = _upload(client, created["id"], video_bytes)
    assert upload.status_code == 200 and upload.json()["status"] == "uploaded"

    job = _process(client, created["id"])

    job_out = client.get(f"{API}/jobs/{job['job_id']}", headers=OPERATOR).json()
    assert job_out["status"] == "succeeded" and job_out["kind"] == "enrollment.process"
    assert job_out["result"]["status"] == "review"
    detail = client.get(f"{API}/enrollments/{created['id']}", headers=OPERATOR).json()
    assert detail["status"] == "review" and detail["processing_mode"] == "fixture"
    assert detail["sources"] == {"views": "simulated", "identity": "simulated", "weight": "simulated",
                                 "age": "simulated"}
    assert detail["capabilities"] == {"video": False, "muzzle": False, "weight": False, "age": True}
    assert detail["review_reasons"] == []
    assert detail["job"] == {"id": job["job_id"], "status": "succeeded"}
    views = detail["manifest"]["views"]
    assert set(views) == {"muzzle", "teeth", "body"}
    for view in views.values():
        assert "path" not in view
        image = client.get(view["url"])
        assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    assert client.get(views["muzzle"]["crop_url"]).status_code == 200
    identity = detail["identity"]
    assert identity["outcome"] == "new" and identity["possible_duplicate"] is False
    assert {c["animal_id"]: c["animal_name"] for c in identity["candidates"]}["animal-demo-002"]
    assert detail["estimates"]["weight"]["range_low"] == 480.0

    confirmed = _confirm(client, created["id"], SARI)

    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["status"] == "confirmed" and body["animal_id"] == "animal-demo-001"
    assert body["reviewer_id"] == "user-operator" and body["decision"]["outcome"] == "register_new"
    with read_session() as session:
        animal = session.get(Animal, "animal-demo-001")
        refs = session.scalars(select(AnimalReference).where(AnimalReference.animal_id == animal.id)).all()
        estimates = {e.kind: e for e in session.scalars(select(Estimate).where(Estimate.animal_id == animal.id))}
        frame_media = {m.id: m for m in session.scalars(select(Media).where(Media.kind.in_(("frame", "crop"))))}
    assert (animal.name, animal.identity_status, animal.confirmed_by) == ("Sari", "confirmed", "user-operator")
    assert animal.enrollment_id == created["id"]
    assert {r.view for r in refs} == {"muzzle", "teeth", "body"}
    assert all(r.media_id in frame_media for r in refs)
    assert next(r for r in refs if r.view == "muzzle").crop_media_id in frame_media
    age, weight = estimates["age"], estimates["weight"]
    assert (age.range_low, age.range_high, age.source, age.unit) == (24, 30, "simulated", "months")
    assert (weight.range_low, weight.range_high, weight.source, weight.unit) == (480, 560, "simulated", "kg")
    assert weight.evidence["enrollment_id"] == created["id"] and weight.evidence["evidence_media_id"]
    events = _events(created["id"])
    for event in ("enrollment.created", "enrollment.video_uploaded", "enrollment.processing_started",
                  "enrollment.processed", "enrollment.confirmed"):
        assert event in events
    assert "animal.registered" in _events(animal_id="animal-demo-001")

    passport = client.get(f"{API}/animals/animal-demo-001/passport", headers=MANAGER).json()
    titles = [line["title"] for line in passport["passbook"]["lines"]]
    assert "Enrolled from guided video" in titles
    enrolled = next(line for line in passport["passbook"]["lines"] if line["title"] == "Enrolled from guided video")
    assert enrolled["stamp"]["kind"] == "confirmed"
    assert passport["valuations"] == []  # the manager confirms valuation inputs separately
    assert all(ref["media_url"] for ref in passport["references"])


def test_confirm_twice_is_invalid_state(client, video_bytes):
    detail = _reviewed(client, None, "sample-enrollment-001")
    assert _confirm(client, detail["id"], SARI).status_code == 200

    again = _confirm(client, detail["id"], SARI)

    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_STATE"


def test_duplicate_needs_an_override_or_a_link(client, video_bytes):
    detail = _reviewed(client, video_bytes, "sample-enrollment-dup")
    assert detail["identity"]["possible_duplicate"] is True
    assert detail["identity"]["animal_name"]
    assert "possible_duplicate" in detail["review_reasons"]

    refused = _confirm(client, detail["id"], {"decision": "register_new"})

    assert refused.status_code == 422
    error = refused.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["override_required"] == ["possible_duplicate"]
    assert error["details"]["candidate_animal_id"] == "animal-demo-002"

    forced = _confirm(client, detail["id"], {"decision": "register_new",
                                             "override_note": "Different ear notch; calf of Bima."})

    assert forced.status_code == 200, forced.text
    new_id = forced.json()["animal_id"]
    assert new_id == "animal-demo-001"
    with read_session() as session:
        animal = session.get(Animal, new_id)
        event = session.scalar(select(AuditEvent).where(AuditEvent.subject_id == detail["id"],
                                                        AuditEvent.event_type == "enrollment.confirmed"))
    assert animal.identity_status == "confirmed" and animal.name == "Unnamed"
    assert event.data["flags"] == ["possible_duplicate_override"]
    assert forced.json()["decision"]["override_note"] == "Different ear notch; calf of Bima."


def test_link_existing_adds_references(client, video_bytes):
    detail = _reviewed(client, video_bytes, "sample-enrollment-dup")
    with read_session() as session:
        before = len(session.scalars(select(AnimalReference).where(
            AnimalReference.animal_id == "animal-demo-002")).all())
        animals_before = len(session.scalars(select(Animal.id)).all())

    linked = _confirm(client, detail["id"], {"decision": "link_existing", "link_to": "animal-demo-002"})

    assert linked.status_code == 200, linked.text
    assert linked.json()["animal_id"] == "animal-demo-002"
    assert linked.json()["decision"]["matches_candidate"] is True
    with read_session() as session:
        refs = session.scalars(select(AnimalReference).where(AnimalReference.animal_id == "animal-demo-002")).all()
        animals_after = len(session.scalars(select(Animal.id)).all())
    assert len(refs) == before + 3
    assert all(r.media_id for r in refs if r.enrollment_id == detail["id"])
    assert animals_after == animals_before
    assert "animal.references_linked" in _events(animal_id="animal-demo-002")
    passport = client.get(f"{API}/animals/animal-demo-002/passport", headers=MANAGER).json()
    assert "Reference frames added" in [line["title"] for line in passport["passbook"]["lines"]]


@pytest.mark.parametrize("link_to", [None, "animal-other-001", "animal-nope"])
def test_link_existing_needs_an_animal_on_this_farm(client, link_to):
    detail = _reviewed(client, None, "sample-enrollment-dup")

    response = _confirm(client, detail["id"], {"decision": "link_existing", "link_to": link_to})

    assert response.status_code == 422 and response.json()["error"]["details"]["field"] == "link_to"


def test_unclear_sample_requires_override_and_stays_pending(client, video_bytes):
    detail = _reviewed(client, video_bytes, "sample-enrollment-unclear")
    assert "muzzle_view_missing" in detail["review_reasons"]
    assert set(detail["manifest"]["views"]) == {"teeth", "body"}

    refused = _confirm(client, detail["id"], {"decision": "register_new"})

    assert refused.status_code == 422
    assert "required_views_missing" in refused.json()["error"]["details"]["override_required"]
    assert refused.json()["error"]["details"]["missing_views"] == ["muzzle"]

    confirmed = _confirm(client, detail["id"], {"decision": "register_new",
                                                "override_note": "Muzzle retake scheduled; register for the herd count."})

    assert confirmed.status_code == 200, confirmed.text
    with read_session() as session:
        animal = session.get(Animal, confirmed.json()["animal_id"])
    assert animal.identity_status == "pending_review" and animal.confirmed_by is None
    assert confirmed.json()["decision"]["identity_status"] == "pending_review"


def test_reject_and_retry_creates_a_linked_enrollment(client, video_bytes):
    detail = _reviewed(client, video_bytes, "sample-enrollment-unclear")

    no_reason = _confirm(client, detail["id"], {"decision": "reject"})
    rejected = _confirm(client, detail["id"], {"decision": "reject", "reject_reason": "Muzzle out of frame."})

    assert no_reason.status_code == 422
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert rejected.json()["decision"]["reject_reason"] == "Muzzle out of frame."
    assert "enrollment.rejected" in _events(detail["id"])

    retry = client.post(f"{API}/enrollments/{detail['id']}/retry", headers=OPERATOR)

    assert retry.status_code == 201
    new = retry.json()
    assert new["status"] == "created" and new["retry_of_id"] == detail["id"]
    assert new["sample_key"] == "sample-enrollment-unclear" and new["id"] != detail["id"]
    old = client.get(f"{API}/enrollments/{detail['id']}", headers=OPERATOR).json()
    assert old["status"] == "rejected"
    listed = client.get(f"{API}/enrollments", params={"status": "created"}, headers=OPERATOR).json()["items"]
    assert [item["id"] for item in listed] == [new["id"]]


def test_retry_is_refused_while_created(client):
    created = _create(client, "sample-enrollment-001")

    response = client.post(f"{API}/enrollments/{created['id']}/retry", headers=OPERATOR)

    assert response.status_code == 409


def test_sample_without_video_processes_without_frames(client):
    detail = _reviewed(client, None, "sample-enrollment-001")

    views = detail["manifest"]["views"]
    assert set(views) == {"muzzle", "teeth", "body"}
    assert all(view["url"] is None and view["media_id"] is None for view in views.values())
    assert views["muzzle"]["crop_url"] is None
    assert "footage_not_attached" in detail["review_reasons"]

    confirmed = _confirm(client, detail["id"], SARI)

    assert confirmed.status_code == 200
    with read_session() as session:
        refs = session.scalars(select(AnimalReference).where(AnimalReference.animal_id == "animal-demo-001")).all()
    assert len(refs) == 3 and all(r.media_id is None for r in refs)


def test_process_requires_video_or_known_sample(client):
    created = _create(client)

    response = client.post(f"{API}/enrollments/{created['id']}/process", headers=OPERATOR)

    assert response.status_code == 422
    assert response.json()["error"]["details"]["reason"] == "video_required"


def test_unknown_sample_video_is_reviewable(client, video_bytes):
    detail = _reviewed(client, video_bytes, None)

    assert detail["identity"]["reason"] == "perception_unavailable"
    assert "fixture_view_assignment" in detail["review_reasons"]
    assert "weight_unavailable" in detail["review_reasons"]
    assert all(view["url"] for view in detail["manifest"]["views"].values())


def test_unreadable_video_fails_the_enrollment(client):
    created = _create(client)
    assert _upload(client, created["id"], b"\x00" * 2048).status_code == 200

    job = _process(client, created["id"])

    detail = client.get(f"{API}/enrollments/{created['id']}", headers=OPERATOR).json()
    assert detail["status"] == "failed" and "video_unreadable" in detail["review_reasons"]
    assert client.get(f"{API}/jobs/{job['job_id']}", headers=OPERATOR).json()["status"] == "succeeded"
    assert client.post(f"{API}/enrollments/{created['id']}/retry", headers=OPERATOR).status_code == 201


def test_octet_stream_mp4_is_accepted_and_exe_rejected(client, video_bytes):
    created = _create(client)

    exe = _upload(client, created["id"], b"MZ\x90\x00", filename="tool.exe", content_type="application/octet-stream")
    html = _upload(client, created["id"], b"<html>", filename="x.mp4", content_type="text/html")
    mp4 = _upload(client, created["id"], video_bytes, filename="clip.MP4", content_type="application/octet-stream")

    assert exe.status_code == 422 and exe.json()["error"]["code"] == "VALIDATION_FAILED"
    assert html.status_code == 422
    assert mp4.status_code == 200
    with read_session() as session:
        enrollment = session.get(Enrollment, created["id"])
        media = session.get(Media, enrollment.video_media_id)
    assert media.content_type == "video/mp4" and media.kind == "video" and Path(media.path).suffix == ".mp4"


def test_upload_after_processing_is_invalid_state(client, video_bytes):
    detail = _reviewed(client, None, "sample-enrollment-001")

    response = _upload(client, detail["id"], video_bytes)

    assert response.status_code == 409


def test_roles_and_farm_scope(client):
    assert client.post(f"{API}/enrollments", json={}, headers=MANAGER).status_code == 201
    created = _create(client, "sample-enrollment-001", headers=OPERATOR)

    vet = client.post(f"{API}/enrollments", json={}, headers=VET)
    vet_read = client.get(f"{API}/enrollments/{created['id']}", headers=VET)
    other = client.get(f"{API}/enrollments/{created['id']}", headers=OTHER_FARM)
    other_process = client.post(f"{API}/enrollments/{created['id']}/process", headers=OTHER_FARM)
    anonymous = client.post(f"{API}/enrollments", json={})

    assert vet.status_code == 403 and vet.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert vet_read.status_code == 403
    assert other.status_code == 404 and other_process.status_code == 404
    assert anonymous.status_code == 401
    other_list = client.get(f"{API}/enrollments", headers=OTHER_FARM).json()["items"]
    assert other_list == []


def test_jobs_are_farm_scoped(client):
    created = _create(client, "sample-enrollment-001")
    job = _process(client, created["id"])

    assert client.get(f"{API}/jobs/{job['job_id']}", headers=VET).status_code == 200
    assert client.get(f"{API}/jobs/{job['job_id']}", headers=OTHER_FARM).status_code == 404


def test_post_enrollment_scenario_numbers_the_next_animal(client):
    assert client.post(f"{API}/demo/reset", params={"scenario": "post-enrollment"},
                       headers=MANAGER).status_code == 200
    detail = _reviewed(client, None, "sample-enrollment-001")

    confirmed = _confirm(client, detail["id"], SARI)

    assert confirmed.json()["animal_id"] == "animal-demo-007"


@pytest.mark.skipif(not probe_capabilities()["muzzle"], reason="muzzle model or onnxruntime not available")
def test_auto_mode_runs_the_real_muzzle_matcher_against_the_herd(client, video_bytes, monkeypatch):
    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "auto")
    monkeypatch.setattr(perception, "probe_capabilities",
                        lambda: {"video": False, "muzzle": True, "weight": False, "age": True})
    get_settings.cache_clear()
    perception.clear_caches()

    first = _reviewed(client, video_bytes, "sample-enrollment-001")

    assert first["sources"]["identity"] == "prototype" and first["sources"]["views"] == "simulated"
    assert first["identity"]["outcome"] == "new" and first["identity"]["reason"] == "empty_gallery"
    assert _confirm(client, first["id"], SARI).status_code == 200

    # Sari's muzzle crop is now in the farm gallery: the same footage enrolled again verifies against it.
    again = _reviewed(client, video_bytes, None)

    identity = again["identity"]
    assert identity["source"] == "prototype"
    assert identity["outcome"] == "candidate" and identity["animal_id"] == "animal-demo-001"
    assert identity["animal_name"] == "Sari" and identity["possible_duplicate"] is True
    assert identity["gallery"]["animals"] == 1
    refused = _confirm(client, again["id"], {"decision": "register_new", "animal": SARI["animal"]})
    assert refused.status_code == 422
    assert "possible_duplicate" in refused.json()["error"]["details"]["override_required"]
