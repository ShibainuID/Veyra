"""Deterministic insurance eligibility (plan Section 4: eligibility).

Each catalog rule is checked against facts gathered from the records. A rule fails, passes, or is unknown when
the fact is missing or an estimated range straddles the limit. Any failed rule makes the product `ineligible`;
otherwise any unknown rule makes it `unknown` (with what review is needed); otherwise it is `eligible`.
The language model explains these outcomes; it never decides them.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from persistence.models import Animal, Estimate, Valuation

OUTCOMES = ("eligible", "ineligible", "unknown")
RANGE_FIELDS = {"age_months": ("age_months_low", "age_months_high")}
REVIEW_HINTS = {
    "identity_status": "Confirm the animal's identity",
    "age_months": "Confirm the animal's age",
    "valuation_confirmed": "Confirm a valuation",
    "ownership_document": "Add an ownership document reference",
    "breed_category": "Confirm the breed category",
    "vet_health_check_days": "Record a veterinary health check",
}


def latest_estimate(session: Session, animal_id: str, kind: str) -> Estimate | None:
    return session.scalar(select(Estimate).where(Estimate.animal_id == animal_id, Estimate.kind == kind)
                          .order_by(Estimate.created_at.desc(), Estimate.id.desc()).limit(1))


def facts_for(session: Session, animal: Animal) -> dict:
    """The facts the catalog rules read. A missing fact is `None` and makes its rule unknown, never failed."""
    age = latest_estimate(session, animal.id, "age")
    has_valuation = session.scalar(select(Valuation.id).where(Valuation.animal_id == animal.id).limit(1))
    return {
        "identity_status": animal.identity_status,
        "age_months_low": age.range_low if age else None,
        "age_months_high": age.range_high if age else None,
        "valuation_confirmed": True if has_valuation else None,
        "ownership_document": "present" if animal.ownership_doc_refs else None,
        "breed_category": animal.breed_category,
        "vet_health_check_days": None,  # no veterinary health-check record exists yet
    }


def _fmt(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _range_status(op: str, low: float, high: float, value) -> str:
    if op == "between":
        lo, hi = value
        if lo <= low and high <= hi:
            return "pass"
        if high < lo or low > hi:
            return "fail"
        return "unknown"
    if op == "lte":
        if high <= value:
            return "pass"
        if low > value:
            return "fail"
        return "unknown"
    if op == "eq":
        if low == high == value:
            return "pass"
        if not (low <= value <= high):
            return "fail"
        return "unknown"
    raise ValueError(f"unknown rule op {op!r}")


def _scalar_status(op: str, fact, value) -> str:
    if op == "eq":
        return "pass" if fact == value else "fail"
    if op == "lte":
        return "pass" if fact <= value else "fail"
    if op == "between":
        lo, hi = value
        return "pass" if lo <= fact <= hi else "fail"
    raise ValueError(f"unknown rule op {op!r}")


def check_rule(rule: dict, facts: dict) -> dict:
    field, op, value = rule["field"], rule["op"], rule["value"]
    if field in RANGE_FIELDS:
        low_key, high_key = RANGE_FIELDS[field]
        low, high = facts.get(low_key), facts.get(high_key)
        if low is None or high is None:
            status, detail = "unknown", f"{field} is not on record"
        else:
            status = _range_status(op, low, high, value)
            detail = f"Estimated {_fmt(low)}–{_fmt(high)} months"
    else:
        fact = facts.get(field)
        if fact is None:
            status, detail = "unknown", f"{field} is not on record"
        else:
            status, detail = _scalar_status(op, fact, value), f"{field} is {_fmt(fact)}"
    return {"field": field, "terms_ref": rule["terms_ref"], "text": rule["text"], "status": status,
            "detail": detail}


def evaluate(product: dict, facts: dict) -> dict:
    reasons = [check_rule(rule, facts) for rule in product["eligibility"]]
    statuses = {reason["status"] for reason in reasons}
    outcome = "ineligible" if "fail" in statuses else "unknown" if "unknown" in statuses else "eligible"
    needs_review = [REVIEW_HINTS.get(reason["field"], f"Review {reason['field']}")
                    for reason in reasons if reason["status"] == "unknown"]
    return {"product_id": product["product_id"], "outcome": outcome, "reasons": reasons,
            "needs_review": needs_review}
