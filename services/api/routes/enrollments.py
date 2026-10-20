"""Guided-video enrollment (plan Section 5: `/enrollments`). Managers and operators only; farm-scoped.

Writes use explicit `SessionLocal()` blocks instead of the `get_session` dependency where a job is submitted:
the job may run inline in this thread (`VEYRA_SYNC_JOBS=1`), so the request's writing session must be
committed and closed before `jobs.submit`. Large uploads are streamed to a temp file before any writing
transaction opens.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

import workers.enrollment_job  # noqa: F401  (registers the `enrollment.process` handler)
from config import get_settings
from domain import enrollment as enrollments
from domain.auth import ENROLLERS, Principal
from domain.errors import DomainError
from persistence.db import SessionLocal, get_read_session, read_session
from routes.deps import require_roles
from schemas import error_responses
from schemas_enrollment import (
    ConfirmBody,
    EnrollmentCreate,
    EnrollmentCreated,
    EnrollmentList,
    EnrollmentOut,
    EnrollmentStatus,
    JobAccepted,
)
from workers import jobs

router = APIRouter(prefix="/enrollments", tags=["enrollments"])
enroller = require_roles(*ENROLLERS)
_CHUNK = 1 << 20


def _created(enrollment) -> dict:
    return {"id": enrollment.id, "status": enrollment.status, "sample_key": enrollment.sample_key,
            "retry_of_id": enrollment.retry_of_id,
            "upload": {"method": "PUT", "url": f"/api/v1/enrollments/{enrollment.id}/video"}}


def _detail(farm_id: str, enrollment_id: str) -> dict:
    with read_session() as session:
        return enrollments.get_enrollment(session, farm_id, enrollment_id)


@router.post("", status_code=201, response_model=EnrollmentCreated, responses=error_responses(401, 403, 422))
def create_enrollment(body: EnrollmentCreate | None = None, principal: Principal = Depends(enroller)) -> dict:
    with SessionLocal() as session:
        enrollment = enrollments.create(session, principal, body.sample_key if body else None)
        session.commit()
        return _created(enrollment)


@router.get("", response_model=EnrollmentList, responses=error_responses(401, 403, 422))
def list_enrollments(status: EnrollmentStatus | None = None, principal: Principal = Depends(enroller),
                     session: Session = Depends(get_read_session)) -> dict:
    return {"items": enrollments.list_enrollments(session, principal.farm_id, status)}


@router.get("/{enrollment_id}", response_model=EnrollmentOut, responses=error_responses(401, 403, 404))
def get_enrollment(enrollment_id: str, principal: Principal = Depends(enroller),
                   session: Session = Depends(get_read_session)) -> dict:
    return enrollments.get_enrollment(session, principal.farm_id, enrollment_id)


def _spool(upload: UploadFile, ext: str) -> Path:
    """Copy the upload to a temp file named `*.ext` (the stored media takes its extension), enforcing the cap."""
    upload_dir = get_settings().data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=upload_dir, suffix=f".{ext}", delete=False)
    size = 0
    try:
        with handle:
            while chunk := upload.file.read(_CHUNK):
                size += len(chunk)
                if size > enrollments.MAX_VIDEO_BYTES:
                    raise DomainError("VALIDATION_FAILED", "The video is larger than 200 MB.",
                                      {"max_bytes": enrollments.MAX_VIDEO_BYTES})
                handle.write(chunk)
        if size == 0:
            raise DomainError("VALIDATION_FAILED", "The uploaded video is empty.", {"bytes": 0})
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return Path(handle.name)


@router.put("/{enrollment_id}/video", response_model=EnrollmentOut,
            responses=error_responses(401, 403, 404, 409, 422))
def upload_video(enrollment_id: str, file: UploadFile = File(...), principal: Principal = Depends(enroller)) -> dict:
    with read_session() as session:
        enrollments.check_uploadable(session, principal.farm_id, enrollment_id)
    content_type, ext = enrollments.resolve_video_type(file.content_type, file.filename)
    spooled = _spool(file, ext)
    try:
        with SessionLocal() as session:
            enrollments.attach_video(session, principal, enrollment_id, spooled, content_type)
            session.commit()
    finally:
        spooled.unlink(missing_ok=True)
    return _detail(principal.farm_id, enrollment_id)


@router.post("/{enrollment_id}/process", status_code=202, response_model=JobAccepted,
             responses=error_responses(401, 403, 404, 409, 422))
def process_enrollment(enrollment_id: str, principal: Principal = Depends(enroller)) -> dict:
    with SessionLocal() as session:
        job = enrollments.start_processing(session, principal, enrollment_id)
        session.commit()
        job_id = job.id
    jobs.submit(job_id)  # after the writing session closed: a sync job runs in this thread
    return {"job_id": job_id}


@router.post("/{enrollment_id}/confirm", response_model=EnrollmentOut,
             responses=error_responses(401, 403, 404, 409, 422))
def confirm_enrollment(enrollment_id: str, body: ConfirmBody, principal: Principal = Depends(enroller)) -> dict:
    with SessionLocal() as session:
        enrollments.confirm(session, principal, enrollment_id, body.model_dump())
        session.commit()
    return _detail(principal.farm_id, enrollment_id)


@router.post("/{enrollment_id}/retry", status_code=201, response_model=EnrollmentCreated,
             responses=error_responses(401, 403, 404, 409))
def retry_enrollment(enrollment_id: str, principal: Principal = Depends(enroller)) -> dict:
    with SessionLocal() as session:
        enrollment = enrollments.retry(session, principal, enrollment_id)
        session.commit()
        return _created(enrollment)

