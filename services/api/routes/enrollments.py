"""Enrollment endpoints (PRD Section 6): create, upload video, process, review, confirm, reject."""

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from domain import audit, enrollment as flow, jobs
from domain.errors import APIError, ErrorCode
from persistence.models import Enrollment, Job, Media, User
from persistence.storage import MediaTooLarge
from routes.deps import SessionDep, UserDep, get_owned, require_roles

router = APIRouter(prefix="/enrollments", tags=["enrollments"])
Capturer = Annotated[User, Depends(require_roles("manager", "operator"))]


class CaptureInputs(BaseModel):
    sex: Literal["female", "male"] | None = None
    breed: str | None = Field(default=None, max_length=100)
    documented_birth_date: date | None = None
    tape_heart_girth_cm: float | None = Field(default=None, gt=50, lt=350)
    marker_cm: float = Field(default=15.0, gt=1, lt=100)
    sample_key: str | None = Field(default=None, max_length=100, description="Demo fixture key for the age adapter")


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    status: str
    capture_inputs: dict
    video_media_id: uuid.UUID | None
    process_job_id: uuid.UUID | None
    processing_mode: str | None
    manifest: dict | None
    identity_result: dict | None
    estimate_results: dict | None
    review_reasons: list
    animal_id: uuid.UUID | None
    created_at: datetime
    reviewed_at: datetime | None


class JobAccepted(BaseModel):
    job_id: uuid.UUID
    status: str


class ConfirmIn(BaseModel):
    decision: Literal["new_animal", "existing_animal"]
    animal_id: uuid.UUID | None = None
    acknowledge_review: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class ConfirmOut(BaseModel):
    enrollment_id: uuid.UUID
    animal_id: uuid.UUID
    display_id: str


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _out(e: Enrollment) -> EnrollmentOut:
    # The muzzle reference embedding is internal; strip it from API responses.
    identity = dict(e.identity_result) if e.identity_result else None
    if identity:
        identity.pop("reference", None)
    return EnrollmentOut(id=e.id, status=e.status, capture_inputs=e.capture_inputs or {}, video_media_id=e.video_media_id,
                         process_job_id=e.process_job_id, processing_mode=e.processing_mode, manifest=e.manifest,
                         identity_result=identity, estimate_results=e.estimate_results, review_reasons=e.review_reasons or [],
                         animal_id=e.animal_id, created_at=e.created_at, reviewed_at=e.reviewed_at)


def _sync_failed_processing(session, e: Enrollment) -> None:
    """A processing job that exhausted its retries leaves the enrollment failed, so the operator can re-record."""
    if e.status == "processing" and e.process_job_id:
        job = session.get(Job, e.process_job_id)
        if job is not None and job.status == "failed":
            e.status = "failed"
            audit.record(session, e.farm_id, "enrollment.processing_failed", "enrollment", e.id, actor_type="system",
                         details={"job_id": str(job.id)})
            session.commit()


@router.post("", response_model=EnrollmentOut, status_code=201)
def create_enrollment(body: CaptureInputs, session: SessionDep, user: Capturer) -> EnrollmentOut:
    e = Enrollment(farm_id=user.farm_id, created_by=user.id, capture_inputs=body.model_dump(mode="json", exclude_none=True))
    session.add(e)
    session.flush()
    audit.record(session, user.farm_id, "enrollment.created", "enrollment", e.id, actor_id=user.id)
    session.commit()
    return _out(e)


@router.get("", response_model=list[EnrollmentOut])
def list_enrollments(session: SessionDep, user: UserDep, status: str | None = None) -> list[EnrollmentOut]:
    q = select(Enrollment).where(Enrollment.farm_id == user.farm_id)
    if status:
        q = q.where(Enrollment.status == status)
    rows = list(session.scalars(q.order_by(Enrollment.created_at.desc())))
    for e in rows:
        _sync_failed_processing(session, e)
    return [_out(e) for e in rows]


@router.get("/{enrollment_id}", response_model=EnrollmentOut)
def get_enrollment(enrollment_id: uuid.UUID, session: SessionDep, user: UserDep) -> EnrollmentOut:
    e = get_owned(session, Enrollment, enrollment_id, user)
    _sync_failed_processing(session, e)
    return _out(e)


@router.post("/{enrollment_id}/video", response_model=EnrollmentOut)
def upload_video(enrollment_id: uuid.UUID, request: Request, file: UploadFile, session: SessionDep,
                 user: Capturer) -> EnrollmentOut:
    e = get_owned(session, Enrollment, enrollment_id, user)
    if e.status not in ("created", "uploaded"):
        raise APIError(ErrorCode.CONFLICT, f"Cannot replace the video of a '{e.status}' enrollment.")
    try:
        key, size, sha = request.app.state.media.save(user.farm_id, file.file, Path(file.filename or ".mp4").suffix)
    except MediaTooLarge:
        raise APIError(ErrorCode.PAYLOAD_TOO_LARGE, "Upload exceeds the configured size limit.") from None
    media = Media(farm_id=user.farm_id, kind="video", storage_key=key, original_filename=file.filename,
                  content_type=file.content_type, size_bytes=size, sha256=sha, uploaded_by=user.id)
    session.add(media)
    session.flush()
    e.video_media_id = media.id
    e.status = "uploaded"
    audit.record(session, user.farm_id, "enrollment.video_uploaded", "enrollment", e.id, actor_id=user.id,
                 details={"media_id": str(media.id), "sha256": sha, "size_bytes": size})
    session.commit()
    return _out(e)


@router.post("/{enrollment_id}/process", response_model=JobAccepted, status_code=202)
def process_enrollment(enrollment_id: uuid.UUID, session: SessionDep, user: Capturer) -> JobAccepted:
    e = get_owned(session, Enrollment, enrollment_id, user)
    if e.status != "uploaded":
        raise APIError(ErrorCode.CONFLICT, f"Enrollment is '{e.status}'; upload a video before processing.")
    job = jobs.enqueue(session, user.farm_id, flow.PROCESS_JOB, {"enrollment_id": str(e.id)}, user.id)
    e.status = "processing"
    e.process_job_id = job.id
    session.commit()
    return JobAccepted(job_id=job.id, status=job.status)


@router.post("/{enrollment_id}/confirm", response_model=ConfirmOut)
def confirm_enrollment(enrollment_id: uuid.UUID, body: ConfirmIn, session: SessionDep, user: Capturer) -> ConfirmOut:
    e = get_owned(session, Enrollment, enrollment_id, user)
    animal = flow.confirm(session, e, user, body.decision, body.animal_id, body.acknowledge_review, body.notes)
    session.commit()
    return ConfirmOut(enrollment_id=e.id, animal_id=animal.id, display_id=animal.display_id)


@router.post("/{enrollment_id}/reject", response_model=EnrollmentOut)
def reject_enrollment(enrollment_id: uuid.UUID, body: RejectIn, session: SessionDep, user: Capturer) -> EnrollmentOut:
    e = get_owned(session, Enrollment, enrollment_id, user)
    flow.reject(session, e, user, body.reason)
    session.commit()
    return _out(e)

