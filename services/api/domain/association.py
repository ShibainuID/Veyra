"""Strict camera identity association (plan Section 4: identity association) and identity continuity.

A track becomes `associated` with an animal only from
- a `zone_scan`: an animal's muzzle is scanned inside the camera's calibrated scan zone, and exactly one track's
  box centre is inside that zone at the scan time ("the cow must be alone in the zone"), method `zone_handoff`;
- a `muzzle_match` on the track itself, method `muzzle_match`; or
- an explicit human review (`PATCH /tracks/{id}` by a manager or operator).

Both automatic paths use the same bar: more than `MIN_INLIERS` inliers and quality of at least `MIN_QUALITY`, for an
animal that exists, has `identity_status == "confirmed"`, and belongs to the camera's farm. A rejected match is still
recorded, but the track keeps its state and its `association_evidence` says why (`low_inliers`,
`candidate_not_registered`, ...). An animal of another farm is reported as `candidate_not_registered`, so a camera
never learns that another farm's animal exists. A scan with no track in the zone associates nothing; a scan with two
or more tracks in the zone associates nothing and makes every one of them `uncertain` (never guess).

Continuity (`handoff_v2`, ml/results/handoff_policy.md): an associated track loses its identity, becoming
`uncertain`, when it is missing for more than `MAX_GAP_S`, or when it overlaps another track at IoU above `CROWD_IOU`
for at least `CROWD_S`. An overlap release counts from the start of the overlap, so the few observations already
stored since then are downgraded to `uncertain` (the only rewrite of an observation, and only ever away from an
animal). `track_lost` also makes the track `uncertain`. A released identity is never re-attached automatically: an
uncertain track ignores later matches and scans; only a human review can assign it again.

Gaps are checked when the track reports again and, for every associated track of the same replay (or of the live
feed, if it reported within `LIVE_TRACK_GAP`) on the camera, whenever any track on that camera reports.

A new `track_key` starts `unassigned`. Each observation copies the track's association at ingest time, so an
unassigned or uncertain track can never become an animal's last-seen observation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import audit, clock
from domain.errors import DomainError
from domain.ids import new_id
from persistence.models import Animal, Camera, CameraScanZone, Observation, Replay, Track

MIN_INLIERS = 5  # exclusive: inliers must be greater than this
MIN_QUALITY = 0.6  # inclusive
LIVE_TRACK_GAP = timedelta(seconds=30)  # a live track key silent this long starts a new track

# Identity continuity, policy handoff_v2. Selected on 10 minutes of real barn footage (8-Calves, 20 fps) with zero
# wrong identities as the first criterion; see ml/results/handoff_policy.md and POLICY in the ML teammate's
# services/api/domain/tracks.py (origin/main).
HANDOFF_POLICY = "handoff_v2"
MAX_GAP_S = 1.0  # release when the associated track is missing for longer than this (exclusive)
CROWD_IOU = 0.6  # release when it overlaps another track at an IoU above this (exclusive) ...
CROWD_S = 0.25  # ... for at least this long, counted from the start of the overlap (inclusive)
SAME_FRAME_S = 0.02  # two tracks' observations this close in time belong to the same camera frame
ZONE_PRESENCE_S = MAX_GAP_S  # a track counts as present at a scan if its latest frame is no older than this
_EPS = 1e-6

EVENTS = ("frame", "muzzle_match", "track_lost", "zone_scan")
STATUSES = ("unassigned", "associated", "uncertain")
RULE = {"name": "muzzle_association_v1", "min_inliers_exclusive": MIN_INLIERS, "min_quality": MIN_QUALITY}
CONTINUITY = {"name": HANDOFF_POLICY, "max_gap_s": MAX_GAP_S, "crowd_iou": CROWD_IOU, "crowd_s": CROWD_S,
              "source": "ml/results/handoff_policy.md"}


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


# --- geometry ----------------------------------------------------------------------------------------------------


def centroid(bbox: list[float]) -> tuple[float, float]:
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def iou(a: list[float], b: list[float]) -> float:
    """Intersection over union of two `[x, y, w, h]` boxes."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


