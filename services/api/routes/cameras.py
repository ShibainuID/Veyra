"""Camera endpoints (PRD Section 6, M07): cameras, scan zones, scan handoffs, recordings, worker observations."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from domain import audit, jobs, monitoring
from domain.errors import APIError, ErrorCode
from domain.passport import require_confirmed_identity
from domain.tracks import TracksFormatError, parse_tracks
from persistence.models import Animal, Camera, CameraRecording, CameraZone, Enrollment, Media, TrackLink, User, ZoneScan
from persistence.storage import MediaTooLarge
from routes.deps import SessionDep, UserDep, get_owned, require_roles

router = APIRouter(prefix="/cameras", tags=["cameras"])
Manager = Annotated[User, Depends(require_roles("manager"))]
Capturer = Annotated[User, Depends(require_roles("manager", "operator"))]
Service = Annotated[User, Depends(require_roles("service"))]


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=200)


class ZoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    polygon: list[list[float]] = Field(min_length=3, max_length=20,
                                       description="Normalised image coordinates [[x, y], ...], 0 <= x, y <= 1")

    @field_validator("polygon")
    @classmethod
    def normalised_points(cls, polygon: list[list[float]]) -> list[list[float]]:
        if any(len(p) != 2 or not all(0.0 <= v <= 1.0 for v in p) for p in polygon):
            raise ValueError("each point must be [x, y] with 0 <= x, y <= 1")
        return polygon


class ScanIn(BaseModel):
    zone_id: uuid.UUID
    animal_id: uuid.UUID
    scanned_at: datetime
    enrollment_id: uuid.UUID | None = None


class ObservationsIn(BaseModel):
    started_at: datetime
    tracks: dict


def _camera(c: Camera) -> dict:
    return {"id": str(c.id), "name": c.name, "location": c.location, "created_at": c.created_at}


def _zone(z: CameraZone) -> dict:
    return {"id": str(z.id), "camera_id": str(z.camera_id), "name": z.name, "kind": z.kind, "polygon": z.polygon,
            "created_at": z.created_at}


def link_out(link: TrackLink) -> dict:
    return {"id": str(link.id), "recording_id": str(link.recording_id), "scan_id": str(link.scan_id),
            "animal_id": str(link.animal_id), "track_id": link.track_id, "status": link.status, "reason": link.reason,
            "policy_version": link.policy_version, "linked_from": link.linked_from, "linked_until": link.linked_until,
            "release_reason": link.release_reason, "candidates": link.details.get("candidates", [])}


def recording_out(session, r: CameraRecording) -> dict:
    links = session.scalars(select(TrackLink).where(TrackLink.recording_id == r.id).order_by(TrackLink.created_at))
    return {"id": str(r.id), "camera_id": str(r.camera_id), "status": r.status, "source": r.source,
            "scenario": r.scenario, "started_at": r.started_at, "duration_s": r.duration_s and float(r.duration_s),
            "video_media_id": r.video_media_id and str(r.video_media_id),
            "tracks_media_id": r.tracks_media_id and str(r.tracks_media_id), "job_id": r.job_id and str(r.job_id),
            "summary": r.summary, "links": [link_out(link) for link in links], "created_at": r.created_at}


def queue_recording(session, recording: CameraRecording, user: User) -> dict:
    session.add(recording)
    session.flush()
    job = jobs.enqueue(session, recording.farm_id, monitoring.PROCESS_JOB, {"recording_id": str(recording.id)}, user.id)
    recording.job_id = job.id
    audit.record(session, recording.farm_id, "camera.recording_queued", "camera_recording", recording.id,
                 actor_id=user.id, details={"camera_id": str(recording.camera_id), "source": recording.source,
                                            "scenario": recording.scenario})
    return {"recording_id": str(recording.id), "job_id": str(job.id), "status": job.status}


@router.post("", status_code=201)
def create_camera(body: CameraIn, session: SessionDep, user: Manager) -> dict:
    camera = Camera(farm_id=user.farm_id, name=body.name, location=body.location)
    session.add(camera)
    session.flush()
    audit.record(session, user.farm_id, "camera.created", "camera", camera.id, actor_id=user.id)
    session.commit()
    return _camera(camera)


@router.get("")
def list_cameras(session: SessionDep, user: UserDep) -> list[dict]:
    return [_camera(c) for c in session.scalars(select(Camera).where(Camera.farm_id == user.farm_id).order_by(Camera.name))]


@router.post("/{camera_id}/zones", status_code=201)
def create_zone(camera_id: uuid.UUID, body: ZoneIn, session: SessionDep, user: Manager) -> dict:
    camera = get_owned(session, Camera, camera_id, user)
    zone = CameraZone(farm_id=user.farm_id, camera_id=camera.id, name=body.name, kind="scan", polygon=body.polygon,
                      created_by=user.id)
    session.add(zone)
    session.flush()
    audit.record(session, user.farm_id, "camera.zone_created", "camera", camera.id, actor_id=user.id,
                 details={"zone_id": str(zone.id), "polygon": body.polygon})
    session.commit()
    return _zone(zone)


@router.get("/{camera_id}/zones")
def list_zones(camera_id: uuid.UUID, session: SessionDep, user: UserDep) -> list[dict]:
    camera = get_owned(session, Camera, camera_id, user)
    return [_zone(z) for z in session.scalars(select(CameraZone).where(CameraZone.camera_id == camera.id))]


@router.post("/{camera_id}/scans", status_code=201)
def record_scan(camera_id: uuid.UUID, body: ScanIn, session: SessionDep, user: Capturer) -> dict:
    """Record that a confirmed animal was scanned in a scan zone; processing hands its identity to one track."""
    camera = get_owned(session, Camera, camera_id, user)
    zone = get_owned(session, CameraZone, body.zone_id, user)
    if zone.camera_id != camera.id:
        raise APIError(ErrorCode.VALIDATION_FAILED, "The zone belongs to another camera.")
    animal = get_owned(session, Animal, body.animal_id, user)
    require_confirmed_identity(animal)
    if body.enrollment_id is not None:
        enrollment = get_owned(session, Enrollment, body.enrollment_id, user)
        if enrollment.status != "confirmed" or enrollment.animal_id != animal.id:
            raise APIError(ErrorCode.IDENTITY_UNCONFIRMED, "The enrollment is not a confirmed scan of this animal.")
    scan = ZoneScan(farm_id=user.farm_id, camera_id=camera.id, zone_id=zone.id, animal_id=animal.id,
                    enrollment_id=body.enrollment_id, scanned_at=body.scanned_at, created_by=user.id)
    session.add(scan)
    session.flush()
    audit.record(session, user.farm_id, "camera.zone_scan_recorded", "animal", animal.id, actor_id=user.id,
                 details={"scan_id": str(scan.id), "camera_id": str(camera.id), "zone_id": str(zone.id),
                          "scanned_at": body.scanned_at.isoformat()})
    session.commit()
    return {"id": str(scan.id), "camera_id": str(camera.id), "zone_id": str(zone.id), "animal_id": str(animal.id),
            "scanned_at": scan.scanned_at}


@router.post("/{camera_id}/recordings", status_code=202)
def upload_recording(camera_id: uuid.UUID, request: Request, file: UploadFile, session: SessionDep, user: Capturer,
                     started_at: Annotated[datetime, Form()]) -> dict:
    camera = get_owned(session, Camera, camera_id, user)
    try:
        key, size, sha = request.app.state.media.save(user.farm_id, file.file, Path(file.filename or ".mp4").suffix)
    except MediaTooLarge:
        raise APIError(ErrorCode.PAYLOAD_TOO_LARGE, "Upload exceeds the configured size limit.") from None
    media = Media(farm_id=user.farm_id, kind="video", storage_key=key, original_filename=file.filename,
                  content_type=file.content_type, size_bytes=size, sha256=sha, uploaded_by=user.id)
    session.add(media)
    session.flush()
    out = queue_recording(session, CameraRecording(farm_id=user.farm_id, camera_id=camera.id, video_media_id=media.id,
                                                   started_at=started_at, source="prototype", created_by=user.id), user)
    session.commit()
    return out


@router.get("/{camera_id}/recordings/{recording_id}")
def get_recording(camera_id: uuid.UUID, recording_id: uuid.UUID, session: SessionDep, user: UserDep) -> dict:
    recording = get_owned(session, CameraRecording, recording_id, user)
    if recording.camera_id != camera_id:
        raise APIError(ErrorCode.NOT_FOUND, "CameraRecording not found.")
    return recording_out(session, recording)


@router.post("/{camera_id}/observations", status_code=202)
def ingest_observations(camera_id: uuid.UUID, body: ObservationsIn, request: Request, session: SessionDep,
                        user: Service) -> dict:
    """Internal: a camera worker posts tracks it computed on the farm; the same rules run as for uploads."""
    camera = get_owned(session, Camera, camera_id, user)
    try:
        tracks = parse_tracks(body.tracks)
    except TracksFormatError as exc:
        raise APIError(ErrorCode.VALIDATION_FAILED, str(exc)) from None
    source = tracks.source if tracks.source in ("live", "prototype", "simulated") else "prototype"
    recording = CameraRecording(farm_id=user.farm_id, camera_id=camera.id, started_at=body.started_at, source=source,
                                created_by=user.id)
    session.add(recording)
    session.flush()
    monitoring.store_tracks(session, request.app.state.media, recording, body.tracks)
    out = queue_recording(session, recording, user)
    session.commit()
    return out
