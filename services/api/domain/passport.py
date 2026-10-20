"""Herd list and Digital Livestock Passport views (plan Section 5: `GET /animals`, `GET /animals/{id}/passport`).

Read-only: each function takes the caller's read session and the principal's farm, and returns plain dicts that
`schemas.py` validates and serializes. Another farm's animal is `NOT_FOUND`.

Coverage per animal: `active` when any policy is active; `pending` when a policy is awaiting payment or
activation, or a policy application or premium payment action is in flight; otherwise `none`.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain import clock, health
from domain.audit import actor_ref, user_names
from domain.errors import DomainError
from domain.passbook import (
    AWAITING_STATUSES, action_amount, awaiting_actions, build_passbook, exposure_summary, product_name,
)
from persistence.media import signed_url
from persistence.models import (
    AgentAction, Alert, Animal, AnimalReference, Camera, Claim, Estimate, Incident, Observation, Policy,
    PolicyApplication, Valuation, WalletEntry,
)

COVERAGE_STATUSES = ("active", "pending", "none")
PENDING_POLICY_STATUSES = ("awaiting_payment", "paid_pending_activation")
COVERAGE_ACTION_TYPES = ("POLICY_APPLICATION", "PREMIUM_PAYMENT")
IN_FLIGHT_ACTION_STATUSES = AWAITING_STATUSES
WALLET_SIGNS = {"credit": 1, "debit": -1, "hold": -1, "release": 1}
DEFAULT_CURRENCY = "USD"


@dataclass
class _Herd:
    """The farm's rows that the herd cards need, grouped by animal id (lists newest first)."""

    estimates: dict[str, list[Estimate]] = field(default_factory=lambda: defaultdict(list))
    valuations: dict[str, list[Valuation]] = field(default_factory=lambda: defaultdict(list))
    policies: dict[str, list[Policy]] = field(default_factory=lambda: defaultdict(list))
    actions: dict[str, list[AgentAction]] = field(default_factory=lambda: defaultdict(list))
    alerts: dict[str, list[Alert]] = field(default_factory=lambda: defaultdict(list))
    last_observation: dict[str, Observation] = field(default_factory=dict)
    camera_names: dict[str, str] = field(default_factory=dict)


def _group(target: dict, rows, key: str = "animal_id") -> None:
    for row in rows:
        target[getattr(row, key)].append(row)


def _load_herd(session: Session, farm_id: str, animal_ids: list[str]) -> _Herd:
    herd = _Herd()
    _group(herd.estimates, session.scalars(select(Estimate).where(Estimate.animal_id.in_(animal_ids))
                                           .order_by(Estimate.created_at.desc(), Estimate.id)))
    _group(herd.valuations, session.scalars(select(Valuation).where(Valuation.animal_id.in_(animal_ids))
                                            .order_by(Valuation.version.desc())))
    _group(herd.policies, session.scalars(select(Policy).where(Policy.farm_id == farm_id,
                                                               Policy.animal_id.in_(animal_ids))
                                          .order_by(Policy.created_at.desc(), Policy.id)))
    _group(herd.actions, session.scalars(select(AgentAction).where(AgentAction.farm_id == farm_id,
                                                                   AgentAction.animal_id.in_(animal_ids))
                                         .order_by(AgentAction.created_at.desc(), AgentAction.id)))
    _group(herd.alerts, session.scalars(select(Alert).where(Alert.farm_id == farm_id, Alert.animal_id.in_(animal_ids))
                                        .order_by(Alert.created_at.desc(), Alert.id)))
    latest = (select(Observation.animal_id, func.max(Observation.observed_at).label("observed_at"))
              .where(Observation.farm_id == farm_id, Observation.animal_id.in_(animal_ids))
              .group_by(Observation.animal_id).subquery())
    on_latest = (Observation.animal_id == latest.c.animal_id) & (Observation.observed_at == latest.c.observed_at)
    newest = select(Observation).join(latest, on_latest).where(Observation.farm_id == farm_id)
    for observation in session.scalars(newest.order_by(Observation.id)):
        herd.last_observation.setdefault(observation.animal_id, observation)
    herd.camera_names = dict(session.execute(select(Camera.id, Camera.name).where(Camera.farm_id == farm_id)).all())
    return herd


def _range(estimate: Estimate | None) -> dict | None:
    if estimate is None:
        return None
    return {"range_low": estimate.range_low, "range_high": estimate.range_high, "unit": estimate.unit,
            "source": estimate.source}


