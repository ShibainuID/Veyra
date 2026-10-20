"""Indicative valuation (plan Section 4: valuation).

`value = floor(weight_kg × unit_price_minor_per_kg)` in minor units, for both ends of the weight range. The
weight range is the latest (or a chosen) weight estimate, or a manager/operator override; an override keeps the
original estimate on record. Every confirmation is a new version. Identity confirmation is not required.
"""

import math
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain import audit
from domain.auth import Principal
from domain.eligibility import latest_estimate
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import PassbookContext, register_formatter
from persistence.models import Animal, AuditEvent, Estimate, Valuation

WEIGHT_BASES = ("estimate", "override")
CURRENCY = "USD"


def value_minor(weight_kg: float, unit_price_minor_per_kg: int) -> int:
    return math.floor(Decimal(str(weight_kg)) * Decimal(unit_price_minor_per_kg))


def latest_valuation(session: Session, animal_id: str) -> Valuation | None:
    return session.scalar(select(Valuation).where(Valuation.animal_id == animal_id)
                          .order_by(Valuation.version.desc()).limit(1))


def farm_animal(session: Session, farm_id: str, animal_id: str) -> Animal:
    animal = session.get(Animal, animal_id)
    if animal is None or animal.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Animal not found.", {"animal_id": animal_id})
    return animal


def _weight_estimate(session: Session, animal_id: str, estimate_id: str | None) -> Estimate | None:
    if estimate_id is None:
        return latest_estimate(session, animal_id, "weight")
    estimate = session.get(Estimate, estimate_id)
    if estimate is None or estimate.animal_id != animal_id or estimate.kind != "weight":
        raise DomainError("NOT_FOUND", "Weight estimate not found for this animal.", {"estimate_id": estimate_id})
    return estimate


def _range(estimate: Estimate | None) -> dict | None:
    if estimate is None:
        return None
    return {"estimate_id": estimate.id, "low_kg": estimate.range_low, "high_kg": estimate.range_high,
            "source": estimate.source, "method_version": estimate.method_version}


def confirm(session: Session, principal: Principal, animal_id: str, *, weight_basis: str,
            unit_price_minor_per_kg: int, price_source: str, price_date: date, estimate_id: str | None = None,
            weight_low_kg: float | None = None, weight_high_kg: float | None = None) -> Valuation:
    animal = farm_animal(session, principal.farm_id, animal_id)
    if weight_basis not in WEIGHT_BASES:
        raise DomainError("VALIDATION_FAILED", "weight_basis must be estimate or override.")
    if unit_price_minor_per_kg <= 0:
        raise DomainError("VALIDATION_FAILED", "The unit price must be positive.")
    estimate = _weight_estimate(session, animal.id, estimate_id)
    if weight_basis == "estimate":
        if estimate is None or estimate.range_low is None or estimate.range_high is None:
            raise DomainError("INVALID_STATE", "No weight estimate range is on record; enter an override.",
                              {"animal_id": animal.id})
        low, high, override = estimate.range_low, estimate.range_high, None
    else:
        if weight_low_kg is None or weight_high_kg is None:
            raise DomainError("VALIDATION_FAILED", "An override needs weight_low_kg and weight_high_kg.")
        if weight_low_kg <= 0 or weight_high_kg < weight_low_kg:
            raise DomainError("VALIDATION_FAILED", "The override range needs 0 < low ≤ high.",
                              {"weight_low_kg": weight_low_kg, "weight_high_kg": weight_high_kg})
        low, high = weight_low_kg, weight_high_kg
        override = {"low_kg": low, "high_kg": high}

    version = (session.scalar(select(func.max(Valuation.version)).where(Valuation.animal_id == animal.id)) or 0) + 1
    valuation = Valuation(
        id=new_id("val"), animal_id=animal.id, version=version, weight_low_kg=low, weight_high_kg=high,
        weight_basis=weight_basis, estimate_id=estimate.id if estimate else None,
        unit_price_minor_per_kg=unit_price_minor_per_kg, currency=CURRENCY, price_source=price_source,
        price_date=price_date, value_low_minor=value_minor(low, unit_price_minor_per_kg),
        value_high_minor=value_minor(high, unit_price_minor_per_kg), confirmed_by=principal.user_id,
    )
    session.add(valuation)
    session.flush()
    actor_type, actor_id = audit.actor_from(principal)
    audit.record(session, farm_id=animal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="valuation.confirmed", subject_type="valuation", subject_id=valuation.id,
                 animal_id=animal.id, data={
                     "valuation_id": valuation.id, "version": version, "weight_basis": weight_basis,
                     "weight_low_kg": low, "weight_high_kg": high, "unit_price_minor_per_kg": unit_price_minor_per_kg,
                     "price_source": price_source, "price_date": price_date.isoformat(),
                     "value_low_minor": valuation.value_low_minor, "value_high_minor": valuation.value_high_minor,
                     "currency": CURRENCY, "original_estimate": _range(estimate), "override": override,
                 })
    return valuation


def money(minor: int | None) -> str:
    if minor is None:
        return "—"
    sign = "-" if minor < 0 else ""
    whole, cents = divmod(abs(minor), 100)
    return f"{sign}{whole:,}.{cents:02d}"


def _kg(value) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


@register_formatter("valuation.confirmed")
def _valuation_confirmed(event: AuditEvent, ctx: PassbookContext) -> dict:
    data = event.data
    currency = data.get("currency", CURRENCY)
    detail = (f"{_kg(data['weight_low_kg'])}–{_kg(data['weight_high_kg'])} kg × "
              f"{money(data['unit_price_minor_per_kg'])} {currency}/kg")
    if data.get("value_high_minor") is not None:
        # The whole range, since the amount column prints only its low bound (what cover is written up to).
        detail += f" = {money(data['value_low_minor'])}–{money(data['value_high_minor'])} {currency}"
    detail += f" · price {data['price_date']}"
    if data.get("override"):
        detail += " · weight override"
    return {"title": "Valued", "detail": detail, "amount_minor": data["value_low_minor"],
            "currency": data.get("currency", CURRENCY), "stamp": {"kind": "confirmed"}}
