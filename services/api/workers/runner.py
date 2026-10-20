"""Job worker loop: `python -m workers.runner` from services/api.

Handlers are registered by job type. A handler receives the session, the job, and a context with
settings and media storage, and returns a JSON-serialisable result; raising marks the attempt failed.
"""

import importlib
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from config import Settings
from domain import jobs
from persistence.db import Database
from persistence.models import Job
from persistence.storage import MediaStore


@dataclass
class WorkerContext:
    settings: Settings
    media: MediaStore


Handler = Callable[[Session, Job, WorkerContext], dict]
HANDLERS: dict[str, Handler] = {}
# Modules that register handlers on import.
HANDLER_MODULES = ("domain.enrollment", "domain.monitoring")
log = logging.getLogger("veyra.worker")


def handler(job_type: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn

    return register


@handler("echo")
def _echo(_session: Session, job: Job, _ctx: WorkerContext) -> dict:
    """Health-check job type: returns its payload."""
    return {"echo": job.payload}


def load_handlers() -> None:
    for module in HANDLER_MODULES:
        importlib.import_module(module)


def run_once(db: Database, ctx: WorkerContext) -> bool:
    """Process one queued job. Returns False when the queue is empty."""
    load_handlers()
    with db.sessions() as session:
        job = jobs.claim_next(session)
        if job is None:
            return False
        fn = HANDLERS.get(job.job_type)
        try:
            if fn is None:
                raise LookupError(f"no handler for job type {job.job_type!r}")
            result = fn(session, job, ctx)
            jobs.succeed(session, job, result)
            log.info("job %s (%s) succeeded", job.id, job.job_type)
        except Exception:
            session.rollback()
            job = session.get(Job, job.id)
            jobs.fail(session, job, traceback.format_exc(), ctx.settings.job_max_attempts)
            log.exception("job %s (%s) failed on attempt %s", job.id, job.job_type, job.attempts)
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    db = Database(settings.database_url)
    ctx = WorkerContext(settings, MediaStore(settings.media_root, settings.max_upload_bytes))
    log.info("worker started")
    while True:
        if not run_once(db, ctx):
            time.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    main()
