"""The Agent Wallet: proposed actions, human approval, and idempotent sandbox execution (plan Section 4).

The agent prepares an action; the server builds its payload from current records (the client never supplies
amounts) and hashes it as canonical JSON. Only a manager approves, naming the exact hash and version they saw.
Execution needs an `Idempotency-Key` and runs as three short steps, never holding a write transaction across
the provider call:

1. tx1: checks (state, expiry, stale payload, funds), insert the execution `executing` (unique per action and
   per key), move the action `approved → executing`, hold the funds. Commit.
2. Call the sandbox provider in its own session; the provider stores its record under the key and commits.
3. tx2: apply the result. Success → `succeeded`, release + debit, domain effects. Decline → `failed`, release.
   Timeout → `unknown` with the hold kept; a retry with the same key reconciles from the provider record.

A payment success only marks the policy `paid_pending_activation`; after tx2 commits, the insurer is asked
separately to activate it. Agent proposal, human decision, and provider result are separate audit events.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from adapters.sandbox import ProviderTimeout, lookup
from adapters.sandbox import insurer, payment
from domain import audit, clock, evidence, insurance, wallet
from domain.auth import Principal
from domain.canonical import sha256_hex
from domain.catalog import get_product, load_catalog, provider_name
from domain.eligibility import facts_for
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import ACTION_TITLES, PassbookContext, action_amount, product_name, register_formatter
from domain.valuation import farm_animal, latest_valuation
from persistence.db import SessionLocal, read_session
from persistence.models import (
    ActionExecution, AgentAction, Alert, Animal, AuditEvent, EvidenceManifest, Policy, PolicyApplication,
)

logger = logging.getLogger("veyra.actions")

ACTION_TYPES = tuple(ACTION_TITLES)
APPROVAL_TTL = timedelta(minutes=30)
EXECUTION_LEASE = timedelta(minutes=2)  # a same-key retry may reconcile a record-less `executing` row after this
REF_KEYS = ("animal_id", "product_id", "policy_application_id", "alert_id", "claim_id")
REVISABLE_STATUSES = ("pending_approval", "approved", "expired", "cancelled", "declined", "failed")
UNKNOWN_ERRORS = {
    "PROVIDER_TIMEOUT": "No answer from the provider in time.",
    "PROVIDER_ERROR": "The provider call failed before an answer arrived.",
    "PROCESS_RESTARTED": "The API restarted while this execution was in flight.",
}
OPEN_STATUSES = ("pending_approval", "approved")
IN_FLIGHT_STATUSES = ("executing", "unknown", "succeeded")
SUCCESS_RESPONSES = ("accepted", "succeeded", "received")
DISCLOSED_FIELDS = ["animal_id", "breed", "sex", "age_range", "weight_range", "valuation_range", "identity_reference"]


class CommitThenRaise(Exception):
    """A rule failed after recording a state change that must be kept (expiry, a blocked claim): the caller
    commits its session and then raises `error`."""

    def __init__(self, error: DomainError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass
class Built:
    payload: dict
    animal_id: str | None
    subject_type: str
    subject_id: str
    manifest_items: list[dict]

    @property
    def subject(self) -> tuple[str, str]:
        return self.subject_type, self.subject_id


Builder = Callable[[Session, str, dict], Built]
Effect = Callable[[Session, AgentAction, ActionExecution, dict], dict]
Caller = Callable[[Session, str, dict, str], dict]
Blocked = Callable[[Session, Principal, dict, DomainError], bool]


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    provider: str
    operation: str
    build: Builder
    call: Caller
    apply: Effect
    holds_funds: bool = False
    on_blocked: Blocked | None = None  # records why a proposal was refused; True keeps that record


SPECS: dict[str, ActionSpec] = {}


def register(spec: ActionSpec) -> None:
    SPECS[spec.action_type] = spec


def payload_hash(payload: dict) -> str:
    return sha256_hex(payload)


# Shared lookups ------------------------------------------------------------------------------------------------

def confirmed_animal(session: Session, farm_id: str, animal_id: str | None) -> Animal:
    if not animal_id:
        raise DomainError("VALIDATION_FAILED", "animal_id is required for this action.")
    animal = farm_animal(session, farm_id, animal_id)
    if animal.identity_status != "confirmed":
        raise DomainError("IDENTITY_UNCONFIRMED", "The animal's identity must be confirmed before acting for it.",
                          {"animal_id": animal.id, "identity_status": animal.identity_status})
    return animal


def require_ref(refs: dict, name: str) -> str:
    value = refs.get(name)
    if not value:
        raise DomainError("VALIDATION_FAILED", f"{name} is required for this action.", {"field": name})
    return value


def active_policy(session: Session, farm_id: str, animal_id: str) -> Policy | None:
    return session.scalar(select(Policy).where(Policy.farm_id == farm_id, Policy.animal_id == animal_id,
                                               Policy.status == "active")
                          .order_by(Policy.created_at.desc(), Policy.id).limit(1))


def in_flight(session: Session, farm_id: str, action_type: str, subject_type: str, subject_id: str) -> str | None:
    return session.scalar(select(AgentAction.id).where(
        AgentAction.farm_id == farm_id, AgentAction.action_type == action_type,
        AgentAction.subject_type == subject_type, AgentAction.subject_id == subject_id,
        AgentAction.status.in_(IN_FLIGHT_STATUSES)).limit(1))


def _today_cover() -> tuple[str, str]:
    today = clock.now().date()
    return today.isoformat(), insurer.one_year_cover(today).isoformat()


# Builders ------------------------------------------------------------------------------------------------------

def build_application(session: Session, farm_id: str, refs: dict) -> Built:
    animal = confirmed_animal(session, farm_id, refs.get("animal_id"))
    catalog = load_catalog()
    product = get_product(catalog, require_ref(refs, "product_id"))
    open_policy = session.scalar(select(Policy.id).where(
        Policy.farm_id == farm_id, Policy.animal_id == animal.id,
        Policy.status.in_(("awaiting_payment", "paid_pending_activation", "active"))).limit(1))
    if open_policy or in_flight(session, farm_id, "POLICY_APPLICATION", "animal", animal.id):
        raise DomainError("INVALID_STATE", "This animal already has a policy or an application in progress.",
                          {"animal_id": animal.id, "policy_id": open_policy})
    valuation = latest_valuation(session, animal.id)
    insured = insurance.insured_value(catalog, valuation)
    result = insurance.evaluate_product(product, facts_for(session, animal), insured, catalog["currency"])
    if result["outcome"] != "eligible" or insured is None:
        raise DomainError("INVALID_STATE", "The product is not eligible for this animal under the sample terms.", {
            "product_id": product["product_id"], "outcome": result["outcome"],
            "reasons": [r for r in result["reasons"] if r["status"] != "pass"],
            "needs_review": result["needs_review"]})
    items = evidence.animal_items(session, animal)
    start, end = _today_cover()
    payload = {
        "animal_id": animal.id, "product_id": product["product_id"], "provider_id": catalog["provider"]["id"],
        "terms_version": catalog["catalog_version"], "insured_value_minor": insured,
        "premium_minor": result["premium_minor"], "deductible_minor": result["deductible_minor"],
        "currency": catalog["currency"], "coverage_start": start, "coverage_end": end,
        "disclosed_fields": list(DISCLOSED_FIELDS),
        "evidence_manifest_version": evidence.resolve_version(session, farm_id, ("animal", animal.id), items),
    }
    return Built(payload, animal.id, "animal", animal.id, items)


def _farm_application(session: Session, farm_id: str, application_id: str) -> PolicyApplication:
    application = session.get(PolicyApplication, application_id)
    if application is None or application.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Policy application not found.", {"policy_application_id": application_id})
    return application


def build_payment(session: Session, farm_id: str, refs: dict) -> Built:
    application = _farm_application(session, farm_id, require_ref(refs, "policy_application_id"))
    animal = confirmed_animal(session, farm_id, application.animal_id)
    policy = session.scalar(select(Policy).where(Policy.application_id == application.id).limit(1))
    if application.status != "accepted" or policy is None or policy.status != "awaiting_payment":
        raise DomainError("INVALID_STATE", "The premium can be paid only for an accepted application awaiting payment.",
                          {"application_status": application.status, "policy_status": policy.status if policy else None})
    if in_flight(session, farm_id, "PREMIUM_PAYMENT", "policy_application", application.id):
        raise DomainError("INVALID_STATE", "A premium payment for this application is already in progress.",
                          {"policy_application_id": application.id})
    items = evidence.animal_items(session, animal) + evidence.application_items(application, policy)
    subject = ("policy_application", application.id)
    payload = {
        "animal_id": animal.id, "policy_application_id": application.id, "policy_id": policy.id,
        "provider_id": policy.provider_id, "amount_minor": application.premium_minor,
        "currency": application.currency, "terms_version": application.terms_version,
        "evidence_manifest_version": evidence.resolve_version(session, farm_id, subject, items), "mode": "sandbox",
    }
    return Built(payload, animal.id, *subject, items)


def _fmt_time(value) -> str:
    return clock.isoformat(value).replace("T", " ").replace("Z", " UTC")


def alert_summary(alert: Alert, animal: Animal) -> str:
    rule = alert.rule or {}
    facts = ", ".join(f"{key} {rule[key]}" for key in ("score", "baseline", "threshold", "reason", "mean_visibility")
                      if key in rule)
    kind = alert.kind.replace("_", " ")
    text = (f"{kind.capitalize()} alert for {animal.name} ({animal.id}) on camera {alert.camera_id}, "
            f"{_fmt_time(alert.window_start)} to {_fmt_time(alert.window_end)}.")
    if rule.get("name"):
        text += f" Rule {rule['name']}" + (f": {facts}." if facts else ".")
    if rule.get("source"):
        text += f" Source: {rule['source']}."
    return text


def build_notification(session: Session, farm_id: str, refs: dict) -> Built:
    alert_id = require_ref(refs, "alert_id")
    alert = session.get(Alert, alert_id)
    if alert is None or alert.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Alert not found.", {"alert_id": alert_id})
    if alert.animal_id is None:
        raise DomainError("INVALID_STATE", "This alert is on an unassigned track, not on a passport animal; the "
                          "insurer can be notified only about a confirmed animal.", {"alert_id": alert.id})
    animal = confirmed_animal(session, farm_id, alert.animal_id)
    policy = active_policy(session, farm_id, animal.id)
    if policy is None:
        raise DomainError("INVALID_STATE", "The animal has no active policy to notify the insurer under.",
                          {"animal_id": animal.id})
    items = evidence.identity_items(session, animal) + evidence.alert_items(session, alert) + [
        evidence.policy_item(policy)]
    subject = ("alert", alert.id)
    payload = {
        "animal_id": animal.id, "alert_id": alert.id, "policy_id": policy.id, "provider_id": policy.provider_id,
        "summary": alert_summary(alert, animal),
        "evidence_manifest_version": evidence.resolve_version(session, farm_id, subject, items),
    }
    return Built(payload, animal.id, *subject, items)


# Domain effects ------------------------------------------------------------------------------------------------

def apply_application(session: Session, action: AgentAction, execution: ActionExecution, response: dict) -> dict:
    p = action.payload
    application = PolicyApplication(
        id=new_id("app"), farm_id=action.farm_id, animal_id=p["animal_id"], product_id=p["product_id"],
        provider_id=p["provider_id"], terms_version=p["terms_version"], insured_value_minor=p["insured_value_minor"],
        premium_minor=p["premium_minor"], deductible_minor=p["deductible_minor"], currency=p["currency"],
        coverage_start=_date(p["coverage_start"]), coverage_end=_date(p["coverage_end"]), status="accepted",
        provider_ref=response.get("application_ref"))
    session.add(application)
    session.flush()
    policy = Policy(
        id=new_id("pol"), farm_id=action.farm_id, animal_id=p["animal_id"], application_id=application.id,
        product_id=p["product_id"], provider_id=p["provider_id"], terms_version=p["terms_version"],
        insured_value_minor=p["insured_value_minor"], premium_minor=p["premium_minor"],
        deductible_minor=p["deductible_minor"], currency=p["currency"], status="awaiting_payment",
        effective_date=None, expiry_date=None, activation_receipt=None)
    session.add(policy)
    session.flush()
    return {"policy_application_id": application.id, "policy_id": policy.id, "policy_status": policy.status}


def apply_payment(session: Session, action: AgentAction, execution: ActionExecution, response: dict) -> dict:
    policy_id = action.payload["policy_id"]
    rows = session.execute(update(Policy).where(Policy.id == policy_id, Policy.status == "awaiting_payment")
                           .values(status="paid_pending_activation")).rowcount
    if rows != 1:
        logger.warning("payment %s succeeded but policy %s was not awaiting payment", action.id, policy_id)
    return {"policy_id": policy_id, "policy_status": "paid_pending_activation"}


def apply_receipt_only(session: Session, action: AgentAction, execution: ActionExecution, response: dict) -> dict:
    return {}


def _date(value: str) -> date:
    return date.fromisoformat(value)


register(ActionSpec("POLICY_APPLICATION", insurer.PROVIDER, "submit_application", build_application,
                    lambda s, key, payload, farm_id: insurer.submit_application(s, key, payload), apply_application))
register(ActionSpec("PREMIUM_PAYMENT", payment.PROVIDER, payment.OPERATION, build_payment,
                    lambda s, key, payload, farm_id: payment.charge(s, key, payload, farm_id=farm_id), apply_payment,
                    holds_funds=True))
register(ActionSpec("INSURER_NOTIFICATION", insurer.PROVIDER, "submit_notification", build_notification,
                    lambda s, key, payload, farm_id: insurer.submit_notification(s, key, payload), apply_receipt_only))


# Reads ---------------------------------------------------------------------------------------------------------

def farm_action(session: Session, farm_id: str, action_id: str) -> AgentAction:
    action = session.get(AgentAction, action_id)
    if action is None or action.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Agent action not found.", {"action_id": action_id})
    return action


def is_expired(action: AgentAction) -> bool:
    return action.status in OPEN_STATUSES and clock.now() >= action.expires_at


def effective_status(action: AgentAction) -> str:
    return "expired" if is_expired(action) else action.status


def _columns(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def action_view(session: Session, action: AgentAction) -> dict:
    payload = dict(action.payload or {})
    manifest = session.get(EvidenceManifest, action.evidence_manifest_id) if action.evidence_manifest_id else None
    execution = session.scalar(select(ActionExecution).where(ActionExecution.action_id == action.id))
    amount = action_amount(payload)
    balance_after = None
    if action.action_type == "PREMIUM_PAYMENT" and amount is not None:
        available = wallet.balance(session, action.farm_id)
        balance_after = available - amount if action.status in OPEN_STATUSES else available
    catalog = load_catalog()
    return {
        **_columns(action), "payload": payload, "status": effective_status(action),
        "evidence_manifest": ({"id": manifest.id, "version": manifest.version, "manifest_hash": manifest.manifest_hash,
                               "items": list(manifest.items)} if manifest else None),
        "execution": _columns(execution) if execution else None,
        "review": {"recipient": provider_name(catalog, payload.get("provider_id", "")),
                   "animal_id": action.animal_id, "currency": payload.get("currency"),
                   # A claim moves no money; its review shows the claimed amount.
                   "amount_minor": amount if amount is not None else payload.get("claimed_amount_minor"),
                   "terms_version": payload.get("terms_version"),
                   "evidence_manifest_version": payload.get("evidence_manifest_version"),
                   "balance_after_minor": balance_after},
    }


def list_actions(session: Session, farm_id: str, *, status: str | None = None,
                 animal_id: str | None = None) -> list[dict]:
    query = select(AgentAction).where(AgentAction.farm_id == farm_id)
    if animal_id is not None:
        query = query.where(AgentAction.animal_id == animal_id)
    actions = session.scalars(query.order_by(AgentAction.created_at.desc(), AgentAction.id)).all()
    views = [action_view(session, action) for action in actions]
    return [view for view in views if status is None or view["status"] == status]


# Propose, decide, cancel ---------------------------------------------------------------------------------------

def _audit(session: Session, action: AgentAction, event_type: str, actor_type: str, actor_id: str,
           data: dict | None = None) -> None:
    audit.record(session, farm_id=action.farm_id, actor_type=actor_type, actor_id=actor_id, event_type=event_type,
                 subject_type="agent_action", subject_id=action.id, animal_id=action.animal_id,
                 data={"action_id": action.id, "action_type": action.action_type, "version": action.version,
                       "payload_hash": action.payload_hash, **(data or {})})


def _transition(session: Session, action: AgentAction, expected: tuple[str, ...], **values) -> bool:
    rows = session.execute(update(AgentAction).where(AgentAction.id == action.id, AgentAction.status.in_(expected))
                           .values(updated_at=clock.now(), **values)).rowcount
    return rows == 1


def _expire(session: Session, action: AgentAction) -> None:
    if _transition(session, action, OPEN_STATUSES, status="expired"):
        _audit(session, action, "action.expired", "system", "veyra", {"expires_at": clock.isoformat(action.expires_at)})


def propose(session: Session, principal: Principal, refs: dict, rationale: str | None = None,
            revises: AgentAction | None = None) -> AgentAction:
    action_type = refs.get("action_type")
    spec = SPECS.get(action_type)
    if spec is None:
        raise DomainError("VALIDATION_FAILED", "Unknown action type.", {"action_type": action_type})
    if refs.get("animal_id"):
        confirmed_animal(session, principal.farm_id, refs["animal_id"])
    try:
        built = spec.build(session, principal.farm_id, refs)
    except DomainError as error:
        if spec.on_blocked is not None and spec.on_blocked(session, principal, refs, error):
            raise CommitThenRaise(error) from None
        raise
    if refs.get("animal_id") and built.animal_id != refs["animal_id"]:
        raise DomainError("VALIDATION_FAILED", "animal_id does not match the action's subject.",
                          {"animal_id": refs["animal_id"], "subject_animal_id": built.animal_id})
    manifest = evidence.ensure(session, principal.farm_id, built.subject, built.manifest_items)
    if manifest.version != built.payload["evidence_manifest_version"]:
        raise RuntimeError("evidence manifest version changed while proposing")

    prior = session.scalars(select(AgentAction).where(
        AgentAction.farm_id == principal.farm_id, AgentAction.action_type == action_type,
        AgentAction.subject_type == built.subject_type, AgentAction.subject_id == built.subject_id,
        AgentAction.status.in_(OPEN_STATUSES)).order_by(AgentAction.version.desc())).all()
    latest_version = session.scalar(select(AgentAction.version).where(
        AgentAction.farm_id == principal.farm_id, AgentAction.action_type == action_type,
        AgentAction.subject_type == built.subject_type, AgentAction.subject_id == built.subject_id)
        .order_by(AgentAction.version.desc()).limit(1))
    now = clock.now()
    supersedes = prior[0] if prior else revises
    action = AgentAction(
        id=new_id("act"), farm_id=principal.farm_id, action_type=action_type, animal_id=built.animal_id,
        subject_type=built.subject_type, subject_id=built.subject_id,
        version=(latest_version or 0) + 1 if supersedes else 1, supersedes_id=supersedes.id if supersedes else None,
        payload=built.payload, payload_hash=payload_hash(built.payload), evidence_manifest_id=manifest.id,
        evidence_manifest_version=manifest.version, status="pending_approval", rationale=rationale,
        proposed_by_type="agent", proposed_by_id=principal.user_id, expires_at=now + APPROVAL_TTL,
        created_at=now, updated_at=now)
    for old in prior:
        if _transition(session, old, OPEN_STATUSES, status="cancelled", cancel_reason="superseded"):
            _audit(session, old, "action.cancelled", "agent", principal.user_id,
                   {"cancel_reason": "superseded", "superseded_by": action.id})
    session.add(action)
    session.flush()
    _audit(session, action, "action.proposed", "agent", principal.user_id, {
        "on_behalf_of": principal.user_id, "rationale": rationale, "supersedes_id": action.supersedes_id,
        "evidence_manifest_version": manifest.version, "amount_minor": action_amount(built.payload),
        "currency": built.payload.get("currency"), "product_id": built.payload.get("product_id")})
    return action


def decide(session: Session, principal: Principal, action_id: str, *, decision: str, payload_hash: str,
           version: int, note: str | None = None) -> AgentAction:
    action = farm_action(session, principal.farm_id, action_id)
    if action.status == "pending_approval" and is_expired(action):
        _expire(session, action)
        raise CommitThenRaise(DomainError("ACTION_EXPIRED", "The approval window has passed; prepare it again.",
                                          {"expires_at": clock.isoformat(action.expires_at)}))
    if action.status == "expired":
        raise DomainError("ACTION_EXPIRED", "The approval window has passed; prepare it again.")
    if action.status != "pending_approval":
        raise DomainError("INVALID_STATE", "Only an action waiting for approval can be decided.",
                          {"status": action.status})
    if payload_hash != action.payload_hash or version != action.version:
        raise DomainError("APPROVAL_STALE", "The action changed since it was reviewed; review the current version.",
                          {"payload_hash": action.payload_hash, "version": action.version})
    if decision not in ("approve", "decline"):
        raise DomainError("VALIDATION_FAILED", "decision must be approve or decline.")
    status = "approved" if decision == "approve" else "declined"
    now = clock.now()
    if not _transition(session, action, ("pending_approval",), status=status, decided_by=principal.user_id,
                       decided_at=now, decision=decision, decision_note=note):
        raise DomainError("INVALID_STATE", "The action was decided or changed by someone else.")
    actor_type, actor_id = audit.actor_from(principal)
    _audit(session, action, f"action.{status}", actor_type, actor_id, {
        "note": note, "amount_minor": action_amount(action.payload), "currency": action.payload.get("currency")})
    return action


def cancel(session: Session, principal: Principal, action_id: str) -> AgentAction:
    action = farm_action(session, principal.farm_id, action_id)
    if action.status not in OPEN_STATUSES:
        raise DomainError("INVALID_STATE", "Only a pending or approved action can be cancelled.",
                          {"status": action.status})
    if not _transition(session, action, OPEN_STATUSES, status="cancelled", cancel_reason="cancelled_by_user"):
        raise DomainError("INVALID_STATE", "The action changed while cancelling.")
    actor_type, actor_id = audit.actor_from(principal)
    _audit(session, action, "action.cancelled", actor_type, actor_id, {"cancel_reason": "cancelled_by_user"})
    return action


def revise(session: Session, principal: Principal, action_id: str) -> AgentAction:
    """Prepare the action again from its own references and current records; an open original is superseded."""
    action = farm_action(session, principal.farm_id, action_id)
    if action.status not in REVISABLE_STATUSES:
        raise DomainError("INVALID_STATE", "An action that ran or is running cannot be revised.",
                          {"status": action.status})
    refs = {"action_type": action.action_type, **{key: action.payload.get(key) for key in REF_KEYS}}
    return propose(session, principal, refs, action.rationale, revises=action)


# Execute -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Started:
    execution_id: str
    status: str
    call_provider: bool


def _changed_fields(old: dict, new: dict) -> list[str]:
    return sorted(key for key in set(old) | set(new) if old.get(key) != new.get(key))


def _start(principal: Principal, action_id: str, key: str) -> _Started:
    """tx1: every check, then claim the execution and hold funds. Commits before any provider call."""
    with SessionLocal() as session:
        action = farm_action(session, principal.farm_id, action_id)
        by_key = session.scalar(select(ActionExecution).where(ActionExecution.idempotency_key == key))
        if by_key is not None:
            if by_key.action_id != action.id:
                raise DomainError("DUPLICATE_EXECUTION", "This Idempotency-Key was already used for another action.")
            if by_key.status == "executing" and _stranded(session, action, by_key):
                return _Started(by_key.id, "unknown", call_provider=False)
            return _Started(by_key.id, by_key.status, call_provider=False)
        if session.scalar(select(ActionExecution.id).where(ActionExecution.action_id == action.id)):
            raise DomainError("DUPLICATE_EXECUTION", "This action was already executed under another key.")
        if action.status in ("pending_approval", "declined", "cancelled"):
            raise DomainError("APPROVAL_REQUIRED", "A manager must approve this action before it runs.",
                              {"status": action.status})
        if action.status == "expired":
            raise DomainError("ACTION_EXPIRED", "The approval window has passed; prepare it again.")
        if action.status != "approved":
            raise DomainError("INVALID_STATE", "The action is not ready to execute.", {"status": action.status})
        if is_expired(action):
            _expire(session, action)
            session.commit()
            raise DomainError("ACTION_EXPIRED", "The approval window has passed; prepare it again.",
                              {"expires_at": clock.isoformat(action.expires_at)})

        spec = SPECS[action.action_type]
        stale_reason, rebuilt = None, None
        rebuild_error = None
        try:
            rebuilt = spec.build(session, action.farm_id, action.payload)
        except DomainError as error:
            rebuild_error = error
            stale_reason = {"code": error.code, "message": error.message}
        if rebuilt is None or payload_hash(rebuilt.payload) != action.payload_hash:
            changed = _changed_fields(action.payload, rebuilt.payload) if rebuilt else []
            if _transition(session, action, ("approved",), status="cancelled", cancel_reason="approval_stale"):
                _audit(session, action, "action.cancelled", "system", "veyra",
                       {"cancel_reason": "approval_stale", "changed_fields": changed, "reason": stale_reason})
            session.commit()
            if rebuild_error is not None and rebuild_error.code == "IDENTITY_UNCONFIRMED":
                raise rebuild_error
            raise DomainError("APPROVAL_STALE", "The records changed since approval; prepare and approve it again.",
                              {"changed_fields": changed, "reason": stale_reason})

        amount = action_amount(action.payload) if spec.holds_funds else None
        if amount is not None:
            available = wallet.balance(session, action.farm_id)
            if available < amount:
                raise DomainError("INSUFFICIENT_SANDBOX_FUNDS", "The sandbox wallet cannot cover this payment.",
                                  {"available_minor": available, "amount_minor": amount})
        execution = ActionExecution(id=new_id("exe"), action_id=action.id, idempotency_key=key, status="executing",
                                    provider_id=spec.provider, started_at=clock.now())
        session.add(execution)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise DomainError("DUPLICATE_EXECUTION", "This action is already being executed.") from None
        if not _transition(session, action, ("approved",), status="executing"):
            session.rollback()
            raise DomainError("INVALID_STATE", "The action changed while starting execution.")
        if amount is not None:
            wallet.post(session, action.farm_id, "hold", amount, f"Hold · {ACTION_TITLES[action.action_type]}",
                        action.id, action.payload.get("currency", wallet.CURRENCY))
        session.commit()
        return _Started(execution.id, "executing", call_provider=True)


def _stranded(session: Session, action: AgentAction, execution: ActionExecution) -> bool:
    """An `executing` row whose result was never applied: the provider already answered (its record exists), or
    the lease ran out with no record. Inside the lease and without a record, another request may still be
    calling the provider, so the row is left alone."""
    spec = SPECS[action.action_type]
    if lookup(session, spec.provider, spec.operation, execution.idempotency_key) is not None:
        return True
    return clock.now() - execution.started_at >= EXECUTION_LEASE


def _call_provider(spec: ActionSpec, farm_id: str, key: str, payload: dict) -> tuple[dict | None, str | None]:
    """Run the provider in its own short session: (response, None), or (None, why the outcome is unknown)."""
    with SessionLocal() as session:
        try:
            response = spec.call(session, key, payload, farm_id)
            session.commit()
            return response, None
        except ProviderTimeout:
            session.commit()
            return None, "PROVIDER_TIMEOUT"
        except Exception:
            session.rollback()
            logger.exception("sandbox provider %s.%s failed", spec.provider, spec.operation)
            return None, "PROVIDER_ERROR"


def _finish(execution_id: str, response: dict | None, executed_by: str,
            unknown_code: str = "PROVIDER_TIMEOUT") -> bool:
    """tx2: apply a provider result exactly once. Returns True only when this call applied a success."""
    with SessionLocal() as session:
        execution = session.get(ActionExecution, execution_id)
        action = session.get(AgentAction, execution.action_id)
        spec = SPECS[action.action_type]
        amount = action_amount(action.payload) if spec.holds_funds else None
        now = clock.now()
        if response is None:
            rows = session.execute(update(ActionExecution).where(
                ActionExecution.id == execution.id, ActionExecution.status == "executing").values(
                status="unknown", error={"code": unknown_code, "message": UNKNOWN_ERRORS[unknown_code]})).rowcount
            if rows == 1:
                _transition(session, action, ("executing",), status="unknown")
                _audit(session, action, "action.executed", "provider", spec.provider, {
                    "status": "unknown", "execution_id": execution.id, "idempotency_key": execution.idempotency_key,
                    "executed_by": executed_by, "amount_minor": amount, "currency": action.payload.get("currency"),
                    "error": {"code": unknown_code}})
            session.commit()
            return False
        succeeded = response.get("status") in SUCCESS_RESPONSES
        status = "succeeded" if succeeded else "failed"
        error = None if succeeded else {"code": response.get("code", "PROVIDER_DECLINED"),
                                        "message": response.get("message", "The provider declined the request.")}
        rows = session.execute(update(ActionExecution).where(
            ActionExecution.id == execution.id, ActionExecution.status.in_(("executing", "unknown"))).values(
            status=status, provider_receipt=dict(response) if succeeded else None, error=error,
            completed_at=now)).rowcount
        if rows != 1:  # another request already applied the result and runs the follow-up
            session.rollback()
            return False
        _transition(session, action, ("executing", "unknown"), status=status)
        if amount is not None:
            title = ACTION_TITLES[action.action_type]
            currency = action.payload.get("currency", wallet.CURRENCY)
            wallet.post(session, action.farm_id, "release", amount, f"Release hold · {title}", action.id, currency)
            if succeeded:
                wallet.post(session, action.farm_id, "debit", amount, f"Premium · {action.animal_id} · "
                            f"{action.payload.get('policy_id')}", action.id, currency)
        effects = spec.apply(session, action, execution, response) if succeeded else {}
        _audit(session, action, "action.executed", "provider", spec.provider, {
            "status": status, "execution_id": execution.id, "idempotency_key": execution.idempotency_key,
            "executed_by": executed_by, "receipt": dict(response) if succeeded else None, "error": error,
            "amount_minor": action_amount(action.payload), "currency": action.payload.get("currency"), **effects})
        session.commit()
        return succeeded


def _reconcile(execution_id: str) -> dict:
    with read_session() as session:
        execution = session.get(ActionExecution, execution_id)
        action = session.get(AgentAction, execution.action_id)
        spec = SPECS[action.action_type]
        record = lookup(session, spec.provider, spec.operation, execution.idempotency_key)
        if record is None:
            return {"status": "failed", "code": "PROVIDER_NO_RECORD",
                    "message": "The provider has no record of this request; nothing was charged or sent."}
        return dict(record.response)


def execute(principal: Principal, action_id: str, key: str | None) -> str:
    """Execute an approved action once per idempotency key; returns the action id. Opens its own sessions."""
    if not key or not key.strip():
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Send an Idempotency-Key header to execute an action.")
    key = key.strip()
    started = _start(principal, action_id, key)
    if not started.call_provider:
        if started.status == "unknown":
            succeeded = _finish(started.execution_id, _reconcile(started.execution_id), principal.user_id)
            if succeeded:
                _after_success(started.execution_id)
        return action_id
    with read_session() as session:
        action = farm_action(session, principal.farm_id, action_id)
        spec, payload, farm_id = SPECS[action.action_type], dict(action.payload), action.farm_id
    response, unknown_code = _call_provider(spec, farm_id, key, payload)
    if _finish(started.execution_id, response, principal.user_id, unknown_code or "PROVIDER_TIMEOUT"):
        _after_success(started.execution_id)
    return action_id


def _after_success(execution_id: str) -> None:
    with read_session() as session:
        execution = session.get(ActionExecution, execution_id)
        action = session.get(AgentAction, execution.action_id)
        action_type, farm_id, payload, key = action.action_type, action.farm_id, dict(action.payload), \
            execution.idempotency_key
    if action_type == "PREMIUM_PAYMENT":
        activate_policy(farm_id, payload["policy_id"], f"{key}:activation")


def recover_stranded() -> int:
    """Startup: the API is one process, so any `executing` row is an orphan of a previous run. Mark it `unknown`
    (its hold stays) so a same-key retry reconciles it from the provider record. Returns how many were marked."""
    with SessionLocal() as session:
        stranded = session.scalars(select(ActionExecution).where(ActionExecution.status == "executing")).all()
        marked = 0
        for execution in stranded:
            rows = session.execute(update(ActionExecution).where(
                ActionExecution.id == execution.id, ActionExecution.status == "executing").values(
                status="unknown", error={"code": "PROCESS_RESTARTED",
                                         "message": UNKNOWN_ERRORS["PROCESS_RESTARTED"]})).rowcount
            if rows != 1:
                continue
            action = session.get(AgentAction, execution.action_id)
            _transition(session, action, ("executing",), status="unknown")
            _audit(session, action, "action.execution_orphaned", "system", "veyra",
                   {"execution_id": execution.id, "idempotency_key": execution.idempotency_key})
            marked += 1
        session.commit()
        return marked


# Activation ----------------------------------------------------------------------------------------------------

def activate_policy(farm_id: str, policy_id: str, key: str) -> None:
    """Ask the insurer to activate a paid policy, then record its answer. Payment alone never activates."""
    with SessionLocal() as session:
        policy = insurance.farm_policy(session, farm_id, policy_id)
        if policy.status != "paid_pending_activation":
            return
        response = insurer.confirm_activation(session, key, policy)
        session.commit()
    with SessionLocal() as session:
        policy = insurance.farm_policy(session, farm_id, policy_id)
        data = {"policy_id": policy.id, "product_id": policy.product_id, "insured_value_minor": policy.insured_value_minor,
                "currency": policy.currency, "receipt": response, "idempotency_key": key}
        if response.get("activated"):
            rows = session.execute(update(Policy).where(
                Policy.id == policy.id, Policy.status == "paid_pending_activation").values(
                status="active", effective_date=_date(response["effective_date"]),
                expiry_date=_date(response["expiry_date"]), activation_receipt=dict(response))).rowcount
            if rows == 1:
                audit.record(session, farm_id=farm_id, actor_type="provider", actor_id=policy.provider_id,
                             event_type="policy.activated", subject_type="policy", subject_id=policy.id,
                             animal_id=policy.animal_id, data=data)
        else:
            audit.record(session, farm_id=farm_id, actor_type="provider", actor_id=policy.provider_id,
                         event_type="policy.activation_pending", subject_type="policy", subject_id=policy.id,
                         animal_id=policy.animal_id, data=data)
        session.commit()


def check_activation(principal: Principal, policy_id: str, key: str | None = None) -> None:
    with read_session() as session:
        policy = insurance.farm_policy(session, principal.farm_id, policy_id)
        status = policy.status
        if status != "paid_pending_activation":
            if status == "active":
                return
            raise DomainError("INVALID_STATE", "Only a paid policy waiting for the insurer can be checked.",
                              {"status": status})
    activate_policy(principal.farm_id, policy_id, key or f"{policy_id}:activation-check:{new_id('chk')}")


# Passbook lines ------------------------------------------------------------------------------------------------

def _label(event: AuditEvent) -> str:
    return ACTION_TITLES.get(event.data.get("action_type"), "Agent action")


def _amount_fields(event: AuditEvent) -> dict:
    return {"amount_minor": event.data.get("amount_minor"), "currency": event.data.get("currency")}


@register_formatter("action.proposed")
def _proposed(event: AuditEvent, ctx: PassbookContext) -> dict:
    product = event.data.get("product_id")
    return {"title": f"{_label(event)} prepared", "detail": product_name(product) if product else None,
            **_amount_fields(event)}


@register_formatter("action.approved")
def _approved(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": f"{_label(event)} approved", "detail": event.data.get("note"), "stamp": {"kind": "approved"},
            **_amount_fields(event)}


@register_formatter("action.declined")
def _declined(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": f"{_label(event)} declined", "detail": event.data.get("note"), "stamp": {"kind": "declined"},
            "status": "void", **_amount_fields(event)}


@register_formatter("action.cancelled")
def _cancelled(event: AuditEvent, ctx: PassbookContext) -> dict:
    reason = (event.data.get("cancel_reason") or "").replace("_", " ")
    return {"title": f"{_label(event)} cancelled", "detail": reason or None, "status": "void"}


@register_formatter("action.expired")
def _expired(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": f"{_label(event)} expired", "detail": "Not approved within 30 minutes", "status": "void"}


_EXECUTED_WORDS = {"succeeded": "posted", "failed": "failed", "unknown": "unknown"}


@register_formatter("action.executed")
def _executed(event: AuditEvent, ctx: PassbookContext) -> dict:
    status = event.data.get("status")
    receipt = event.data.get("receipt") or {}
    ref = next((receipt[k] for k in ("payment_ref", "application_ref", "notification_ref", "claim_ref") if k in receipt),
               None)
    word = {"succeeded": "sent", "failed": "failed", "unknown": "outcome unknown"}.get(status, status)
    if event.data.get("action_type") == "PREMIUM_PAYMENT" and status == "succeeded":
        word = "paid"
    detail = ref or (event.data.get("error") or {}).get("code")
    return {"title": f"{_label(event)} {word}", "detail": detail, "stamp": {"kind": _EXECUTED_WORDS.get(status, "unknown")},
            "status": "void" if status == "failed" else "posted", **_amount_fields(event)}


@register_formatter("action.execution_orphaned")
def _orphaned(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": f"{_label(event)} outcome unknown", "detail": "Interrupted by a restart; retry to reconcile",
            "stamp": {"kind": "unknown"}}


@register_formatter("policy.activated")
def _activated(event: AuditEvent, ctx: PassbookContext) -> dict:
    receipt = event.data.get("receipt") or {}
    return {"title": f"Policy active · {product_name(event.data.get('product_id'))}",
            "detail": f"{receipt.get('effective_date')} to {receipt.get('expiry_date')} · {receipt.get('confirmation_ref')}",
            "amount_minor": event.data.get("insured_value_minor"), "currency": event.data.get("currency"),
            "stamp": {"kind": "posted"}}


@register_formatter("policy.activation_pending")
def _activation_pending(event: AuditEvent, ctx: PassbookContext) -> dict:
    receipt = event.data.get("receipt") or {}
    return {"title": f"Activation pending · {product_name(event.data.get('product_id'))}",
            "detail": (receipt.get("status") or "pending").replace("_", " "), "stamp": {"kind": "unknown"}}



import domain.claims  # noqa: E402,F401  (registers CLAIM_SUBMISSION; imported last because it builds on this module)
