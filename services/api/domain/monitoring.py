"""Camera monitoring (PRD M07, M08, Sections 4.1 step 7 and 4.5).

recording -> tracks -> scan-zone handoffs (track links) -> per-minute observations -> movement alerts

A track carries an animal's identity only through a confirmed scan-zone handoff, and only while the continuity
policy in `domain.tracks` trusts it. Alerts are built only from usable observations of confirmed links. A
reduced-movement alert requests inspection; it does not diagnose illness, and it cannot start a claim by itself.
"""

import io
import json
import statistics
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import audit, evidence
from domain.perception import get_perception
from domain.tracks import POLICY, Tracks, follow_link, movement_windows, parse_tracks, resolve_handoff
from persistence.models import (
    Alert,
    Animal,
    CameraRecording,
    CameraZone,
    Media,
    Observation,
    TrackLink,
    ZoneScan,
)
from persistence.storage import MediaStore
from workers.runner import WorkerContext, handler

PROCESS_JOB = "camera.process_recording"

# Transparent movement rule (PRD Section 4.2). Movement is in body diagonals per visible minute.
RULE = {
    "version": "reduced_movement_v1",
    "window_minutes": 30,
    "baseline_hours": 24,
    "min_baseline_windows": 30,
    "min_usable_windows": 15,
    "min_visible_fraction": 0.6,
    "ratio_threshold": 0.5,
    "statistic": "median",
}
CLIP_SECONDS = 20.0


def store_bytes(session: Session, media: MediaStore, farm_id: uuid.UUID, data: bytes, kind: str, suffix: str,
                content_type: str, filename: str, owner: uuid.UUID) -> Media:
    key, size, sha = media.save(farm_id, io.BytesIO(data), suffix, enforce_limit=False)
    row = Media(farm_id=farm_id, kind=kind, storage_key=key, original_filename=filename, content_type=content_type,
                size_bytes=size, sha256=sha, uploaded_by=owner)
    session.add(row)
    session.flush()
    return row


def store_tracks(session: Session, media: MediaStore, recording: CameraRecording, data: dict) -> Media:
    row = store_bytes(session, media, recording.farm_id, json.dumps(data, separators=(",", ":")).encode(), "document",
                      ".json", "application/json", f"tracks-{recording.id}.json", recording.created_by)
    recording.tracks_media_id = row.id
    return row


def _at(recording: CameraRecording, seconds: float) -> datetime:
    return recording.started_at + timedelta(seconds=seconds)


def _seconds(recording: CameraRecording, when: datetime) -> float:
    return (when - recording.started_at).total_seconds()


def link_scans(session: Session, recording: CameraRecording, tracks: Tracks) -> list[TrackLink]:
    end = _at(recording, tracks.duration_s)
    scans = list(session.scalars(
        select(ZoneScan).where(ZoneScan.camera_id == recording.camera_id, ZoneScan.scanned_at >= recording.started_at,
                               ZoneScan.scanned_at <= end).order_by(ZoneScan.scanned_at)))
    links, claimed = [], {}
    for scan in scans:
        zone = session.get(CameraZone, scan.zone_id)
        handoff = resolve_handoff(tracks, zone.polygon, _seconds(recording, scan.scanned_at))
        status, reason, track_id = handoff.status, handoff.reason, handoff.track_id
        if status == "confirmed" and track_id in claimed and claimed[track_id] != scan.animal_id:
            # Two different animals cannot share one track; neither scan may hand over identity through it.
            status, reason = "uncertain", "track_already_linked"
        link = TrackLink(farm_id=recording.farm_id, camera_id=recording.camera_id, recording_id=recording.id,
                         scan_id=scan.id, animal_id=scan.animal_id, track_id=track_id if status == "confirmed" else None,
                         status=status, reason=reason, policy_version=POLICY["version"],
                         details={"candidates": list(handoff.candidates), "policy": POLICY})
        if status == "confirmed":
            claimed[track_id] = scan.animal_id
            until, why = follow_link(tracks, track_id, handoff.linked_from_t)
            link.linked_from = _at(recording, handoff.linked_from_t)
            link.linked_until = None if until is None else _at(recording, until)
            link.release_reason = why
        session.add(link)
        session.flush()
        audit.record(session, recording.farm_id, f"camera.identity_{status}", "animal", scan.animal_id,
                     actor_type="worker", details={"track_link_id": str(link.id), "recording_id": str(recording.id),
                                                   "track_id": link.track_id, "reason": reason,
                                                   "release_reason": link.release_reason,
                                                   "candidates": list(handoff.candidates)})
        links.append(link)
    return links


