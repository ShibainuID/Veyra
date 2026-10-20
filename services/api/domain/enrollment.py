"""Guided-video enrollment (`/enrollments`).

States: `created → uploaded → processing → review → confirmed | rejected`, plus `failed` when processing
could not produce anything to review. Every transition is a guarded update on the expected status. A retry
never reopens an enrollment: it creates a new one with `retry_of_id`; an old one still under review or
processing is superseded (`superseded_by_retry`) in the same transaction, otherwise it stays as it was.

Perception only proposes. A person decides at review time:
- `register_new` creates the animal. A possible duplicate (identity `candidate`, or `possible_duplicate`),
  a missing required view, or an uncertain identity each need an `override_note`. Without a muzzle view, or
  with an uncertain identity, the animal is created `pending_review`, not `confirmed`, so no financial action
  can be prepared for it (`IDENTITY_UNCONFIRMED` downstream).
- `link_existing` adds the enrollment's references to an animal already on the farm; no animal is created and
  no estimates are added (the existing animal's valuation basis does not change behind the manager's back).
  Unless the matcher returned that very animal as its `candidate`, linking needs an `override_note`.
- The duplicate check ran against the herd at processing time. If an animal was registered (or got a muzzle
  reference from another enrollment) since then, `register_new` needs an `override_note`, or a retry re-runs
  the check (`herd_changed_since_processing`).
- `reject` keeps the record with the reason.
No valuation is created here: the manager confirms the valuation inputs separately.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from adapters.perception import REQUIRED_VIEWS, Perception, load_samples
from domain import audit, clock
from domain.auth import Principal
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import PassbookContext, register_formatter
from persistence.media import media_path, signed_url
from persistence.models import Animal, AnimalReference, AuditEvent, Enrollment, Estimate, Job, Media
from workers import jobs

STATUSES = ("created", "uploaded", "processing", "review", "confirmed", "rejected", "failed")
DECISIONS = ("register_new", "link_existing", "reject")
# `processing` is retryable so a job that hangs or dies leaves a way out; the old job's guarded save then fails.
RETRYABLE = ("review", "processing", "rejected", "failed")
SUPERSEDED = "superseded_by_retry"
PROCESS_JOB = "enrollment.process"
MAX_VIDEO_BYTES = 200 * 1024 * 1024
VIDEO_EXT_BY_TYPE = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
VIDEO_TYPE_BY_EXT = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}
ANIMAL_ID_PREFIX = "animal-demo-"
_ANIMAL_NUMBER = re.compile(r"animal-demo-(\d+)")
_ESTIMATE_COLUMNS = ("range_low", "range_high", "unit", "source", "method_version", "review_required",
                     "review_reason")


def _get(session: Session, farm_id: str, enrollment_id: str) -> Enrollment:
    enrollment = session.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Enrollment not found.")
    return enrollment


def _transition(session: Session, enrollment: Enrollment, expected: tuple[str, ...], status: str, **values) -> None:
    changed = session.execute(
        update(Enrollment).where(Enrollment.id == enrollment.id, Enrollment.status.in_(expected))
        .values(status=status, updated_at=clock.now(), **values)
    ).rowcount
    if changed != 1:
        raise DomainError("INVALID_STATE", f"The enrollment is not in a state that allows this ({enrollment.status}).",
                          {"status": enrollment.status, "expected": list(expected)})
    session.refresh(enrollment)


def _audit(session: Session, principal: Principal, enrollment: Enrollment, event_type: str,
           animal_id: str | None = None, data: dict | None = None) -> None:
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=enrollment.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type=event_type, subject_type="enrollment", subject_id=enrollment.id, animal_id=animal_id,
                 data=data)


def known_sample(sample_key: str | None) -> bool:
    return bool(sample_key) and sample_key in load_samples()


# ----- create, upload, process, retry ---------------------------------------------------------------------


def create(session: Session, principal: Principal, sample_key: str | None = None,
           retry_of_id: str | None = None) -> Enrollment:
    if sample_key is not None and not known_sample(sample_key):
        raise DomainError("VALIDATION_FAILED", "Unknown sample.", {"sample_key": sample_key,
                                                                   "known": sorted(load_samples())})
    enrollment = Enrollment(id=new_id("enr"), farm_id=principal.farm_id, status="created", sample_key=sample_key,
                            review_reasons=[], retry_of_id=retry_of_id, created_by=principal.user_id)
    session.add(enrollment)
    session.flush()
    _audit(session, principal, enrollment, "enrollment.created",
           data={"sample_key": sample_key, "retry_of_id": retry_of_id})
    return enrollment


def resolve_video_type(declared: str | None, filename: str | None) -> tuple[str, str]:
    """(content type, extension) for an upload: an allowed declared type, or the extension of an octet-stream."""
    content_type = (declared or "").split(";")[0].strip().lower()
    if content_type in VIDEO_EXT_BY_TYPE:
        return content_type, VIDEO_EXT_BY_TYPE[content_type]
    if content_type in ("", "application/octet-stream"):
        ext = Path(filename or "").suffix.lstrip(".").lower()
        if ext in VIDEO_TYPE_BY_EXT:
            return VIDEO_TYPE_BY_EXT[ext], ext
    raise DomainError("VALIDATION_FAILED", "The upload must be an MP4, WebM, or QuickTime video.",
                      {"content_type": content_type or None, "filename": filename,
                       "allowed": sorted(VIDEO_EXT_BY_TYPE)})


def check_uploadable(session: Session, farm_id: str, enrollment_id: str) -> Enrollment:
    enrollment = _get(session, farm_id, enrollment_id)
    if enrollment.status not in ("created", "uploaded"):
        raise DomainError("INVALID_STATE", "Video can only be uploaded before processing starts.",
                          {"status": enrollment.status, "expected": ["created", "uploaded"]})
    return enrollment


def attach_video(session: Session, principal: Principal, enrollment_id: str, media: Media) -> Path | None:
    """Insert the placed video's row (`persistence.media.place_file`) and point the enrollment at it.

    A re-upload replaces the previous video: its row is deleted here and its file path returned, for the caller
    to unlink after commit. On rollback the caller unlinks the new file.
    """
    enrollment = check_uploadable(session, principal.farm_id, enrollment_id)
    previous_id = enrollment.video_media_id
    session.add(media)
    session.flush()
    _transition(session, enrollment, ("created", "uploaded"), "uploaded", video_media_id=media.id)
    replaced = None
    if previous_id is not None:
        previous = session.get(Media, previous_id)
        if previous is not None:
            replaced = media_path(previous)
            session.delete(previous)
            session.flush()
    _audit(session, principal, enrollment, "enrollment.video_uploaded",
           data={"media_id": media.id, "content_type": media.content_type, "bytes": media.bytes,
                 "sha256": media.sha256, "replaced_media_id": previous_id})
    return replaced


def start_processing(session: Session, principal: Principal, enrollment_id: str) -> Job:
    """Mark the enrollment `processing` and enqueue its job. The caller commits, closes, then `jobs.submit`s."""
    enrollment = _get(session, principal.farm_id, enrollment_id)
    if enrollment.status not in ("created", "uploaded"):
        raise DomainError("INVALID_STATE", "This enrollment has already been processed; retry to start again.",
                          {"status": enrollment.status, "expected": ["created", "uploaded"]})
    if enrollment.video_media_id is None and not known_sample(enrollment.sample_key):
        raise DomainError("VALIDATION_FAILED", "Upload the enrollment video first.",
                          {"reason": "video_required", "sample_key": enrollment.sample_key})
    import workers.enrollment_job  # noqa: F401  (registers the job handler; imported late to avoid a cycle)

    _transition(session, enrollment, ("created", "uploaded"), "processing")
    job = jobs.enqueue(session, enrollment.farm_id, PROCESS_JOB, enrollment.id)
    _audit(session, principal, enrollment, "enrollment.processing_started", data={"job_id": job.id})
    return job


def retry(session: Session, principal: Principal, enrollment_id: str) -> Enrollment:
    """A new enrollment linked to the old one. An old one still under review or processing is superseded in the
    same transaction (review → rejected, processing → failed), so it can no longer be confirmed or saved."""
    old = _get(session, principal.farm_id, enrollment_id)
    if old.status not in RETRYABLE:
        raise DomainError("INVALID_STATE",
                          "Only an enrollment under review, processing, rejected, or failed can be retried.",
                          {"status": old.status, "expected": list(RETRYABLE)})
    previous_status = old.status
    new = create(session, principal, old.sample_key, retry_of_id=old.id)
    if previous_status == "review":
        _transition(session, old, ("review",), "rejected", reviewer_id=principal.user_id,
                    decision=_decision(principal, "reject", reject_reason=SUPERSEDED, superseded_by=new.id))
    elif previous_status == "processing":
        _transition(session, old, ("processing",), "failed",
                    review_reasons=[*(old.review_reasons or []), SUPERSEDED])
    if previous_status in ("review", "processing"):
        _audit(session, principal, old, "enrollment.superseded",
               data={"superseded_by": new.id, "previous_status": previous_status})
    return new


# ----- decision -------------------------------------------------------------------------------------------


def missing_views(enrollment: Enrollment) -> list[str]:
    views = (enrollment.manifest or {}).get("views") or {}
    return [view for view in REQUIRED_VIEWS if view not in views]


def possible_duplicate(identity: dict) -> bool:
    return identity.get("outcome") == "candidate" or bool(identity.get("possible_duplicate"))


def _gallery_as_of(enrollment: Enrollment) -> datetime:
    stamp = ((enrollment.manifest or {}).get("perception") or {}).get("gallery_as_of")
    if stamp:
        try:
            return datetime.fromisoformat(stamp)
        except ValueError:
            pass
    return enrollment.created_at  # unknown: the most cautious time this enrollment's check could have run


def herd_changes_since_processing(session: Session, enrollment: Enrollment) -> list[str]:
    """Animals the duplicate check could not have seen: registered, or given a muzzle reference by another
    enrollment, after this enrollment's gallery snapshot. Read in the confirm transaction (it holds the lock)."""
    as_of = _gallery_as_of(enrollment)
    new_animals = session.scalars(select(Animal.id).where(Animal.farm_id == enrollment.farm_id,
                                                          Animal.created_at > as_of))
    new_refs = session.scalars(
        select(AnimalReference.animal_id).join(Animal, Animal.id == AnimalReference.animal_id)
        .where(Animal.farm_id == enrollment.farm_id, AnimalReference.view == "muzzle",
               AnimalReference.created_at > as_of, AnimalReference.enrollment_id.is_distinct_from(enrollment.id)))
    return sorted(set(new_animals) | set(new_refs))


