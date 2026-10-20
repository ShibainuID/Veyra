"""Persisted background jobs on an in-process thread pool (plan Section 1: processing runs as persisted jobs).

Usage from a route or domain function:

    job = jobs.enqueue(session, farm_id, "enrollment.process", enrollment_id)   # adds the row
    session.commit()                                                             # the caller commits ...
    session.close()
    jobs.submit(job.id)                                                          # ... and only then submits

`submit` must be called after the caller's writing session has committed and closed. With
`VEYRA_SYNC_JOBS=1` (tests) the job runs inline in the calling thread, and a thread may hold only one
writing transaction (`persistence.db` raises `RuntimeError` on a second), so an open writer would fail the
job. Otherwise it runs on a module `ThreadPoolExecutor(max_workers=2)`.

Status moves `queued → running → succeeded | failed` through guarded updates. A handler is
`fn(job_id) -> dict | None`; its return value is the job `result`. A handler exception marks the job
`failed` with `error = {code, message}` and never escapes into the pool. A demo reset cancels queued
futures and waits briefly for running ones (`persistence.lifecycle` reset hook).
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from config import get_settings
from domain import clock
from domain.errors import DomainError
from domain.ids import new_id
from persistence.db import SessionLocal, read_session
from persistence.lifecycle import register_reset_hook
from persistence.models import Job

JOB_STATUSES = ("queued", "running", "succeeded", "failed")
MAX_WORKERS = 2
RESET_WAIT_S = 10.0

Handler = Callable[[str], dict | None]

logger = logging.getLogger("veyra.jobs")

_handlers: dict[str, Handler] = {}
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_futures: set[Future] = set()


def register_handler(kind: str, fn: Handler | None = None):
    """Register `fn` for `kind`, or use as a decorator: `@register_handler("enrollment.process")`."""

    def register(handler: Handler) -> Handler:
        _handlers[kind] = handler
        return handler

    return register(fn) if fn is not None else register


def enqueue(session: Session, farm_id: str, kind: str, subject_id: str) -> Job:
    """Add a queued job in the caller's transaction. The caller commits, closes, then calls `submit`."""
    if kind not in _handlers:
        raise ValueError(f"no handler registered for job kind {kind!r}")
    job = Job(id=new_id("job"), farm_id=farm_id, kind=kind, subject_id=subject_id, status="queued")
    session.add(job)
    session.flush()
    return job


def submit(job_id: str) -> None:
    """Run the job: inline when `sync_jobs` (no writing session may be open in this thread), else on the pool."""
    if get_settings().sync_jobs:
        run_job(job_id)
        return
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="veyra-job")
        future = _executor.submit(run_job, job_id)
        _futures.add(future)
    future.add_done_callback(_forget)


def _forget(future: Future) -> None:
    with _lock:
        _futures.discard(future)


def _transition(job_id: str, expected: str, status: str, **values) -> bool:
    with SessionLocal() as session:
        changed = session.execute(
            update(Job).where(Job.id == job_id, Job.status == expected)
            .values(status=status, updated_at=clock.now(), **values)
        ).rowcount
        session.commit()
    return changed == 1


def run_job(job_id: str) -> str | None:
    """Claim a queued job, run its handler, and record the outcome. Returns the final status (None if not claimed)."""
    with read_session() as session:
        job = session.get(Job, job_id)
        kind = job.kind if job else None
    if kind is None or not _transition(job_id, "queued", "running"):
        return None
    handler = _handlers.get(kind)
    try:
        if handler is None:
            raise DomainError("INTERNAL_ERROR", f"No handler for job kind {kind!r}.")
        result = handler(job_id)
    except DomainError as exc:
        error = {"code": exc.code, "message": exc.message}
    except Exception as exc:  # a handler bug fails the job, never the pool
        logger.exception("job %s (%s) failed", job_id, kind)
        error = {"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}
    else:
        _transition(job_id, "running", "succeeded", result=result or {}, error=None)
        return "succeeded"
    _transition(job_id, "running", "failed", error=error)
    return "failed"


def get_job(session: Session, farm_id: str, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Job not found.")
    return job


def latest_job(session: Session, kind: str, subject_id: str) -> Job | None:
    return session.scalar(select(Job).where(Job.kind == kind, Job.subject_id == subject_id)
                          .order_by(Job.created_at.desc(), Job.id.desc()).limit(1))


def job_out(job: Job) -> dict:
    return {"id": job.id, "kind": job.kind, "subject_id": job.subject_id, "status": job.status,
            "result": job.result, "error": job.error}


def drain(timeout_s: float = RESET_WAIT_S) -> None:
    """Cancel queued futures and wait up to `timeout_s` for running ones."""
    with _lock:
        pending = list(_futures)
    for future in pending:
        future.cancel()
    running = [f for f in pending if not f.cancelled()]
    if running:
        _, not_done = wait(running, timeout=timeout_s)
        if not_done:
            logger.warning("%d job(s) still running after %.0f s at reset", len(not_done), timeout_s)


register_reset_hook(drain)
