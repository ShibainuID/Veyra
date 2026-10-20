"""Monitoring alerts: creation with cooldown, review, and the plain summary.

An alert is a reviewable prompt, never a diagnosis. Review rules:
- status moves only forward: `open → acknowledged → resolved`; anything else is `INVALID_STATE`;
- managers and operators may acknowledge and resolve; a vet may acknowledge and add notes but not resolve;
- resolving needs a note in the same request;
- a note is `{author, author_name, role, at, text, kind}` where kind is `assessment` for a vet, else `review`.
Status changes are guarded updates on the expected status, so two reviewers cannot both move the same alert.

Cooldown: a new alert is skipped when an alert of the same kind, camera, and subject (the animal when there is one,
otherwise the track) has a window ending within the cooldown of the new window's end, in observation time. Replays
of the same scenario started close together therefore raise one alert, whatever its review status.
"""

from datetime import UTC, datetime, tzinfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from domain import audit, clock
from domain.auth import Principal
from domain.errors import DomainError
from domain.ids import new_id
from domain.movement import DEFAULT_CONFIG, MovementConfig, alert_summary, in_cooldown
from persistence.models import Alert, Animal, Camera, Track

KINDS = ("reduced_movement", "observation_quality")
STATUSES = ("open", "acknowledged", "resolved")
NEXT_STATUS = {"open": "acknowledged", "acknowledged": "resolved"}
RESOLVERS = ("manager", "operator")
ACKNOWLEDGERS = ("manager", "operator", "vet")
STATUS_EVENTS = {"acknowledged": "alert.acknowledged", "resolved": "alert.resolved"}


def summary_of(alert: Alert, *, camera_name: str, animal_name: str | None, track_key: str | None,
               zone: tzinfo = UTC) -> str:
    return alert_summary(kind=alert.kind, rule=alert.rule or {}, camera_name=camera_name,
                         window_start=alert.window_start, window_end=alert.window_end, animal_name=animal_name,
                         track_key=track_key, zone=zone)


def create(session: Session, *, farm_id: str, kind: str, camera_id: str, track: Track | None, animal_id: str | None,
           window_start: datetime, window_end: datetime, rule: dict, clip: dict | None,
           baseline_start: datetime | None = None, baseline_end: datetime | None = None,
           actor: tuple[str, str] = ("system", "replay"),
           config: MovementConfig = DEFAULT_CONFIG) -> Alert | None:
    """Create an alert unless one for the same subject is within the cooldown. The caller commits."""
    if kind not in KINDS:
        raise ValueError(f"unknown alert kind {kind!r}")
    if animal_id is None and track is None:
        raise ValueError("an alert needs an animal or a track")
    query = select(Alert.window_end).where(
        Alert.farm_id == farm_id, Alert.kind == kind, Alert.camera_id == camera_id,
        Alert.window_end > window_end - config.cooldown, Alert.window_end < window_end + config.cooldown)
    if animal_id is not None:
        query = query.where(Alert.animal_id == animal_id)
    else:
        query = query.where(Alert.animal_id.is_(None), Alert.track_id == track.id)
    if in_cooldown(session.scalars(query).all(), window_end, config):
        return None
    now = clock.now()
    alert = Alert(id=new_id("alr"), farm_id=farm_id, kind=kind, animal_id=animal_id,
                  track_id=track.id if track else None, camera_id=camera_id, window_start=window_start,
                  window_end=window_end, baseline_start=baseline_start, baseline_end=baseline_end, rule=rule,
                  clip=clip, status="open", notes=[], created_at=now, updated_at=now)
    session.add(alert)
    session.flush()
    camera = session.get(Camera, camera_id)
    animal = session.get(Animal, animal_id) if animal_id else None
    summary = summary_of(alert, camera_name=camera.name if camera else camera_id,
                         animal_name=animal.name if animal else None, track_key=track.track_key if track else None)
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="alert.created",
                 subject_type="alert", subject_id=alert.id, animal_id=animal_id,
                 data={"kind": kind, "rule": rule.get("name"), "summary": summary, "camera_id": camera_id,
                       "track_id": alert.track_id, "window_start": clock.isoformat(window_start),
                       "window_end": clock.isoformat(window_end)})
    return alert


def farm_alert(session: Session, farm_id: str, alert_id: str) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None or alert.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Alert not found.")
    return alert


