"""Background job queue on PostgreSQL.

Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED`, so several workers can run without
taking the same job. Failed jobs are retried until `max_attempts`, then marked failed.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import audit
from persistence.models import Job


def enqueue(session: Session, farm_id: uuid.UUID, job_type: str, payload: dict, created_by: uuid.UUID | None) -> Job:
    job = Job(farm_id=farm_id, job_type=job_type, payload=payload, created_by=created_by)
    session.add(job)
    session.flush()
    audit.record(session, farm_id, "job.queued", "job", job.id, actor_id=created_by, details={"job_type": job_type})
    return job


def claim_next(session: Session) -> Job | None:
    job = session.scalars(
        select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)
    ).first()
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    session.commit()
    return job


def succeed(session: Session, job: Job, result: dict) -> None:
    job.status = "succeeded"
    job.result = result
    job.error = None
    job.finished_at = datetime.now(UTC)
    audit.record(session, job.farm_id, "job.succeeded", "job", job.id, actor_type="worker")
    session.commit()


def fail(session: Session, job: Job, error: str, max_attempts: int) -> None:
    job.error = error[:4000]
    if job.attempts < max_attempts:
        job.status = "queued"
        job.started_at = None
    else:
        job.status = "failed"
        job.finished_at = datetime.now(UTC)
        audit.record(session, job.farm_id, "job.failed", "job", job.id, actor_type="worker", details={"error": job.error})
    session.commit()
