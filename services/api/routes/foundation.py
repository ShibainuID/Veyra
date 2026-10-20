"""Foundation endpoints: health, current user, media upload, job status, and audit history."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from domain import audit
from domain.errors import APIError, ErrorCode
from persistence.models import AuditEvent, Job, Media, User
from persistence.storage import MediaTooLarge
from routes.deps import SessionDep, UserDep, get_owned, require_roles

router = APIRouter()


class UserOut(BaseModel):
    id: uuid.UUID
    farm_id: uuid.UUID
    name: str
    role: str


class MediaOut(BaseModel):
    id: uuid.UUID
    kind: str
    original_filename: str | None
    content_type: str | None
    size_bytes: int
    sha256: str
    created_at: datetime


class JobOut(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    attempts: int
    result: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AuditOut(BaseModel):
    id: uuid.UUID
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str
    details: dict
    created_at: datetime


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: UserDep) -> User:
    return user


@router.post("/media", response_model=MediaOut, status_code=201)
def upload_media(
    request: Request,
    session: SessionDep,
    file: UploadFile,
    kind: Literal["video", "image", "document"],
    user: Annotated[User, Depends(require_roles("manager", "operator", "veterinarian"))],
) -> Media:
    store = request.app.state.media
    try:
        key, size, sha = store.save(user.farm_id, file.file, Path(file.filename or "").suffix)
    except MediaTooLarge:
        raise APIError(ErrorCode.PAYLOAD_TOO_LARGE, "Upload exceeds the configured size limit.") from None
    media = Media(farm_id=user.farm_id, kind=kind, storage_key=key, original_filename=file.filename,
                  content_type=file.content_type, size_bytes=size, sha256=sha, uploaded_by=user.id)
    session.add(media)
    session.flush()
    audit.record(session, user.farm_id, "media.uploaded", "media", media.id, actor_id=user.id,
                 details={"kind": kind, "sha256": sha, "size_bytes": size})
    session.commit()
    return media


@router.get("/media/{media_id}", response_model=MediaOut)
def get_media(media_id: uuid.UUID, session: SessionDep, user: UserDep) -> Media:
    return get_owned(session, Media, media_id, user)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, session: SessionDep, user: UserDep) -> Job:
    return get_owned(session, Job, job_id, user)


@router.get("/audit-events", response_model=list[AuditOut])
def list_audit_events(
    session: SessionDep,
    user: UserDep,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEvent]:
    query = select(AuditEvent).where(AuditEvent.farm_id == user.farm_id)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    return list(session.scalars(query.order_by(AuditEvent.created_at.desc()).limit(limit)))