# --- inputs ------------------------------------------------------------------------------------------------------


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


@dataclass(frozen=True)
class ZoneScanInput:
    """A muzzle scan made in the camera's scan zone: who the matcher says was scanned, and how strongly."""
    observed_at: datetime
    animal_id: str | None
    inliers: int | None
    quality: float | None


@dataclass
class ZoneHandoff:
    """What a scan did. `outcome`: associated, already_associated, rejected, no_track, crowded, track_uncertain, or
    conflict. `track_ids` are the tracks in the zone; `observation` is the scan's observation on the one track in
    the zone (None when there was not exactly one)."""
    outcome: str
    reason: str | None
    message: str
    track_ids: list[str] = field(default_factory=list)
    track_keys: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    observation: Observation | None = None


def _validate(item: ObservationInput) -> None:
    problems = []
    if item.event not in EVENTS or item.event == "zone_scan":
        problems.append("event must be one of frame, muzzle_match, track_lost (a zone_scan is not on a track)")
    if len(item.bbox) != 4 or any(not 0 <= v <= 1 for v in item.bbox):
        problems.append("bbox must be [x, y, w, h] with values between 0 and 1")
    if not 0 <= item.visibility <= 1:
        problems.append("visibility must be between 0 and 1")
    if item.observed_at.tzinfo is None:
        problems.append("observed_at must include a timezone")
    if problems:
        raise DomainError("VALIDATION_FAILED", "The observation is not valid.", {"problems": problems})


def _camera_and_replay(session: Session, farm_id: str, camera_id: str, replay_id: str | None) -> Camera:
    camera = session.get(Camera, camera_id)
    if camera is None or camera.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Camera not found.")
    if replay_id is not None:
        replay = session.get(Replay, replay_id)
        if replay is None or replay.farm_id != farm_id or replay.camera_id != camera_id:
            raise DomainError("NOT_FOUND", "Replay not found for this camera.")
    return camera


def _scope(replay_id: str | None):
    return Track.replay_id.is_(None) if replay_id is None else Track.replay_id == replay_id


def _find_track(session: Session, replay_id: str | None, camera_id: str, track_key: str,
                observed_at: datetime) -> Track | None:
    """The open track for this key. A live feed (no replay) may reuse a key for a different animal later, so a key
    silent for more than `LIVE_TRACK_GAP` starts a new, unassigned track instead of inheriting the old identity."""
    query = select(Track).where(Track.camera_id == camera_id, Track.track_key == track_key, _scope(replay_id))
    track = session.scalar(query.order_by(Track.last_seen.desc()).limit(1))
    if track is not None and replay_id is None and observed_at - track.last_seen > LIVE_TRACK_GAP:
        return None
    return track


def _set_track(track: Track, *, status: str, animal_id: str | None, method: str | None, evidence: dict) -> None:
    track.association_status = status
    track.animal_id = animal_id
    track.association_method = method
    track.association_evidence = evidence


# --- continuity (handoff_v2) -------------------------------------------------------------------------------------


def _release(session: Session, track: Track, *, at: datetime, reason: str, farm_id: str, actor: tuple[str, str],
             detail: dict | None = None, downgrade: bool = False) -> None:
    """The continuity policy stops trusting this track's identity at `at`: the track becomes uncertain. With
    `downgrade` (an overlap, untrusted from its start), observations already stored on it from `at` on lose the
    animal too; a missing track was trusted up to its last sighting, so nothing is rewritten."""
    previous, method = track.animal_id, track.association_method
    _set_track(track, status="uncertain", animal_id=None, method=None,
               evidence={"event": "continuity", "decision": "released", "reason": reason,
                         "released_at": clock.isoformat(at), "previous_animal_id": previous,
                         "previous_method": method, "policy": CONTINUITY, **(detail or {}),
                         "previous": {k: v for k, v in (track.association_evidence or {}).items()
                                      if k != "continuity"}})
    if downgrade:
        for row in session.scalars(select(Observation).where(Observation.track_id == track.id,
                                                             Observation.observed_at >= at,
                                                             Observation.animal_id.is_not(None))):
            row.animal_id, row.association_status = None, "uncertain"
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.lost",
                 subject_type="track", subject_id=track.id, animal_id=previous,
                 data={"reason": reason, "track_key": track.track_key, "camera_id": track.camera_id,
                       "replay_id": track.replay_id, "released_at": clock.isoformat(at), "policy": HANDOFF_POLICY,
                       **(detail or {})})


