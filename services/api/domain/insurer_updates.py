"""Insurer-reported claim updates (the sandbox insurer's assessment progression for the demo).

After a claim is submitted only the insurer moves it. VEYRA records what the insurer reports, in its words, with
`actor_type: provider` and `source: sandbox`: `under_review`, `more_info_requested` (with the note of what is
outstanding), `approved` (optionally with the insurer-stated settlement amount and a disbursement state), or
`declined`. `approved` alone never means paid: the disbursement reads `scheduled` unless the insurer's update says
`paid`. Nothing here computes or promises a payout.
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from domain import audit, clock
from domain.auth import Principal
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import PassbookContext, register_formatter
from domain.valuation import money
from persistence.models import AuditEvent, Claim, ClaimInsurerUpdate, Policy

STATUSES = ("under_review", "more_info_requested", "approved", "declined")
DISBURSEMENTS = ("scheduled", "paid")
UNSUBMITTED = ("draft", "ready")
SOURCE = "sandbox"
STATUS_WORDS = {
    "assessment_pending": "Submitted — Pending assessment",
    "under_review": "Under review by the insurer",
    "more_info_requested": "Insurer asked for more information",
    "approved": "Approved by the insurer",
    "declined": "Declined by the insurer",
}


def record_update(session: Session, principal: Principal, claim_id: str, *, status: str, note: str | None = None,
                  settlement_minor: int | None = None, disbursement: str | None = None) -> ClaimInsurerUpdate:
    """Record one sandbox-insurer update on a submitted claim (demo control). The caller commits."""
    claim = session.get(Claim, claim_id)
    if claim is None or claim.farm_id != principal.farm_id:
        raise DomainError("NOT_FOUND", "Claim not found.", {"claim_id": claim_id})
    if claim.status in UNSUBMITTED or claim.receipt is None:
        raise DomainError("INVALID_STATE", "The insurer can update a claim only after it was submitted.",
                          {"status": claim.status})
    if status not in STATUSES:
        raise DomainError("VALIDATION_FAILED", "Unknown insurer status.", {"status": status})
    if status != "approved" and (settlement_minor is not None or disbursement is not None):
        raise DomainError("VALIDATION_FAILED", "Only an approval carries a settlement amount or a disbursement.",
                          {"status": status})
    if status == "approved":
        disbursement = disbursement or "scheduled"
    if disbursement is not None and disbursement not in DISBURSEMENTS:
        raise DomainError("VALIDATION_FAILED", "Unknown disbursement state.", {"disbursement": disbursement})
    if status == "more_info_requested" and not (note or "").strip():
        raise DomainError("VALIDATION_FAILED", "Say what the insurer needs in the note.", {"field": "note"})
    policy = session.get(Policy, claim.policy_id)
    provider_id = policy.provider_id if policy else "sandbox-insurer"
    row = ClaimInsurerUpdate(id=new_id("ciu"), farm_id=claim.farm_id, claim_id=claim.id, provider_id=provider_id,
                             status=status, note=(note or "").strip() or None, settlement_minor=settlement_minor,
                             currency=claim.currency, disbursement=disbursement, source=SOURCE,
                             created_at=clock.now())
    session.add(row)
    session.execute(update(Claim).where(Claim.id == claim.id, Claim.status.not_in(UNSUBMITTED))
                    .values(assessment_status=status, updated_at=clock.now()))
    audit.record(session, farm_id=claim.farm_id, actor_type="provider", actor_id=provider_id,
                 event_type="claim.insurer_update", subject_type="claim", subject_id=claim.id,
                 animal_id=claim.animal_id,
                 data={"claim_id": claim.id, "update_id": row.id, "status": status, "note": row.note,
                       "settlement_minor": settlement_minor, "currency": claim.currency,
                       "disbursement": disbursement, "source": SOURCE, "recorded_by": principal.user_id})
    session.flush()
    return row


def updates_for(session: Session, claim_id: str) -> list[ClaimInsurerUpdate]:
    return list(session.scalars(select(ClaimInsurerUpdate).where(ClaimInsurerUpdate.claim_id == claim_id)
                                .order_by(ClaimInsurerUpdate.created_at, ClaimInsurerUpdate.id)))


def update_view(row: ClaimInsurerUpdate) -> dict:
    return {"id": row.id, "status": row.status, "label": STATUS_WORDS.get(row.status, row.status),
            "note": row.note, "settlement_minor": row.settlement_minor, "currency": row.currency,
            "disbursement": row.disbursement, "provider_id": row.provider_id, "source": row.source,
            "created_at": row.created_at}


@register_formatter("claim.insurer_update")
def _insurer_update(event: AuditEvent, ctx: PassbookContext) -> dict:
    data = event.data
    title = f"Insurer update · {STATUS_WORDS.get(data.get('status'), data.get('status'))} (sandbox)"
    detail = data.get("note")
    if data.get("status") == "approved":
        stated = (f"Settlement stated by the insurer {money(data['settlement_minor'])} {data.get('currency')}"
                  if data.get("settlement_minor") is not None else "No settlement amount stated")
        disbursed = "paid by the insurer" if data.get("disbursement") == "paid" else "disbursement scheduled by insurer"
        detail = f"{stated} · {disbursed}" + (f" · {data['note']}" if data.get("note") else "")
    return {"title": title, "detail": detail}
