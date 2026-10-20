"""Camera monitoring: scenarios, replays, cameras, observations, and track review (plan Section 5).

Any signed-in role may read. Starting a replay and reviewing tracks needs a manager or operator; the internal
observation feed needs `X-Service-Token`. Every read is scoped to the principal's farm.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import domain.monitoring_passbook  # noqa: F401  (registers the passbook formatters)
from config import get_settings
from domain import alerts as alert_rules
from domain import association, audit
from domain.auth import ENROLLERS, Principal, ServicePrincipal
from domain.errors import DomainError
from persistence.db import SessionLocal, get_read_session, get_session
from persistence.models import Alert, Animal, Camera, Observation, Replay, Track
from routes.demo import require_demo_mode
from routes.deps import current_principal, require_roles, service_principal
from schemas import error_responses
from schemas_monitoring import (
    AnimalObservations, CameraList, ObservationIn, ObservationIngested, ReplayOut, ReplayStarted, ScenarioList,
    TrackOut, TrackReview,
)
from workers import replay as replays

router = APIRouter(tags=["monitoring"])
RECENT_LIMIT = 50
LOW_VISIBILITY = 0.6


def _observation(row: Observation) -> dict:
    return {"id": row.id, "camera_id": row.camera_id, "track_id": row.track_id, "animal_id": row.animal_id,
            "association_status": row.association_status, "observed_at": row.observed_at, "bbox": list(row.bbox),
            "visibility": row.visibility, "event": row.event, "media_ref": row.media_ref, "source": row.source}


def _track(row: Track, animal_names: dict[str, str]) -> dict:
    return {"id": row.id, "replay_id": row.replay_id, "camera_id": row.camera_id, "track_key": row.track_key,
            "animal_id": row.animal_id, "animal_name": animal_names.get(row.animal_id) if row.animal_id else None,
            "association_status": row.association_status, "association_method": row.association_method,
            "association_evidence": dict(row.association_evidence) if row.association_evidence else None,
            "first_seen": row.first_seen, "last_seen": row.last_seen}


def _animal_names(session: Session, farm_id: str) -> dict[str, str]:
    return dict(session.execute(select(Animal.id, Animal.name).where(Animal.farm_id == farm_id)).all())


def _cameras(session: Session, farm_id: str) -> list[dict]:
    names = _animal_names(session, farm_id)
    items = []
    for camera in session.scalars(select(Camera).where(Camera.farm_id == farm_id).order_by(Camera.id)):
        last = session.scalar(select(Observation).where(Observation.camera_id == camera.id)
                              .order_by(Observation.observed_at.desc(), Observation.id.desc()).limit(1))
        items.append({
            "id": camera.id, "name": camera.name, "location": camera.location, "map_x": camera.map_x,
            "map_y": camera.map_y,
            "last_observation": None if last is None else {
                "id": last.id, "observed_at": last.observed_at, "track_id": last.track_id,
                "animal_id": last.animal_id, "animal_name": names.get(last.animal_id) if last.animal_id else None,
                "association_status": last.association_status, "visibility": last.visibility,
                "bbox": list(last.bbox)}})
    return items


@router.get("/demo/replays", response_model=ScenarioList, dependencies=[Depends(require_demo_mode)],
            responses=error_responses(401, 404))
def list_scenarios(principal: Principal = Depends(current_principal),
                   session: Session = Depends(get_read_session)) -> dict:
    cameras = _cameras(session, principal.farm_id)
    names = {camera["id"]: camera["name"] for camera in cameras}
    scenarios = [{**scenario, "camera_name": names.get(scenario["camera_id"])}
                 for scenario in replays.list_scenarios(get_settings()) if scenario["camera_id"] in names]
    return {"scenarios": scenarios, "cameras": cameras}


@router.post("/demo/replays/{scenario_id}/start", status_code=status.HTTP_202_ACCEPTED, response_model=ReplayStarted,
             dependencies=[Depends(require_demo_mode)], responses=error_responses(401, 403, 404))
def start_replay(scenario_id: str, principal: Principal = Depends(require_roles(*ENROLLERS))) -> dict:
    # No session dependency: the replay opens its own short writing sessions (speed 0 runs inside this request).
    settings = get_settings()
    replay = replays.start(settings, farm_id=principal.farm_id, actor=audit.actor_from(principal),
                           scenario_id=scenario_id)
    scenario = replays.load_scenario(settings, scenario_id)
    return {"replay_id": replay.id, "scenario_id": scenario_id, "status": replay.status,
            "started_at": replay.started_at, "speed": replay.speed, "duration_s": scenario["duration_s"]}


@router.get("/replays/{replay_id}", response_model=ReplayOut, responses=error_responses(401, 404))
def get_replay(replay_id: str, principal: Principal = Depends(current_principal),
               session: Session = Depends(get_read_session)) -> dict:
    replay = session.get(Replay, replay_id)
    if replay is None or replay.farm_id != principal.farm_id:
        raise DomainError("NOT_FOUND", "Replay not found.")
    try:
        duration = replays.load_scenario(get_settings(), replay.scenario_id)["duration_s"]
    except DomainError:
        duration = 0.0
    names = _animal_names(session, principal.farm_id)
    tracks = session.scalars(select(Track).where(Track.replay_id == replay.id)
                             .order_by(Track.first_seen, Track.track_key)).all()
    alert_rows = list(session.scalars(select(Alert).where(Alert.track_id.in_([t.id for t in tracks]))
                                      .order_by(Alert.created_at, Alert.id))) if tracks else []
    return {"id": replay.id, "scenario_id": replay.scenario_id, "camera_id": replay.camera_id,
            "status": replay.status, "speed": replay.speed, "started_at": replay.started_at,
            "finished_at": replay.finished_at, "duration_s": duration,
            "progress_s": replays.progress_of(replay, duration, session),
            "tracks": [_track(track, names) for track in tracks],
            "alerts": alert_rules.views(session, principal.farm_id, alert_rows)}


@router.get("/cameras", response_model=CameraList, responses=error_responses(401))
def list_cameras(principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return {"items": _cameras(session, principal.farm_id)}


@router.post("/cameras/{camera_id}/observations", status_code=status.HTTP_201_CREATED,
             response_model=ObservationIngested, responses=error_responses(401, 404, 422))
def ingest_observation(camera_id: str, body: ObservationIn, service: ServicePrincipal = Depends(service_principal),
                       session: Session = Depends(get_session)) -> dict:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise DomainError("NOT_FOUND", "Camera not found.")
    item = association.ObservationInput(**body.model_dump(exclude={"replay_id"}))
    observation = association.ingest(session, farm_id=camera.farm_id, camera_id=camera_id, item=item,
                                     replay_id=body.replay_id, actor=audit.actor_from(service), source="simulated")
    session.flush()
    track = session.get(Track, observation.track_id)
    result = {"observation": _observation(observation), "track": _track(track, _animal_names(session, camera.farm_id))}
    session.commit()
    return result


@router.get("/animals/{animal_id}/observations", response_model=AnimalObservations,
            responses=error_responses(401, 404))
def animal_observations(animal_id: str, principal: Principal = Depends(current_principal),
                        session: Session = Depends(get_read_session)) -> dict:
    animal = session.get(Animal, animal_id)
    if animal is None or animal.farm_id != principal.farm_id:
        raise DomainError("NOT_FOUND", "Animal not found.")
    mine = (Observation.farm_id == principal.farm_id, Observation.animal_id == animal_id,
            Observation.association_status == "associated")
    recent = session.scalars(select(Observation).where(*mine)
                             .order_by(Observation.observed_at.desc(), Observation.id.desc())
                             .limit(RECENT_LIMIT)).all()
    cameras = dict(session.execute(select(Camera.id, Camera.name).where(Camera.farm_id == principal.farm_id)).all())
    tracks = session.scalars(select(Track).join(Camera, Camera.id == Track.camera_id)
                             .where(Camera.farm_id == principal.farm_id, Track.animal_id == animal_id,
                                    Track.association_status == "associated")
                             .order_by(Track.last_seen.desc())).all()
    last = recent[0] if recent else None
    visibilities = [row.visibility for row in recent]
    open_quality = session.scalars(select(Alert.id).where(
        Alert.farm_id == principal.farm_id, Alert.animal_id == animal_id, Alert.kind == "observation_quality",
        Alert.status == "open")).all()
    names = {animal.id: animal.name}
    return {
        "animal_id": animal_id,
        "last_observation": None if last is None else {
            "id": last.id, "camera_id": last.camera_id, "camera_name": cameras.get(last.camera_id),
            "observed_at": last.observed_at, "bbox": list(last.bbox), "visibility": last.visibility,
            "association_status": last.association_status},
        "tracks": [_track(track, names) for track in tracks],
        "recent": [_observation(row) for row in recent],
        "quality_summary": {
            "observations": len(recent),
            "mean_visibility": round(sum(visibilities) / len(visibilities), 4) if visibilities else None,
            "low_visibility": sum(v < LOW_VISIBILITY for v in visibilities), "min_visibility": LOW_VISIBILITY,
            "open_quality_alerts": len(open_quality)},
    }


@router.patch("/tracks/{track_id}", response_model=TrackOut, responses=error_responses(401, 403, 404, 409, 422))
def review_track(track_id: str, body: TrackReview, principal: Principal = Depends(require_roles(*ENROLLERS))) -> dict:
    with SessionLocal() as session:
        track = association.review(session, farm_id=principal.farm_id, track_id=track_id, animal_id=body.animal_id,
                                   note=body.note, actor=audit.actor_from(principal))
        session.flush()
        result = _track(track, _animal_names(session, principal.farm_id))
        session.commit()
    return result