def next_animal_id(session: Session) -> str:
    taken = {int(m.group(1)) for animal_id in session.scalars(
        select(Animal.id).where(Animal.id.like(f"{ANIMAL_ID_PREFIX}%"))) if (m := _ANIMAL_NUMBER.fullmatch(animal_id))}
    number = 1
    while number in taken:
        number += 1
    return f"{ANIMAL_ID_PREFIX}{number:03d}"


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def confirm(session: Session, principal: Principal, enrollment_id: str, body: dict) -> Enrollment:
    enrollment = _get(session, principal.farm_id, enrollment_id)
    if enrollment.status != "review":
        raise DomainError("INVALID_STATE", "Only an enrollment under review can be decided.",
                          {"status": enrollment.status, "expected": ["review"]})
    decision = body.get("decision")
    if decision == "reject":
        return _reject(session, principal, enrollment, _clean(body.get("reject_reason")))
    if decision == "link_existing":
        return _link_existing(session, principal, enrollment, body.get("link_to"), _clean(body.get("override_note")))
    if decision == "register_new":
        return _register_new(session, principal, enrollment, body.get("animal"), _clean(body.get("override_note")))
    raise DomainError("VALIDATION_FAILED", "Unknown decision.", {"decision": decision, "allowed": list(DECISIONS)})