def _sweep_gaps(session: Session, *, camera_id: str, replay_id: str | None, now: datetime, farm_id: str,
                actor: tuple[str, str]) -> None:
    """Release every associated track on the camera (same replay, or recently active live tracks) that has been
    missing for more than `MAX_GAP_S` by `now`. The identity was trusted up to its last sighting."""
    query = select(Track).where(Track.camera_id == camera_id, _scope(replay_id),
                                Track.association_status == "associated",
                                Track.last_seen < now - timedelta(seconds=MAX_GAP_S))
    if replay_id is None:
        query = query.where(Track.last_seen >= now - LIVE_TRACK_GAP)
    for track in session.scalars(query):
        _release(session, track, at=track.last_seen, reason="track_missing", farm_id=farm_id, actor=actor,
                 detail={"missing_s": round((now - track.last_seen).total_seconds(), 3)})


def _same_frame(session: Session, *, camera_id: str, replay_id: str | None, track_id: str,
                at: datetime) -> list[tuple[Track, Observation]]:
    """Every other track's frame observation from the same camera frame as `at` (nearest one per track)."""
    window = timedelta(seconds=SAME_FRAME_S)
    rows = session.execute(
        select(Track, Observation).join(Observation, Observation.track_id == Track.id)
        .where(Track.camera_id == camera_id, _scope(replay_id), Track.id != track_id,
               Observation.event == "frame", Observation.observed_at >= at - window,
               Observation.observed_at <= at + window)).all()
    nearest: dict[str, tuple[Track, Observation]] = {}
    for other, row in rows:
        best = nearest.get(other.id)
        if best is None or abs(row.observed_at - at) < abs(best[1].observed_at - at):
            nearest[other.id] = (other, row)
    return list(nearest.values())


def _crowding(session: Session, track: Track, *, at: datetime, crowded: bool, previous_frame: datetime | None,
              other: Track | None, overlap: float, farm_id: str, actor: tuple[str, str]) -> None:
    """Advance an associated track's overlap clock for the camera frame at `at`. The overlap restarts when the
    track's previous frame was not crowded; once it has lasted `CROWD_S`, the identity is released from its start."""
    if track.association_status != "associated":
        return
    evidence = dict(track.association_evidence or {})
    state = dict(evidence.get("continuity") or {})
    since = datetime.fromisoformat(state["crowd_since"]) if state.get("crowd_since") else None
    last = datetime.fromisoformat(state["crowd_last"]) if state.get("crowd_last") else None
    if since is not None and previous_frame is not None and last is not None and \
            last < previous_frame - timedelta(seconds=_EPS):
        since = last = None  # the previous frame of this track was clear: that overlap ended
    if crowded:
        since = since or at
        last = max(last or at, at)
        if (at - since).total_seconds() >= CROWD_S - _EPS:
            _release(session, track, at=since, reason="overlap", farm_id=farm_id, actor=actor, downgrade=True,
                     detail={"overlap_with": other.track_key if other else None, "iou": round(overlap, 3),
                             "overlap_s": round((at - since).total_seconds(), 3)})
            return
    if since is None:
        if "continuity" in evidence:
            evidence.pop("continuity")
            track.association_evidence = evidence
        return
    evidence["continuity"] = {"crowd_since": clock.isoformat(since), "crowd_last": clock.isoformat(last),
                              "overlap_with": other.track_key if other else state.get("overlap_with")}
    track.association_evidence = evidence