def _association(links: list[TrackLink], track_id: str, start: datetime, end: datetime) -> tuple[str, TrackLink | None]:
    """confirmed only if a confirmed link covers the whole window; any partial or ambiguous cover is uncertain."""
    partial = False
    for link in links:
        if link.status == "uncertain" and track_id in link.details.get("candidates", []):
            partial = True
        if link.status != "confirmed" or link.track_id != track_id:
            continue
        until = link.linked_until or datetime.max.replace(tzinfo=start.tzinfo)
        if link.linked_from <= start and end <= until:
            return "confirmed", link
        if link.linked_from < end and start < until:
            partial = True
    return ("uncertain" if partial else "unassociated"), None


def record_observations(session: Session, recording: CameraRecording, tracks: Tracks,
                        links: list[TrackLink]) -> list[Observation]:
    rows = []
    for track_id in tracks.track_ids():
        for w in movement_windows(tracks, track_id):
            start, end = _at(recording, w["start_s"]), _at(recording, w["end_s"])
            status, link = _association(links, track_id, start, end)
            rows.append(Observation(
                farm_id=recording.farm_id, camera_id=recording.camera_id, recording_id=recording.id,
                track_link_id=link and link.id, track_id=track_id, animal_id=link and link.animal_id,
                association_status=status, observed_at=start, window_seconds=w["end_s"] - w["start_s"],
                movement_score=w["movement_score"], source=recording.source,
                quality={"visible_fraction": w["visible_fraction"], "mean_conf": w["mean_conf"],
                         "usable": w["visible_fraction"] >= RULE["min_visible_fraction"]}))
    session.add_all(rows)
    session.flush()
    return rows


def _open_alert(session: Session, animal_id: uuid.UUID, kind: str, since: datetime) -> Alert | None:
    return session.scalars(select(Alert).where(Alert.animal_id == animal_id, Alert.kind == kind,
                                               Alert.status.in_(("open", "acknowledged")), Alert.window_end >= since)).first()


def _clip(session: Session, ctx: WorkerContext, recording: CameraRecording, alert: Alert, track_id: str) -> Media | None:
    if recording.video_media_id is None or recording.tracks_media_id is None:
        return None
    video = session.get(Media, recording.video_media_id)
    tracks_file = session.get(Media, recording.tracks_media_id)
    end_s = min(_seconds(recording, alert.window_end), float(recording.duration_s or 0))
    start_s = max(end_s - CLIP_SECONDS, _seconds(recording, alert.window_start), 0.0)
    out = ctx.media.path(f"{recording.farm_id}/clips/{alert.id}.mp4")
    perception = get_perception(ctx.settings.yolo_weights, ctx.settings.calf_detector_weights)
    if not perception.extract_clip(ctx.media.path(video.storage_key), out, start_s, end_s, track_id,
                                   json.loads(ctx.media.path(tracks_file.storage_key).read_text())):
        return None
    row = Media(farm_id=recording.farm_id, kind="clip", storage_key=str(out.relative_to(ctx.media.root.resolve())),
                original_filename=out.name, content_type="video/mp4", size_bytes=out.stat().st_size,
                sha256=ctx.media.sha256(str(out.relative_to(ctx.media.root.resolve()))), uploaded_by=recording.created_by)
    session.add(row)
    session.flush()
    return row


def evaluate_animal(session: Session, ctx: WorkerContext, recording: CameraRecording, animal_id: uuid.UUID) -> dict:
    """Apply RULE to the animal's latest confirmed observations; returns what was decided and why."""
    obs = list(session.scalars(
        select(Observation).where(Observation.animal_id == animal_id, Observation.association_status == "confirmed")
        .order_by(Observation.observed_at)))
    if not obs:
        return {"animal_id": str(animal_id), "decision": "no_confirmed_observations"}
    window_end = max(o.observed_at + timedelta(seconds=float(o.window_seconds)) for o in obs)
    window_start = window_end - timedelta(minutes=RULE["window_minutes"])
    baseline_start = window_start - timedelta(hours=RULE["baseline_hours"])
    in_window = [o for o in obs if o.observed_at >= window_start]
    usable = [o for o in in_window if o.quality.get("usable")]
    baseline = [o for o in obs if baseline_start <= o.observed_at < window_start and o.quality.get("usable")]
    base = {"animal_id": str(animal_id), "window_start": window_start, "window_end": window_end,
            "window_observations": len(in_window), "usable_windows": len(usable), "baseline_windows": len(baseline)}

    kind, measurements = None, {}
    if len(in_window) >= RULE["min_usable_windows"] and len(usable) < RULE["min_usable_windows"]:
        kind = "observation_quality"
        measurements = {"reason": "insufficient_visibility"}
    elif len(usable) < RULE["min_usable_windows"]:
        return {**base, "decision": "too_few_observations"}
    elif len(baseline) < RULE["min_baseline_windows"]:
        return {**base, "decision": "baseline_not_established"}
    else:
        baseline_value = statistics.median(float(o.movement_score) for o in baseline)
        window_value = statistics.median(float(o.movement_score) for o in usable)
        ratio = window_value / baseline_value if baseline_value > 0 else 1.0
        measurements = {"baseline_movement": round(baseline_value, 4), "window_movement": round(window_value, 4),
                        "ratio": round(ratio, 4)}
        if ratio >= RULE["ratio_threshold"]:
            return {**base, **measurements, "decision": "within_baseline"}
        kind = "reduced_movement"

    if _open_alert(session, animal_id, kind, window_start):
        return {**base, **measurements, "decision": f"{kind}_already_open"}
    track_id = in_window[-1].track_id
    alert = Alert(farm_id=recording.farm_id, animal_id=animal_id, track_id=track_id, kind=kind,
                  rule={**RULE, **measurements, "usable_windows": len(usable), "baseline_windows": len(baseline)},
                  window_start=window_start, window_end=window_end, source=recording.source)
    session.add(alert)
    session.flush()
    clip = _clip(session, ctx, recording, alert, track_id)
    alert.evidence_media_ids = [str(clip.id)] if clip else []
    pack = evidence.snapshot(session, alert, "alert_created")
    audit.record(session, recording.farm_id, "alert.created", "animal", animal_id, actor_type="worker",
                 details={"alert_id": str(alert.id), "kind": kind, **measurements,
                          "evidence_version": pack.version, "evidence_sha256": pack.manifest_sha256})
    return {**base, **measurements, "decision": f"{kind}_alert", "alert_id": str(alert.id)}


