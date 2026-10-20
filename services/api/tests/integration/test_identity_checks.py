"""Claim-time muzzle identity check: a death claim needs a re-scan that matches the enrolled animal."""

import cv2
import pytest
from sqlalchemy import select

import adapters.muzzle
from adapters import perception
from adapters.perception import probe_capabilities
from config import get_settings
from persistence.db import SessionLocal, read_session
from persistence.media import store_bytes
from persistence.models import AnimalReference, AuditEvent, IdentityCheck
from tests.integration.test_claims import BIMA, _alert, _draft, _finding, _incident
from tests.integration.test_financial_flow import approved, error_code, execute, propose, propose_ok
from tests.support import ASSESSOR, MANAGER, OPERATOR, OTHER_FARM, VET
from tests.video_support import textured_image, write_enrollment_video

API = "/api/v1"


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory) -> bytes:
    return write_enrollment_video(tmp_path_factory.mktemp("video") / "scan.mp4").read_bytes()


def _png(seed: int = 7) -> bytes:
    ok, data = cv2.imencode(".png", textured_image(seed=seed))
    assert ok
    return data.tobytes()


def _death_claim(client, animal_id=BIMA) -> dict:
    """A death claim with everything but the identity check in place."""
    incident = _incident(client, animal_id=animal_id, kind="death", linked_alert_ids=[_alert(animal_id=animal_id)],
                         description="Found dead in Pen A at the morning check.").json()
    claim = _draft(client, incident["id"]).json()
    assert _finding(client, incident["id"]).status_code == 201
    patched = client.patch(f"{API}/claims/{claim['id']}", json={"declaration_confirmed": True}, headers=MANAGER)
    assert patched.status_code == 200, patched.text
    return patched.json()


def _sample(client, claim_id, sample, headers=OPERATOR):
    return client.post(f"{API}/claims/{claim_id}/identity-checks", json={"sample": sample}, headers=headers)


def _upload(client, claim_id, data, filename="muzzle.png", content_type="image/png", headers=OPERATOR):
    return client.post(f"{API}/claims/{claim_id}/identity-checks", files={"file": (filename, data, content_type)},
                       headers=headers)


def _item(claim: dict, key="identity_verified") -> dict | None:
    return next((item for item in claim["checklist"] if item["key"] == key), None)


def _attach_reference(animal_id: str = BIMA) -> None:
    """Give the animal's seeded muzzle reference a crop on disk, so the matcher has something to compare with."""
    with SessionLocal() as session:
        media = store_bytes(session, "farm-wahyu", "crop", _png(seed=11), "image/png", "png")
        ref = session.scalars(select(AnimalReference).where(AnimalReference.animal_id == animal_id,
                                                            AnimalReference.view == "muzzle")).first()
        ref.crop_media_id = media.id
        session.commit()


@pytest.fixture
def matcher(monkeypatch):
    """The muzzle capability on, with a fake identifier whose answer the test sets."""
    answer = {"outcome": "candidate", "reason": None, "animal_id": BIMA,
              "candidates": [{"animal_id": BIMA, "inliers": 41, "cosine": 0.91}]}

    class FakeIdentifier:
        def __init__(self, model_path):
            pass

        def reference(self, image_id, crop_bgr):
            return f"ref:{image_id}"

        def check_duplicate(self, crop_bgr, gallery):
            answer["gallery"] = {a: list(r) for a, r in gallery.animals.items()}
            answer["crop_shape"] = crop_bgr.shape
            return {"source": "prototype", "method_version": "muzzle_hybrid_v1", "accept_inliers": 5,
                    "possible_duplicate": True, **{k: v for k, v in answer.items()
                                                   if k not in ("gallery", "crop_shape")}}

    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "auto")
    monkeypatch.setattr(perception, "probe_capabilities",
                        lambda: {"video": False, "muzzle": True, "weight": False, "age": True})
    monkeypatch.setattr(adapters.muzzle, "MuzzleIdentifier", FakeIdentifier)
    get_settings.cache_clear()
    perception.clear_caches()
    yield answer
    perception.clear_caches()


def test_death_claim_requires_the_identity_check(client):
    claim = _death_claim(client)
    item = _item(claim)
    assert claim["identity_check_required"] is True and claim["incident_kind"] == "death"
    assert item["status"] == "missing" and item["detail"] == "Not scanned yet"
    assert item["label"] == "Muzzle re-scan matches the enrolled animal"
    assert claim["missing"] == ["identity_verified"] and claim["status"] == "draft"
    response = propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert error_code(response) == "EVIDENCE_INCOMPLETE"
    assert response.json()["error"]["details"]["missing"] == ["identity_verified"]


