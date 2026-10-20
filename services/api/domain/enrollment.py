"""Enrollment workflow (PRD Section 4.1 steps 1-2, M02, M03).

created -> uploaded -> processing -> ready | needs_review -> confirmed | rejected

Processing runs in the worker: it extracts frames, runs the muzzle, weight, and age adapters, and
computes the muzzle reference features. Confirmation is always a human decision. Uncertain identity,
possible duplicates, and incomplete evidence require an explicit acknowledgement from the reviewer.
"""

import hashlib
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.age import estimate_age
from domain import audit
from domain.errors import APIError, ErrorCode
from domain.perception import GalleryReference, get_perception
from persistence.models import Animal, Enrollment, Estimate, Job, Media, MuzzleReference, User
from persistence.storage import MediaStore
from workers.runner import WorkerContext, handler

PROCESS_JOB = "enrollment.process"


def _register_file(session: Session, media: MediaStore, farm_id: uuid.UUID, path: Path, uploaded_by: uuid.UUID) -> uuid.UUID:
    key = str(path.resolve().relative_to(media.root.resolve()))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    row = Media(farm_id=farm_id, kind="image", storage_key=key, original_filename=path.name, content_type="image/jpeg",
                size_bytes=path.stat().st_size, sha256=digest, uploaded_by=uploaded_by)
    session.add(row)
    session.flush()
    return row.id


def load_gallery(session: Session, media: MediaStore, farm_id: uuid.UUID) -> list[GalleryReference]:
    refs = session.scalars(select(MuzzleReference).where(MuzzleReference.farm_id == farm_id))
    return [GalleryReference(r.animal_id, r.id, r.embedding, media.path(r.sift_storage_key)) for r in refs]


@handler(PROCESS_JOB)
def process(session: Session, job: Job, ctx: WorkerContext) -> dict:
    enrollment = session.get(Enrollment, uuid.UUID(job.payload["enrollment_id"]))
    if enrollment is None or enrollment.farm_id != job.farm_id:
        raise LookupError("enrollment not found for this job")
    video = session.get(Media, enrollment.video_media_id)
    inputs = enrollment.capture_inputs or {}
    perception = get_perception(ctx.settings.yolo_weights)
    out_dir = ctx.media.path(f"{enrollment.farm_id}/enrollments/{enrollment.id}")
    owner = enrollment.created_by

    manifest = perception.process_video(ctx.media.path(video.storage_key), out_dir, float(inputs.get("marker_cm", 15.0)))
    manifest.get("video", {}).pop("path", None)
    files: dict[str, Path] = {}
    for view, info in manifest.get("views", {}).items():
        files[view] = Path(info.pop("path"))
        info["media_id"] = str(_register_file(session, ctx.media, enrollment.farm_id, files[view], owner))
        if "crop_path" in info:
            files["muzzle_crop"] = Path(info.pop("crop_path"))
            info["crop_media_id"] = str(_register_file(session, ctx.media, enrollment.farm_id, files["muzzle_crop"], owner))
    reasons = list(manifest.get("review_reasons", []))

    identity = None
    if "muzzle_crop" in files:
        features_key = f"{enrollment.farm_id}/enrollments/{enrollment.id}/muzzle_features.npz"
        embedding = perception.save_reference_features(files["muzzle_crop"], ctx.media.path(features_key))
        identity = perception.identify(files["muzzle_crop"], load_gallery(session, ctx.media, enrollment.farm_id))
        identity["reference"] = None if embedding is None else {"features_key": features_key, "embedding": embedding,
                                                                "model_version": perception.model_version}
        if identity["outcome"] == "uncertain":
            reasons.append(f"identity_{identity['reason']}")
        if identity.get("possible_duplicate"):
            reasons.append("possible_duplicate_registration")

    body = manifest.get("views", {}).get("body")
    if body and body.get("scale_reference"):
        weight = perception.estimate_weight(files["body"], body["scale_reference"], inputs.get("tape_heart_girth_cm"))
    else:
        weight = {"source": "prototype", "review_required": True,
                  "review_reason": "body_view_missing" if body is None else "marker_not_detected"}
    if weight.get("review_required"):
        reasons.append(f"weight_{weight.get('review_reason')}")

    teeth = manifest.get("views", {}).get("teeth")
    birth = inputs.get("documented_birth_date")
    age = estimate_age(inputs.get("sample_key", ""), [teeth["media_id"]] if teeth else [],
                       documented_birth_date=date.fromisoformat(birth) if birth else None)
    if age.get("review_required"):
        reasons.append(f"age_{age['review_reason']}")

    reasons = list(dict.fromkeys(reasons))
    enrollment.manifest = manifest
    enrollment.identity_result = identity
    enrollment.estimate_results = {"weight": weight, "age": age}
    enrollment.review_reasons = reasons
    enrollment.processing_mode = "prototype"
    enrollment.status = "needs_review" if reasons else "ready"
    audit.record(session, enrollment.farm_id, "enrollment.processed", "enrollment", enrollment.id, actor_type="worker",
                 details={"status": enrollment.status, "identity_outcome": identity and identity["outcome"],
                          "review_reasons": reasons})
    return {"enrollment_id": str(enrollment.id), "status": enrollment.status,
            "identity_outcome": identity and identity["outcome"], "review_reasons": reasons}