def _decision(principal: Principal, outcome: str, **extra) -> dict:
    return {"outcome": outcome, "decided_by": principal.user_id, "decided_at": clock.isoformat(clock.now()), **extra}


def _reject(session: Session, principal: Principal, enrollment: Enrollment, reason: str | None) -> Enrollment:
    if reason is None:
        raise DomainError("VALIDATION_FAILED", "Say why the enrollment is rejected.", {"field": "reject_reason"})
    _transition(session, enrollment, ("review",), "rejected", reviewer_id=principal.user_id,
                decision=_decision(principal, "reject", reject_reason=reason))
    _audit(session, principal, enrollment, "enrollment.rejected", data={"reason": reason})
    return enrollment


def _link_existing(session: Session, principal: Principal, enrollment: Enrollment, link_to: str | None,
                   note: str | None) -> Enrollment:
    animal = session.get(Animal, link_to) if link_to else None
    if animal is None or animal.farm_id != enrollment.farm_id:
        raise DomainError("VALIDATION_FAILED", "Choose an animal on this farm to link the enrollment to.",
                          {"field": "link_to", "link_to": link_to})
    identity = enrollment.identity or {}
    suggested = identity.get("animal_id")
    matches = identity.get("outcome") == "candidate" and suggested == animal.id
    # Linking adds this video's frames as the animal's references, so the matcher must have verified that very
    # animal; anything else is a human override and is recorded as one.
    overrides = [] if matches else ["unverified_link"]
    if overrides and note is None:
        message = "Linking to an animal the matcher did not verify needs an override note."
        raise DomainError("VALIDATION_FAILED", message, {
            "field": "override_note", "override_required": overrides, "candidate_animal_id": suggested,
            "identity_outcome": identity.get("outcome"),
            "options": ["link_existing with override_note", "register_new", "reject"],
        })
    _transition(session, enrollment, ("review",), "confirmed", reviewer_id=principal.user_id, animal_id=animal.id,
                decision=_decision(principal, "link_existing", animal_id=animal.id, override_note=note,
                                   overrides=overrides, matches_candidate=matches))
    references = _add_references(session, enrollment, animal.id)
    _audit(session, principal, enrollment, "enrollment.confirmed", animal_id=animal.id,
           data={"decision": "link_existing", "sample_key": enrollment.sample_key, "references": len(references),
                 "override_note": note, "overrides": overrides,
                 "flags": ["unverified_link_override"] if overrides else []})
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=animal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="animal.references_linked", subject_type="animal", subject_id=animal.id,
                 animal_id=animal.id, data={"enrollment_id": enrollment.id, "views": [r.view for r in references]})
    return enrollment


