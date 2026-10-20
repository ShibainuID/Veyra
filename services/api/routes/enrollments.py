"""Guided-video enrollment (`/enrollments`). Managers and operators only; farm-scoped.

Writes use explicit `SessionLocal()` blocks instead of the `get_session` dependency where a job is submitted:
the job may run inline in this thread (`VEYRA_SYNC_JOBS=1`), so the request's writing session must be
committed and closed before `jobs.submit`. Large uploads are streamed to a temp file before any writing
transaction opens.
"""

import hashlib
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

import workers.enrollment_job  # noqa: F401  (registers the `enrollment.process` handler)
from config import get_settings
from domain import enrollment as enrollments
from domain.auth import ENROLLERS, Principal
from domain.errors import DomainError
from persistence.db import SessionLocal, get_read_session, read_session
from persistence.media import media_path, place_file
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
MULTIPART_OVERHEAD = 1 << 20  # boundaries and part headers on top of the file itself


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


def _spool(upload: UploadFile, ext: str) -> tuple[Path, str, int]:
    """Copy the upload to `<data_dir>/uploads/*.ext`, hashing as it goes and enforcing the cap.

    The spool sits on the same volume as the media dir, so `place_file` can move it in with `os.replace`.
    """
    upload_dir = get_settings().data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=upload_dir, suffix=f".{ext}", delete=False)  # noqa: SIM115
    digest, size = hashlib.sha256(), 0
    try:
        with handle:
            while chunk := upload.file.read(_CHUNK):
                size += len(chunk)
                if size > enrollments.MAX_VIDEO_BYTES:
                    raise _too_large()
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise DomainError("VALIDATION_FAILED", "The uploaded video is empty.", {"bytes": 0})
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return Path(handle.name), digest.hexdigest(), size


def _too_large() -> DomainError:
    return DomainError("VALIDATION_FAILED", "The video is larger than 200 MB.",
                       {"max_bytes": enrollments.MAX_VIDEO_BYTES})


class _UploadLimitRoute(APIRoute):
    """Refuses an oversize video upload from its `Content-Length` before the multipart body is read."""

    def get_route_handler(self):
        handler = super().get_route_handler()
        if self.name != "upload_video":
            return handler

        async def limited(request: Request):
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > enrollments.MAX_VIDEO_BYTES + MULTIPART_OVERHEAD:
                raise _too_large()
            return await handler(request)

        return limited


router.route_class = _UploadLimitRoute


@router.put("/{enrollment_id}/video", response_model=EnrollmentOut,
            responses=error_responses(401, 403, 404, 409, 422))
def upload_video(enrollment_id: str, file: UploadFile = File(...), principal: Principal = Depends(enroller)) -> dict:
    with read_session() as session:
        enrollments.check_uploadable(session, principal.farm_id, enrollment_id)
    content_type, ext = enrollments.resolve_video_type(file.content_type, file.filename)
    spooled, sha256, size = _spool(file, ext)
    # Move the file into the media dir before the writing transaction: only the row insert holds the lock.
    try:
        media = place_file(principal.farm_id, "video", spooled, content_type, sha256, size)
    finally:
        spooled.unlink(missing_ok=True)
    try:
        with SessionLocal() as session:
            replaced = enrollments.attach_video(session, principal, enrollment_id, media)
            session.commit()
    except BaseException:
        media_path(media).unlink(missing_ok=True)
        raise
    if replaced is not None:
        replaced.unlink(missing_ok=True)
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