def _latest(estimates: list[Estimate], kind: str) -> Estimate | None:
    return next((estimate for estimate in estimates if estimate.kind == kind), None)


def _coverage(policies: list[Policy], actions: list[AgentAction]) -> dict:
    active = [policy for policy in policies if policy.status == "active"]
    pending = [policy for policy in policies if policy.status in PENDING_POLICY_STATUSES]
    policy = (active or pending or [None])[0]
    if policy is not None:
        return {"status": "active" if active else "pending", "policy_id": policy.id, "product_id": policy.product_id,
                "policy_status": policy.status}
    action = next((a for a in actions if a.action_type in COVERAGE_ACTION_TYPES
                   and a.status in IN_FLIGHT_ACTION_STATUSES), None)
    if action is not None:
        return {"status": "pending", "policy_id": None, "product_id": (action.payload or {}).get("product_id"),
                "policy_status": None}
    return {"status": "none", "policy_id": None, "product_id": None, "policy_status": None}


def _last_seen(observation: Observation | None, camera_names: dict[str, str]) -> dict | None:
    if observation is None:
        return None
    return {"camera_id": observation.camera_id, "camera_name": camera_names.get(observation.camera_id),
            "observed_at": observation.observed_at, "association_status": observation.association_status}


def _card(animal: Animal, herd: _Herd) -> dict:
    estimates = herd.estimates[animal.id]
    valuation = (herd.valuations[animal.id] or [None])[0]
    open_alerts = [alert for alert in herd.alerts[animal.id] if alert.status == "open"]
    last = herd.last_observation.get(animal.id)
    return {
        "id": animal.id, "name": animal.name, "breed": animal.breed, "breed_category": animal.breed_category,
        "sex": animal.sex, "identity_status": animal.identity_status,
        "age": _range(_latest(estimates, "age")),
        "weight": _range(_latest(estimates, "weight")),
        "valuation": None if valuation is None else {
            "value_low_minor": valuation.value_low_minor, "value_high_minor": valuation.value_high_minor,
            "currency": valuation.currency, "price_date": valuation.price_date, "version": valuation.version},
        "coverage": _coverage(herd.policies[animal.id], herd.actions[animal.id]),
        "alerts": {"open_count": len(open_alerts), "kinds": sorted({alert.kind for alert in open_alerts})},
        "last_observation": _last_seen(herd.last_observation.get(animal.id), herd.camera_names),
        "health": health.classify(herd.alerts[animal.id], last.observed_at if last else None, clock.now()),
        "awaiting_approval_count": sum(action.status == "pending_approval" for action in herd.actions[animal.id]),
    }


def _matches(card: dict, coverage: str | None, alerts: str | None, q: str | None) -> bool:
    if coverage is not None and card["coverage"]["status"] != coverage:
        return False
    if alerts == "open" and card["alerts"]["open_count"] == 0:
        return False
    needle = (q or "").strip().lower()
    return not needle or needle in card["id"].lower() or needle in card["name"].lower()


def wallet_balance(session: Session, farm_id: str) -> int:
    rows = session.execute(select(WalletEntry.entry_type, func.sum(WalletEntry.amount_minor))
                           .where(WalletEntry.farm_id == farm_id).group_by(WalletEntry.entry_type)).all()
    return sum(WALLET_SIGNS.get(entry_type, 0) * total for entry_type, total in rows)


def _summary(session: Session, farm_id: str, cards: list[dict], herd: _Herd) -> dict:
    latest = [vals[0] for vals in herd.valuations.values() if vals]
    active = [p for policies in herd.policies.values() for p in policies if p.status == "active"]
    count = select(func.count())
    return {
        "animal_count": len(cards),
        "exposure_low_minor": sum(v.value_low_minor for v in latest),
        "exposure_high_minor": sum(v.value_high_minor for v in latest),
        "insured_minor": sum(policy.insured_value_minor for policy in active),
        "uncovered_count": sum(card["coverage"]["status"] == "none" for card in cards),
        "open_alerts": session.scalar(count.select_from(Alert).where(Alert.farm_id == farm_id,
                                                                      Alert.status == "open")),
        "pending_approvals": session.scalar(count.select_from(AgentAction).where(
            AgentAction.farm_id == farm_id, AgentAction.status == "pending_approval")),
        "wallet_balance_minor": wallet_balance(session, farm_id),
        "currency": latest[0].currency if latest else DEFAULT_CURRENCY,
    }


