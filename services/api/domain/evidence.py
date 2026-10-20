"""Evidence packs for observation alerts (PRD M08, M10 health-risk notification, M11 claim preparation).

A pack is an immutable, versioned manifest of everything behind one alert: who the animal is and how the camera
track got that identity, the observation windows and the rule that fired, the clip and source files with their
SHA-256, and any review or veterinary assessment. Each change to the alert adds a version. Agent actions and
claims bind to (`version`, `manifest_sha256`), so an approval given on one version does not carry over to another.

The pack states what was observed. It is not a diagnosis, and on its own it cannot initiate a claim submission.
"""

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from persistence.models import (
    Alert,
    Animal,
    CameraRecording,
    EvidencePack,
    Media,
    MuzzleReference,
    Observation,
    TrackLink,
    ZoneScan,
)

SCHEMA = "veyra.evidence/v1"
STATEMENT = ("Camera observation for inspection. It is not a diagnosis, and it does not by itself establish a "
             "covered incident or start a claim.")


def canonical_sha256(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _media(session: Session, media_id, role: str) -> dict | None:
    row = media_id and session.get(Media, media_id)
    if row is None:
        return None
    return {"role": role, "media_id": str(row.id), "kind": row.kind, "content_type": row.content_type,
            "size_bytes": row.size_bytes, "sha256": row.sha256}


def build_manifest(session: Session, alert: Alert, version: int, reason: str) -> dict:
    animal = session.get(Animal, alert.animal_id)
    window_end = alert.window_end
    observations = list(session.scalars(
        select(Observation).where(Observation.animal_id == alert.animal_id, Observation.association_status == "confirmed",
                                  Observation.observed_at >= alert.window_start, Observation.observed_at < window_end)
        .order_by(Observation.observed_at)))
    link_ids = sorted({o.track_link_id for o in observations if o.track_link_id}, key=str)
    links = [session.get(TrackLink, i) for i in link_ids]
    recordings = sorted({o.recording_id for o in observations if o.recording_id}, key=str)
    media = [m for m in (_media(session, mid, "clip") for mid in alert.evidence_media_ids) if m]
    for rid in recordings:
        rec = session.get(CameraRecording, rid)
        media += [m for m in (_media(session, rec.video_media_id, "recording_video"),
                              _media(session, rec.tracks_media_id, "tracks")) if m]
    identity_links = []
    for link in links:
        scan = session.get(ZoneScan, link.scan_id)
        identity_links.append({
            "track_link_id": str(link.id), "camera_id": str(link.camera_id), "recording_id": str(link.recording_id),
            "track_id": link.track_id, "method": "scan_zone_handoff", "policy_version": link.policy_version,
            "scan": {"scan_id": str(scan.id), "zone_id": str(scan.zone_id), "scanned_at": scan.scanned_at,
                     "enrollment_id": scan.enrollment_id and str(scan.enrollment_id)},
            "linked_from": link.linked_from, "linked_until": link.linked_until, "release_reason": link.release_reason})
    return {
        "schema": SCHEMA,
        "version": version,
        "reason": reason,
        "statement": STATEMENT,
        "source": alert.source,
        "alert": {"id": str(alert.id), "kind": alert.kind, "status": alert.status, "window_start": alert.window_start,
                  "window_end": window_end, "created_at": alert.created_at},
        "animal": {
            "id": str(animal.id), "display_id": animal.display_id, "identity_status": animal.identity_status,
            "muzzle_reference_ids": [str(r) for r in session.scalars(
                select(MuzzleReference.id).where(MuzzleReference.animal_id == animal.id))],
        },
        "identity_links": identity_links,
        "rule": alert.rule,
        "observations": [{"id": str(o.id), "observed_at": o.observed_at, "window_seconds": float(o.window_seconds),
                          "movement_score": float(o.movement_score), "visible_fraction": o.quality.get("visible_fraction"),
                          "track_id": o.track_id} for o in observations],
        "media": media,
        # Kept apart, as the PRD requires: camera observation above, human review and professional findings here.
        "review": {"status": alert.status, "notes": alert.review_notes,
                   "reviewed_by": alert.reviewed_by and str(alert.reviewed_by), "reviewed_at": alert.reviewed_at},
        "veterinary_assessment": alert.assessment,
        "completeness": {
            "identity_confirmed": animal.identity_status == "confirmed" and bool(identity_links),
            "clip_attached": any(m["role"] == "clip" for m in media),
            "veterinary_assessment": alert.assessment is not None,
        },
    }


def snapshot(session: Session, alert: Alert, reason: str) -> EvidencePack:
    version = (session.scalar(select(func.max(EvidencePack.version)).where(EvidencePack.alert_id == alert.id)) or 0) + 1
    manifest = build_manifest(session, alert, version, reason)
    manifest = json.loads(json.dumps(manifest, default=str))
    pack = EvidencePack(farm_id=alert.farm_id, animal_id=alert.animal_id, alert_id=alert.id, version=version,
                        manifest=manifest, manifest_sha256=canonical_sha256(manifest))
    session.add(pack)
    session.flush()
    return pack


def latest(session: Session, alert_id) -> EvidencePack | None:
    return session.scalars(select(EvidencePack).where(EvidencePack.alert_id == alert_id)
                           .order_by(EvidencePack.version.desc()).limit(1)).first()