def _check_overlap(session: Session, track: Track, item: ObservationInput, *, previous_frame: datetime | None,
                   replay_id: str | None, farm_id: str, actor: tuple[str, str]) -> None:
    """Compare this frame with every other track's box in the same camera frame. Each pair is compared once, when
    the second of the two frames arrives, and both tracks' overlap clocks advance."""
    others = _same_frame(session, camera_id=track.camera_id, replay_id=replay_id, track_id=track.id,
                         at=item.observed_at)
    worst, worst_iou = None, 0.0
    for other, row in others:
        overlap = iou(item.bbox, row.bbox)
        if overlap > CROWD_IOU:
            _crowding(session, other, at=row.observed_at, crowded=True, previous_frame=None, other=track,
                      overlap=overlap, farm_id=farm_id, actor=actor)
            if overlap > worst_iou:
                worst, worst_iou = other, overlap
    _crowding(session, track, at=item.observed_at, crowded=worst is not None, previous_frame=previous_frame,
              other=worst, overlap=worst_iou, farm_id=farm_id, actor=actor)


# --- events on a track -------------------------------------------------------------------------------------------


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
            _conflict(session, track, evidence, candidate.id, farm_id=farm_id, actor=actor)
        return
    _set_track(track, status="associated", animal_id=candidate.id, method="muzzle_match",
               evidence={**evidence, "decision": "associated", "reason": None})
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.associated",
                 subject_type="track", subject_id=track.id, animal_id=candidate.id,
                 data={"method": "muzzle_match", "track_key": track.track_key, "camera_id": track.camera_id,
                       "inliers": item.inliers, "quality": item.quality, "replay_id": track.replay_id})


def _conflict(session: Session, track: Track, evidence: dict, candidate_id: str, *, farm_id: str,
              actor: tuple[str, str]) -> None:
    previous = track.animal_id
    _set_track(track, status="uncertain", animal_id=None, method=None,
               evidence={**evidence, "decision": "conflict", "reason": "conflicting_match",
                         "previous_animal_id": previous})
    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="track.lost",
                 subject_type="track", subject_id=track.id, animal_id=previous,
                 data={"reason": "conflicting_match", "track_key": track.track_key,
                       "camera_id": track.camera_id, "candidate_animal_id": candidate_id})


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
    """Record one camera observation: find or start its track, apply the continuity policy and the association rule
    for its event, and store the observation with the track's association as it stands now. The caller commits."""
    _validate(item)
    _camera_and_replay(session, farm_id, camera_id, replay_id)
    track = _find_track(session, replay_id, camera_id, item.track_key, item.observed_at)
    previous_frame = None
    if track is None:
        track = Track(id=new_id("trk"), replay_id=replay_id, camera_id=camera_id, track_key=item.track_key,
                      animal_id=None, association_status="unassigned", association_method=None,
                      association_evidence=None, first_seen=item.observed_at, last_seen=item.observed_at)
        session.add(track)
        session.flush()
    else:
        previous_frame = track.last_seen
        if track.association_status == "associated" and \
                (item.observed_at - track.last_seen).total_seconds() > MAX_GAP_S:
            _release(session, track, at=track.last_seen, reason="track_missing", farm_id=farm_id, actor=actor,
                     detail={"missing_s": round((item.observed_at - track.last_seen).total_seconds(), 3)})
    track.first_seen = min(track.first_seen, item.observed_at)
    track.last_seen = max(track.last_seen, item.observed_at)
    _sweep_gaps(session, camera_id=camera_id, replay_id=replay_id, now=item.observed_at, farm_id=farm_id,
                actor=actor)
    if item.event == "frame":
        _check_overlap(session, track, item, previous_frame=previous_frame, replay_id=replay_id, farm_id=farm_id,
                       actor=actor)
    elif item.event == "muzzle_match":
        _apply_match(session, track, item, farm_id=farm_id, actor=actor)
    elif item.event == "track_lost":
        _apply_lost(session, track, item, farm_id=farm_id, actor=actor)
    return _store(session, track, item, farm_id=farm_id, camera_id=camera_id, source=source)