def next_display_id(session: Session, farm_id: uuid.UUID) -> str:
    count = session.scalar(select(func.count()).select_from(Animal).where(Animal.farm_id == farm_id))
    return f"animal-{count + 1:03d}"


def _require_acknowledgement(acknowledged: bool, message: str, details: dict) -> None:
    if not acknowledged:
        raise APIError(ErrorCode.APPROVAL_REQUIRED, message, details)


def confirm(
    session: Session,
    enrollment: Enrollment,
    user: User,
    decision: str,
    animal_id: uuid.UUID | None,
    acknowledge_review: bool,
    notes: str | None,
) -> Animal:
    if enrollment.status not in ("ready", "needs_review"):
        raise APIError(ErrorCode.CONFLICT, f"Enrollment is '{enrollment.status}', not ready for review.")
    identity = enrollment.identity_result or {}
    reference = identity.get("reference")
    if reference is None:
        raise APIError(ErrorCode.EVIDENCE_INCOMPLETE, "A usable muzzle view is required to confirm identity.",
                       {"review_reasons": enrollment.review_reasons})
    if enrollment.review_reasons:
        _require_acknowledgement(acknowledge_review, "Review reasons must be acknowledged before confirmation.",
                                 {"review_reasons": enrollment.review_reasons})

    now = datetime.now(UTC)
    if decision == "new_animal":
        if identity.get("outcome") in ("candidate", "uncertain") or identity.get("possible_duplicate"):
            _require_acknowledgement(acknowledge_review, "A registered animal may match; confirm this is a new animal.",
                                     {"candidates": identity.get("candidates", [])})
        animal = Animal(farm_id=enrollment.farm_id, display_id=next_display_id(session, enrollment.farm_id),
                        identity_status="confirmed", confirmed_by=user.id, confirmed_at=now,
                        sex=(enrollment.capture_inputs or {}).get("sex"), breed=(enrollment.capture_inputs or {}).get("breed"))
        session.add(animal)
        session.flush()
        audit.record(session, animal.farm_id, "animal.created", "animal", animal.id, actor_id=user.id,
                     details={"display_id": animal.display_id, "enrollment_id": str(enrollment.id)})
    elif decision == "existing_animal":
        animal = session.get(Animal, animal_id) if animal_id else None
        if animal is None or animal.farm_id != enrollment.farm_id:
            raise APIError(ErrorCode.NOT_FOUND, "Animal not found.")
        matched = identity.get("outcome") == "candidate" and identity.get("animal_id") == str(animal.id)
        if not matched:
            _require_acknowledgement(acknowledge_review, "The muzzle check did not verify this animal; confirm the link.",
                                     {"identity_outcome": identity.get("outcome"), "candidate": identity.get("animal_id")})
    else:
        raise APIError(ErrorCode.VALIDATION_FAILED, "decision must be 'new_animal' or 'existing_animal'.")

    crop_media_id = enrollment.manifest["views"]["muzzle"]["crop_media_id"]
    session.add(MuzzleReference(farm_id=enrollment.farm_id, animal_id=animal.id, media_id=uuid.UUID(crop_media_id),
                                model_version=reference["model_version"], embedding=reference["embedding"],
                                sift_storage_key=reference["features_key"]))
    for kind, result in (enrollment.estimate_results or {}).items():
        session.add(Estimate(
            farm_id=enrollment.farm_id, animal_id=animal.id, enrollment_id=enrollment.id, kind=kind,
            range_low=result.get("range_low"), range_high=result.get("range_high"),
            unit=result.get("unit") or ("kg" if kind == "weight" else "months"),
            source=result.get("source", "prototype"), method_version=result.get("method_version", "unknown"),
            details=result, review_required=bool(result.get("review_required")),
        ))
    enrollment.animal_id = animal.id
    enrollment.status = "confirmed"
    enrollment.reviewed_by = user.id
    enrollment.reviewed_at = now
    audit.record(session, enrollment.farm_id, "enrollment.confirmed", "enrollment", enrollment.id, actor_id=user.id,
                 details={"decision": decision, "animal_id": str(animal.id), "acknowledged_review": acknowledge_review,
                          "review_reasons": enrollment.review_reasons, "notes": notes})
    audit.record(session, enrollment.farm_id, "animal.reference_added", "animal", animal.id, actor_id=user.id,
                 details={"enrollment_id": str(enrollment.id), "media_id": crop_media_id})
    return animal


def reject(session: Session, enrollment: Enrollment, user: User, reason: str) -> None:
    if enrollment.status in ("confirmed", "rejected"):
        raise APIError(ErrorCode.CONFLICT, f"Enrollment is already '{enrollment.status}'.")
    enrollment.status = "rejected"
    enrollment.reviewed_by = user.id
    enrollment.reviewed_at = datetime.now(UTC)
    audit.record(session, enrollment.farm_id, "enrollment.rejected", "enrollment", enrollment.id, actor_id=user.id,
                 details={"reason": reason})
