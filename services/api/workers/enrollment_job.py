"""The `enrollment.process` job: run perception on an enrollment and put it up for review (PRD Section 4.1).

Session rules (`persistence.db`): no transaction is open while perception runs.
1. A read session loads the enrollment, its video path, and the farm's gallery (muzzle crops of confirmed
   animals), then closes.
2. Perception runs: views, identity, weight, age; each step falls back to its labeled fixture on its own.
3. One writing session stores the frames and crops as media, writes the manifest, identity, estimates, and
   review reasons, moves the enrollment `processing → review` (or `failed`), audits `enrollment.processed`
   as the system, and commits.
If perception or saving raises, the enrollment is marked `failed` with the error and the job fails too.
"""

import logging
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select, update

from adapters.perception import GalleryRef, Perception
from config import get_settings
from domain import audit, clock
from domain.auth import ServicePrincipal
from domain.enrollment import PROCESS_JOB
from domain.errors import DomainError
from persistence.db import SessionLocal, read_session
from persistence.media import media_path, store_file
from persistence.models import Animal, AnimalReference, Enrollment, Job, Media
from workers.jobs import register_handler

FRAME_TYPE = "image/jpeg"

logger = logging.getLogger("veyra.enrollment")


def gallery_refs(session, farm_id: str) -> list[GalleryRef]:
    """Muzzle crops of the farm's confirmed animals whose files are on disk (seeded references have none)."""
    rows = session.execute(
        select(AnimalReference.animal_id, Media.id, Media.path)
        .join(Animal, Animal.id == AnimalReference.animal_id)
        .join(Media, Media.id == AnimalReference.crop_media_id)
        .where(Animal.farm_id == farm_id, Animal.identity_status == "confirmed", AnimalReference.view == "muzzle")
        .order_by(AnimalReference.animal_id, AnimalReference.created_at)
    ).all()
    media_dir = get_settings().media_dir
    refs = [GalleryRef(animal_id, media_id, media_dir / path) for animal_id, media_id, path in rows]
    return [ref for ref in refs if ref.path.is_file()]


def _review_reasons(manifest: dict, identity: dict, weight: dict, age: dict) -> list[str]:
    reasons = list(manifest.get("review_reasons") or [])
    if identity.get("outcome") == "uncertain":
        reasons.append("identity_uncertain")
    if identity.get("possible_duplicate"):
        reasons.append("possible_duplicate")
    for prefix, result in (("weight", weight), ("age", age)):
        if result.get("review_required"):
            # Prefixed so an estimator's reason (`teeth_view_missing`) never reads as a missing capture view.
            reason = result.get("review_reason") or "review_required"
            reasons.append(reason if reason.startswith(f"{prefix}_") else f"{prefix}_{reason}")
    return list(dict.fromkeys(reasons))


def run_perception(perception: Perception, video_path: Path | None, work_dir: Path, sample_key: str | None,
                   refs: list[GalleryRef]) -> dict:
    manifest = perception.extract_views(video_path, work_dir, sample_key)
    views = manifest.get("views") or {}
    crop = (views.get("muzzle") or {}).get("crop_path")
    body = (views.get("body") or {}).get("path")
    teeth_id = (views.get("teeth") or {}).get("frame_id")
    identity = perception.identify(Path(crop) if crop else None, refs, sample_key)
    weight = perception.weight(Path(body) if body else None, sample_key)
    age = perception.age(sample_key, [teeth_id] if teeth_id else [])
    manifest["perception"] = {
        "capabilities": dict(perception.capabilities),
        "sources": {"views": manifest.get("source"), "identity": identity.get("source"),
                    "weight": weight.get("source"), "age": age.get("source")},
    }
    return {"manifest": manifest, "identity": identity, "weight": weight, "age": age}