def _animal_fields(enrollment: Enrollment, animal: dict | None) -> dict:
    fields = dict(animal or {})
    if not fields:
        sample = load_samples().get(enrollment.sample_key or "") or {}
        fields = dict(sample.get("proposed_animal") or {})
    missing = [name for name in ("name", "breed", "breed_category", "sex") if not _clean(fields.get(name))]
    if missing:
        raise DomainError("VALIDATION_FAILED", "Describe the new animal.", {"field": "animal", "missing": missing})
    birth_date = fields.get("birth_date")
    if isinstance(birth_date, str):
        try:
            birth_date = date.fromisoformat(birth_date)
        except ValueError:
            raise DomainError("VALIDATION_FAILED", "birth_date must be YYYY-MM-DD.",
                              {"field": "animal.birth_date"}) from None
    return {"name": fields["name"].strip(), "breed": fields["breed"].strip(),
            "breed_category": fields["breed_category"].strip(), "sex": fields["sex"].strip(), "birth_date": birth_date}


def _register_new(session: Session, principal: Principal, enrollment: Enrollment, animal_in: dict | None,
                  note: str | None) -> Enrollment:
    identity = enrollment.identity or {}
    missing = missing_views(enrollment)
    uncertain = identity.get("outcome") == "uncertain"
    changed = herd_changes_since_processing(session, enrollment)
    overrides = ([*(["possible_duplicate"] if possible_duplicate(identity) else []),
                  *(["required_views_missing"] if missing else []),
                  *(["identity_uncertain"] if uncertain else []),
                  *(["herd_changed_since_processing"] if changed else [])])
    if overrides and note is None:
        raise DomainError("VALIDATION_FAILED", "Registering this animal as new needs an override note.", {
            "field": "override_note", "override_required": overrides, "missing_views": missing,
            "candidate_animal_id": identity.get("animal_id"), "changed_animal_ids": changed,
            "options": ["link_existing", "register_new with override_note", "reject",
                        *(["retry to re-run the duplicate check"] if changed else [])],
        })
    fields = _animal_fields(enrollment, animal_in)
    pending = "muzzle" in missing or uncertain
    now = clock.now()
    animal_id = next_animal_id(session)
    # The guarded transition claims the enrollment first; `animal_id` is set once the animal row exists (FK).
    _transition(session, enrollment, ("review",), "confirmed", reviewer_id=principal.user_id,
                decision=_decision(principal, "register_new", animal_id=animal_id, override_note=note,
                                   overrides=overrides, identity_status="pending_review" if pending else "confirmed"))
    animal = Animal(id=animal_id, farm_id=enrollment.farm_id,
                    identity_status="pending_review" if pending else "confirmed",
                    confirmed_by=None if pending else principal.user_id, confirmed_at=None if pending else now,
                    ownership_doc_refs=[], enrollment_id=enrollment.id, created_at=now, **fields)
    session.add(animal)
    session.flush()
    enrollment.animal_id = animal_id
    references = _add_references(session, enrollment, animal_id)
    _add_estimates(session, enrollment, animal, now)
    flags = ["possible_duplicate_override"] if "possible_duplicate" in overrides else []
    _audit(session, principal, enrollment, "enrollment.confirmed", animal_id=animal_id, data={
        "decision": "register_new", "sample_key": enrollment.sample_key, "identity_status": animal.identity_status,
        "override_note": note, "overrides": overrides, "flags": flags, "references": len(references),
        "processing_mode": enrollment.processing_mode})
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=animal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="animal.registered", subject_type="animal", subject_id=animal_id, animal_id=animal_id,
                 data={"name": animal.name, "identity_status": animal.identity_status, "enrollment_id": enrollment.id,
                       "flags": flags})
    return enrollment


