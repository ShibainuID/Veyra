"""The animal passbook (design authority: Passbook Ledger; plan Section 7 F3-F10: "full passbook with all entries").

Every animal keeps a passbook. Its lines are the animal's audit events, numbered in the order they happened,
followed by one `awaiting` line per agent action still waiting for a decision, for execution, or for the
provider. A line reads like a bank passbook entry: a date, a title, an optional amount, and a stamp once a person
or provider has acted.

Titles come from a formatter registry keyed by event type. A domain module registers the formatters for its own
events when it is imported (`@register_formatter("action.approved")`), and the routes import the domain modules,
so every formatter is registered before a passbook is built. A formatter returns only the fields it sets; an event
type without one gets a generic title from its name, so a new event never breaks the passbook.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from domain import clock
from domain.audit import actor_ref, list_events, user_names
from persistence.models import AgentAction, AuditEvent, Policy, Valuation

LINE_KINDS = ("event", "awaiting")
LINE_STATUSES = ("posted", "awaiting", "void")
STAMP_KINDS = ("approved", "declined", "posted", "failed", "unknown", "confirmed")
AWAITING_STATUSES = ("pending_approval", "approved", "executing")
ACTION_TITLES = {
    "POLICY_APPLICATION": "Policy application",
    "PREMIUM_PAYMENT": "Premium payment",
    "INSURER_NOTIFICATION": "Insurer notification",
    "CLAIM_SUBMISSION": "Claim submission",
}
AWAITING_DETAILS = {"pending_approval": "Waiting for manager approval", "approved": "Approved, waiting to execute",
                    "executing": "Executing with the provider"}
FORMATTER_FIELDS = frozenset({"title", "detail", "amount_minor", "currency", "stamp", "status", "action_id"})
_ORIGIN_PREFIXES = ("seed",)


@dataclass
class PassbookContext:
    """What a formatter may look up while building one passbook. `get` reads through a per-passbook cache."""

    session: Session
    farm_id: str
    animal_id: str
    _cache: dict = field(default_factory=dict)

    def get(self, model, record_id: str | None):
        if record_id is None:
            return None
        key = (model, record_id)
        if key not in self._cache:
            self._cache[key] = self.session.get(model, record_id)
        return self._cache[key]


Formatter = Callable[[AuditEvent, PassbookContext], dict]
_FORMATTERS: dict[str, Formatter] = {}


def register_formatter(event_type: str, fn: Formatter | None = None):
    """Register `fn` for `event_type`, or use as a decorator: `@register_formatter("alert.created")`."""

    def register(formatter: Formatter) -> Formatter:
        _FORMATTERS[event_type] = formatter
        return formatter

    return register(fn) if fn is not None else register


def generic_title(event_type: str) -> str:
    """`seed.policy_created` → "Policy created", `alert.created` → "Alert created"."""
    parts = event_type.split(".")
    if len(parts) > 1 and parts[0] in _ORIGIN_PREFIXES:
        parts = parts[1:]
    text = " ".join(parts).replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Event"


@lru_cache
def _catalog_names(path: Path) -> dict[str, str]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return {product["product_id"]: product["name"] for product in catalog["products"]}


def product_name(product_id: str | None) -> str | None:
    if product_id is None:
        return None
    return _catalog_names(get_settings().fixtures_dir / "policies.json").get(product_id, product_id)


def _blank_line(at: str, kind: str, event_type: str, title: str, actor: dict, subject_type: str,
                subject_id: str) -> dict:
    return {"at": at, "kind": kind, "event_type": event_type, "title": title, "detail": None, "actor": actor,
            "amount_minor": None, "currency": None, "stamp": None, "action_id": None, "subject_type": subject_type,
            "subject_id": subject_id, "status": "posted", "expires_at": None, "payload_hash_prefix": None}


def _event_line(event: AuditEvent, ctx: PassbookContext, names: dict[str, str]) -> dict:
    at = clock.isoformat(event.created_at)
    actor = actor_ref(event.actor_type, event.actor_id, names)
    line = _blank_line(at, "event", event.event_type, generic_title(event.event_type), actor, event.subject_type,
                       event.subject_id)
    line["action_id"] = event.data.get("action_id") or (event.subject_id if event.subject_type == "agent_action"
                                                         else None)
    formatter = _FORMATTERS.get(event.event_type)
    if formatter is not None:
        fields = formatter(event, ctx)
        unknown = set(fields) - FORMATTER_FIELDS
        if unknown:
            raise ValueError(f"formatter for {event.event_type!r} returned unknown fields: {sorted(unknown)}")
        line.update(fields)
    if line["stamp"] is not None:
        line["stamp"] = {"by": actor["name"], "at": at, **line["stamp"]}
    return line


def _awaiting_line(action: AgentAction, names: dict[str, str]) -> dict:
    payload = action.payload or {}
    title = ACTION_TITLES.get(action.action_type, generic_title(action.action_type.lower()))
    line = _blank_line(clock.isoformat(action.created_at), "awaiting", f"action.{action.status}", title,
                       actor_ref(action.proposed_by_type, action.proposed_by_id, names), "agent_action", action.id)
    line.update(detail=AWAITING_DETAILS.get(action.status), amount_minor=action_amount(payload),
                currency=payload.get("currency"), action_id=action.id, status="awaiting",
                expires_at=clock.isoformat(action.expires_at), payload_hash_prefix=action.payload_hash[:8])
    return line


def action_amount(payload: dict) -> int | None:
    return payload.get("amount_minor", payload.get("premium_minor"))


def awaiting_actions(session: Session, farm_id: str, animal_id: str) -> list[AgentAction]:
    query = (select(AgentAction)
             .where(AgentAction.farm_id == farm_id, AgentAction.animal_id == animal_id,
                    AgentAction.status.in_(AWAITING_STATUSES))
             .order_by(AgentAction.created_at, AgentAction.id))
    return list(session.scalars(query))


def build_passbook(session: Session, farm_id: str, animal_id: str) -> list[dict]:
    names = user_names(session, farm_id)
    ctx = PassbookContext(session, farm_id, animal_id)
    lines = [_event_line(event, ctx, names) for event in list_events(session, farm_id, animal_id=animal_id)]
    lines += [_awaiting_line(action, names) for action in awaiting_actions(session, farm_id, animal_id)]
    return [{"no": no, **line} for no, line in enumerate(lines, start=1)]


def exposure_summary(session: Session, farm_id: str, animal_id: str) -> dict:
    """The passbook header: what the animal is worth (latest valuation) against what active policies insure."""
    valuation = session.scalar(select(Valuation).where(Valuation.animal_id == animal_id)
                               .order_by(Valuation.version.desc()).limit(1))
    policies = session.scalars(select(Policy).where(Policy.farm_id == farm_id, Policy.animal_id == animal_id,
                                                    Policy.status == "active")).all()
    insured = sum(policy.insured_value_minor for policy in policies)
    low = valuation.value_low_minor if valuation else None
    return {
        "exposure_low_minor": low,
        "exposure_high_minor": valuation.value_high_minor if valuation else None,
        "insured_minor": insured,
        "uninsured_low_minor": max(0, low - insured) if low is not None else None,
        "currency": valuation.currency if valuation else (policies[0].currency if policies else None),
    }


@register_formatter("seed.animal_created")
def _animal_created(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Registered in herd", "detail": event.data.get("name")}


@register_formatter("seed.policy_created")
def _policy_created(event: AuditEvent, ctx: PassbookContext) -> dict:
    data = event.data
    terms = data.get("terms_version")
    return {"title": f"Policy active · {product_name(data.get('product_id'))}",
            "detail": f"{data.get('provider_id')} · terms {terms}" if terms else None,
            "amount_minor": data.get("insured_value_minor"), "currency": data.get("currency"),
            "stamp": {"kind": "posted"}}


@register_formatter("seed.enrollment_confirmed")
def _enrollment_confirmed(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Enrolled from guided video", "detail": event.data.get("sample_key"),
            "stamp": {"kind": "confirmed"}}


@register_formatter("alert.created")
def _alert_created(event: AuditEvent, ctx: PassbookContext) -> dict:
    kind = event.data.get("kind")
    return {"title": f"Alert · {generic_title(kind)}" if kind else "Alert created"}


@register_formatter("alert.acknowledged")
def _alert_acknowledged(event: AuditEvent, ctx: PassbookContext) -> dict:
    return {"title": "Alert acknowledged", "detail": event.data.get("note")}
