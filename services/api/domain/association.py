"""Strict camera identity association (plan Section 4: identity association).

A track becomes `associated` with an animal only from
- a `muzzle_match` with more than `MIN_INLIERS` inliers and quality of at least `MIN_QUALITY`, for an animal that
  exists, has `identity_status == "confirmed"`, and belongs to the camera's farm; or
- an explicit human review (`PATCH /tracks/{id}` by a manager or operator).

A rejected match is still recorded as a `muzzle_match` observation, but the track keeps its state and its
`association_evidence` says why (`low_inliers`, `candidate_not_registered`, ...). An animal of another farm is
reported as `candidate_not_registered`, so a camera never learns that another farm's animal exists.
`track_lost` makes the track `uncertain`; later observations on it carry `animal_id = null`. A new `track_key`
starts `unassigned`. Each observation copies the track's association at ingest time and is never rewritten,
so an unassigned or uncertain track can never become an animal's last-seen observation.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import audit, clock
from domain.errors import DomainError
from domain.ids import new_id
from persistence.models import Animal, Camera, Observation, Replay, Track

MIN_INLIERS = 5  # exclusive: inliers must be greater than this
MIN_QUALITY = 0.6  # inclusive
EVENTS = ("frame", "muzzle_match", "track_lost")
STATUSES = ("unassigned", "associated", "uncertain")
RULE = {"name": "muzzle_association_v1", "min_inliers_exclusive": MIN_INLIERS, "min_quality": MIN_QUALITY}


@dataclass(frozen=True)
class MatchDecision:
    accepted: bool
    reason: str | None  # why it was rejected


def decide_match(*, candidate: Animal | None, farm_id: str, inliers: int | None,
                 quality: float | None) -> MatchDecision:
    """The muzzle-match rule. The candidate is the animal record the matcher named (None if it does not exist)."""
    if candidate is None or candidate.farm_id != farm_id:
        return MatchDecision(False, "candidate_not_registered")
    if candidate.identity_status != "confirmed":
        return MatchDecision(False, "candidate_unconfirmed")
    if inliers is None or inliers <= MIN_INLIERS:
        return MatchDecision(False, "low_inliers")
    if quality is None or quality < MIN_QUALITY:
        return MatchDecision(False, "low_quality")
    return MatchDecision(True, None)


@dataclass(frozen=True)
class ObservationInput:
    track_key: str
    observed_at: datetime
    bbox: list[float]
    visibility: float
    event: str = "frame"
    candidate_animal_id: str | None = None
    inliers: int | None = None
    quality: float | None = None
    reason: str | None = None
    media_ref: str | None = None


def _validate(item: ObservationInput) -> None:
    problems = []
    if item.event not in EVENTS:
        problems.append(f"event must be one of {', '.join(EVENTS)}")
    if len(item.bbox) != 4 or any(not 0 <= v <= 1 for v in item.bbox):
        problems.append("bbox must be [x, y, w, h] with values between 0 and 1")
    if not 0 <= item.visibility <= 1:
        problems.append("visibility must be between 0 and 1")
    if item.observed_at.tzinfo is None:
        problems.append("observed_at must include a timezone")
    if problems:
        raise DomainError("VALIDATION_FAILED", "The observation is not valid.", {"problems": problems})


def _find_track(session: Session, replay_id: str | None, camera_id: str, track_key: str) -> Track | None:
    query = select(Track).where(Track.camera_id == camera_id, Track.track_key == track_key)
    query = query.where(Track.replay_id.is_(None) if replay_id is None else Track.replay_id == replay_id)
    return session.scalar(query.order_by(Track.first_seen.desc()).limit(1))


def _set_track(track: Track, *, status: str, animal_id: str | None, method: str | None, evidence: dict) -> None:
    track.association_status = status
    track.animal_id = animal_id
    track.association_method = method
    track.association_evidence = evidence


def _apply_match(session: Session, track: Track, item: ObservationInput, *, farm_id: str,
                 actor: tuple[str, str]) -> None:
    candidate = session.get(Animal, item.candidate_animal_id) if item.candidate_animal_id else None
    decision = decide_match(candidate=candidate, farm_id=farm_id, inliers=item.inliers, quality=item.quality)
    evidence = {"event": "muzzle_match", "candidate_animal_id": item.candidate_animal_id, "inliers": item.inliers,
                "quality": item.quality, "observed_at": clock.isoformat(item.observed_at), "rule": RULE}
    if not decision.accepted:
        # The track keeps its state; the evidence explains why this match did not count.
        updated = {**(track.association_evidence or {}), "last_rejected": {**evidence, "reason": decision.reason}}
        if track.association_status == "unassigned":
            updated.update(decision="rejected", reason=decision.reason)
        track.association_evidence = updated
        return
    if track.association_status == "uncertain":
        track.association_evidence = {**(track.association_evidence or {}),
                                      "last_rejected": {**evidence, "reason": "track_uncertain"}}
        return
    if track.association_status == "associated":
        if track.animal_id != candidate.id:
            previous = track.animal_id
            _set_track(track, status="uncertain", animal_id=None, method=None,
                       evidence={**evidence, "decision": "conflict", "reason": "conflicting_match",
                                 "previous_animal_id": previous})
            audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.lost",
                         subject_type="track", subject_id=track.id, animal_id=previous,
                         data={"reason": "conflicting_match", "track_key": track.track_key,
                               "camera_id": track.camera_id, "candidate_animal_id": candidate.id})
        return
    _set_track(track, status="associated", animal_id=candidate.id, method="muzzle_match",
               evidence={**evidence, "decision": "associated", "reason": None})
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.associated",
                 subject_type="track", subject_id=track.id, animal_id=candidate.id,
                 data={"method": "muzzle_match", "track_key": track.track_key, "camera_id": track.camera_id,
                       "inliers": item.inliers, "quality": item.quality, "replay_id": track.replay_id})


def _apply_lost(session: Session, track: Track, item: ObservationInput, *, farm_id: str,
                actor: tuple[str, str]) -> None:
    if track.association_status == "uncertain":
        return
    previous = track.animal_id
    _set_track(track, status="uncertain", animal_id=None, method=None,
               evidence={"event": "track_lost", "decision": "lost", "reason": item.reason or "unspecified",
                         "previous_animal_id": previous, "previous_method": track.association_method,
                         "observed_at": clock.isoformat(item.observed_at)})
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.lost",
                 subject_type="track", subject_id=track.id, animal_id=previous,
                 data={"reason": item.reason or "unspecified", "track_key": track.track_key,
                       "camera_id": track.camera_id, "replay_id": track.replay_id})


def ingest(session: Session, *, farm_id: str, camera_id: str, item: ObservationInput, replay_id: str | None = None,
           actor: tuple[str, str] = ("system", "replay"), source: str = "simulated") -> Observation:
    """Record one camera observation: find or start its track, apply the association rule for its event, and
    store the observation with the track's association as it stands now. The caller commits."""
    _validate(item)
    camera = session.get(Camera, camera_id)
    if camera is None or camera.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Camera not found.")
    if replay_id is not None:
        replay = session.get(Replay, replay_id)
        if replay is None or replay.farm_id != farm_id or replay.camera_id != camera_id:
            raise DomainError("NOT_FOUND", "Replay not found for this camera.")
    track = _find_track(session, replay_id, camera_id, item.track_key)
    if track is None:
        track = Track(id=new_id("trk"), replay_id=replay_id, camera_id=camera_id, track_key=item.track_key,
                      animal_id=None, association_status="unassigned", association_method=None,
                      association_evidence=None, first_seen=item.observed_at, last_seen=item.observed_at)
        session.add(track)
        session.flush()
    track.first_seen = min(track.first_seen, item.observed_at)
    track.last_seen = max(track.last_seen, item.observed_at)
    if item.event == "muzzle_match":
        _apply_match(session, track, item, farm_id=farm_id, actor=actor)
    elif item.event == "track_lost":
        _apply_lost(session, track, item, farm_id=farm_id, actor=actor)
    associated = track.association_status == "associated"
    observation = Observation(
        id=new_id("obs"), farm_id=farm_id, camera_id=camera_id, track_id=track.id,
        animal_id=track.animal_id if associated else None, association_status=track.association_status,
        observed_at=item.observed_at, bbox=[float(v) for v in item.bbox], visibility=float(item.visibility),
        event=item.event, media_ref=item.media_ref, source=source)
    session.add(observation)
    return observation


