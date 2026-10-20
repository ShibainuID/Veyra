"""Incidents and claims (plan Section 4: claims).

An incident records what happened; observed behavior (linked alerts), the farmer's report (description and
facts), and professional findings (vet notes) stay in distinct fields. An alert alone never creates a claim.
A claim draft needs an active policy whose covered perils include the incident kind, and builds its checklist
from the product's `claim_requirements`. Proposing `CLAIM_SUBMISSION` with anything missing is refused with
`EVIDENCE_INCOMPLETE`, and the missing keys are kept on the claim (`blocked_reason`).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.sandbox import insurer
from domain import actions, audit, clock, evidence, premiums
from domain.auth import Principal
from domain.catalog import get_product, load_catalog
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import PassbookContext, register_formatter
from domain.valuation import farm_animal
from persistence.models import (
    ActionExecution, AgentAction, Alert, Animal, AnimalReference, AuditEvent, Claim, Incident, Policy, User,
)

FINDING_TYPES = ("vet_assessment", "vet_health_record")
# Only a vet authors a professional finding, so it stays distinct from the farm's own report (PRD 3, 8).
FINDING_AUTHORS = ("vet",)
OPEN_CLAIM_STATUSES = ("draft", "ready")
CHECKLIST_LABELS = {
    "identity_reference": "Passport muzzle reference",
    "active_policy": "Active policy covering the incident",
    "incident_facts": "Incident facts recorded",
    "farmer_declaration": "Farmer declaration confirmed",
    "observation_evidence": "Linked camera observation",
    "vet_assessment": "Veterinary assessment",
    "ownership_document": "Ownership document",
    "vet_health_record": "Veterinary health record",
}


def _actor(principal: Principal) -> tuple[str, str]:
    return audit.actor_from(principal)


def _columns(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


# Incidents -----------------------------------------------------------------------------------------------------

def farm_incident(session: Session, farm_id: str, incident_id: str) -> Incident:
    incident = session.get(Incident, incident_id)
    if incident is None or incident.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Incident not found.", {"incident_id": incident_id})
    return incident


def record_incident(session: Session, principal: Principal, *, animal_id: str, kind: str, occurred_at: datetime,
                    description: str, estimated_loss_minor: int, linked_alert_ids: list[str] | None = None,
                    facts: dict | None = None) -> Incident:
    animal = farm_animal(session, principal.farm_id, animal_id)
    if occurred_at.tzinfo is None:
        raise DomainError("VALIDATION_FAILED", "occurred_at needs a timezone (UTC, ending in Z).")
    if occurred_at > clock.now():
        raise DomainError("VALIDATION_FAILED", "An incident cannot be recorded in the future.",
                          {"occurred_at": clock.isoformat(occurred_at)})
    alert_ids = list(dict.fromkeys(linked_alert_ids or []))
    for alert_id in alert_ids:
        alert = session.get(Alert, alert_id)
        if alert is None or alert.farm_id != principal.farm_id:
            raise DomainError("NOT_FOUND", "Linked alert not found.", {"alert_id": alert_id})
        if alert.animal_id != animal.id:
            raise DomainError("VALIDATION_FAILED", "A linked alert must be about the same animal.",
                              {"alert_id": alert_id, "alert_animal_id": alert.animal_id})
    policy = next((p for p in _active_policies(session, principal.farm_id, animal.id) if in_cover(p, occurred_at)),
                  None)
    incident = Incident(id=new_id("inc"), farm_id=principal.farm_id, animal_id=animal.id,
                        policy_id=policy.id if policy else None, kind=kind, occurred_at=occurred_at,
                        description=description, estimated_loss_minor=estimated_loss_minor, currency="USD",
                        reported_by=principal.user_id, facts=dict(facts or {}), documents=[],
                        professional_findings=[], linked_alert_ids=alert_ids)
    session.add(incident)
    session.flush()
    actor_type, actor_id = _actor(principal)
    audit.record(session, farm_id=principal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="incident.recorded", subject_type="incident", subject_id=incident.id, animal_id=animal.id,
                 data={"incident_id": incident.id, "kind": kind, "estimated_loss_minor": estimated_loss_minor,
                       "currency": "USD", "policy_id": incident.policy_id, "linked_alert_ids": alert_ids})
    return incident


def add_finding(session: Session, principal: Principal, incident_id: str, *, summary: str,
                finding_type: str) -> Incident:
    incident = farm_incident(session, principal.farm_id, incident_id)
    if finding_type not in FINDING_TYPES:
        raise DomainError("VALIDATION_FAILED", "Unknown finding type.", {"finding_type": finding_type})
    finding = {"id": new_id("fnd"), "finding_type": finding_type, "summary": summary,
               "author_id": principal.user_id, "author_name": principal.name, "author_role": principal.role,
               "at": clock.isoformat(clock.now())}
    incident.professional_findings = [*(incident.professional_findings or []), finding]
    # An open claim on this incident reads its checklist again, so the new finding counts at once.
    for claim in session.scalars(select(Claim).where(Claim.farm_id == principal.farm_id, Claim.incident_id == incident.id,
                                                     Claim.status.in_(OPEN_CLAIM_STATUSES))):
        _refresh(session, claim)
    actor_type, actor_id = _actor(principal)
    audit.record(session, farm_id=principal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="incident.finding_added", subject_type="incident", subject_id=incident.id,
                 animal_id=incident.animal_id, data={"incident_id": incident.id, **finding})
    return incident


def list_incidents(session: Session, farm_id: str, animal_id: str | None = None) -> list[Incident]:
    query = select(Incident).where(Incident.farm_id == farm_id)
    if animal_id is not None:
        query = query.where(Incident.animal_id == animal_id)
    return list(session.scalars(query.order_by(Incident.occurred_at.desc(), Incident.id)))


def incident_view(session: Session, incident: Incident) -> dict:
    reporter = session.get(User, incident.reported_by) if incident.reported_by else None
    return {**_columns(incident), "reported_by_name": reporter.name if reporter else None}


# Checklist -----------------------------------------------------------------------------------------------------

def in_cover(policy: Policy, when: datetime) -> bool:
    """Whether `when` falls inside the policy's cover window (effective date to expiry date, inclusive)."""
    if policy.effective_date is None or policy.expiry_date is None:
        return False
    return policy.effective_date <= when.astimezone(UTC).date() <= policy.expiry_date


