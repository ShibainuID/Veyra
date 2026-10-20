"""Sandbox Mutual, the fictional insurer: applications, activation, notifications, and claims.

Activation is the insurer's decision, separate from payment: with `insurer_activation=withhold` the insurer
answers `pending_underwriter_review` and the policy stays unpaid-active (`paid_pending_activation`).
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from adapters.sandbox import demo_settings, lookup, reference, store
from domain import clock
from persistence.models import Policy

PROVIDER = "sandbox-insurer"


def one_year_cover(start: date) -> date:
    """The last day of a one-year cover starting on `start` (start + 1 year − 1 day)."""
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:  # 29 February
        anniversary = date(start.year + 1, 3, 1)
    return anniversary - timedelta(days=1)


def _idempotent(session: Session, operation: str, key: str, request: dict, respond) -> dict:
    existing = lookup(session, PROVIDER, operation, key)
    if existing is not None:
        return dict(existing.response)
    return store(session, PROVIDER, operation, key, request, respond())


def submit_application(session: Session, key: str, payload: dict) -> dict:
    return _idempotent(session, "submit_application", key, payload, lambda: {
        "status": "accepted", "application_ref": reference("SBX-APP", key),
        "accepted_at": clock.isoformat(clock.now())})


def confirm_activation(session: Session, key: str, policy: Policy) -> dict:
    request = {"policy_id": policy.id, "product_id": policy.product_id, "terms_version": policy.terms_version}

    def respond() -> dict:
        if demo_settings(session, policy.farm_id).insurer_activation != "confirm":
            return {"activated": False, "status": "pending_underwriter_review"}
        today = clock.now().date()
        return {"activated": True, "status": "active", "effective_date": today.isoformat(),
                "expiry_date": one_year_cover(today).isoformat(), "confirmation_ref": reference("SBX-POL", key)}

    return _idempotent(session, "confirm_activation", key, request, respond)


def submit_notification(session: Session, key: str, payload: dict) -> dict:
    return _idempotent(session, "submit_notification", key, payload, lambda: {
        "status": "received", "notification_ref": reference("SBX-NTF", key),
        "received_at": clock.isoformat(clock.now())})


def submit_claim(session: Session, key: str, payload: dict) -> dict:
    return _idempotent(session, "submit_claim", key, payload, lambda: {
        "status": "received", "claim_ref": reference("SBX-CLM", key), "assessment_status": "assessment_pending",
        "received_at": clock.isoformat(clock.now())})
