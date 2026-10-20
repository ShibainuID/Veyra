"""The camera muzzle gallery: what the cloud tells each pen camera about the enrolled herd.

A camera worker fetches its farm's gallery (`GET /cameras/{id}/gallery`), loads the muzzle references, and
acknowledges the version it now holds (`POST /cameras/{id}/gallery/ack`). The gallery lists every animal whose
identity is `confirmed`, plus `pending_review` animals flagged as such, with their muzzle references.

`version` is computed, not stored: the number of listed animals plus the number of their muzzle references.
Animals and references are only ever added (enrollment confirm and link), so the number only grows, and every
enrollment that adds an animal or a muzzle reference changes it. A camera is in sync when the version it last
acknowledged equals the current one. A manager's publish records the version pushed to the cameras; in demo mode
the camera workers' acknowledgements are simulated in the same request (labeled `simulated`).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.perception import GalleryRef
from config import get_settings
from domain import audit, clock
from domain.auth import Principal
from domain.errors import DomainError
from domain.passbook import PassbookContext, register_formatter
from persistence.media import signed_url
from persistence.models import (
    Animal, AnimalReference, AuditEvent, Camera, CameraGallerySync, GalleryPublication, Media,
)

GALLERY_STATUSES = ("confirmed", "pending_review")
CAMERA_WORKER = "camera-worker"


@dataclass(frozen=True)
class MuzzleRef:
    reference_id: str
    animal_id: str
    identity_status: str
    crop_media_id: str | None
    path: Path | None  # the crop on disk; None for a seeded reference without footage
    created_at: datetime


def muzzle_refs(session: Session, farm_id: str) -> list[MuzzleRef]:
    """Muzzle references of the farm's gallery animals, oldest first, with the crop file when one is stored."""
    rows = session.execute(
        select(AnimalReference.id, AnimalReference.animal_id, Animal.identity_status,
               AnimalReference.crop_media_id, Media.path, AnimalReference.created_at)
        .join(Animal, Animal.id == AnimalReference.animal_id)
        .outerjoin(Media, Media.id == AnimalReference.crop_media_id)
        .where(Animal.farm_id == farm_id, AnimalReference.view == "muzzle",
               Animal.identity_status.in_(GALLERY_STATUSES))
        .order_by(AnimalReference.animal_id, AnimalReference.created_at, AnimalReference.id)
    ).all()
    media_dir = get_settings().media_dir
    return [MuzzleRef(ref_id, animal_id, status, crop_id, media_dir / path if path else None, created)
            for ref_id, animal_id, status, crop_id, path, created in rows]


def matcher_refs(refs: list[MuzzleRef]) -> list[GalleryRef]:
    """The references the muzzle matcher can load: those whose crop file is on disk."""
    return [GalleryRef(r.animal_id, r.crop_media_id, r.path, r.identity_status)
            for r in refs if r.crop_media_id and r.path is not None and r.path.is_file()]


def _animals(session: Session, farm_id: str) -> list[Animal]:
    return list(session.scalars(select(Animal).where(Animal.farm_id == farm_id,
                                                     Animal.identity_status.in_(GALLERY_STATUSES))
                                .order_by(Animal.id)))


def current_version(session: Session, farm_id: str) -> tuple[int, datetime | None]:
    animals = _animals(session, farm_id)
    refs = muzzle_refs(session, farm_id)
    stamps = [a.created_at for a in animals] + [r.created_at for r in refs]
    return len(animals) + len(refs), max(stamps) if stamps else None


def farm_camera(session: Session, farm_id: str | None, camera_id: str) -> Camera:
    """The camera, scoped to `farm_id` when a person asks (a service token sees every farm's cameras)."""
    camera = session.get(Camera, camera_id)
    if camera is None or (farm_id is not None and camera.farm_id != farm_id):
        raise DomainError("NOT_FOUND", "Camera not found.", {"camera_id": camera_id})
    return camera