def _active_policies(session: Session, farm_id: str, animal_id: str) -> list[Policy]:
    return list(session.scalars(select(Policy).where(Policy.farm_id == farm_id, Policy.animal_id == animal_id,
                                                     Policy.status == "active")
                                .order_by(Policy.created_at.desc(), Policy.id)))


def _covering_policy(session: Session, incident: Incident) -> tuple[Policy, dict] | None:
    """An active policy whose window contains the incident date and whose perils include its kind."""
    catalog = load_catalog()
    candidates = sorted(_active_policies(session, incident.farm_id, incident.animal_id),
                        key=lambda p: p.id != incident.policy_id)
    for policy in candidates:
        product = get_product(catalog, policy.product_id)
        if incident.kind in product["covered_perils"] and in_cover(policy, incident.occurred_at):
            return policy, product
    return None


def _finding(incident: Incident, finding_type: str) -> dict | None:
    return next((f for f in incident.professional_findings or [] if f.get("finding_type") == finding_type), None)


def _linked_alert(session: Session, incident: Incident) -> Alert | None:
    for alert_id in incident.linked_alert_ids or []:
        alert = session.get(Alert, alert_id)
        if alert is not None and alert.farm_id == incident.farm_id:
            return alert
    return None


def compute_checklist(session: Session, claim: Claim) -> list[dict]:
    incident = session.get(Incident, claim.incident_id)
    policy = session.get(Policy, claim.policy_id)
    animal = session.get(Animal, claim.animal_id)
    product = get_product(load_catalog(), policy.product_id)
    muzzle = session.scalar(select(AnimalReference.id).where(AnimalReference.animal_id == animal.id,
                                                             AnimalReference.view == "muzzle").limit(1))
    alert = _linked_alert(session, incident)
    assessment = _finding(incident, "vet_assessment")
    health = _finding(incident, "vet_health_record")
    sources = {
        "identity_reference": muzzle,
        "active_policy": policy.id if policy.status == "active" and in_cover(policy, incident.occurred_at) else None,
        "incident_facts": incident.id if incident.description else None,
        "farmer_declaration": claim.declaration_by if claim.declaration_confirmed else None,
        "observation_evidence": alert.id if alert else None,
        "vet_assessment": assessment["id"] if assessment else None,
        "ownership_document": (animal.ownership_doc_refs or [None])[0],
        "vet_health_record": health["id"] if health else None,
    }
    declarer = session.get(User, claim.declaration_by) if claim.declaration_confirmed and claim.declaration_by else None
    details = {"farmer_declaration": f"Confirmed by {declarer.name}" if declarer else None}
    return [{"key": key, "label": CHECKLIST_LABELS.get(key, key.replace("_", " ").capitalize()),
             "status": "present" if sources.get(key) else "missing", "ref": sources.get(key),
             "detail": details.get(key)}
            for key in product["claim_requirements"]]