def list_herd(session: Session, farm_id: str, *, coverage: str | None = None, alerts: str | None = None,
              q: str | None = None) -> dict:
    """The farm's animals (filtered) and a summary of the whole herd (never filtered)."""
    animals = session.scalars(select(Animal).where(Animal.farm_id == farm_id).order_by(Animal.id)).all()
    herd = _load_herd(session, farm_id, [animal.id for animal in animals])
    cards = [_card(animal, herd) for animal in animals]
    return {"items": [card for card in cards if _matches(card, coverage, alerts, q)],
            "summary": _summary(session, farm_id, cards, herd)}


def _columns(row) -> dict:
    return {attr.key: getattr(row, attr.key) for attr in row.__mapper__.column_attrs}


def _observations(session: Session, farm_id: str, animal_id: str, herd: _Herd) -> dict:
    rows = session.execute(select(Observation.camera_id, func.count(), func.max(Observation.observed_at))
                           .where(Observation.farm_id == farm_id, Observation.animal_id == animal_id)
                           .group_by(Observation.camera_id)).all()
    cameras = sorted(({"camera_id": camera_id, "camera_name": herd.camera_names.get(camera_id), "count": count,
                       "last_observed_at": last} for camera_id, count, last in rows),
                     key=lambda camera: camera["last_observed_at"], reverse=True)
    return {"last": _last_seen(herd.last_observation.get(animal_id), herd.camera_names),
            "count": sum(camera["count"] for camera in cameras), "cameras": cameras}


def _reference(reference: AnimalReference) -> dict:
    return {**_columns(reference),
            "media_url": signed_url(reference.media_id) if reference.media_id else None,
            "crop_url": signed_url(reference.crop_media_id) if reference.crop_media_id else None}


def _pending_action(action: AgentAction, names: dict[str, str]) -> dict:
    return {**_columns(action), "amount_minor": action_amount(action.payload or {}),
            "currency": (action.payload or {}).get("currency"),
            "proposed_by": actor_ref(action.proposed_by_type, action.proposed_by_id, names)}


def build_passport(session: Session, farm_id: str, animal_id: str) -> dict:
    animal = session.get(Animal, animal_id)
    if animal is None or animal.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Animal not found.", {"animal_id": animal_id})
    herd = _load_herd(session, farm_id, [animal_id])
    names = user_names(session, farm_id)

    def scoped(model, *order):
        return session.scalars(select(model).where(model.farm_id == farm_id, model.animal_id == animal_id)
                               .order_by(*order)).all()

    references = session.scalars(select(AnimalReference).where(AnimalReference.animal_id == animal_id)
                                 .order_by(AnimalReference.created_at, AnimalReference.view)).all()
    return {
        "animal": {**_card(animal, herd), "birth_date": animal.birth_date,
                   "ownership_doc_refs": list(animal.ownership_doc_refs or []),
                   "confirmed_by": names.get(animal.confirmed_by, animal.confirmed_by),
                   "confirmed_at": animal.confirmed_at, "enrollment_id": animal.enrollment_id},
        "references": [_reference(reference) for reference in references],
        "estimates": [_columns(estimate) for estimate in herd.estimates[animal_id]],
        "valuations": [{**_columns(v), "confirmed_by": names.get(v.confirmed_by, v.confirmed_by)}
                       for v in herd.valuations[animal_id]],
        "policies": [{**_columns(p), "product_name": product_name(p.product_id)} for p in herd.policies[animal_id]],
        "applications": [{**_columns(a), "product_name": product_name(a.product_id)}
                         for a in scoped(PolicyApplication, PolicyApplication.created_at.desc())],
        "observations": _observations(session, farm_id, animal_id, herd),
        "alerts": [_columns(alert) for alert in herd.alerts[animal_id]],
        "incidents": [_columns(i) for i in scoped(Incident, Incident.occurred_at.desc(), Incident.id)],
        "claims": [_columns(c) for c in scoped(Claim, Claim.created_at.desc(), Claim.id)],
        "pending_actions": [_pending_action(action, names)
                            for action in awaiting_actions(session, farm_id, animal_id)],
        "passbook": {"lines": build_passbook(session, farm_id, animal_id),
                     "summary": exposure_summary(session, farm_id, animal_id)},
    }