def farm_track(session: Session, farm_id: str, track_id: str) -> Track:
    track = session.get(Track, track_id)
    camera = session.get(Camera, track.camera_id) if track else None
    if track is None or camera is None or camera.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Track not found.")
    return track


def review(session: Session, *, farm_id: str, track_id: str, animal_id: str | None, note: str | None,
           actor: tuple[str, str]) -> Track:
    """A person associates a track with a confirmed animal of the farm, or unassigns it. Only later observations
    carry the new association. The caller commits."""
    track = farm_track(session, farm_id, track_id)
    reviewed = {"by": actor[1], "at": clock.isoformat(clock.now()), "note": note}
    if animal_id is None:
        previous = track.animal_id
        _set_track(track, status="unassigned", animal_id=None, method="human_review",
                   evidence={"decision": "unassigned", "reason": "human_review", "previous_animal_id": previous,
                             "review": reviewed})
        audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.unassigned",
                     subject_type="track", subject_id=track.id, animal_id=previous,
                     data={"track_key": track.track_key, "camera_id": track.camera_id, "note": note})
        return track
    animal = session.get(Animal, animal_id)
    if animal is None or animal.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Animal not found.")
    if animal.identity_status != "confirmed":
        raise DomainError("IDENTITY_UNCONFIRMED", "Only an animal with a confirmed identity can be associated.",
                          {"animal_id": animal_id, "identity_status": animal.identity_status})
    _set_track(track, status="associated", animal_id=animal.id, method="human_review",
               evidence={"decision": "associated", "reason": "human_review", "review": reviewed,
                         "previous": dict(track.association_evidence or {})})
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.associated",
                 subject_type="track", subject_id=track.id, animal_id=animal.id,
                 data={"method": "human_review", "track_key": track.track_key, "camera_id": track.camera_id,
                       "note": note})
    return track
