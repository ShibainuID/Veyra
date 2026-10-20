"""The persisted job runner: success, failure, sync versus pool mode, and the reset drain."""

import threading

import pytest

from config import get_settings
from domain.errors import DomainError
from persistence.db import SessionLocal, read_session
from persistence.models import Job
from workers import jobs

FARM = "farm-wahyu"


@pytest.fixture
def handlers():
    added = []

    def add(kind, fn):
        jobs.register_handler(kind, fn)
        added.append(kind)

    yield add
    for kind in added:
        jobs._handlers.pop(kind, None)


def _enqueue(kind: str, subject: str = "subject-1") -> str:
    with SessionLocal() as session:
        job = jobs.enqueue(session, FARM, kind, subject)
        assert job.status == "queued"
        session.commit()
        return job.id


def _job(job_id: str) -> Job:
    with read_session() as session:
        return session.get(Job, job_id)


def test_enqueue_requires_a_registered_handler(client):
    with SessionLocal() as session, pytest.raises(ValueError):
        jobs.enqueue(session, FARM, "test.unknown", "x")


def test_sync_job_succeeds_inline_with_its_result(client, handlers):
    seen = {}

    def handler(job_id):
        seen["status_while_running"] = _job(job_id).status
        seen["thread"] = threading.current_thread()
        return {"ok": True}

    handlers("test.ok", handler)
    job_id = _enqueue("test.ok")

    jobs.submit(job_id)

    job = _job(job_id)
    assert (job.status, job.result, job.error) == ("succeeded", {"ok": True}, None)
    assert seen == {"status_while_running": "running", "thread": threading.current_thread()}


@pytest.mark.parametrize(("exc", "code"), [
    (RuntimeError("boom"), "INTERNAL_ERROR"),
    (DomainError("INVALID_STATE", "not now"), "INVALID_STATE"),
])
def test_handler_exception_fails_the_job(client, handlers, exc, code):
    def handler(job_id):
        raise exc

    handlers("test.fail", handler)
    job_id = _enqueue("test.fail")

    jobs.submit(job_id)

    job = _job(job_id)
    assert job.status == "failed"
    assert job.error["code"] == code and job.error["message"]


def test_a_job_runs_once(client, handlers):
    runs = []
    handlers("test.once", lambda job_id: runs.append(job_id))
    job_id = _enqueue("test.once")

    assert jobs.run_job(job_id) == "succeeded"
    assert jobs.run_job(job_id) is None
    assert runs == [job_id]


def test_submit_inline_fails_while_a_writer_is_open(client, handlers):
    handlers("test.ok", lambda job_id: {"ok": True})
    job_id = _enqueue("test.ok")

    with SessionLocal() as session:
        session.get(Job, job_id)  # this thread now holds the write lock
        with pytest.raises(RuntimeError):
            jobs.submit(job_id)


def test_pool_mode_runs_on_a_worker_thread(client, handlers, monkeypatch):
    monkeypatch.setenv("VEYRA_SYNC_JOBS", "0")
    get_settings.cache_clear()
    threads = []
    handlers("test.pool", lambda job_id: threads.append(threading.current_thread().name) or {"n": 1})
    job_id = _enqueue("test.pool")

    jobs.submit(job_id)
    jobs.drain(timeout_s=10)

    assert _job(job_id).status == "succeeded"
    assert threads and threads[0].startswith("veyra-job")


def test_pool_failure_does_not_break_the_pool(client, handlers, monkeypatch):
    monkeypatch.setenv("VEYRA_SYNC_JOBS", "0")
    get_settings.cache_clear()

    def bad(job_id):
        raise ValueError("bad input")

    handlers("test.bad", bad)
    handlers("test.good", lambda job_id: {"fine": True})
    bad_id, good_id = _enqueue("test.bad"), _enqueue("test.good")

    jobs.submit(bad_id)
    jobs.submit(good_id)
    jobs.drain(timeout_s=10)

    assert _job(bad_id).status == "failed"
    assert _job(good_id).status == "succeeded"


def test_reset_drain_cancels_queued_work(client, handlers, monkeypatch):
    monkeypatch.setenv("VEYRA_SYNC_JOBS", "0")
    get_settings.cache_clear()
    release = threading.Event()
    started = threading.Event()

    def slow(job_id):
        started.set()
        release.wait(5)
        return {}

    handlers("test.slow", slow)
    ids = [_enqueue("test.slow", f"s{i}") for i in range(4)]
    for job_id in ids:
        jobs.submit(job_id)
    started.wait(5)
    threading.Timer(0.2, release.set).start()

    jobs.drain(timeout_s=10)

    statuses = [_job(job_id).status for job_id in ids]
    assert "queued" in statuses  # cancelled before running
    assert "running" not in statuses


def test_get_job_is_farm_scoped(client, handlers):
    handlers("test.ok", lambda job_id: {"ok": True})
    job_id = _enqueue("test.ok")

    with read_session() as session:
        assert jobs.get_job(session, FARM, job_id).id == job_id
        with pytest.raises(DomainError) as err:
            jobs.get_job(session, "farm-other", job_id)
    assert err.value.code == "NOT_FOUND"