def gallery(session: Session, camera: Camera) -> dict:
    animals = _animals(session, camera.farm_id)
    refs = muzzle_refs(session, camera.farm_id)
    by_animal: dict[str, list[MuzzleRef]] = {}
    for ref in refs:
        by_animal.setdefault(ref.animal_id, []).append(ref)
    version, updated_at = current_version(session, camera.farm_id)
    listed = [{"animal_id": a.id, "name": a.name, "identity_status": a.identity_status,
               "references": [{"reference_id": r.reference_id, "view": "muzzle",
                               "media_url": signed_url(r.crop_media_id) if r.crop_media_id else None,
                               "created_at": r.created_at} for r in by_animal.get(a.id, [])]}
              for a in animals]
    # Seeded references carry no footage: a gallery with any of them is partly simulated.
    with_media = [r for r in refs if r.crop_media_id]
    source = "prototype" if refs and len(with_media) == len(refs) else "simulated"
    return {"camera_id": camera.id, "farm_id": camera.farm_id, "version": version, "updated_at": updated_at,
            "animals": listed, "source": source}


def status(session: Session, farm_id: str, version: int | None = None) -> dict[str, dict]:
    """Per camera of the farm: the current version, what it last acknowledged, and whether those match."""
    if version is None:
        version, _ = current_version(session, farm_id)
    syncs = {s.camera_id: s for s in session.scalars(select(CameraGallerySync)
                                                     .where(CameraGallerySync.farm_id == farm_id))}
    out = {}
    for camera_id in session.scalars(select(Camera.id).where(Camera.farm_id == farm_id).order_by(Camera.id)):
        sync = syncs.get(camera_id)
        out[camera_id] = {"current_version": version, "synced_version": sync.synced_version if sync else None,
                          "synced_at": sync.synced_at if sync else None,
                          "in_sync": sync is not None and sync.synced_version == version,
                          "source": sync.source if sync else None}
    return out


def publication(session: Session, farm_id: str) -> dict | None:
    row = session.get(GalleryPublication, farm_id)
    return None if row is None else {"version": row.version, "published_by": row.published_by,
                                     "published_at": row.published_at}


def acknowledge(session: Session, camera: Camera, version: int, *, source: str) -> CameraGallerySync:
    current, _ = current_version(session, camera.farm_id)
    if version > current:
        raise DomainError("VALIDATION_FAILED", "That gallery version does not exist yet.",
                          {"version": version, "current_version": current})
    now = clock.now()
    sync = session.get(CameraGallerySync, camera.id)
    previous = sync.synced_version if sync else None
    if sync is None:
        sync = CameraGallerySync(camera_id=camera.id, farm_id=camera.farm_id, synced_version=version,
                                 synced_at=now, source=source)
        session.add(sync)
    else:
        sync.synced_version, sync.synced_at, sync.source = version, now, source
    session.flush()
    audit.record(session, farm_id=camera.farm_id, actor_type="system", actor_id=CAMERA_WORKER,
                 event_type="camera.gallery_synced", subject_type="camera", subject_id=camera.id,
                 data={"camera_id": camera.id, "version": version, "previous_version": previous,
                       "in_sync": version == current, "source": source})
    return sync


def publish(session: Session, principal: Principal, *, simulate_acks: bool) -> dict:
    version, _ = current_version(session, principal.farm_id)
    now = clock.now()
    row = session.get(GalleryPublication, principal.farm_id)
    if row is None:
        session.add(GalleryPublication(farm_id=principal.farm_id, version=version, published_by=principal.user_id,
                                       published_at=now))
    else:
        row.version, row.published_by, row.published_at = version, principal.user_id, now
    session.flush()
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=principal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="camera.gallery_published", subject_type="farm", subject_id=principal.farm_id,
                 data={"version": version, "simulated_acks": simulate_acks})
    acknowledged = []
    if simulate_acks:
        for camera in session.scalars(select(Camera).where(Camera.farm_id == principal.farm_id).order_by(Camera.id)):
            acknowledge(session, camera, version, source="simulated")
            acknowledged.append(camera.id)
    return {"version": version, "published_at": now, "acknowledged": acknowledged,
            "source": "simulated" if simulate_acks else "prototype"}


@register_formatter("camera.gallery_synced")
def _gallery_synced(event: AuditEvent, ctx: PassbookContext) -> dict:
    data = event.data
    suffix = " (simulated)" if data.get("source") == "simulated" else ""
    return {"title": f"Camera gallery synced · v{data.get('version')}", "detail": f"{data.get('camera_id')}{suffix}"}


@register_formatter("camera.gallery_published")
def _gallery_published(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": f"Gallery pushed to cameras · v{event.data.get('version')}"}