def _add_references(session: Session, enrollment: Enrollment, animal_id: str) -> list[AnimalReference]:
    manifest = enrollment.manifest or {}
    source = manifest.get("source")
    references = []
    for view in REQUIRED_VIEWS:
        spec = (manifest.get("views") or {}).get(view)
        if spec is None:
            continue
        quality = {k: spec[k] for k in ("frame_id", "view_prob", "sharpness", "frames_with_view") if k in spec}
        quality["source"] = source
        if spec.get("media_id") is None:
            quality["note"] = "sample enrollment, footage not attached"
        reference = AnimalReference(id=new_id("ref"), animal_id=animal_id, view=view, media_id=spec.get("media_id"),
                                    crop_media_id=spec.get("crop_media_id"), enrollment_id=enrollment.id,
                                    frame_time_s=spec.get("time_s"), quality=quality)
        session.add(reference)
        references.append(reference)
    session.flush()
    return references


def _estimate(animal_id: str, kind: str, result: dict, now, evidence_extra: dict) -> Estimate:
    evidence = {k: v for k, v in result.items() if k not in _ESTIMATE_COLUMNS and k != "point_kg"}
    evidence.update(evidence_extra)
    return Estimate(id=new_id("est"), animal_id=animal_id, kind=kind, range_low=result.get("range_low"),
                    range_high=result.get("range_high"), point=result.get("point_kg"),
                    unit=result.get("unit") or ("kg" if kind == "weight" else "months"),
                    source=result.get("source") or "simulated", method_version=result.get("method_version") or "none",
                    evidence=evidence, review_required=bool(result.get("review_required")),
                    review_reason=result.get("review_reason"), created_at=now)


def _add_estimates(session: Session, enrollment: Enrollment, animal: Animal, now) -> None:
    estimates = enrollment.estimates or {}
    views = (enrollment.manifest or {}).get("views") or {}
    age = estimates.get("age")
    if animal.birth_date is not None:  # a documented birth date outranks the fixture (age adapter priority)
        teeth = views.get("teeth") or {}
        teeth_ids = [teeth["frame_id"]] if teeth.get("frame_id") else []
        age = Perception(capabilities={}).age(enrollment.sample_key, teeth_ids,
                                              documented_birth_date=animal.birth_date, observed_on=now.date())
    for kind, result, view in (("age", age, "teeth"), ("weight", estimates.get("weight"), "body")):
        if not result:
            continue
        frame = views.get(view) or {}
        session.add(_estimate(animal.id, kind, result, now, {
            "enrollment_id": enrollment.id, "evidence_media_id": frame.get("media_id"), "evidence_view": view}))
    session.flush()