def ingest(session: Session, ctx: WorkerContext, recording: CameraRecording, data: dict) -> dict:
    tracks = parse_tracks(data)
    recording.duration_s = tracks.duration_s
    links = link_scans(session, recording, tracks)
    observations = record_observations(session, recording, tracks, links)
    animals = sorted({o.animal_id for o in observations if o.animal_id}, key=str)
    decisions = [evaluate_animal(session, ctx, recording, a) for a in animals]
    counts = {s: sum(1 for link in links if link.status == s) for s in ("confirmed", "uncertain", "unresolved")}
    return {"tracks": len(tracks.track_ids()), "links": counts, "observations": len(observations),
            "confirmed_observations": sum(1 for o in observations if o.association_status == "confirmed"),
            "decisions": json.loads(json.dumps(decisions, default=str))}


@handler(PROCESS_JOB)
def process_recording(session: Session, job, ctx: WorkerContext) -> dict:
    recording = session.get(CameraRecording, uuid.UUID(job.payload["recording_id"]))
    if recording is None or recording.farm_id != job.farm_id:
        raise LookupError("recording not found for this job")
    recording.status = "processing"
    if recording.tracks_media_id is not None:
        data = json.loads(ctx.media.path(session.get(Media, recording.tracks_media_id).storage_key).read_text())
    else:
        video = session.get(Media, recording.video_media_id)
        perception = get_perception(ctx.settings.yolo_weights, ctx.settings.calf_detector_weights)
        data = perception.track_video(ctx.media.path(video.storage_key))
        store_tracks(session, ctx.media, recording, data)
    summary = ingest(session, ctx, recording, data)
    recording.summary = summary
    recording.status = "processed"
    audit.record(session, recording.farm_id, "camera.recording_processed", "camera_recording", recording.id,
                 actor_type="worker", details={k: v for k, v in summary.items() if k != "decisions"})
    return {"recording_id": str(recording.id), **summary}


def health(session: Session, animal: Animal) -> dict:
    """Camera-based health status for the passport. Observation status only; findings come from a veterinarian."""
    alerts = list(session.scalars(select(Alert).where(Alert.animal_id == animal.id).order_by(Alert.created_at.desc())))
    latest = session.scalars(
        select(Observation).where(Observation.animal_id == animal.id, Observation.association_status == "confirmed")
        .order_by(Observation.observed_at.desc()).limit(1)).first()
    live = [a for a in alerts if a.status in ("open", "acknowledged")]
    reviewed = next((a for a in alerts if a.status == "resolved" and a.assessment), None)
    if any(a.kind == "reduced_movement" and a.status == "open" for a in live):
        status = "needs_inspection"
    elif any(a.kind == "reduced_movement" for a in live):
        status = "under_review"
    elif live:
        status = "observation_gap"
    elif reviewed is not None:
        status = "veterinary_reviewed"
    elif latest is not None:
        status = "normal"
    else:
        status = "not_monitored"
    return {
        "status": status,
        "statement": "Camera observations prompt inspection; they are not a diagnosis.",
        "rule_version": RULE["version"],
        "open_alert_ids": [str(a.id) for a in live],
        "latest_observation": None if latest is None else {
            "observed_at": latest.observed_at, "movement_score": float(latest.movement_score),
            "visible_fraction": latest.quality.get("visible_fraction"), "source": latest.source},
        "last_assessment": None if reviewed is None else {"alert_id": str(reviewed.id), **reviewed.assessment},
    }