def test_non_death_incident_does_not_require_it(client):
    incident = _incident(client).json()  # accidental_injury
    claim = _draft(client, incident["id"]).json()
    assert _item(claim) is None and claim["identity_check_required"] is False


def test_sample_match_completes_the_checklist_and_submits(client):
    claim = _death_claim(client)
    response = _sample(client, claim["id"], "match")
    assert response.status_code == 201, response.text
    check, after = response.json()["check"], response.json()["claim"]
    assert (check["outcome"], check["source"], check["input"]) == ("match", "simulated", "sample")
    assert check["matched_animal_id"] == BIMA and check["inliers"] == 38 and check["checked_by"] == "user-operator"
    assert check["reference"]["reference_id"] and check["scan"]["media_url"] is None
    assert _item(after)["status"] == "present" and _item(after)["ref"] == check["id"]
    assert after["status"] == "ready" and after["missing"] == []

    action = approved(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert "identity_check" in {i["type"] for i in action["evidence_manifest"]["items"]}
    assert execute(client, action["id"], "claim-key").json()["status"] == "succeeded"
    with read_session() as session:
        event = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "claim.identity_checked")).one()
    assert (event.actor_type, event.actor_id, event.data["outcome"], event.data["source"]) == (
        "user", "user-operator", "match", "simulated")
    lines = client.get(f"{API}/animals/{BIMA}/passport", headers=MANAGER).json()["passbook"]["lines"]
    line = next(line for line in lines if line["event_type"] == "claim.identity_checked")
    assert line["title"] == "Identity checked at claim · match" and line["stamp"]["kind"] == "confirmed"


def test_sample_mismatch_blocks_submission_with_the_reason(client):
    claim = _death_claim(client)
    check = _sample(client, claim["id"], "mismatch").json()["check"]
    assert check["outcome"] == "mismatch" and check["matched_animal_id"] == "animal-demo-003"
    assert check["matched_animal_name"] == "Melati" and "Melati" in check["reason"]

    response = propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    assert error_code(response) == "EVIDENCE_INCOMPLETE"
    stored = client.get(f"{API}/claims/{claim['id']}", headers=ASSESSOR).json()
    assert stored["blocked_reason"]["missing"] == ["identity_verified"]
    item = _item(stored)
    assert item["status"] == "missing" and "Muzzle scan matched Melati" in item["detail"]
    assert [c["outcome"] for c in stored["identity_checks"]] == ["mismatch"]


def test_later_mismatch_makes_an_approved_submission_stale(client):
    claim = _death_claim(client)
    _sample(client, claim["id"], "match")
    action = approved(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    _sample(client, claim["id"], "mismatch")

    assert error_code(execute(client, action["id"], "claim-key")) == "APPROVAL_STALE"
    stored = client.get(f"{API}/claims/{claim['id']}", headers=MANAGER).json()
    assert [c["outcome"] for c in stored["identity_checks"]] == ["mismatch", "match"]  # newest first
    assert stored["status"] == "draft"


def test_upload_match_with_the_matcher(client, matcher):
    _attach_reference()
    claim = _death_claim(client)
    response = _upload(client, claim["id"], _png())
    assert response.status_code == 201, response.text
    check = response.json()["check"]
    assert (check["outcome"], check["source"], check["input"], check["inliers"]) == ("match", "prototype", "photo", 41)
    assert check["scan"]["media_url"] and check["scan"]["crop_url"] and check["reference"]["crop_url"]
    assert client.get(check["scan"]["crop_url"]).status_code == 200
    # The guide-box crop: 90% of the width at 1.18 aspect, clamped to the 240 px height (240 x 283).
    assert matcher["crop_shape"][:2] == (240, int(240 * 1.18))
    assert BIMA in matcher["gallery"]
    assert _item(response.json()["claim"])["status"] == "present"
    propose_ok(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])


def test_upload_matching_another_animal_is_a_mismatch(client, matcher):
    _attach_reference()
    matcher.update(animal_id="animal-demo-003",
                   candidates=[{"animal_id": "animal-demo-003", "inliers": 33, "cosine": 0.9},
                               {"animal_id": BIMA, "inliers": 2, "cosine": 0.4}])
    claim = _death_claim(client)
    check = _upload(client, claim["id"], _png()).json()["check"]
    assert check["outcome"] == "mismatch" and check["matched_animal_id"] == "animal-demo-003"
    assert check["reason"] == "Muzzle scan matched Melati (animal-demo-003), not Bima" and check["inliers"] == 33


def test_upload_without_a_verified_match_is_a_mismatch(client, matcher):
    _attach_reference()
    matcher.update(outcome="new", reason="no_verified_match", animal_id=None,
                   candidates=[{"animal_id": BIMA, "inliers": 3, "cosine": 0.5}])
    claim = _death_claim(client)
    check = _upload(client, claim["id"], _png()).json()["check"]
    assert (check["outcome"], check["reason"]) == ("mismatch", "No verified match to this animal")
    assert error_code(propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])) == "EVIDENCE_INCOMPLETE"