def _store(session: Session, track: Track, item: ObservationInput, *, farm_id: str, camera_id: str,
           source: str) -> Observation:
    associated = track.association_status == "associated"
    observation = Observation(
        id=new_id("obs"), farm_id=farm_id, camera_id=camera_id, track_id=track.id,
        animal_id=track.animal_id if associated else None, association_status=track.association_status,
        observed_at=item.observed_at, bbox=[float(v) for v in item.bbox], visibility=float(item.visibility),
        event=item.event, media_ref=item.media_ref, source=source)
    session.add(observation)
    return observation


# --- scan-zone handoff -------------------------------------------------------------------------------------------


def _present(session: Session, *, camera_id: str, replay_id: str | None,
             at: datetime) -> list[tuple[Track, Observation]]:
    """Tracks on camera at `at`: each one's latest observation no later than `at` and no older than
    `ZONE_PRESENCE_S`, unless that observation reports the track lost."""
    since = at - timedelta(seconds=ZONE_PRESENCE_S)
    rows = session.execute(
        select(Track, Observation).join(Observation, Observation.track_id == Track.id)
        .where(Track.camera_id == camera_id, _scope(replay_id), Observation.observed_at >= since,
               Observation.observed_at <= at)
        .order_by(Observation.observed_at)).all()
    latest: dict[str, tuple[Track, Observation]] = {}
    for track, row in rows:
        latest[track.id] = (track, row)  # ordered by time: the last one wins
    return [(track, row) for track, row in latest.values() if row.event != "track_lost"]


def scan_zone_of(session: Session, camera_id: str) -> CameraScanZone | None:
    return session.get(CameraScanZone, camera_id)