def list_alerts(session: Session, farm_id: str, *, status: str | None = None, kind: str | None = None,
                animal_id: str | None = None) -> list[Alert]:
    query = select(Alert).where(Alert.farm_id == farm_id)
    for column, value in ((Alert.status, status), (Alert.kind, kind), (Alert.animal_id, animal_id)):
        if value is not None:
            query = query.where(column == value)
    return list(session.scalars(query.order_by(Alert.created_at.desc(), Alert.window_end.desc(), Alert.id)))


def views(session: Session, farm_id: str, alerts: list[Alert], zone: tzinfo = UTC) -> list[dict]:
    """Alerts joined with the names a reviewer needs and the deterministic summary."""
    cameras = dict(session.execute(select(Camera.id, Camera.name).where(Camera.farm_id == farm_id)).all())
    animals = dict(session.execute(select(Animal.id, Animal.name).where(Animal.farm_id == farm_id)).all())
    track_ids = [a.track_id for a in alerts if a.track_id]
    tracks = dict(session.execute(select(Track.id, Track.track_key).where(Track.id.in_(track_ids))).all()) \
        if track_ids else {}
    out = []
    for alert in alerts:
        camera_name = cameras.get(alert.camera_id, alert.camera_id)
        animal_name = animals.get(alert.animal_id) if alert.animal_id else None
        track_key = tracks.get(alert.track_id)
        out.append({
            "id": alert.id, "kind": alert.kind, "status": alert.status, "animal_id": alert.animal_id,
            "animal_name": animal_name, "track_id": alert.track_id, "track_key": track_key,
            "camera_id": alert.camera_id, "camera_name": camera_name, "window_start": alert.window_start,
            "window_end": alert.window_end, "baseline_start": alert.baseline_start,
            "baseline_end": alert.baseline_end, "rule": dict(alert.rule or {}),
            "clip": dict(alert.clip) if alert.clip else None, "notes": list(alert.notes or []),
            "summary": summary_of(alert, camera_name=camera_name, animal_name=animal_name, track_key=track_key,
                                  zone=zone),
            "created_at": alert.created_at, "updated_at": alert.updated_at,
        })
    return out


def review(session: Session, *, farm_id: str, alert_id: str, principal: Principal, status: str | None,
           note: str | None) -> Alert:
    """Acknowledge, resolve, or annotate an alert. The caller commits."""
    note = note.strip() if note else None
    if status is None and not note:
        raise DomainError("VALIDATION_FAILED", "Give a status, a note, or both.")
    alert = farm_alert(session, farm_id, alert_id)
    now = clock.now()
    actor = audit.actor_from(principal)
    if status is not None:
        if status not in STATUS_EVENTS:
            raise DomainError("VALIDATION_FAILED", "Status must be acknowledged or resolved.")
        allowed = RESOLVERS if status == "resolved" else ACKNOWLEDGERS
        if principal.role not in allowed:
            raise DomainError("FORBIDDEN_ROLE", f"Only a {' or '.join(allowed)} can mark an alert {status}.",
                              {"required": list(allowed), "role": principal.role})
        if status == "resolved" and not note:
            raise DomainError("VALIDATION_FAILED", "Resolving an alert needs a note.", {"field": "note"})
        current = alert.status
        if NEXT_STATUS.get(current) != status:
            raise DomainError("INVALID_STATE", f"An alert that is {current} cannot become {status}.",
                              {"status": current, "requested": status})
        result = session.execute(update(Alert).where(Alert.id == alert.id, Alert.status == current)
                                 .values(status=status, updated_at=now).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise DomainError("INVALID_STATE", "The alert changed while you were reviewing it.", {"status": current})
        session.refresh(alert)
    if note:
        alert.notes.append({"author": principal.user_id, "author_name": principal.name, "role": principal.role,
                            "at": clock.isoformat(now), "text": note,
                            "kind": "assessment" if principal.role == "vet" else "review"})
        alert.updated_at = now
    if status is not None:
        audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type=STATUS_EVENTS[status],
                     subject_type="alert", subject_id=alert.id, animal_id=alert.animal_id,
                     data={"kind": alert.kind, "status": status, "note": note, "role": principal.role})
    else:
        audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="alert.note_added",
                     subject_type="alert", subject_id=alert.id, animal_id=alert.animal_id,
                     data={"kind": alert.kind, "note_kind": "assessment" if principal.role == "vet" else "review",
                           "text": note, "role": principal.role})
    session.flush()
    return alert