def test_uncertain_upload_blocks_and_asks_for_a_retake(client, matcher):
    _attach_reference()
    matcher.update(outcome="uncertain", reason="ambiguous_match", animal_id=None)
    claim = _death_claim(client)
    response = _upload(client, claim["id"], _png())
    after = response.json()["claim"]
    assert response.json()["check"]["outcome"] == "uncertain"
    assert _item(after)["status"] == "missing" and "retake the scan" in _item(after)["detail"]
    assert error_code(propose(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])) == "EVIDENCE_INCOMPLETE"


def test_no_enrolled_image_is_uncertain_not_a_mismatch(client, matcher):
    matcher.update(outcome="new", reason="empty_gallery", animal_id=None, candidates=[])
    claim = _death_claim(client)  # Bima's seeded references carry no footage
    check = _upload(client, claim["id"], _png()).json()["check"]
    assert check["outcome"] == "uncertain" and check["reason"] == "Bima has no enrolled muzzle image to compare with"


def test_upload_without_the_matcher_is_uncertain_and_simulated(client, video_bytes):
    claim = _death_claim(client)
    check = _upload(client, claim["id"], video_bytes, "scan.mp4", "video/mp4").json()["check"]
    assert (check["outcome"], check["source"], check["input"]) == ("uncertain", "simulated", "video")
    assert check["scan"]["crop_url"] and check["scan"]["content_type"] == "video/mp4"


def test_roles_scope_and_inputs(client):
    claim = _death_claim(client)
    assert _sample(client, claim["id"], "match", headers=VET).status_code == 403
    assert _sample(client, claim["id"], "match", headers=ASSESSOR).status_code == 403
    assert _sample(client, claim["id"], "match", headers=OTHER_FARM).status_code == 404
    assert client.post(f"{API}/claims/{claim['id']}/identity-checks", json={"sample": "maybe"},
                       headers=OPERATOR).status_code == 422
    bad = _upload(client, claim["id"], b"MZ...", "tool.exe", "application/x-msdownload")
    assert bad.status_code == 422 and error_code(bad) == "VALIDATION_FAILED"
    assert client.post(f"{API}/claims/{claim['id']}/identity-checks", content=b"x",
                       headers={**OPERATOR, "Content-Type": "text/plain"}).status_code == 422
    assert _sample(client, claim["id"], "match", headers=MANAGER).status_code == 201
    with read_session() as session:
        assert len(session.scalars(select(IdentityCheck)).all()) == 1


def test_submitted_claim_cannot_be_rechecked(client):
    claim = _death_claim(client)
    _sample(client, claim["id"], "match")
    action = approved(client, action_type="CLAIM_SUBMISSION", claim_id=claim["id"])
    execute(client, action["id"], "claim-key")
    response = _sample(client, claim["id"], "mismatch")
    assert response.status_code == 409 and error_code(response) == "INVALID_STATE"


@pytest.mark.skipif(not probe_capabilities()["muzzle"], reason="muzzle model or onnxruntime not available")
def test_real_matcher_matches_the_enrolled_muzzle(client, video_bytes, monkeypatch):
    monkeypatch.setenv("VEYRA_PERCEPTION_MODE", "auto")
    monkeypatch.setattr(perception, "probe_capabilities",
                        lambda: {"video": False, "muzzle": True, "weight": False, "age": True})
    get_settings.cache_clear()
    perception.clear_caches()
    # Enroll the footage and link it to Bima, so Bima's passport holds a muzzle crop on disk.
    created = client.post(f"{API}/enrollments", json={}, headers=OPERATOR).json()
    assert client.put(f"{API}/enrollments/{created['id']}/video", files={"file": ("e.mp4", video_bytes, "video/mp4")},
                      headers=OPERATOR).status_code == 200
    assert client.post(f"{API}/enrollments/{created['id']}/process", headers=OPERATOR).status_code == 202
    linked = client.post(f"{API}/enrollments/{created['id']}/confirm", headers=OPERATOR,
                         json={"decision": "link_existing", "link_to": BIMA, "override_note": "Bima's own footage"})
    assert linked.status_code == 200, linked.text

    claim = _death_claim(client)
    check = _upload(client, claim["id"], video_bytes, "scan.mp4", "video/mp4").json()["check"]

    assert (check["outcome"], check["source"], check["method_version"]) == ("match", "prototype", "muzzle_hybrid_v1")
    assert check["inliers"] > check["accept_inliers"]
    perception.clear_caches()
