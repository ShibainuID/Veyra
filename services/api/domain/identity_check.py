"""Claim-time muzzle identity check: "if the cow dies, scan the muzzle to know right or wrong cow".

A manager or operator scans the muzzle of the animal a claim is about (a photo or a short video), and VEYRA compares
the scan with the muzzle references enrolled for that animal. The check runs in three steps, so no transaction is
open while the matcher runs (`persistence.db` session rules):
1. `prepare` (read session): the claim must be open and about an animal that can be scanned (not theft); loads the
   gallery: this animal's references plus every other confirmed animal's, so a wrong cow surfaces by name.
2. `run` (no session): a photo is cropped to the capture screen's muzzle guide box (`guide_box_crop`); a video goes
   through the perception facade's view extraction for its muzzle crop. The crop goes to the real muzzle matcher
   (`Perception.identify`) when the muzzle capability is available. A demo `sample` (`match`/`mismatch`), or an
   upload without the capability, gets a fixture outcome labeled `simulated`.
3. `record` (writing session): stores the crop, the check row, refreshes the claim checklist, audits
   `claim.identity_checked`.

Outcome mapping: the matcher's candidate is the claim animal → `match`; another animal → `mismatch` naming it;
`new` (no verified match) → `mismatch`, "no verified match to this animal"; `uncertain` → `uncertain` (retake).
When the claim animal has no enrolled muzzle image on disk, the check cannot confirm it: `uncertain` unless another
animal verified (`mismatch`). The matcher result is evidence for a person and the insurer, never a decision.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.perception import Perception, guide_box_crop
from domain import audit, claims, clock, gallery
from domain.auth import Principal
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import PassbookContext, register_formatter
from persistence.media import media_path, signed_url, store_file
from persistence.models import Animal, AnimalReference, AuditEvent, IdentityCheck, Incident, Media, User

PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
VIDEO_TYPES = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
TYPE_BY_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
               "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}
MAX_SCAN_BYTES = 50 * 1024 * 1024
SAMPLES = ("match", "mismatch")
OUTCOMES = ("match", "mismatch", "uncertain")
NOT_SCANNABLE_KINDS = ("theft",)
SIMULATED_METHOD = "identity_check_fixture_v1"
CROP_TYPE = "image/jpeg"
# Fixture outcomes for the demo samples (labeled simulated): plausible support numbers, not measurements.
SAMPLE_INLIERS = {"match": 38, "mismatch": 27}
ACCEPT_INLIERS = 5

logger = logging.getLogger("veyra.identity_check")


@dataclass
class Prepared:
    """What the read session hands to the matcher step."""

    claim_id: str
    farm_id: str
    animal_id: str
    animal_name: str
    reference_id: str | None  # the claim animal's latest muzzle reference, shown beside the scan
    refs: list = field(default_factory=list)  # GalleryRef entries the matcher can load
    animal_refs: int = 0  # how many of `refs` are the claim animal's
    names: dict[str, str] = field(default_factory=dict)


def resolve_scan_type(declared: str | None, filename: str | None) -> tuple[str, str, str]:
    """(kind `photo`|`video`, content type, extension) for an upload, from an allowed type or the file extension."""
    content_type = (declared or "").split(";")[0].strip().lower()
    if content_type in ("", "application/octet-stream"):
        content_type = TYPE_BY_EXT.get(Path(filename or "").suffix.lstrip(".").lower(), content_type)
    if content_type in PHOTO_TYPES:
        return "photo", content_type, PHOTO_TYPES[content_type]
    if content_type in VIDEO_TYPES:
        return "video", content_type, VIDEO_TYPES[content_type]
    raise DomainError("VALIDATION_FAILED", "The scan must be a JPEG, PNG, or WebP photo, or an MP4, WebM, or "
                      "QuickTime video.", {"content_type": content_type or None, "filename": filename,
                                           "allowed": sorted(PHOTO_TYPES) + sorted(VIDEO_TYPES)})


def prepare(session: Session, principal: Principal, claim_id: str) -> Prepared:
    claim = claims.farm_claim(session, principal.farm_id, claim_id)
    if claim.status not in claims.OPEN_CLAIM_STATUSES:
        raise DomainError("INVALID_STATE", "The identity can be checked only on an unsubmitted claim.",
                          {"status": claim.status})
    incident = session.get(Incident, claim.incident_id)
    if incident.kind in NOT_SCANNABLE_KINDS:
        raise DomainError("INVALID_STATE", "A theft claim has no animal to scan.", {"kind": incident.kind})
    animal = session.get(Animal, claim.animal_id)
    refs = [r for r in gallery.muzzle_refs(session, principal.farm_id)
            if r.animal_id == animal.id or r.identity_status == "confirmed"]
    loadable = gallery.matcher_refs(refs)
    own = [r for r in refs if r.animal_id == animal.id]
    shown = next((r for r in reversed(own) if r.crop_media_id), own[-1] if own else None)
    names = dict(session.execute(select(Animal.id, Animal.name).where(Animal.farm_id == principal.farm_id)).all())
    return Prepared(claim_id=claim.id, farm_id=claim.farm_id, animal_id=animal.id, animal_name=animal.name,
                    reference_id=shown.reference_id if shown else None, refs=loadable,
                    animal_refs=sum(1 for r in loadable if r.animal_id == animal.id), names=names)


# ----- the check (no session) ----------------------------------------------------------------------------------

def _candidate(prepared: Prepared, animal_id: str, inliers: int, cosine: float) -> dict:
    return {"animal_id": animal_id, "animal_name": prepared.names.get(animal_id), "inliers": inliers,
            "cosine": cosine}


def _result(outcome: str, reason: str | None, *, source: str, method_version: str, matched: str | None = None,
            candidates: list | None = None, inliers: int | None = None, evidence: dict | None = None) -> dict:
    return {"outcome": outcome, "reason": reason, "matched_animal_id": matched, "candidates": candidates or [],
            "inliers": inliers, "source": source, "method_version": method_version, "evidence": evidence or {}}


def simulated(prepared: Prepared, sample: str) -> dict:
    """The demo outcome for `sample`: the claimed animal, or another confirmed animal of the farm (simulated)."""
    evidence = {"input": "sample", "sample": sample, "accept_inliers": ACCEPT_INLIERS}
    if sample == "match":
        inliers = SAMPLE_INLIERS["match"]
        return _result("match", None, source="simulated", method_version=SIMULATED_METHOD, matched=prepared.animal_id,
                       candidates=[_candidate(prepared, prepared.animal_id, inliers, 0.93)], inliers=inliers,
                       evidence=evidence)
    other = next((a for a in sorted(prepared.names) if a != prepared.animal_id), None)
    if other is None:
        return _result("mismatch", "No verified match to this animal", source="simulated",
                       method_version=SIMULATED_METHOD, evidence=evidence)
    inliers = SAMPLE_INLIERS["mismatch"]
    return _result("mismatch", _matched_other(prepared, other), source="simulated", method_version=SIMULATED_METHOD,
                   matched=other, candidates=[_candidate(prepared, other, inliers, 0.88),
                                              _candidate(prepared, prepared.animal_id, 0, 0.41)],
                   inliers=inliers, evidence=evidence)


def _matched_other(prepared: Prepared, other: str) -> str:
    return f"Muzzle scan matched {prepared.names.get(other, other)} ({other}), not {prepared.animal_name}"


def _photo_crop(photo: Path, work_dir: Path) -> Path | None:
    import cv2

    frame = cv2.imread(str(photo))
    if frame is None:
        return None
    crop_path = work_dir / "scan_muzzle_crop.jpg"
    cv2.imwrite(str(crop_path), guide_box_crop(frame))
    return crop_path


def run(prepared: Prepared, scan: Path, scan_kind: str, work_dir: Path, perception: Perception | None = None) -> dict:
    """Crop the scan and compare it with the gallery. Returns the result plus `crop_path` when a crop was made."""
    perception = perception or Perception()
    work_dir.mkdir(parents=True, exist_ok=True)
    evidence: dict = {"input": scan_kind, "accept_inliers": ACCEPT_INLIERS,
                      "capabilities": {"muzzle": bool(perception.capabilities.get("muzzle")),
                                       "video": bool(perception.capabilities.get("video"))}}
    if scan_kind == "video":
        manifest = perception.extract_views(scan, work_dir, None)
        muzzle = (manifest.get("views") or {}).get("muzzle") or {}
        crop = Path(muzzle["crop_path"]) if muzzle.get("crop_path") else None
        evidence["views"] = {"source": manifest.get("source"), "method_version": manifest.get("method_version"),
                             "frame_id": muzzle.get("frame_id"), "time_s": muzzle.get("time_s")}
        if manifest.get("fallback"):
            evidence["views"]["fallback"] = manifest["fallback"]
    else:
        crop = _photo_crop(scan, work_dir)
        evidence["crop"] = "guide_box_90pct_1.18"
    if crop is None or not crop.is_file():
        reason = "No muzzle frame could be read from the scan; retake the scan"
        return {**_result("uncertain", reason, source="prototype" if perception.capabilities.get("muzzle")
                          else "simulated", method_version="none", evidence=evidence), "crop_path": None}
    if not perception.capabilities.get("muzzle"):
        reason = "The muzzle matcher is not available here, so the scan was not compared; retake where it runs"
        return {**_result("uncertain", reason, source="simulated", method_version="none", evidence=evidence),
                "crop_path": crop}
    identity = perception.identify(crop, prepared.refs, None)
    return {**_map_identity(prepared, identity, evidence), "crop_path": crop}


def _map_identity(prepared: Prepared, identity: dict, evidence: dict) -> dict:
    candidates = [{"animal_id": c.get("animal_id"), "animal_name": prepared.names.get(c.get("animal_id")),
                   "inliers": c.get("inliers"), "cosine": c.get("cosine")} for c in identity.get("candidates") or []]
    evidence = {**evidence, "gallery": identity.get("gallery"), "matcher_outcome": identity.get("outcome"),
                "matcher_reason": identity.get("reason"),
                "accept_inliers": identity.get("accept_inliers", ACCEPT_INLIERS)}
    source = identity.get("source") or "prototype"
    method = identity.get("method_version") or "muzzle_hybrid_v1"
    if identity.get("fallback"):
        evidence["fallback"] = identity["fallback"]
        return _result("uncertain", "The muzzle matcher failed on this scan; retake the scan", source=source,
                       method_version=method, candidates=candidates, evidence=evidence)
    own = next((c for c in candidates if c["animal_id"] == prepared.animal_id), None)
    best = identity.get("animal_id")
    outcome = identity.get("outcome")
    if outcome == "candidate" and best == prepared.animal_id:
        return _result("match", None, source=source, method_version=method, matched=best, candidates=candidates,
                       inliers=own["inliers"] if own else None, evidence=evidence)
    if outcome == "candidate" and best:
        other = next((c for c in candidates if c["animal_id"] == best), None)
        return _result("mismatch", _matched_other(prepared, best), source=source, method_version=method,
                       matched=best, candidates=candidates, inliers=other["inliers"] if other else None,
                       evidence=evidence)
    if outcome == "uncertain":
        reason = ("Two enrolled animals match with similar support; retake the scan"
                  if identity.get("reason") == "ambiguous_match"
                  else "The scan shows too little muzzle detail; retake the scan")
        return _result("uncertain", reason, source=source, method_version=method, candidates=candidates,
                       inliers=own["inliers"] if own else None, evidence=evidence)
    if prepared.animal_refs == 0:
        # Nothing of this animal to compare with: "no match" would accuse the farm on missing data.
        reason = f"{prepared.animal_name} has no enrolled muzzle image to compare with"
        return _result("uncertain", reason, source=source, method_version=method, candidates=candidates,
                       evidence=evidence)
    return _result("mismatch", "No verified match to this animal", source=source, method_version=method,
                   candidates=candidates, inliers=own["inliers"] if own else 0, evidence=evidence)


# ----- record (writing session) --------------------------------------------------------------------------------

def record(session: Session, principal: Principal, prepared: Prepared, result: dict, *,
           scan_media: Media | None = None, stored: list[Path] | None = None) -> IdentityCheck:
    """Insert the scan's media row (already placed on disk), store the crop, add the check, refresh the claim.

    Paths of files written here are appended to `stored`, for the caller to unlink if the transaction fails.
    """
    claim = claims.farm_claim(session, principal.farm_id, prepared.claim_id)
    if claim.status not in claims.OPEN_CLAIM_STATUSES:
        raise DomainError("INVALID_STATE", "The claim was submitted while the scan was checked.",
                          {"status": claim.status})
    if scan_media is not None:
        session.add(scan_media)
        session.flush()
    crop_media = None
    crop_path = result.get("crop_path")
    if crop_path is not None and Path(crop_path).is_file():
        crop_media = store_file(session, prepared.farm_id, "crop", Path(crop_path), CROP_TYPE)
        if stored is not None:
            stored.append(media_path(crop_media))
    check = IdentityCheck(id=new_id("idc"), farm_id=prepared.farm_id, claim_id=claim.id, animal_id=claim.animal_id,
                          media_id=scan_media.id if scan_media else None,
                          crop_media_id=crop_media.id if crop_media else None, reference_id=prepared.reference_id,
                          outcome=result["outcome"], reason=result["reason"],
                          matched_animal_id=result["matched_animal_id"], candidates=list(result["candidates"]),
                          inliers=result["inliers"], source=result["source"],
                          method_version=result["method_version"], evidence=dict(result["evidence"]),
                          checked_by=principal.user_id, created_at=clock.now())
    session.add(check)
    session.flush()
    checklist = claims.refresh(session, claim)
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=prepared.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="claim.identity_checked", subject_type="claim", subject_id=claim.id,
                 animal_id=claim.animal_id,
                 data={"claim_id": claim.id, "check_id": check.id, "outcome": check.outcome, "reason": check.reason,
                       "matched_animal_id": check.matched_animal_id, "inliers": check.inliers,
                       "source": check.source, "method_version": check.method_version,
                       "input": check.evidence.get("input"), "missing": claims.missing_keys(checklist)})
    return check


# ----- read model ----------------------------------------------------------------------------------------------

def checks_for(session: Session, claim_id: str) -> list[IdentityCheck]:
    return list(session.scalars(select(IdentityCheck).where(IdentityCheck.claim_id == claim_id)
                                .order_by(IdentityCheck.created_at.desc(), IdentityCheck.id.desc())))


def _url(media_id: str | None) -> str | None:
    return signed_url(media_id) if media_id else None


def check_view(session: Session, check: IdentityCheck) -> dict:
    scan = session.get(Media, check.media_id) if check.media_id else None
    reference = session.get(AnimalReference, check.reference_id) if check.reference_id else None
    checker = session.get(User, check.checked_by)
    matched = session.get(Animal, check.matched_animal_id) if check.matched_animal_id else None
    return {
        "id": check.id, "claim_id": check.claim_id, "animal_id": check.animal_id, "outcome": check.outcome,
        "reason": check.reason, "matched_animal_id": check.matched_animal_id,
        "matched_animal_name": matched.name if matched else None, "candidates": list(check.candidates or []),
        "inliers": check.inliers, "accept_inliers": (check.evidence or {}).get("accept_inliers", ACCEPT_INLIERS),
        "source": check.source, "method_version": check.method_version,
        "input": (check.evidence or {}).get("input"), "fallback": (check.evidence or {}).get("fallback"),
        "checked_by": check.checked_by, "checked_by_name": checker.name if checker else None,
        "created_at": check.created_at,
        "scan": {"media_url": _url(check.media_id), "content_type": scan.content_type if scan else None,
                 "crop_url": _url(check.crop_media_id)},
        "reference": None if reference is None else {
            "reference_id": reference.id, "crop_url": _url(reference.crop_media_id),
            "frame_url": _url(reference.media_id), "note": (reference.quality or {}).get("note")},
    }


@register_formatter("claim.identity_checked")
def _identity_checked(event: AuditEvent, ctx: PassbookContext) -> dict:
    outcome = event.data.get("outcome") or "uncertain"
    stamp = {"match": "confirmed", "mismatch": "failed"}.get(outcome, "unknown")
    source = event.data.get("source")
    detail = event.data.get("reason") or (f"{event.data.get('inliers')} inliers" if event.data.get("inliers") else None)
    if source == "simulated":
        detail = f"{detail} · simulated" if detail else "Simulated"
    return {"title": f"Identity checked at claim · {outcome}", "detail": detail, "stamp": {"kind": stamp}}
