"""Phase 2: enrollment video -> passport -> confirmed weight -> valuation, with the PRD's review rules."""

API = "/api/v1"


def enroll(client, headers, worker, video: str, **inputs) -> dict:
    """Create an enrollment, upload a fake video, process it, and return the enrollment body."""
    e = client.post(f"{API}/enrollments", json={"sample_key": "sample-enrollment-001", **inputs}, headers=headers)
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    r = client.post(f"{API}/enrollments/{eid}/video", headers=headers, files={"file": ("cow.mp4", video.encode(), "video/mp4")})
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/enrollments/{eid}/process", headers=headers)
    assert r.status_code == 202, r.text
    assert client.get(f"{API}/jobs/{r.json()['job_id']}", headers=headers).json()["status"] == "queued"
    worker()
    return client.get(f"{API}/enrollments/{eid}", headers=headers).json()


def confirm(client, headers, eid, **body):
    return client.post(f"{API}/enrollments/{eid}/confirm", json={"decision": "new_animal", **body}, headers=headers)


def test_full_enrollment_to_valuation(client, make_user, worker):
    operator, op = make_user("operator")
    _, mgr = make_user("manager", farm_id=operator.farm_id)

    e = enroll(client, op, worker, "COW:bella")
    assert e["status"] == "ready"
    assert e["review_reasons"] == []
    assert e["identity_result"]["outcome"] == "new"
    assert "reference" not in e["identity_result"]
    assert {"muzzle", "teeth", "body"} <= set(e["manifest"]["views"])
    assert e["estimate_results"]["age"]["source"] == "simulated"

    r = confirm(client, op, e["id"])
    assert r.status_code == 200, r.text
    animal = r.json()
    assert animal["display_id"] == "animal-001"

    p = client.get(f"{API}/animals/{animal['animal_id']}/passport", headers=op).json()
    assert p["identity"]["status"] == "confirmed"
    assert len(p["identity"]["references"]) == 1
    weight = p["estimates"]["weight"]["current"]
    assert (weight["range_low"], weight["range_high"], weight["source"]) == (480.0, 560.0, "prototype")
    assert p["estimates"]["age"]["current"]["range_low"] == 24
    assert p["last_observed"] is None and p["policies"] == []

    r = client.post(f"{API}/animals/{animal['animal_id']}/valuations", json={"weight_estimate_id": weight["id"]}, headers=mgr)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "EVIDENCE_INCOMPLETE"

    r = client.post(f"{API}/animals/{animal['animal_id']}/estimates/{weight['id']}/confirm", json={}, headers=mgr)
    assert r.status_code == 200 and r.json()["confirmed"]

    r = client.post(f"{API}/animals/{animal['animal_id']}/valuations", json={"weight_estimate_id": weight["id"]}, headers=mgr)
    assert r.status_code == 201, r.text
    v = r.json()
    assert (v["currency"], v["unit_price_minor_per_kg"]) == ("USD", 400)
    assert (v["value_low_minor"], v["value_high_minor"]) == (480 * 400, 560 * 400)
    assert "not a market quote" in v["price_source"]

    actions = [h["action"] for h in client.get(f"{API}/animals/{animal['animal_id']}/passport", headers=op).json()["history"]]
    assert {"animal.created", "animal.reference_added", "estimate.confirmed", "valuation.created"} <= set(actions)


def test_rescan_matches_existing_animal_and_blocks_silent_duplicate(client, make_user, worker):
    _, op = make_user("operator")
    first = enroll(client, op, worker, "COW:bella")
    animal_id = confirm(client, op, first["id"]).json()["animal_id"]

    again = enroll(client, op, worker, "COW:bella")
    assert again["identity_result"]["outcome"] == "candidate"
    assert again["identity_result"]["animal_id"] == animal_id
    assert "possible_duplicate_registration" in again["review_reasons"]

    r = confirm(client, op, again["id"])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "APPROVAL_REQUIRED"

    r = confirm(client, op, again["id"], decision="existing_animal", animal_id=animal_id, acknowledge_review=True)
    assert r.status_code == 200
    assert r.json()["display_id"] == "animal-001"
    p = client.get(f"{API}/animals/{animal_id}/passport", headers=op).json()
    assert len(p["identity"]["references"]) == 2
    assert len(p["estimates"]["weight"]["history"]) == 2


def test_new_animal_over_a_match_needs_explicit_acknowledgement(client, make_user, worker):
    _, op = make_user("operator")
    confirm(client, op, enroll(client, op, worker, "COW:bella")["id"])
    again = enroll(client, op, worker, "COW:bella")
    r = confirm(client, op, again["id"], acknowledge_review=True)
    assert r.status_code == 200
    assert r.json()["display_id"] == "animal-002"


