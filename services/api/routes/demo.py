"""Demo-only endpoints (PRD Section 6): start a labelled, simulated camera replay. Absent unless demo mode is on."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from domain import audit, monitoring, replays
from domain.errors import APIError, ErrorCode
from persistence.models import Animal, Camera, CameraRecording, CameraZone, User, ZoneScan
from routes.cameras import queue_recording
from routes.deps import SessionDep, get_owned, require_roles

router = APIRouter(prefix="/demo", tags=["demo"])
Manager = Annotated[User, Depends(require_roles("manager"))]


class ReplayIn(BaseModel):
    animal_ids: list[uuid.UUID] | None = Field(default=None, description="Animals handed over through the scan zone, "
                                                                         "in scan order; defaults to confirmed animals")


def _demo_camera(session, user: User, fixture: dict) -> tuple[Camera, CameraZone]:
    camera = session.scalars(select(Camera).where(Camera.farm_id == user.farm_id,
                                                  Camera.name == fixture["camera"]["name"])).first()
    if camera is None:
        camera = Camera(farm_id=user.farm_id, **fixture["camera"])
        session.add(camera)
        session.flush()
    zone = session.scalars(select(CameraZone).where(CameraZone.camera_id == camera.id,
                                                    CameraZone.name == fixture["scan_zone"]["name"])).first()
    if zone is None:
        zone = CameraZone(farm_id=user.farm_id, camera_id=camera.id, kind="scan", created_by=user.id,
                          **fixture["scan_zone"])
        session.add(zone)
        session.flush()
    return camera, zone


@router.post("/replays/{scenario}/start", status_code=202)
def start_replay(scenario: str, body: ReplayIn, request: Request, session: SessionDep, user: Manager) -> dict:
    settings = request.app.state.settings
    if not settings.demo_mode:
        raise APIError(ErrorCode.NOT_FOUND, "Not found.")
    fixture = replays.load_fixture(settings.fixtures_root)
    try:
        replay = replays.generate(scenario, fixture)
    except KeyError:
        raise APIError(ErrorCode.NOT_FOUND, f"Unknown replay scenario '{scenario}'.",
                       {"scenarios": sorted(fixture["scenarios"])}) from None
    if body.animal_ids is not None:
        animals = [get_owned(session, Animal, a, user) for a in body.animal_ids]
    else:
        animals = list(session.scalars(select(Animal).where(Animal.farm_id == user.farm_id,
                                                            Animal.identity_status == "confirmed")
                                       .order_by(Animal.display_id)))
    animals = [a for a in animals if a.identity_status == "confirmed"][:len(replay.scans)]
    if not animals:
        raise APIError(ErrorCode.IDENTITY_UNCONFIRMED, "Enroll and confirm at least one animal before a replay.")

    camera, zone = _demo_camera(session, user, fixture)
    duration = replay.tracks["frames"][-1][0]
    # The replay ends now, so its observations and alerts read as recent.
    started_at = datetime.now(UTC) - timedelta(seconds=duration)
    recording = CameraRecording(farm_id=user.farm_id, camera_id=camera.id, started_at=started_at, source="simulated",
                                scenario=scenario, created_by=user.id)
    session.add(recording)
    session.flush()
    monitoring.store_tracks(session, request.app.state.media, recording, replay.tracks)
    for animal, (_, scan_t) in zip(animals, replay.scans):
        session.add(ZoneScan(farm_id=user.farm_id, camera_id=camera.id, zone_id=zone.id, animal_id=animal.id,
                             scanned_at=started_at + timedelta(seconds=scan_t), created_by=user.id))
    out = queue_recording(session, recording, user)
    audit.record(session, user.farm_id, "demo.replay_started", "camera_recording", recording.id, actor_id=user.id,
                 details={"scenario": scenario, "animal_ids": [str(a.id) for a in animals]})
    session.commit()
    return {**out, "scenario": scenario, "label": replay.label, "source": "simulated", "camera_id": str(camera.id),
            "zone_id": str(zone.id), "animal_ids": [str(a.id) for a in animals]}