# ----- read models ----------------------------------------------------------------------------------------


def _view_out(spec: dict) -> dict:
    out = dict(spec)
    out["url"] = signed_url(spec["media_id"]) if spec.get("media_id") else None
    if "crop_media_id" in spec:
        out["crop_url"] = signed_url(spec["crop_media_id"]) if spec.get("crop_media_id") else None
    return out


def _identity_out(session: Session, farm_id: str, identity: dict | None) -> dict | None:
    if identity is None:
        return None
    identity = json.loads(json.dumps(identity))
    ids = {c.get("animal_id") for c in identity.get("candidates") or []} | {identity.get("animal_id")}
    ids.discard(None)
    names = dict(session.execute(select(Animal.id, Animal.name)
                                 .where(Animal.farm_id == farm_id, Animal.id.in_(ids))).all()) if ids else {}
    for candidate in identity.get("candidates") or []:
        candidate["animal_name"] = names.get(candidate.get("animal_id"))
    if identity.get("animal_id"):
        identity["animal_name"] = names.get(identity["animal_id"])
    identity["possible_duplicate"] = bool(identity.get("possible_duplicate"))
    return identity


def enrollment_out(session: Session, enrollment: Enrollment, *, full: bool = True) -> dict:
    manifest = enrollment.manifest
    perception = (manifest or {}).get("perception") or {}
    job = jobs.latest_job(session, PROCESS_JOB, enrollment.id)
    out = {
        "id": enrollment.id, "status": enrollment.status, "sample_key": enrollment.sample_key,
        "video_media_id": enrollment.video_media_id,
        "video_url": signed_url(enrollment.video_media_id) if enrollment.video_media_id else None,
        "processing_mode": enrollment.processing_mode, "review_reasons": list(enrollment.review_reasons or []),
        "sources": perception.get("sources"), "capabilities": perception.get("capabilities"),
        "decision": enrollment.decision, "reviewer_id": enrollment.reviewer_id, "animal_id": enrollment.animal_id,
        "retry_of_id": enrollment.retry_of_id, "created_by": enrollment.created_by,
        "created_at": enrollment.created_at, "updated_at": enrollment.updated_at,
        "job": {"id": job.id, "status": job.status} if job else None,
    }
    if full:
        if manifest is not None:
            manifest = json.loads(json.dumps(manifest))
            manifest["views"] = {name: _view_out(spec) for name, spec in (manifest.get("views") or {}).items()}
        out.update(manifest=manifest, identity=_identity_out(session, enrollment.farm_id, enrollment.identity),
                   estimates=enrollment.estimates)
    return out


def get_enrollment(session: Session, farm_id: str, enrollment_id: str) -> dict:
    return enrollment_out(session, _get(session, farm_id, enrollment_id))


def list_enrollments(session: Session, farm_id: str, status: str | None = None) -> list[dict]:
    query = select(Enrollment).where(Enrollment.farm_id == farm_id)
    if status is not None:
        query = query.where(Enrollment.status == status)
    rows = session.scalars(query.order_by(Enrollment.created_at.desc(), Enrollment.id)).all()
    return [enrollment_out(session, row, full=False) for row in rows]


# ----- passbook -------------------------------------------------------------------------------------------


@register_formatter("enrollment.confirmed")
def _enrollment_confirmed(event: AuditEvent, ctx: PassbookContext) -> dict:
    data = event.data
    if data.get("decision") == "link_existing":
        return {"title": "Enrollment linked to this animal", "detail": data.get("sample_key"),
                "stamp": {"kind": "confirmed"}}
    detail = "Identity pending review" if data.get("identity_status") == "pending_review" else data.get("sample_key")
    if data.get("override_note"):
        detail = f"{detail} · override: {data['override_note']}" if detail else f"Override: {data['override_note']}"
    return {"title": "Enrolled from guided video", "detail": detail, "stamp": {"kind": "confirmed"}}


@register_formatter("animal.registered")
def _animal_registered(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Registered in herd", "detail": event.data.get("name")}


@register_formatter("animal.references_linked")
def _references_linked(event: AuditEvent, ctx: PassbookContext) -> dict:
    views = event.data.get("views") or []
    return {"title": "Reference frames added", "detail": ", ".join(views) if views else None}