def test_incomplete_evidence_requires_acknowledgement(client, make_user, worker):
    _, op = make_user("operator")
    e = enroll(client, op, worker, "COW:daisy CUT NOTEETH")
    assert e["status"] == "needs_review"
    assert {"scene_cut_detected", "teeth_view_missing", "age_teeth_view_missing"} <= set(e["review_reasons"])
    r = confirm(client, op, e["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "APPROVAL_REQUIRED"
    assert confirm(client, op, e["id"], acknowledge_review=True).status_code == 200


def test_missing_muzzle_cannot_confirm_identity(client, make_user, worker):
    _, op = make_user("operator")
    e = enroll(client, op, worker, "COW:daisy NOMUZZLE")
    assert "muzzle_view_missing" in e["review_reasons"]
    r = confirm(client, op, e["id"], acknowledge_review=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "EVIDENCE_INCOMPLETE"


def test_missing_marker_leaves_weight_for_review(client, make_user, worker):
    _, op = make_user("operator")
    e = enroll(client, op, worker, "COW:daisy NOMARKER")
    assert e["estimate_results"]["weight"]["review_required"]
    assert "weight_marker_not_detected" in e["review_reasons"]


def test_manager_override_keeps_original_estimate(client, make_user, worker):
    operator, op = make_user("operator")
    _, mgr = make_user("manager", farm_id=operator.farm_id)
    animal_id = confirm(client, op, enroll(client, op, worker, "COW:bella")["id"]).json()["animal_id"]
    original = client.get(f"{API}/animals/{animal_id}/passport", headers=op).json()["estimates"]["weight"]["current"]
    r = client.post(f"{API}/animals/{animal_id}/estimates/{original['id']}/confirm",
                    json={"range_low": 500, "range_high": 520, "note": "scale weight 510 kg"}, headers=mgr)
    assert r.status_code == 200
    weights = client.get(f"{API}/animals/{animal_id}/passport", headers=op).json()["estimates"]["weight"]
    assert weights["current"]["source"] == "manual"
    assert weights["current"]["supersedes_id"] == original["id"]
    assert [h["source"] for h in weights["history"]] == ["prototype", "manual"]


def test_operator_cannot_confirm_estimates_or_value(client, make_user, worker):
    _, op = make_user("operator")
    animal_id = confirm(client, op, enroll(client, op, worker, "COW:bella")["id"]).json()["animal_id"]
    weight_id = client.get(f"{API}/animals/{animal_id}/passport", headers=op).json()["estimates"]["weight"]["current"]["id"]
    assert client.post(f"{API}/animals/{animal_id}/estimates/{weight_id}/confirm", json={}, headers=op).status_code == 403
    assert client.post(f"{API}/animals/{animal_id}/valuations", json={"weight_estimate_id": weight_id},
                       headers=op).status_code == 403


def test_gallery_and_records_are_scoped_to_farm(client, make_user, worker):
    _, farm_a = make_user("operator")
    _, farm_b = make_user("operator")
    e_a = enroll(client, farm_a, worker, "COW:bella")
    animal_id = confirm(client, farm_a, e_a["id"]).json()["animal_id"]

    e_b = enroll(client, farm_b, worker, "COW:bella")
    assert e_b["identity_result"]["outcome"] == "new"
    assert client.get(f"{API}/enrollments/{e_a['id']}", headers=farm_b).status_code == 404
    assert client.get(f"{API}/animals/{animal_id}/passport", headers=farm_b).status_code == 404
    assert client.get(f"{API}/animals", headers=farm_b).json() == []


def test_processing_failure_marks_enrollment_failed(client, make_user, worker):
    _, op = make_user("operator")
    e = enroll(client, op, worker, "COW:bella CRASH")
    assert e["status"] == "failed"
    job = client.get(f"{API}/jobs/{e['process_job_id']}", headers=op).json()
    assert job["status"] == "failed" and "simulated perception failure" in job["error"]


def test_process_requires_uploaded_video(client, make_user):
    _, op = make_user("operator")
    eid = client.post(f"{API}/enrollments", json={}, headers=op).json()["id"]
    r = client.post(f"{API}/enrollments/{eid}/process", headers=op)
    assert r.status_code == 409


def test_reject_closes_enrollment(client, make_user, worker):
    _, op = make_user("operator")
    e = enroll(client, op, worker, "COW:bella CUT")
    r = client.post(f"{API}/enrollments/{e['id']}/reject", json={"reason": "two animals in frame"}, headers=op)
    assert r.json()["status"] == "rejected"
    assert confirm(client, op, e["id"], acknowledge_review=True).status_code == 409
