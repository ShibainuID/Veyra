"""Phase 1 API checks: authentication, roles, farm isolation, media hashing, jobs, and audit history."""

import hashlib

from workers.runner import run_once


def test_health_needs_no_token(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_missing_token_returns_prd_error_shape(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_invalid_token_is_rejected(client):
    r = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_returns_role_and_farm(client, make_user):
    user, headers = make_user("operator")
    body = client.get("/api/v1/me", headers=headers).json()
    assert body["role"] == "operator"
    assert body["farm_id"] == str(user.farm_id)


def test_media_upload_stores_sha256_and_audits(client, make_user, settings):
    _, headers = make_user("operator")
    data = b"fake-video-bytes" * 100
    r = client.post("/api/v1/media", params={"kind": "video"}, headers=headers,
                    files={"file": ("cow.mp4", data, "video/mp4")})
    assert r.status_code == 201
    media = r.json()
    assert media["sha256"] == hashlib.sha256(data).hexdigest()
    assert media["size_bytes"] == len(data)

    events = client.get("/api/v1/audit-events", params={"entity_type": "media"}, headers=headers).json()
    assert [e["action"] for e in events] == ["media.uploaded"]
    assert events[0]["details"]["sha256"] == media["sha256"]


def test_upload_over_limit_is_rejected_without_leftover_files(client, make_user, settings):
    _, headers = make_user("operator")
    r = client.post("/api/v1/media", params={"kind": "video"}, headers=headers,
                    files={"file": ("big.mp4", b"x" * (settings.max_upload_bytes + 1), "video/mp4")})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert not any(p.is_file() for p in settings.media_root.rglob("*"))


def test_assessor_cannot_upload_media(client, make_user):
    _, headers = make_user("assessor")
    r = client.post("/api/v1/media", params={"kind": "image"}, headers=headers,
                    files={"file": ("x.jpg", b"img", "image/jpeg")})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_other_farm_cannot_read_media(client, make_user):
    _, headers_a = make_user("operator")
    _, headers_b = make_user("manager")
    media_id = client.post("/api/v1/media", params={"kind": "image"}, headers=headers_a,
                           files={"file": ("x.jpg", b"img", "image/jpeg")}).json()["id"]
    assert client.get(f"/api/v1/media/{media_id}", headers=headers_a).status_code == 200
    r = client.get(f"/api/v1/media/{media_id}", headers=headers_b)
    assert r.status_code == 404


def test_job_runs_through_worker_and_is_audited(client, make_user, db, settings):
    from domain import jobs

    user, headers = make_user("operator")
    with db.sessions() as s:
        job = jobs.enqueue(s, user.farm_id, "echo", {"hello": "cow"}, user.id)
        s.commit()
        job_id = job.id

    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()["status"] == "queued"
    assert run_once(db, settings.job_max_attempts) is True
    body = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "succeeded"
    assert body["result"] == {"echo": {"hello": "cow"}}
    actions = {e["action"] for e in client.get("/api/v1/audit-events", params={"entity_id": str(job_id)},
                                               headers=headers).json()}
    assert actions == {"job.queued", "job.succeeded"}


def test_unknown_job_type_is_retried_then_failed(client, make_user, db, settings):
    from domain import jobs

    user, headers = make_user("operator")
    with db.sessions() as s:
        job_id = jobs.enqueue(s, user.farm_id, "does-not-exist", {}, user.id).id
        s.commit()
    run_once(db, settings.job_max_attempts)
    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()["status"] == "queued"
    run_once(db, settings.job_max_attempts)
    body = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "failed"
    assert body["attempts"] == settings.job_max_attempts
    assert "no handler" in body["error"]
    assert run_once(db, settings.job_max_attempts) is False


def test_audit_events_are_farm_scoped(client, make_user, db):
    _, headers_a = make_user("operator")
    user_b, headers_b = make_user("operator")
    client.post("/api/v1/media", params={"kind": "image"}, headers=headers_a,
                files={"file": ("x.jpg", b"img", "image/jpeg")})
    assert client.get("/api/v1/audit-events", headers=headers_b).json() == []


def test_same_farm_users_share_records(client, make_user, db):
    user, headers = make_user("operator")
    _, manager_headers = make_user("manager", farm_id=user.farm_id)
    media_id = client.post("/api/v1/media", params={"kind": "image"}, headers=headers,
                           files={"file": ("x.jpg", b"img", "image/jpeg")}).json()["id"]
    assert client.get(f"/api/v1/media/{media_id}", headers=manager_headers).status_code == 200