def missing_keys(checklist: list[dict]) -> list[str]:
    return [item["key"] for item in checklist if item["status"] == "missing"]


def _refresh(session: Session, claim: Claim) -> list[dict]:
    checklist = compute_checklist(session, claim)
    claim.checklist = checklist
    if claim.status in OPEN_CLAIM_STATUSES:
        claim.status = "draft" if missing_keys(checklist) else "ready"
        if not missing_keys(checklist):
            claim.blocked_reason = None
    claim.updated_at = clock.now()
    return checklist


# Claims --------------------------------------------------------------------------------------------------------

def farm_claim(session: Session, farm_id: str, claim_id: str) -> Claim:
    claim = session.get(Claim, claim_id)
    if claim is None or claim.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Claim not found.", {"claim_id": claim_id})
    return claim


def draft_claim(session: Session, principal: Principal, incident_id: str) -> Claim:
    incident = farm_incident(session, principal.farm_id, incident_id)
    existing = session.scalar(select(Claim).where(Claim.farm_id == principal.farm_id, Claim.incident_id == incident.id)
                              .order_by(Claim.created_at.desc()).limit(1))
    if existing is not None:
        if existing.status in OPEN_CLAIM_STATUSES:
            _refresh(session, existing)
        return existing
    covering = _covering_policy(session, incident)
    if covering is None:
        raise DomainError("INVALID_STATE", "No active policy for this animal covers this kind of incident on that date.",
                          {"incident_id": incident.id, "kind": incident.kind,
                           "reason": "no_active_policy_covering_incident"})
    policy, _ = covering
    claim = Claim(id=new_id("clm"), farm_id=principal.farm_id, policy_id=policy.id, incident_id=incident.id,
                  animal_id=incident.animal_id, status="draft", checklist=[], blocked_reason=None,
                  declaration_confirmed=False, declaration_by=None, claimed_amount_minor=incident.estimated_loss_minor,
                  currency=incident.currency, evidence_manifest_id=None, receipt=None, assessment_status=None)
    session.add(claim)
    session.flush()
    checklist = _refresh(session, claim)
    actor_type, actor_id = _actor(principal)
    audit.record(session, farm_id=principal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="claim.drafted", subject_type="claim", subject_id=claim.id, animal_id=claim.animal_id,
                 data={"claim_id": claim.id, "incident_id": incident.id, "policy_id": policy.id,
                       "claimed_amount_minor": claim.claimed_amount_minor, "currency": claim.currency,
                       "missing": missing_keys(checklist)})
    return claim