def _store_views(session, farm_id: str, manifest: dict, stored: list[Path]) -> None:
    """Replace worker-local frame paths with media ids (`path → media_id`, `crop_path → crop_media_id`)."""
    for spec in (manifest.get("views") or {}).values():
        for path_key, id_key, kind in (("path", "media_id", "frame"), ("crop_path", "crop_media_id", "crop")):
            if path_key not in spec:
                continue
            local = spec.pop(path_key)
            spec[id_key] = None
            if local and Path(local).is_file():
                media = store_file(session, farm_id, kind, Path(local), FRAME_TYPE)
                stored.append(media_path(media))
                spec[id_key] = media.id


def _record(enrollment_id: str, farm_id: str, outcome: dict) -> dict:
    manifest, identity = outcome["manifest"], outcome["identity"]
    reasons = _review_reasons(manifest, identity, outcome["weight"], outcome["age"])
    unreadable = "video_unreadable" in reasons and not manifest.get("views")
    status = "failed" if unreadable else "review"
    stored: list[Path] = []
    actor_type, actor_id = audit.actor_from(ServicePrincipal())
    try:
        with SessionLocal() as session:
            _store_views(session, farm_id, manifest, stored)
            changed = session.execute(
                update(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.status == "processing")
                .values(status=status, processing_mode=manifest.get("processing_mode"), manifest=manifest,
                        identity=identity, estimates={"weight": outcome["weight"], "age": outcome["age"]},
                        review_reasons=reasons, updated_at=clock.now())
            ).rowcount
            if changed != 1:
                raise DomainError("INVALID_STATE", "The enrollment left processing before the results were saved.")
            audit.record(session, farm_id=farm_id, actor_type=actor_type, actor_id=actor_id,
                         event_type="enrollment.processed", subject_type="enrollment", subject_id=enrollment_id,
                         data={"status": status, "processing_mode": manifest.get("processing_mode"),
                               "sources": manifest["perception"]["sources"], "identity_outcome": identity.get("outcome"),
                               "possible_duplicate": bool(identity.get("possible_duplicate")),
                               "review_reasons": reasons})
            session.commit()
    except Exception:
        for path in stored:
            path.unlink(missing_ok=True)
        raise
    return {"enrollment_id": enrollment_id, "status": status, "review_reasons": reasons,
            "processing_mode": manifest.get("processing_mode")}


def _mark_failed(enrollment_id: str, farm_id: str, exc: Exception) -> None:
    error = {"code": getattr(exc, "code", "INTERNAL_ERROR"), "message": f"{type(exc).__name__}: {exc}"}
    actor_type, actor_id = audit.actor_from(ServicePrincipal())
    with SessionLocal() as session:
        changed = session.execute(
            update(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.status == "processing")
            .values(status="failed", review_reasons=["processing_failed"], manifest={"error": error},
                    updated_at=clock.now())
        ).rowcount
        if changed == 1:
            audit.record(session, farm_id=farm_id, actor_type=actor_type, actor_id=actor_id,
                         event_type="enrollment.failed", subject_type="enrollment", subject_id=enrollment_id,
                         data={"error": error})
        session.commit()


@register_handler(PROCESS_JOB)
def process_enrollment(job_id: str) -> dict:
    with read_session() as session:
        job = session.get(Job, job_id)
        enrollment = session.get(Enrollment, job.subject_id) if job else None
        if enrollment is None:
            raise DomainError("NOT_FOUND", "The job's enrollment does not exist.")
        if enrollment.status != "processing":
            raise DomainError("INVALID_STATE", f"The enrollment is {enrollment.status}, not processing.")
        enrollment_id, farm_id, sample_key = enrollment.id, enrollment.farm_id, enrollment.sample_key
        video = session.get(Media, enrollment.video_media_id) if enrollment.video_media_id else None
        video_path = media_path(video) if video else None
        refs = gallery_refs(session, farm_id)

    work_root = get_settings().data_dir / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=f"{enrollment_id}-", dir=work_root))
    try:
        try:
            outcome = run_perception(Perception(), video_path, work_dir, sample_key, refs)
            return _record(enrollment_id, farm_id, outcome)
        except Exception as exc:
            logger.exception("processing failed for %s", enrollment_id)
            _mark_failed(enrollment_id, farm_id, exc)  # guarded: a no-op if the enrollment left processing
            raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