def zone_scan(session: Session, *, farm_id: str, camera_id: str, scan: ZoneScanInput, replay_id: str | None = None,
              actor: tuple[str, str] = ("system", "replay"), source: str = "simulated") -> ZoneHandoff:
    """Hand a scanned animal's identity to the one track inside the camera's scan zone, or to none. The caller
    commits."""
    if scan.observed_at.tzinfo is None:
        raise DomainError("VALIDATION_FAILED", "The scan is not valid.",
                          {"problems": ["observed_at must include a timezone"]})
    _camera_and_replay(session, farm_id, camera_id, replay_id)
    zone = scan_zone_of(session, camera_id)
    if zone is None:
        raise DomainError("VALIDATION_FAILED", "This camera has no calibrated scan zone.",
                          {"problems": ["camera has no scan_zone"], "camera_id": camera_id})
    _sweep_gaps(session, camera_id=camera_id, replay_id=replay_id, now=scan.observed_at, farm_id=farm_id,
                actor=actor)
    session.flush()
    inside = [(track, row) for track, row in _present(session, camera_id=camera_id, replay_id=replay_id,
                                                      at=scan.observed_at)
              if point_in_polygon(*centroid(row.bbox), zone.polygon)]
    inside.sort(key=lambda pair: pair[0].track_key)
    tracks = [track for track, _ in inside]
    candidate = session.get(Animal, scan.animal_id) if scan.animal_id else None
    decision = decide_match(candidate=candidate, farm_id=farm_id, inliers=scan.inliers, quality=scan.quality)
    evidence = {"event": "zone_scan", "candidate_animal_id": scan.animal_id, "inliers": scan.inliers,
                "quality": scan.quality, "observed_at": clock.isoformat(scan.observed_at), "zone": zone.polygon,
                "tracks_in_zone": len(tracks), "track_keys": [t.track_key for t in tracks], "rule": RULE,
                "policy": CONTINUITY}
    result = ZoneHandoff(outcome="", reason=None, message="", track_ids=[t.id for t in tracks],
                         track_keys=[t.track_key for t in tracks], evidence=evidence)

    if not decision.accepted:
        result.outcome, result.reason = "rejected", decision.reason
        result.message = "The scan did not meet the muzzle-match bar, so no identity was handed over."
        for track in tracks:
            updated = {**(track.association_evidence or {}), "last_rejected": {**evidence, "reason": decision.reason}}
            if track.association_status == "unassigned":
                updated.update(decision="rejected", reason=decision.reason, event="zone_scan",
                               tracks_in_zone=len(tracks), observed_at=evidence["observed_at"])
            track.association_evidence = updated
    elif not tracks:
        result.outcome, result.reason = "no_track", "no_track_in_zone"
        result.message = "No track in the scan zone at the scan, so no identity was handed over."
    elif len(tracks) > 1:
        result.outcome, result.reason = "crowded", "multiple_tracks_in_zone"
        result.message = f"{len(tracks)} animals in the scan zone — scan one animal at a time."
        for track in tracks:
            previous = track.animal_id
            _set_track(track, status="uncertain", animal_id=None, method=None,
                       evidence={**evidence, "decision": "crowded", "reason": "multiple_tracks_in_zone",
                                 "message": result.message, "previous_animal_id": previous})
            if previous is not None:
                audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1],
                             event_type="track.lost", subject_type="track", subject_id=track.id, animal_id=previous,
                             data={"reason": "multiple_tracks_in_zone", "track_key": track.track_key,
                                   "camera_id": camera_id, "replay_id": replay_id})
    else:
        track = tracks[0]
        if track.association_status == "uncertain":
            result.outcome, result.reason = "track_uncertain", "track_uncertain"
            result.message = "The track in the zone already lost its identity; a person must review it."
            track.association_evidence = {**(track.association_evidence or {}),
                                          "last_rejected": {**evidence, "reason": "track_uncertain"}}
        elif track.association_status == "associated" and track.animal_id != candidate.id:
            result.outcome, result.reason = "conflict", "conflicting_match"
            result.message = "The track in the zone carries another animal's identity, so it is now uncertain."
            _conflict(session, track, evidence, candidate.id, farm_id=farm_id, actor=actor)
        elif track.association_status == "associated":
            result.outcome = "already_associated"
            result.message = "The track in the zone already carries this animal's identity."
        else:
            result.outcome = "associated"
            result.message = "Identified in the scan zone: the one animal in the zone carries the scanned identity."
            _set_track(track, status="associated", animal_id=candidate.id, method="zone_handoff",
                       evidence={**evidence, "decision": "associated", "reason": None})
            audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1],
                         event_type="track.associated", subject_type="track", subject_id=track.id,
                         animal_id=candidate.id,
                         data={"method": "zone_handoff", "track_key": track.track_key, "camera_id": camera_id,
                               "inliers": scan.inliers, "quality": scan.quality, "tracks_in_zone": 1,
                               "replay_id": replay_id})
        _, row = inside[0]
        result.observation = _store(
            session, track, ObservationInput(track_key=track.track_key, observed_at=scan.observed_at,
                                             bbox=list(row.bbox), visibility=row.visibility, event="zone_scan"),
            farm_id=farm_id, camera_id=camera_id, source=source)

    audit.record(session, farm_id=farm_id, actor_type=actor[0], actor_id=actor[1], event_type="camera.zone_scan",
                 subject_type="camera", subject_id=camera_id,
                 animal_id=candidate.id if decision.accepted and result.outcome == "associated" else None,
                 data={"outcome": result.outcome, "reason": result.reason, "tracks_in_zone": len(tracks),
                       "track_keys": result.track_keys, "inliers": scan.inliers, "quality": scan.quality,
                       "replay_id": replay_id, "policy": HANDOFF_POLICY})
    return result


# --- review ------------------------------------------------------------------------------------------------------


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