def confirm_declaration(session: Session, principal: Principal, claim_id: str) -> Claim:
    claim = farm_claim(session, principal.farm_id, claim_id)
    if claim.status not in OPEN_CLAIM_STATUSES:
        raise DomainError("INVALID_STATE", "The declaration can change only on an unsubmitted claim.",
                          {"status": claim.status})
    claim.declaration_confirmed = True
    claim.declaration_by = principal.user_id
    checklist = _refresh(session, claim)
    actor_type, actor_id = _actor(principal)
    audit.record(session, farm_id=principal.farm_id, actor_type=actor_type, actor_id=actor_id,
                 event_type="claim.declaration_confirmed", subject_type="claim", subject_id=claim.id,
                 animal_id=claim.animal_id, data={"claim_id": claim.id, "missing": missing_keys(checklist)})
    return claim


def list_claims(session: Session, farm_id: str, animal_id: str | None = None) -> list[Claim]:
    query = select(Claim).where(Claim.farm_id == farm_id)
    if animal_id is not None:
        query = query.where(Claim.animal_id == animal_id)
    return list(session.scalars(query.order_by(Claim.created_at.desc(), Claim.id)))


def claim_view(session: Session, claim: Claim) -> dict:
    policy = session.get(Policy, claim.policy_id)
    product = get_product(load_catalog(), policy.product_id) if policy else None
    payout = None
    formula = product.get("payout_formula") if product else None
    if formula:
        payout = {"amount_minor": premiums.illustrative_payout(claim.claimed_amount_minor, policy.insured_value_minor,
                                                               policy.deductible_minor),
                  "currency": claim.currency, "expression": formula["expression"], "terms_ref": formula["terms_ref"],
                  "illustrative": True, "note": formula.get("note") or "Illustrative only; the insurer assesses."}
    checklist = [{"ref": None, **item} for item in claim.checklist or []]
    return {**_columns(claim), "checklist": checklist, "missing": missing_keys(checklist),
            "product_id": policy.product_id if policy else None, "illustrative_payout": payout}


# CLAIM_SUBMISSION ----------------------------------------------------------------------------------------------

def claim_items(session: Session, claim: Claim, incident: Incident, policy: Policy, animal: Animal) -> list[dict]:
    items = evidence.identity_items(session, animal) + [evidence.policy_item(policy)] + evidence.incident_items(incident)
    for alert_id in incident.linked_alert_ids or []:
        alert = session.get(Alert, alert_id)
        if alert is not None and alert.farm_id == claim.farm_id:
            items += evidence.alert_items(session, alert)
    items += evidence.ownership_items(animal)
    if claim.declaration_confirmed:
        declarer = session.get(User, claim.declaration_by) if claim.declaration_by else None
        items.append(evidence.item("farmer_declaration", claim.id,
                                   f"Declaration by {declarer.name if declarer else claim.declaration_by}"))
    return items


def build_claim_submission(session: Session, farm_id: str, refs: dict) -> actions.Built:
    claim = farm_claim(session, farm_id, actions.require_ref(refs, "claim_id"))
    animal = actions.confirmed_animal(session, farm_id, claim.animal_id)
    if claim.status not in OPEN_CLAIM_STATUSES:
        raise DomainError("INVALID_STATE", "This claim was already submitted.", {"status": claim.status})
    if actions.in_flight(session, farm_id, "CLAIM_SUBMISSION", "claim", claim.id):
        raise DomainError("INVALID_STATE", "A submission for this claim is already in progress.")
    missing = missing_keys(compute_checklist(session, claim))
    if missing:
        raise DomainError("EVIDENCE_INCOMPLETE", "The claim checklist is incomplete.", {"missing": missing,
                                                                                        "claim_id": claim.id})
    incident = session.get(Incident, claim.incident_id)
    policy = session.get(Policy, claim.policy_id)
    items = claim_items(session, claim, incident, policy, animal)
    subject = ("claim", claim.id)
    payload = {
        "claim_id": claim.id, "policy_id": policy.id, "incident_id": incident.id, "animal_id": animal.id,
        "provider_id": policy.provider_id, "claimed_amount_minor": claim.claimed_amount_minor,
        "currency": claim.currency, "declaration_confirmed": True, "terms_version": policy.terms_version,
        "evidence_manifest_version": evidence.resolve_version(session, farm_id, subject, items),
    }
    return actions.Built(payload, animal.id, *subject, items)


