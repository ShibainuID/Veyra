"""Digital Livestock Passport: the joined view of one animal's records (PRD Section 4.4, M04).

It is assembled from many tables rather than stored. Original estimates and confirmed overrides stay
separate, and location is reported as the last associated observation, never as a current position.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import audit, monitoring
from domain.errors import APIError, ErrorCode
from persistence.models import (
    Alert,
    Animal,
    AuditEvent,
    Claim,
    Enrollment,
    Estimate,
    Farm,
    MuzzleReference,
    Observation,
    Policy,
    User,
    Valuation,
)


def _estimate(e: Estimate) -> dict:
    return {"id": str(e.id), "kind": e.kind, "range_low": None if e.range_low is None else float(e.range_low),
            "range_high": None if e.range_high is None else float(e.range_high), "unit": e.unit, "source": e.source,
            "method_version": e.method_version, "review_required": e.review_required,
            "supersedes_id": e.supersedes_id and str(e.supersedes_id), "confirmed": e.confirmed_at is not None,
            "confirmed_at": e.confirmed_at, "created_at": e.created_at}


def _valuation(v: Valuation) -> dict:
    return {"id": str(v.id), "weight_estimate_id": str(v.weight_estimate_id), "currency": v.currency,
            "unit_price_minor_per_kg": v.unit_price_minor_per_kg, "price_source": v.price_source, "price_date": v.price_date,
            "value_low_minor": v.value_low_minor, "value_high_minor": v.value_high_minor,
            "confirmed": v.confirmed_at is not None, "created_at": v.created_at}


def current_estimate(estimates: list[Estimate]) -> Estimate | None:
    """The latest confirmed estimate, otherwise the latest one."""
    confirmed = [e for e in estimates if e.confirmed_at]
    pool = confirmed or estimates
    return max(pool, key=lambda e: e.created_at) if pool else None


def build(session: Session, animal: Animal) -> dict:
    farm = session.get(Farm, animal.farm_id)
    where = lambda model: model.animal_id == animal.id  # noqa: E731
    estimates = list(session.scalars(select(Estimate).where(where(Estimate)).order_by(Estimate.created_at)))
    by_kind = {k: [e for e in estimates if e.kind == k] for k in ("age", "weight")}
    last_seen = session.scalars(
        select(Observation).where(where(Observation), Observation.association_status == "confirmed")
        .order_by(Observation.observed_at.desc()).limit(1)
    ).first()
    policies = list(session.scalars(select(Policy).where(where(Policy)).order_by(Policy.created_at.desc())))
    claims = list(session.scalars(select(Claim).where(Claim.policy_id.in_([p.id for p in policies])))) if policies else []
    history = session.scalars(
        select(AuditEvent).where(AuditEvent.entity_type == "animal", AuditEvent.entity_id == str(animal.id))
        .order_by(AuditEvent.created_at.desc()).limit(50)
    )
    return {
        "animal_id": str(animal.id),
        "display_id": animal.display_id,
        "farm_id": str(animal.farm_id),
        "currency": farm.currency,
        "identity": {
            "status": animal.identity_status,
            "confirmed_by": animal.confirmed_by and str(animal.confirmed_by),
            "confirmed_at": animal.confirmed_at,
            "references": [{"reference_id": str(r.id), "media_id": str(r.media_id), "model_version": r.model_version,
                            "created_at": r.created_at}
                           for r in session.scalars(select(MuzzleReference).where(where(MuzzleReference)))],
            "enrollment_ids": [str(eid) for eid in session.scalars(select(Enrollment.id).where(where(Enrollment)))],
        },
        "profile": {"sex": animal.sex, "breed": animal.breed, "ownership_document_ids": animal.ownership_document_ids},
        "estimates": {kind: {"current": (c := current_estimate(rows)) and _estimate(c), "history": [_estimate(e) for e in rows]}
                      for kind, rows in by_kind.items()},
        "valuations": [_valuation(v) for v in session.scalars(
            select(Valuation).where(where(Valuation)).order_by(Valuation.created_at.desc()))],
        "last_observed": None if last_seen is None else {
            "camera_id": str(last_seen.camera_id), "observed_at": last_seen.observed_at, "track_id": last_seen.track_id,
            "source": last_seen.source},
        "open_alerts": [{"id": str(a.id), "kind": a.kind, "status": a.status, "window_start": a.window_start,
                         "window_end": a.window_end}
                        for a in session.scalars(select(Alert).where(where(Alert), Alert.status.in_(("open", "acknowledged"))))],
        "health": monitoring.health(session, animal),
        "policies": [{"id": str(p.id), "status": p.status, "insured_value_minor": p.insured_value_minor,
                      "premium_minor": p.premium_minor, "effective_from": p.effective_from, "effective_to": p.effective_to}
                     for p in policies],
        "claims": [{"id": str(c.id), "status": c.status, "policy_id": str(c.policy_id)} for c in claims],
        "history": [{"action": h.action, "actor_type": h.actor_type, "actor_id": h.actor_id, "details": h.details,
                     "created_at": h.created_at} for h in history],
    }


def require_confirmed_identity(animal: Animal) -> None:
    if animal.identity_status != "confirmed":
        raise APIError(ErrorCode.IDENTITY_UNCONFIRMED, "Animal identity is not confirmed.",
                       {"identity_status": animal.identity_status})


def confirm_estimate(session: Session, animal: Animal, estimate: Estimate, user: User,
                     override: tuple[float, float] | None, note: str | None) -> Estimate:
    require_confirmed_identity(animal)
    now = datetime.now(UTC)
    if override is None:
        if estimate.range_low is None or estimate.range_high is None:
            raise APIError(ErrorCode.EVIDENCE_INCOMPLETE, "This estimate has no range; enter a confirmed value instead.")
        estimate.confirmed_by, estimate.confirmed_at = user.id, now
        confirmed = estimate
    else:
        low, high = override
        if low > high:
            raise APIError(ErrorCode.VALIDATION_FAILED, "range_low must not exceed range_high.")
        confirmed = Estimate(farm_id=animal.farm_id, animal_id=animal.id, enrollment_id=estimate.enrollment_id,
                             kind=estimate.kind, range_low=low, range_high=high, unit=estimate.unit, source="manual",
                             method_version="manager_override_v1", details={"note": note}, supersedes_id=estimate.id,
                             confirmed_by=user.id, confirmed_at=now)
        session.add(confirmed)
        session.flush()
    audit.record(session, animal.farm_id, "estimate.confirmed", "animal", animal.id, actor_id=user.id,
                 details={"estimate_id": str(confirmed.id), "kind": confirmed.kind, "override": override is not None,
                          "original_estimate_id": str(estimate.id), "note": note})
    return confirmed


def value_animal(session: Session, animal: Animal, estimate: Estimate, user: User, unit_price_minor_per_kg: int,
                 price_source: str, price_date: datetime) -> Valuation:
    """Indicative value range = confirmed weight range x unit price. Not an insurer-agreed value or payout."""
    require_confirmed_identity(animal)
    if estimate.kind != "weight" or estimate.animal_id != animal.id:
        raise APIError(ErrorCode.VALIDATION_FAILED, "Valuation needs a weight estimate of this animal.")
    if estimate.confirmed_at is None:
        raise APIError(ErrorCode.EVIDENCE_INCOMPLETE, "The weight estimate must be confirmed by a manager first.")
    farm = session.get(Farm, animal.farm_id)
    valuation = Valuation(
        farm_id=animal.farm_id, animal_id=animal.id, weight_estimate_id=estimate.id, currency=farm.currency,
        unit_price_minor_per_kg=unit_price_minor_per_kg, price_source=price_source, price_date=price_date,
        value_low_minor=round(float(estimate.range_low) * unit_price_minor_per_kg),
        value_high_minor=round(float(estimate.range_high) * unit_price_minor_per_kg),
        confirmed_by=user.id, confirmed_at=datetime.now(UTC),
    )
    session.add(valuation)
    session.flush()
    audit.record(session, animal.farm_id, "valuation.created", "animal", animal.id, actor_id=user.id,
                 details={"valuation_id": str(valuation.id), "value_low_minor": valuation.value_low_minor,
                          "value_high_minor": valuation.value_high_minor, "currency": valuation.currency,
                          "unit_price_minor_per_kg": unit_price_minor_per_kg, "price_source": price_source})
    return valuation


def get_estimate(session: Session, animal: Animal, estimate_id: uuid.UUID) -> Estimate:
    estimate = session.get(Estimate, estimate_id)
    if estimate is None or estimate.animal_id != animal.id:
        raise APIError(ErrorCode.NOT_FOUND, "Estimate not found for this animal.")
    return estimate