def block_claim(session: Session, principal: Principal, refs: dict, error: DomainError) -> bool:
    if error.code != "EVIDENCE_INCOMPLETE":
        return False
    claim = farm_claim(session, principal.farm_id, refs["claim_id"])
    _refresh(session, claim)
    claim.status = "draft"
    claim.blocked_reason = {"code": error.code, "message": error.message, "missing": list(error.details["missing"]),
                            "at": clock.isoformat(clock.now())}
    audit.record(session, farm_id=principal.farm_id, actor_type="agent", actor_id=principal.user_id,
                 event_type="claim.blocked", subject_type="claim", subject_id=claim.id, animal_id=claim.animal_id,
                 data={"claim_id": claim.id, "missing": list(error.details["missing"])})
    return True


def apply_claim_submission(session: Session, action: AgentAction, execution: ActionExecution,
                           response: dict) -> dict:
    claim = session.get(Claim, action.payload["claim_id"])
    claim.status = response.get("assessment_status", "assessment_pending")
    claim.assessment_status = response.get("assessment_status", "assessment_pending")
    claim.receipt = dict(response)
    claim.evidence_manifest_id = action.evidence_manifest_id
    claim.blocked_reason = None
    claim.updated_at = clock.now()
    audit.record(session, farm_id=claim.farm_id, actor_type="provider", actor_id=execution.provider_id,
                 event_type="claim.submitted", subject_type="claim", subject_id=claim.id, animal_id=claim.animal_id,
                 data={"claim_id": claim.id, "action_id": action.id, "receipt": dict(response),
                       "claimed_amount_minor": claim.claimed_amount_minor, "currency": claim.currency})
    return {"claim_id": claim.id, "claim_status": claim.status}


actions.register(actions.ActionSpec(
    "CLAIM_SUBMISSION", insurer.PROVIDER, "submit_claim", build_claim_submission,
    lambda s, key, payload, farm_id: insurer.submit_claim(s, key, payload), apply_claim_submission,
    on_blocked=block_claim))


# Passbook lines ------------------------------------------------------------------------------------------------

def _kind(value: str | None) -> str:
    return (value or "incident").replace("_", " ")


@register_formatter("incident.recorded")
def _incident_recorded(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": f"Incident recorded · {_kind(event.data.get('kind'))}",
            "amount_minor": event.data.get("estimated_loss_minor"), "currency": event.data.get("currency"),
            "detail": "Estimated loss reported by the farm"}


@register_formatter("incident.finding_added")
def _finding_added(event: AuditEvent, ctx: PassbookContext) -> dict:
    title = "Vet assessment added" if event.data.get("finding_type") == "vet_assessment" else "Vet health record added"
    summary = event.data.get("summary") or ""
    return {"title": title, "detail": summary if len(summary) <= 120 else summary[:117] + "...",
            "stamp": {"kind": "confirmed"}}


@register_formatter("claim.drafted")
def _claim_drafted(event: AuditEvent, ctx: PassbookContext) -> dict:
    missing = event.data.get("missing") or []
    return {"title": "Claim drafted", "detail": f"Missing: {', '.join(missing)}" if missing else "Checklist complete",
            "amount_minor": event.data.get("claimed_amount_minor"), "currency": event.data.get("currency")}


@register_formatter("claim.declaration_confirmed")
def _declaration(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Farmer declaration confirmed", "stamp": {"kind": "confirmed"}}


@register_formatter("claim.blocked")
def _claim_blocked(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Claim held · evidence incomplete",
            "detail": f"Missing: {', '.join(event.data.get('missing') or [])}", "status": "void"}


@register_formatter("claim.submitted")
def _claim_submitted(event: AuditEvent, ctx: PassbookContext) -> dict:
    receipt = event.data.get("receipt") or {}
    return {"title": "Claim submitted · assessment pending", "detail": receipt.get("claim_ref"),
            "amount_minor": event.data.get("claimed_amount_minor"), "currency": event.data.get("currency"),
            "stamp": {"kind": "posted"}}
