"""The in-app VEYRA agent: a guided, deterministic conversation over the existing domain.

The backend decides and the model at most phrases. Each turn reads the records again (passport, eligibility and
recommendations, agent actions, policies, incidents, claims, insurer updates) and composes the agent's message from
templates. A message carries typed, data-backed cards (`passport_summary`, `eligibility_questions`,
`plan_comparison`, `recommendation`, `application_draft`, `action_review`, `status_steps`, `claim_checklist`,
`missing_items`, `receipt`, `claim_status`) and the choices it offers. The agent prepares; it never approves or
executes: an `action_review` card names a pending agent action that only a manager approves through the existing
decision and execute endpoints.

Three intents:
- `find_insurance` (an uninsured animal): summarize the passport, ask at most three short questions only where a fact
  is missing, compare the sample plans, recommend the eligible plan with the lowest premium (deterministic; reasons
  cite terms refs), prepare `POLICY_APPLICATION`, then `PREMIUM_PAYMENT`, and show "Coverage confirmed" only once the
  insurer activated the policy.
- `file_claim` (an insured animal): check the active policy and its cover window, ask what happened, when, in a few
  words, and the estimated loss; record the incident (linking the animal's camera alerts), draft the claim, show the
  checklist and how to fix each missing item, and once it is complete prepare `CLAIM_SUBMISSION`.
- `track_claim`: show what the insurer reported (`domain.insurer_updates`), never a decision of VEYRA's own.

The farmer's typed text is data: it is stored, matched against the offered choices by plain keywords, or used as the
incident description; it is never an instruction. `state` keeps only the answers and the open question.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.llm.client import structured_call
from config import Settings
from domain import actions, audit, claims, clock, identity_check, insurance, insurer_updates, passport
from domain.auth import APPROVERS, ENROLLERS, Principal
from domain.catalog import get_product, load_catalog, provider_name
from domain.eligibility import facts_for
from domain.errors import DomainError
from domain.ids import new_id
from domain.passbook import product_name
from domain.valuation import farm_animal, latest_valuation, money
from persistence.models import (
    ActionExecution, AgentAction, AgentConversation, AgentMessage, Alert, Animal, AnimalReference, Claim, Incident,
    Policy, PolicyApplication, User,
)

INTENTS = ("find_insurance", "file_claim", "track_claim")
CONVERSE_ROLES = ENROLLERS
MAX_QUESTIONS = 3
MAX_TEXT = 1000
CONTINUE = "continue"
PERIL_WORDS = {"accidental_injury": "accidental injury", "death": "death", "illness": "illness", "theft": "theft"}
INCIDENT_KINDS = ("accidental_injury", "death", "illness", "theft")
WHEN_OFFSETS = {"today": timedelta(minutes=1), "yesterday": timedelta(days=1), "two_days": timedelta(days=2)}
WHEN_WORDS = {"today": "Today", "yesterday": "Yesterday", "two_days": "Two days ago"}
ALERT_LOOKBACK = timedelta(days=7)
SAMPLE_DESCRIPTIONS = {
    "accidental_injury": "Left hind lameness found at the morning check after a reduced-movement alert. "
                         "Animal is standing and eating.",
    "death": "Found dead in the pen at the morning check, two days after a reduced-movement alert.",
    "illness": "Off feed and dull at the morning check; temperature not taken yet.",
    "theft": "Missing from the pen at the morning count; the gate was found open.",
}
SAMPLE_INJURY_LOSS = 60000
STATUS_WORDS = insurer_updates.STATUS_WORDS
_CLOSED_ACTIONS = ("declined", "cancelled", "expired")


# Turns ---------------------------------------------------------------------------------------------------------

@dataclass
class Turn:
    """One agent message before it is stored: template text, cards, choices, and the words a rephrase must keep."""

    text: str
    cards: list[dict] = field(default_factory=list)
    choices: list[dict] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)


def card(type_: str, **data) -> dict:
    return {"type": type_, "data": _jsonable(data)}


def choice(key: str, label: str, value: str | None = None, *, style: str = "secondary",
           href: str | None = None) -> dict:
    return {"key": key, "value": value, "label": label, "style": style, "href": href}


def link(label: str, href: str, style: str = "link") -> dict:
    return choice("link", label, None, style=style, href=href)


def _jsonable(value):
    if isinstance(value, datetime):
        return clock.isoformat(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def usd(minor: int | None, currency: str = "USD") -> str:
    return f"{money(minor)} {currency}"


def _agent_href(animal_id: str, intent: str) -> str:
    return f"/agent?animal={animal_id}&intent={intent}"


# Reads ---------------------------------------------------------------------------------------------------------

def farm_conversation(session: Session, farm_id: str, conversation_id: str) -> AgentConversation:
    conversation = session.get(AgentConversation, conversation_id)
    if conversation is None or conversation.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Conversation not found.", {"conversation_id": conversation_id})
    return conversation


def _messages(session: Session, conversation_id: str) -> list[AgentMessage]:
    return list(session.scalars(select(AgentMessage).where(AgentMessage.conversation_id == conversation_id)
                                .order_by(AgentMessage.seq)))


def _latest_agent_message(session: Session, conversation_id: str) -> AgentMessage | None:
    return session.scalar(select(AgentMessage).where(AgentMessage.conversation_id == conversation_id,
                                                     AgentMessage.role == "agent")
                          .order_by(AgentMessage.seq.desc()).limit(1))


def _coverage(session: Session, farm_id: str, animal: Animal) -> dict:
    card_ = passport._card(animal, passport._load_herd(session, farm_id, [animal.id]))
    coverage = dict(card_["coverage"])
    coverage["product_name"] = product_name(coverage.get("product_id"))
    return {"card": card_, "coverage": coverage}


COVERAGE_LABELS = {"active": "Coverage active", "pending": "Cover pending", "none": "Not insured"}


def conversation_view(session: Session, conversation: AgentConversation) -> dict:
    animal = session.get(Animal, conversation.animal_id)
    coverage = _coverage(session, conversation.farm_id, animal)["coverage"]
    return {
        "id": conversation.id, "intent": conversation.intent, "animal_id": animal.id,
        "animal": {"id": animal.id, "name": animal.name, "breed": animal.breed,
                   "identity_status": animal.identity_status, "coverage_status": coverage["status"],
                   "coverage_label": COVERAGE_LABELS[coverage["status"]],
                   "product_name": coverage.get("product_name"), "policy_id": coverage.get("policy_id")},
        "created_by": conversation.created_by, "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [{"id": m.id, "seq": m.seq, "role": m.role, "text": m.text, "cards": list(m.cards or []),
                      "choices": list(m.choices or []), "source": m.source, "created_at": m.created_at}
                     for m in _messages(session, conversation.id)],
    }


def _latest_action(session: Session, farm_id: str, action_type: str, subject_type: str,
                   subject_id: str) -> AgentAction | None:
    return session.scalar(select(AgentAction).where(
        AgentAction.farm_id == farm_id, AgentAction.action_type == action_type,
        AgentAction.subject_type == subject_type, AgentAction.subject_id == subject_id)
        .order_by(AgentAction.created_at.desc(), AgentAction.version.desc()).limit(1))


def _execution(session: Session, action: AgentAction | None) -> ActionExecution | None:
    if action is None:
        return None
    return session.scalar(select(ActionExecution).where(ActionExecution.action_id == action.id))


def _status(action: AgentAction | None) -> str | None:
    return actions.effective_status(action) if action is not None else None


def _vet_name(session: Session, farm_id: str) -> str | None:
    return session.scalar(select(User.name).where(User.farm_id == farm_id, User.role == "vet").limit(1))


# Passport summary ----------------------------------------------------------------------------------------------

def _range_text(estimate: dict | None, unit: str) -> str | None:
    if not estimate or estimate.get("range_low") is None:
        return None
    low, high = estimate["range_low"], estimate["range_high"]
    fmt = lambda v: str(int(v)) if float(v).is_integer() else f"{v:g}"  # noqa: E731
    return f"{fmt(low)}–{fmt(high)} {unit}"


def passport_summary(session: Session, farm_id: str, animal: Animal) -> tuple[dict, dict]:
    read = _coverage(session, farm_id, animal)
    card_, coverage = read["card"], read["coverage"]
    valuation = latest_valuation(session, animal.id)
    names = audit.user_names(session, farm_id)
    policy = session.get(Policy, coverage["policy_id"]) if coverage.get("policy_id") else None
    data = {
        "animal_id": animal.id, "name": animal.name, "breed": animal.breed, "sex": animal.sex,
        "identity_status": animal.identity_status,
        "coverage": {**coverage, "label": COVERAGE_LABELS[coverage["status"]],
                     "effective_date": policy.effective_date if policy else None,
                     "expiry_date": policy.expiry_date if policy else None},
        "age": card_["age"], "weight": card_["weight"],
        "valuation": None if valuation is None else {
            "id": valuation.id, "version": valuation.version, "value_low_minor": valuation.value_low_minor,
            "value_high_minor": valuation.value_high_minor, "currency": valuation.currency,
            "price_date": valuation.price_date, "confirmed_by": names.get(valuation.confirmed_by,
                                                                          valuation.confirmed_by)},
        "ownership_documents": len(animal.ownership_doc_refs or []),
        "open_alerts": card_["alerts"]["open_count"], "last_seen": card_["last_observation"],
        "passport_href": f"/animals/{animal.id}",
    }
    return card("passport_summary", **data), data


def _summary_turn(session: Session, farm_id: str, animal: Animal) -> tuple[Turn, dict]:
    summary_card, data = passport_summary(session, farm_id, animal)
    coverage = data["coverage"]
    parts = [f"I opened {animal.name}'s passport ({animal.id})."]
    if coverage["status"] == "active":
        parts.append(f"{animal.name} is covered by {coverage['product_name']} ({coverage['policy_id']}).")
    elif coverage["status"] == "pending":
        parts.append(f"{animal.name}'s cover is pending: it is not active yet.")
    else:
        parts.append(f"{animal.name} is not insured.")
    if animal.identity_status == "confirmed":
        parts.append("Identity is confirmed.")
    else:
        parts.append(f"Identity is not confirmed ({animal.identity_status.replace('_', ' ')}).")
    valuation = data["valuation"]
    if valuation:
        parts.append(f"The indicative value is {money(valuation['value_low_minor'])}–"
                     f"{usd(valuation['value_high_minor'], valuation['currency'])} (valuation v{valuation['version']}, "
                     f"an estimate, not an insurer-agreed value).")
    else:
        parts.append("No valuation is confirmed yet.")
    return Turn(" ".join(parts), [summary_card], keep=[animal.name]), data


# Find insurance ------------------------------------------------------------------------------------------------

def insurance_phase(session: Session, farm_id: str, animal: Animal) -> tuple[str, dict]:
    """Where the animal's cover stands, read from its policies and agent actions."""
    policies = list(session.scalars(select(Policy).where(Policy.farm_id == farm_id, Policy.animal_id == animal.id)
                                    .order_by(Policy.created_at.desc(), Policy.id)))
    active = next((p for p in policies if p.status == "active"), None)
    if active is not None:
        return "covered", {"policy": active}
    pending = next((p for p in policies if p.status in passport.PENDING_POLICY_STATUSES), None)
    if pending is not None:
        if pending.status == "paid_pending_activation":
            return "awaiting_insurer", {"policy": pending}
        payment = _latest_action(session, farm_id, "PREMIUM_PAYMENT", "policy_application", pending.application_id)
        status = _status(payment)
        if status in ("pending_approval", "approved"):
            return "payment_review", {"policy": pending, "action": payment}
        if status in ("executing", "unknown"):
            return "payment_in_flight", {"policy": pending, "action": payment}
        return "payment_needed", {"policy": pending, "action": payment}
    application = _latest_action(session, farm_id, "POLICY_APPLICATION", "animal", animal.id)
    status = _status(application)
    if status in ("pending_approval", "approved"):
        return "application_review", {"action": application}
    if status in ("executing", "unknown"):
        return "application_in_flight", {"action": application}
    if status == "failed":
        return "application_failed", {"action": application}
    return "shopping", {"action": application}


def _questions(session: Session, animal: Animal, answers: dict) -> list[dict]:
    """The short questions worth asking: only where a fact the sample terms read is missing."""
    facts = facts_for(session, animal)
    questions = []
    if facts["ownership_document"] is None:
        questions.append({"id": "ownership_document", "text": f"Do you hold an ownership document for {animal.name}?",
                          "why": "Mortality + Theft needs one on file.", "terms_ref": "sample-v1 §2.4"})
    if animal.breed_category == "dairy":
        questions.append({"id": "vet_check", "text": f"Has a vet checked {animal.name} in the last 30 days?",
                          "why": "Dairy Health Plus needs a recent veterinary health check.",
                          "terms_ref": "sample-v1 §2.7"})
    return [q | {"answer": answers.get(q["id"])} for q in questions[:MAX_QUESTIONS]]


def _question_turn(animal: Animal, questions: list[dict], index: int) -> Turn:
    question = questions[index]
    lead = "One question before I compare plans:" if len(questions) == 1 else \
        f"Question {index + 1} of {len(questions)} before I compare plans:"
    return Turn(f"{lead} {question['text'][0].lower()}{question['text'][1:]}",
                [card("eligibility_questions", questions=questions, current=question["id"])],
                [choice(question["id"], "Yes", "yes", style="primary"), choice(question["id"], "No", "no")],
                keep=[animal.name])


def _answer_turn(animal: Animal, question_id: str, answer: str) -> Turn:
    if question_id == "ownership_document":
        if answer == "yes":
            return Turn(f"Mortality + Theft needs that document on file before it can be offered (sample-v1 §2.4). "
                        f"Add it in {animal.name}'s passport documents; until it is there, I show Mortality + Theft "
                        f"as needing review.",
                        choices=[link(f"Open {animal.name}'s documents", f"/animals/{animal.id}#documents")],
                        keep=[animal.name])
        return Turn("Then theft cover isn't available yet: Mortality + Theft needs an ownership document on file "
                    "(sample-v1 §2.4).", keep=[animal.name])
    if answer == "yes":
        return Turn(f"VEYRA has no veterinary health-check record for {animal.name} yet, so Dairy Health Plus stays "
                    f"under review until the vet records one (sample-v1 §2.7).", keep=[animal.name])
    return Turn("Dairy Health Plus needs a veterinary health check within the last 30 days (sample-v1 §2.7), so it "
                "stays under review until one is recorded.", keep=[animal.name])


def rank(results: list[dict]) -> list[dict]:
    """Eligible priced plans, lowest premium-to-cover first; ties keep the catalog order."""
    eligible = [(i, r) for i, r in enumerate(results) if r["outcome"] == "eligible" and r["premium_minor"] is not None]
    return [r for _, r in sorted(eligible, key=lambda pair: (pair[1]["premium_minor"], pair[0]))]


def _rate_text(product: dict) -> str:
    bps = product["premium"]["rate_bps"]
    return f"{Decimal(bps) / Decimal(100):.2f}%"


def recommendation_card(results: list[dict], best: dict, insured: int, currency: str) -> dict:
    catalog = load_catalog()
    product = get_product(catalog, best["product_id"])
    reasons = [{"text": "Eligible under the sample terms: every rule passes.", "terms_ref": None}]
    reasons += [{"text": r["text"], "terms_ref": r["terms_ref"]} for r in best["reasons"] if r["status"] == "pass"]
    others = [r for r in results if r["product_id"] != best["product_id"]]
    not_eligible = [r for r in others if r["outcome"] != "eligible"]
    reasons.append({"text": f"Premium {usd(best['premium_minor'], currency)} a year: {_rate_text(product)} of the "
                            f"insured value {usd(insured, currency)}.", "terms_ref": product["premium"]["terms_ref"]})
    reasons.append({"text": f"Deductible {usd(best['deductible_minor'], currency)}.",
                    "terms_ref": product["deductible"]["terms_ref"]})
    tradeoffs = []
    for other in not_eligible:
        extra = [PERIL_WORDS.get(p, p) for p in other["covered_perils"] if p not in best["covered_perils"]]
        if not extra:
            continue
        if other["outcome"] == "unknown":
            why = "needs review: " + "; ".join(other["needs_review"]).lower()
            ref = next((r["terms_ref"] for r in other["reasons"] if r["status"] == "unknown"), None)
        else:
            failing = next((r for r in other["reasons"] if r["status"] == "fail"), None)
            why = f"not eligible: {failing['text'].rstrip('.').lower()}" if failing else "not eligible"
            ref = failing["terms_ref"] if failing else None
        tradeoffs.append({"text": f"Does not cover {', '.join(extra)}. {other['product_name']} would, but it "
                                  f"{why}.", "terms_ref": ref})
    excluded = [{"text": e["text"], "terms_ref": e["terms_ref"]} for e in product["exclusions"]]
    return card("recommendation", product_id=best["product_id"], product_name=best["product_name"],
                premium_minor=best["premium_minor"], deductible_minor=best["deductible_minor"],
                insured_value_minor=insured, currency=currency, covered_perils=list(best["covered_perils"]),
                reasons=reasons, tradeoffs=tradeoffs, exclusions=excluded,
                rule="Eligible plans first, then the lowest premium for the same cover.")


def _comparison_turns(session: Session, principal: Principal, animal: Animal, state: dict) -> list[Turn]:
    rec = insurance.recommend(session, principal.farm_id, animal.id)
    results, insured, currency = rec["results"], rec["insured_value_minor"], rec["currency"]
    catalog = load_catalog()
    insurer = provider_name(catalog, catalog["provider"]["id"])
    counts = {o: sum(r["outcome"] == o for r in results) for o in ("eligible", "unknown", "ineligible")}
    review = "needs" if counts["unknown"] == 1 else "need"
    text = (f"I checked {animal.name} against the {len(results)} sample plans from {insurer}: {counts['eligible']} "
            f"eligible, {counts['unknown']} {review} review, {counts['ineligible']} not eligible.")
    if insured is not None:
        text += (f" Cover is written up to the lower bound of the indicative value, {usd(insured, currency)} "
                 f"(sample-v1 §1.2).")
    comparison = card("plan_comparison", results=[{k: v for k, v in r.items()} for r in results],
                      insured_value_minor=insured, currency=currency, catalog_version=rec["catalog_version"],
                      provider=insurer, note="Fictional sample terms for the demo, not market quotes.")
    turns = [Turn(text, [comparison], keep=[animal.name, insurer])]
    ranked = rank(results)
    if not ranked or insured is None:
        review_items = sorted({item for r in results for item in r["needs_review"]})
        turns.append(Turn(f"None of the sample plans is eligible for {animal.name} yet. What needs review: "
                          f"{'; '.join(review_items) or 'see the comparison'}.",
                          choices=[choice(CONTINUE, "Check again", style="primary"),
                                   link(f"Open {animal.name}'s passport", f"/animals/{animal.id}")],
                          keep=[animal.name]))
        state["awaiting"] = None
        return turns
    best = ranked[0]
    lead = "the only eligible plan" if len(ranked) == 1 else "the eligible plan with the lowest premium"
    turns.append(Turn(f"I recommend {best['product_name']} for {animal.name}: it is {lead}, "
                      f"{usd(best['premium_minor'], currency)} a year for {usd(insured, currency)} of cover, with a "
                      f"{usd(best['deductible_minor'], currency)} deductible. The reasons cite the sample terms.",
                      [recommendation_card(results, best, insured, currency)],
                      [choice("prepare_application", "Prepare application", best["product_id"], style="primary"),
                       choice("not_now", "Not now")],
                      keep=[animal.name, best["product_name"]]))
    state["awaiting"] = "plan_decision"
    state["product_id"] = best["product_id"]
    return turns


def _shopping_turns(session: Session, principal: Principal, animal: Animal, state: dict) -> list[Turn]:
    """The questions still open, then the comparison and the recommendation."""
    if animal.identity_status != "confirmed":
        state["awaiting"] = None
        return [Turn(f"Insurance can be prepared only for an animal with a confirmed identity. Confirm "
                     f"{animal.name}'s identity first.",
                     choices=[link(f"Open {animal.name}'s passport", f"/animals/{animal.id}", style="primary")],
                     keep=[animal.name])]
    if latest_valuation(session, animal.id) is None:
        state["awaiting"] = None
        return [Turn(f"Every sample plan needs a manager-confirmed valuation (sample-v1 §2.3), and {animal.name} has "
                     f"none yet. Confirm the valuation in the passport, then check again.",
                     choices=[link("Confirm the valuation", f"/animals/{animal.id}#valuation", style="primary"),
                              choice(CONTINUE, "I've confirmed it, check again")],
                     keep=[animal.name])]
    questions = _questions(session, animal, state.setdefault("answers", {}))
    open_index = next((i for i, q in enumerate(questions) if q["answer"] is None), None)
    if open_index is not None:
        state["awaiting"] = questions[open_index]["id"]
        return [_question_turn(animal, questions, open_index)]
    return _comparison_turns(session, principal, animal, state)


def _manifest_items(session: Session, action: AgentAction) -> list[dict]:
    view = actions.action_view(session, action)
    return (view.get("evidence_manifest") or {}).get("items", [])


def application_draft_card(session: Session, animal: Animal, action: AgentAction) -> dict:
    p = action.payload
    summary = passport._card(animal, passport._load_herd(session, animal.farm_id, [animal.id]))
    valuation = latest_valuation(session, animal.id)
    muzzle = session.scalar(select(AnimalReference.id).where(AnimalReference.animal_id == animal.id,
                                                             AnimalReference.view == "muzzle").limit(1))
    currency = p["currency"]
    fields = [
        {"label": "Animal", "value": f"{animal.name} · {animal.id}", "source": "Passport"},
        {"label": "Breed and sex", "value": f"{animal.breed} · {animal.sex}", "source": "Passport"},
        {"label": "Age", "value": _range_text(summary["age"], "months") or "Not on record",
         "source": "Passport estimate"},
        {"label": "Weight", "value": _range_text(summary["weight"], "kg") or "Not on record",
         "source": "Passport estimate"},
        {"label": "Indicative value", "value": (f"{money(valuation.value_low_minor)}–"
                                                f"{usd(valuation.value_high_minor, valuation.currency)}"
                                                if valuation else "Not on record"),
         "source": f"Valuation v{valuation.version}" if valuation else "Passport"},
        {"label": "Identity reference", "value": muzzle or "Not on record", "source": "Passport muzzle reference"},
        {"label": "Plan", "value": product_name(p["product_id"]), "source": p["terms_version"]},
        {"label": "Insured value", "value": usd(p["insured_value_minor"], currency), "source": "sample-v1 §1.2"},
        {"label": "Premium a year", "value": usd(p["premium_minor"], currency), "source": "sample-v1 §3.1"},
        {"label": "Deductible", "value": usd(p["deductible_minor"], currency), "source": "sample-v1 §3.2"},
        {"label": "Cover", "value": f"{p['coverage_start']} to {p['coverage_end']}",
         "source": "Starts once the insurer confirms (sandbox)"},
    ]
    return card("application_draft", action_id=action.id, product_id=p["product_id"],
                product_name=product_name(p["product_id"]), fields=fields,
                evidence=_manifest_items(session, action), disclosed_fields=list(p.get("disclosed_fields") or []),
                recipient=provider_name(load_catalog(), p["provider_id"]))


def action_card(action: AgentAction) -> dict:
    return card("action_review", action_id=action.id, action_type=action.action_type, status=_status(action),
                version=action.version)


def _approver_note(principal: Principal) -> str:
    return "" if principal.role in APPROVERS else " You can prepare it; approval needs a manager."


def _propose(session: Session, principal: Principal, refs: dict, rationale: str) -> tuple[AgentAction | None,
                                                                                            DomainError | None]:
    """Prepare an agent action inside a savepoint: a refusal rolls back only this attempt (a blocked claim keeps
    its recorded reason, as the actions route does)."""
    savepoint = session.begin_nested()
    try:
        action = actions.propose(session, principal, refs, rationale)
    except actions.CommitThenRaise as blocked:
        savepoint.commit()
        return None, blocked.error
    except DomainError as error:
        savepoint.rollback()
        return None, error
    savepoint.commit()
    return action, None


def _prepare_application(session: Session, principal: Principal, animal: Animal, product_id: str,
                         state: dict) -> list[Turn]:
    name = product_name(product_id)
    action, error = _propose(session, principal, {"action_type": "POLICY_APPLICATION", "animal_id": animal.id,
                                                  "product_id": product_id},
                             f"Recommended by the VEYRA agent: {name} is the eligible plan with the lowest premium "
                             f"for {animal.name} under the sample terms.")
    state["awaiting"] = None
    if error is not None:
        return [Turn(f"I couldn't prepare the application: {error.message}",
                     choices=[choice(CONTINUE, "Check again", style="primary")], keep=[animal.name])]
    insurer = provider_name(load_catalog(), action.payload["provider_id"])
    return [Turn(f"I prepared the application to {insurer} for {name} and filled it from {animal.name}'s passport. "
                 f"Check the details and the evidence: nothing is sent until a manager approves it."
                 f"{_approver_note(principal)}",
                 [application_draft_card(session, animal, action), action_card(action)],
                 [choice(CONTINUE, "Check status")], keep=[animal.name, name, insurer])]


def _prepare_payment(session: Session, principal: Principal, animal: Animal, policy: Policy) -> list[Turn]:
    action, error = _propose(session, principal, {"action_type": "PREMIUM_PAYMENT",
                                                  "policy_application_id": policy.application_id},
                             f"Premium for {product_name(policy.product_id)} on {animal.name}, as accepted by the "
                             f"insurer.")
    if error is not None:
        return [Turn(f"I couldn't prepare the premium payment: {error.message}",
                     choices=[choice(CONTINUE, "Check again", style="primary")], keep=[animal.name])]
    return [Turn(f"I prepared the premium payment of {usd(policy.premium_minor, policy.currency)} from the sandbox "
                 f"wallet. No real money moves. Cover starts only when the insurer confirms it after payment."
                 f"{_approver_note(principal)}",
                 [action_card(action)], [choice(CONTINUE, "Check status")], keep=[animal.name])]


def status_steps_card(session: Session, farm_id: str, policy: Policy) -> dict:
    """Submitted → Payment recorded (sandbox) → Coverage confirmed by insurer, each read from its own record."""
    insurer = provider_name(load_catalog(), policy.provider_id)
    application = session.get(PolicyApplication, policy.application_id) if policy.application_id else None
    app_action = _latest_action(session, farm_id, "POLICY_APPLICATION", "animal", policy.animal_id)
    app_exec = _execution(session, app_action) if app_action and app_action.status == "succeeded" else None
    receipt = (app_exec.provider_receipt or {}) if app_exec else {}
    steps = [{"key": "submitted", "label": "Application submitted", "state": "done" if application else "waiting",
              "detail": (f"Accepted by {insurer} · {application.provider_ref}" if application else
                         "Not submitted"), "at": receipt.get("accepted_at") or (application.created_at
                                                                                 if application else None)}]
    payment = _latest_action(session, farm_id, "PREMIUM_PAYMENT", "policy_application",
                             policy.application_id) if policy.application_id else None
    pay_status, pay_exec = _status(payment), _execution(session, payment)
    pay_receipt = (pay_exec.provider_receipt or {}) if pay_exec and pay_exec.status == "succeeded" else {}
    paid = policy.status in ("paid_pending_activation", "active") and bool(pay_receipt)
    if paid:
        pay_state, pay_detail = "done", (f"{usd(pay_receipt.get('amount_minor'), pay_receipt.get('currency', 'USD'))}"
                                         f" · {pay_receipt.get('payment_ref')}")
    elif pay_status == "failed":
        pay_state, pay_detail = "failed", ((pay_exec.error or {}).get("message") if pay_exec else None) or \
            "The sandbox payment did not go through"
    elif pay_status in ("pending_approval", "approved", "executing", "unknown"):
        pay_state, pay_detail = "current", {"pending_approval": "Waiting for a manager's approval",
                                            "approved": "Approved, sending", "executing": "Sending",
                                            "unknown": "Outcome unknown; reconcile in Approvals"}[pay_status]
    elif policy.status == "active" and not policy.application_id:
        pay_state, pay_detail = "done", "Paid before VEYRA (seeded history)"
    else:
        pay_state = "current" if policy.status == "awaiting_payment" else "waiting"
        pay_detail = f"{usd(policy.premium_minor, policy.currency)} due"
    steps.append({"key": "payment", "label": "Payment recorded (sandbox)", "state": pay_state, "detail": pay_detail,
                  "at": pay_receipt.get("charged_at")})
    activation = policy.activation_receipt or {}
    if policy.status == "active":
        cov_state = "done"
        cov_detail = f"{insurer} · effective {policy.effective_date} to {policy.expiry_date}"
        if activation.get("confirmation_ref"):
            cov_detail += f" · {activation['confirmation_ref']}"
    elif policy.status == "paid_pending_activation":
        cov_state, cov_detail = "current", f"Waiting for {insurer} to confirm"
    else:
        cov_state, cov_detail = "waiting", "After payment, the insurer confirms cover"
    steps.append({"key": "coverage", "label": "Coverage confirmed by insurer", "state": cov_state,
                  "detail": cov_detail, "at": None})
    if not policy.application_id:
        steps[0] = {**steps[0], "state": "done", "detail": "Issued before VEYRA (seeded history)"}
    return card("status_steps", policy_id=policy.id, policy_status=policy.status, steps=steps, provider=insurer)


def _insurance_status_turns(session: Session, principal: Principal, animal: Animal, phase: str, ctx: dict,
                            state: dict, note: str | None = None) -> list[Turn]:
    keep = [animal.name]
    action = ctx.get("action")
    policy = ctx.get("policy")
    if phase == "application_review":
        state["awaiting"] = None
        return [Turn(f"The application is waiting for a manager's approval.{_approver_note(principal)}",
                     [action_card(action)], [choice(CONTINUE, "Check status")], keep=keep)]
    if phase == "application_in_flight":
        return [Turn("The application is with the insurer and its outcome isn't confirmed yet.", [action_card(action)],
                     [choice(CONTINUE, "Check status", style="primary")], keep=keep)]
    if phase == "application_failed":
        execution = _execution(session, action)
        reason = (execution.error or {}).get("message") if execution and execution.error else "it was declined"
        product_id = action.payload.get("product_id")
        return [Turn(f"The insurer didn't accept the application: {reason} Nothing was charged.",
                     [action_card(action)],
                     [choice("prepare_application", "Prepare it again", product_id, style="primary")], keep=keep)]
    insurer = provider_name(load_catalog(), policy.provider_id)
    steps = status_steps_card(session, principal.farm_id, policy)
    if phase == "payment_needed":
        application = session.get(PolicyApplication, policy.application_id)
        prior = _status(action)
        text = (f"{insurer} accepted the application ({application.provider_ref}). The premium of "
                f"{usd(policy.premium_minor, policy.currency)} is due before cover can start.")
        if prior in _CLOSED_ACTIONS or prior == "failed":
            text += f" The last payment was {prior}; nothing was charged."
        state["awaiting"] = None
        return [Turn(text, [steps], [choice("prepare_payment", "Prepare premium payment", policy.id,
                                            style="primary")], keep=keep + [insurer])]
    if phase == "payment_review":
        return [Turn(f"The premium payment is waiting for a manager's approval. It comes from the sandbox wallet."
                     f"{_approver_note(principal)}", [steps, action_card(action)],
                     [choice(CONTINUE, "Check status")], keep=keep)]
    if phase == "payment_in_flight":
        return [Turn("The premium payment was sent and its outcome isn't confirmed yet.", [steps, action_card(action)],
                     [choice(CONTINUE, "Check status", style="primary")], keep=keep)]
    if phase == "awaiting_insurer":
        pay_exec = _execution(session, _latest_action(session, principal.farm_id, "PREMIUM_PAYMENT",
                                                      "policy_application", policy.application_id))
        ref = (pay_exec.provider_receipt or {}).get("payment_ref") if pay_exec else None
        text = (f"Payment recorded (sandbox{', ' + ref if ref else ''}). {insurer} hasn't confirmed the cover yet, "
                f"so {animal.name} is not covered until it does.")
        if note:
            text += f" {note}"
        options = ([choice("activation_check", f"Ask {insurer} again", policy.id, style="primary")]
                   if principal.role in APPROVERS else [choice(CONTINUE, "Check again", style="primary")])
        if principal.role not in APPROVERS:
            text += " A manager can ask the insurer again."
        return [Turn(text, [steps], options, keep=keep + [insurer])]
    # covered
    state["awaiting"] = None
    activation = policy.activation_receipt or {}
    name = product_name(policy.product_id)
    if policy.application_id:
        text = (f"Coverage confirmed by {insurer} · effective {policy.effective_date} to {policy.expiry_date}"
                f"{' (' + activation['confirmation_ref'] + ')' if activation.get('confirmation_ref') else ''}. "
                f"{animal.name} is covered under {name}.")
    else:
        text = (f"{animal.name} already has active cover under {name} ({policy.id}), effective "
                f"{policy.effective_date} to {policy.expiry_date}. There is nothing to buy.")
    receipt = card("receipt", kind="policy_activation", title="Coverage confirmed by insurer", provider=insurer,
                   reference=activation.get("confirmation_ref"), policy_id=policy.id, product_name=name,
                   effective_date=policy.effective_date, expiry_date=policy.expiry_date,
                   insured_value_minor=policy.insured_value_minor, currency=policy.currency,
                   source=activation.get("source") or "sandbox")
    return [Turn(text, [steps, receipt],
                 [link(f"Open {animal.name}'s passport", f"/animals/{animal.id}", style="secondary"),
                  link("Help with a claim", _agent_href(animal.id, "file_claim"))], keep=keep + [insurer, name])]


def _find_insurance(session: Session, principal: Principal, animal: Animal, state: dict, picked: dict | None,
                    note: str | None) -> list[Turn]:
    phase, ctx = insurance_phase(session, principal.farm_id, animal)
    key = picked["key"] if picked else CONTINUE
    value = picked.get("value") if picked else None
    if key in ("ownership_document", "vet_check") and phase == "shopping":
        state.setdefault("answers", {})[key] = value
        return [_answer_turn(animal, key, value), *_shopping_turns(session, principal, animal, state)]
    if key == "prepare_application" and phase in ("shopping", "application_failed"):
        return _prepare_application(session, principal, animal, value, state)
    if key == "not_now" and phase == "shopping":
        state["awaiting"] = None
        return [Turn(f"OK. Nothing was prepared or sent. The plans stay here when you're ready.",
                     choices=[choice(CONTINUE, "Show the plans again"),
                              link(f"Open {animal.name}'s passport", f"/animals/{animal.id}")], keep=[animal.name])]
    if key == "prepare_payment" and phase == "payment_needed":
        return _prepare_payment(session, principal, animal, ctx["policy"])
    if phase == "shopping":
        return _shopping_turns(session, principal, animal, state)
    return _insurance_status_turns(session, principal, animal, phase, ctx, state, note)


# File a claim --------------------------------------------------------------------------------------------------

def _claim_policy(session: Session, farm_id: str, animal: Animal) -> tuple[Policy | None, dict | None]:
    policy = actions.active_policy(session, farm_id, animal.id)
    return (policy, get_product(load_catalog(), policy.product_id)) if policy else (None, None)


def _link_alerts(session: Session, principal: Principal, incident: Incident) -> list[str]:
    """Attach the animal's camera alerts from the week before the incident (camera evidence), once each."""
    since = incident.occurred_at - ALERT_LOOKBACK
    found = [a.id for a in session.scalars(select(Alert).where(
        Alert.farm_id == incident.farm_id, Alert.animal_id == incident.animal_id, Alert.window_end >= since)
        .order_by(Alert.window_end.desc(), Alert.id).limit(3))]
    new = [alert_id for alert_id in found if alert_id not in (incident.linked_alert_ids or [])]
    if new:
        incident.linked_alert_ids = [*(incident.linked_alert_ids or []), *new]
        audit.record(session, farm_id=incident.farm_id, actor_type="agent", actor_id=principal.user_id,
                     event_type="incident.alerts_linked", subject_type="incident", subject_id=incident.id,
                     animal_id=incident.animal_id, data={"incident_id": incident.id, "alert_ids": new})
    return new


def _fixes(session: Session, principal: Principal, animal: Animal, claim: Claim, missing: list[str]) -> list[dict]:
    vet = _vet_name(session, principal.farm_id) or "your vet"
    href = f"/claims/{claim.id}"
    fixes = {
        "vet_assessment": {"fix": f"Ask {vet} to add the veterinary assessment: the vet signs in and adds it on the "
                                  f"claim. Only a vet can add it.", "href": f"{href}#assessment"},
        "vet_health_record": {"fix": f"Ask {vet} to add a veterinary health record on the claim.",
                              "href": f"{href}#assessment"},
        "farmer_declaration": {"fix": "The manager confirms the farmer declaration: that the facts are true." if
                               principal.role in APPROVERS else
                               "A manager confirms the farmer declaration: that the facts are true.",
                               "choice": choice("confirm_declaration", "Confirm the declaration", claim.id,
                                                style="primary") if principal.role in APPROVERS else None},
        "identity_verified": {"fix": f"Re-scan {animal.name}'s muzzle so the claim is checked against the enrolled "
                                     f"animal. Use the claim page to scan, or the sample re-scan for the demo.",
                              "href": f"{href}#verify-identity",
                              "choice": choice("sample_rescan", "Use the sample re-scan (demo)", claim.id)},
        "observation_evidence": {"fix": f"No camera alert is linked. Review {animal.name}'s footage in Monitor; when a "
                                        f"camera alert is recorded for {animal.name}, check again and I'll link it.",
                                 "href": "/monitor"},
        "ownership_document": {"fix": f"Add the ownership document in {animal.name}'s passport documents.",
                               "href": f"/animals/{animal.id}#documents"},
    }
    items = []
    for key in missing:
        fix = fixes.get(key, {"fix": "Add this on the claim page.", "href": href})
        items.append({"key": key, "label": claims.CHECKLIST_LABELS.get(key, key.replace("_", " ")),
                      "fix": fix["fix"], "href": fix.get("href"), "choice": fix.get("choice")})
    return items


def claim_checklist_card(claim_view: dict, incident: Incident | None = None) -> dict:
    return card("claim_checklist", claim_id=claim_view["id"], incident_id=claim_view["incident_id"],
                policy_id=claim_view["policy_id"], status=claim_view["status"],
                claimed_amount_minor=claim_view["claimed_amount_minor"], currency=claim_view["currency"],
                incident_kind=claim_view.get("incident_kind"), items=list(claim_view["checklist"]),
                linked_alert_ids=list(incident.linked_alert_ids or []) if incident else [])


def _claim_turns(session: Session, principal: Principal, animal: Animal, claim: Claim, state: dict,
                 lead: str | None = None, prepare: bool = False) -> list[Turn]:
    """Where an existing claim stands: its checklist and fixes, its submission review, or its receipt."""
    state["awaiting"] = None
    state["claim_id"] = claim.id
    keep = [animal.name]
    incident = session.get(Incident, claim.incident_id)
    if claim.status in claims.OPEN_CLAIM_STATUSES:
        linked = _link_alerts(session, principal, incident)
        claims.refresh(session, claim)
        submission = _latest_action(session, principal.farm_id, "CLAIM_SUBMISSION", "claim", claim.id)
        sub_status = _status(submission)
        view = claims.claim_view(session, claim)
        checklist = claim_checklist_card(view, incident)
        if sub_status in ("pending_approval", "approved", "executing", "unknown"):
            return [Turn(f"The claim submission is waiting for a manager's approval.{_approver_note(principal)}",
                         [checklist, action_card(submission)], [choice(CONTINUE, "Check status")], keep=keep)]
        missing = view["missing"]
        present = [item["label"] for item in view["checklist"] if item["status"] == "present"]
        text = lead or f"Claim {claim.id} is a draft under {claim.policy_id}."
        if linked:
            text += f" I linked camera alert {', '.join(linked)} as observation evidence."
        if missing:
            labels = [claims.CHECKLIST_LABELS.get(k, k) for k in missing]
            text += (f" Attached from the passport and records: {', '.join(present).lower() or 'nothing yet'}. "
                     f"Still missing: {', '.join(labels).lower()}.")
            fixes = _fixes(session, principal, animal, claim, missing)
            options = [f["choice"] for f in fixes if f.get("choice")]
            options += [choice(CONTINUE, "Check again"), link("Open the claim", f"/claims/{claim.id}")]
            return [Turn(text, [checklist, card("missing_items", claim_id=claim.id, items=fixes)], options, keep=keep)]
        if sub_status in (*_CLOSED_ACTIONS, "failed") and not prepare:
            return [Turn(f"{text} Every checklist item is present. The last submission was {sub_status}; nothing was "
                         f"sent to the insurer.", [checklist],
                         [choice("prepare_submission", "Prepare the submission again", claim.id, style="primary")],
                         keep=keep)]
        action, error = _propose(session, principal, {"action_type": "CLAIM_SUBMISSION", "claim_id": claim.id},
                                 f"Claim for {animal.name}: every checklist item is present.")
        if error is not None:
            return [Turn(f"{text} I couldn't prepare the submission: {error.message}", [checklist],
                         [choice(CONTINUE, "Check again", style="primary")], keep=keep)]
        insurer = provider_name(load_catalog(), action.payload["provider_id"])
        return [Turn(f"{text} Every checklist item is present, so I prepared the claim submission to {insurer} for "
                     f"{usd(claim.claimed_amount_minor, claim.currency)} claimed. Nothing is sent until a manager "
                     f"approves it.{_approver_note(principal)}",
                     [checklist, action_card(action)], [choice(CONTINUE, "Check status")], keep=keep + [insurer])]
    return _submitted_turns(session, principal, animal, claim)


def _submitted_turns(session: Session, principal: Principal, animal: Animal, claim: Claim) -> list[Turn]:
    receipt_data = claim.receipt or {}
    policy = session.get(Policy, claim.policy_id)
    insurer = provider_name(load_catalog(), policy.provider_id)
    ref = receipt_data.get("claim_ref")
    receipt = card("receipt", kind="claim_submission", title="Claim received by insurer", provider=insurer,
                   reference=ref, claim_id=claim.id, policy_id=claim.policy_id,
                   claimed_amount_minor=claim.claimed_amount_minor, currency=claim.currency,
                   received_at=receipt_data.get("received_at"), source="sandbox")
    status = claim_status_card(session, claim)
    text = (f"{insurer} received the claim ({ref}). Status: Submitted — Pending assessment. The insurer assesses "
            f"it; its decision, any outstanding paperwork, and payout status show here only when the insurer reports "
            f"them.")
    return [Turn(text, [receipt, status],
                 [link("Track this claim", _agent_href(animal.id, "track_claim"), style="secondary"),
                  link("Open the claim", f"/claims/{claim.id}")], keep=[animal.name, insurer])]


def claim_status_card(session: Session, claim: Claim) -> dict:
    receipt = claim.receipt or {}
    updates = [insurer_updates.update_view(u) for u in insurer_updates.updates_for(session, claim.id)]
    timeline = [{"status": "assessment_pending", "label": STATUS_WORDS["assessment_pending"],
                 "note": receipt.get("claim_ref"), "settlement_minor": None, "disbursement": None,
                 "at": receipt.get("received_at"), "source": "sandbox"}]
    timeline += [{"status": u["status"], "label": u["label"], "note": u["note"],
                  "settlement_minor": u["settlement_minor"], "disbursement": u["disbursement"],
                  "at": u["created_at"], "source": u["source"]} for u in updates]
    latest = updates[-1] if updates else None
    outstanding = [latest["note"]] if latest and latest["status"] == "more_info_requested" and latest["note"] else []
    return card("claim_status", claim_id=claim.id, reference=receipt.get("claim_ref"),
                status=latest["status"] if latest else "assessment_pending",
                label=latest["label"] if latest else STATUS_WORDS["assessment_pending"],
                claimed_amount_minor=claim.claimed_amount_minor, currency=claim.currency, timeline=timeline,
                outstanding=outstanding,
                settlement=({"amount_minor": latest["settlement_minor"], "disbursement": latest["disbursement"],
                             "stated_by": "insurer"} if latest and latest["status"] == "approved" else None))


def _ask_kind(animal: Animal, product: dict, state: dict) -> Turn:
    state["awaiting"] = "incident_kind"
    covered = ", ".join(PERIL_WORDS.get(p, p) for p in product["covered_perils"])
    return Turn(f"What happened to {animal.name}? {product['name']} covers {covered}.",
                choices=[choice("incident_kind", PERIL_WORDS[k].capitalize(), k,
                                style="primary" if k in product["covered_perils"] else "secondary")
                         for k in INCIDENT_KINDS], keep=[animal.name, product["name"]])


def _incident_and_claim(session: Session, principal: Principal, animal: Animal, policy: Policy,
                        state: dict) -> list[Turn]:
    draft = state.get("draft", {})
    occurred = datetime.fromisoformat(draft["occurred_at"].replace("Z", "+00:00"))
    try:
        incident = claims.record_incident(session, principal, animal_id=animal.id, kind=draft["kind"],
                                          occurred_at=occurred, description=draft["description"],
                                          estimated_loss_minor=draft["loss_minor"],
                                          facts={"reported_via": "VEYRA agent conversation"})
        _link_alerts(session, principal, incident)
        claim = claims.draft_claim(session, principal, incident.id)
    except DomainError as error:
        state["awaiting"] = None
        return [Turn(f"I couldn't draft the claim: {error.message}",
                     choices=[choice("new_claim", "Start again", style="primary")], keep=[animal.name])]
    state.pop("draft", None)
    lead = (f"I recorded the incident ({incident.id}) and drafted claim {claim.id} under {policy.id} for "
            f"{usd(claim.claimed_amount_minor, claim.currency)} claimed (the farm's estimate).")
    return _claim_turns(session, principal, animal, claim, state, lead)


def parse_minor(text: str) -> int | None:
    """'600', '600.50', '1,200 USD', '$1,200.00' → minor units; anything else → None."""
    cleaned = re.sub(r"(?i)\b(usd|dollars?)\b|\$", "", text).replace(",", "").strip()
    if not re.fullmatch(r"\d{1,9}(\.\d{1,2})?", cleaned):
        return None
    try:
        return int((Decimal(cleaned) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _file_claim(session: Session, principal: Principal, animal: Animal, state: dict, picked: dict | None,
                text: str | None) -> list[Turn]:
    keep = [animal.name]
    policy, product = _claim_policy(session, principal.farm_id, animal)
    key = picked["key"] if picked else (CONTINUE if text is None else None)
    value = picked.get("value") if picked else None
    if state.get("claim_id") and key not in ("new_claim",):
        claim = claims.farm_claim(session, principal.farm_id, state["claim_id"])
        if key == "confirm_declaration" and claim.status in claims.OPEN_CLAIM_STATUSES:
            if principal.role not in APPROVERS:
                return [Turn("Only a manager can confirm the farmer declaration.",
                             choices=[choice(CONTINUE, "Check again")], keep=keep)]
            claims.confirm_declaration(session, principal, claim.id)
            return _claim_turns(session, principal, animal, claim, state,
                                f"Declaration confirmed by {principal.name} for claim {claim.id}.")
        if key == "prepare_submission" and claim.status in claims.OPEN_CLAIM_STATUSES:
            return _claim_turns(session, principal, animal, claim, state, prepare=True)
        if key == "sample_rescan" and claim.status in claims.OPEN_CLAIM_STATUSES:
            try:
                prepared = identity_check.prepare(session, principal, claim.id)
                check = identity_check.record(session, principal, prepared,
                                              identity_check.simulated(prepared, "match"))
            except DomainError as error:
                return [Turn(f"I couldn't run the sample re-scan: {error.message}",
                             choices=[choice(CONTINUE, "Check again")], keep=keep)]
            return _claim_turns(session, principal, animal, claim, state,
                                f"The sample muzzle re-scan ({check.id}, simulated) matched {animal.name}.")
        return _claim_turns(session, principal, animal, claim, state)
    if animal.identity_status != "confirmed":
        state["awaiting"] = None
        return [Turn(f"{animal.name}'s identity isn't confirmed, so no claim can be prepared for it.",
                     choices=[link(f"Open {animal.name}'s passport", f"/animals/{animal.id}", style="primary")],
                     keep=keep)]
    if policy is None:
        state["awaiting"] = None
        phase, _ = insurance_phase(session, principal.farm_id, animal)
        words = "Its cover isn't confirmed by the insurer yet" if phase != "shopping" else "It has no active cover"
        return [Turn(f"{words}, so there is no policy to claim against for {animal.name}.",
                     choices=[link("Find insurance with the agent", _agent_href(animal.id, "find_insurance"),
                                   style="primary")], keep=keep)]
    awaiting = state.get("awaiting")
    draft = state.setdefault("draft", {})
    if key == "new_claim" or (key == CONTINUE and awaiting is None and not draft):
        state.pop("claim_id", None)
        state["draft"] = {}
        if key == CONTINUE:
            latest = session.scalar(select(Claim).where(Claim.farm_id == principal.farm_id,
                                                        Claim.animal_id == animal.id)
                                    .order_by(Claim.created_at.desc()).limit(1))
            if latest is not None and latest.status in claims.OPEN_CLAIM_STATUSES:
                return _claim_turns(session, principal, animal, latest, state,
                                    f"There is already a claim in progress for {animal.name} ({latest.id}).")
            if latest is not None:
                earlier = Turn(f"{animal.name}'s latest claim ({latest.id}) is submitted. I can track it, or help "
                               f"with a new claim below.",
                               choices=[link("Track that claim", _agent_href(animal.id, "track_claim"))], keep=keep)
            else:
                earlier = None
        covered = ", ".join(PERIL_WORDS.get(p, p) for p in product["covered_perils"])
        requirement_labels = [claims.CHECKLIST_LABELS.get(k, k) for k in product["claim_requirements"]]
        turn = Turn(f"{animal.name} is covered by {product['name']} ({policy.id}) from {policy.effective_date} to "
                    f"{policy.expiry_date}. It covers {covered}. A claim needs: {', '.join(requirement_labels).lower()}.",
                    [card("claim_checklist", claim_id=None, incident_id=None, policy_id=policy.id, status="preview",
                          claimed_amount_minor=None, currency=policy.currency, incident_kind=None,
                          items=[{"key": k, "label": claims.CHECKLIST_LABELS.get(k, k), "status": "required",
                                  "ref": None, "detail": None} for k in product["claim_requirements"]],
                          linked_alert_ids=[])], keep=keep + [product["name"]])
        if key == CONTINUE and earlier is not None:
            return [earlier, turn, _ask_kind(animal, product, state)]
        return [turn, _ask_kind(animal, product, state)]
    if key == "incident_kind":
        if value not in product["covered_perils"]:
            word = PERIL_WORDS.get(value, value)
            return [Turn(f"{product['name']} doesn't cover {word}, so no claim can be drafted for it. Choose what "
                         f"happened if it was a covered event.", keep=keep + [product["name"]]),
                    _ask_kind(animal, product, state)]
        draft["kind"] = value
        state["awaiting"] = "incident_when"
        return [Turn("When did it happen?", choices=[choice("incident_when", WHEN_WORDS[k], k,
                                                            style="primary" if k == "today" else "secondary")
                                                     for k in WHEN_OFFSETS], keep=keep)]
    if key == "incident_when":
        when = (clock.now() - WHEN_OFFSETS[value]).replace(microsecond=0)
        if not claims.in_cover(policy, when):
            return [Turn(f"{when.date()} is outside the cover window ({policy.effective_date} to "
                         f"{policy.expiry_date}), so this policy doesn't cover it. Pick another day if it happened "
                         f"later.", choices=[choice("incident_when", WHEN_WORDS[k], k) for k in WHEN_OFFSETS],
                         keep=keep)]
        draft["occurred_at"] = clock.isoformat(when)
        state["awaiting"] = "incident_description"
        return [Turn("Describe what happened in a sentence or two: where, what you saw, and who found it. Type it "
                     "below.", choices=[choice("incident_description", "Use the sample description (demo)",
                                               SAMPLE_DESCRIPTIONS[draft["kind"]])], keep=keep)]
    if key == "incident_description" or (awaiting == "incident_description" and text is not None):
        description = (value if key == "incident_description" else text or "").strip()
        if len(description) < 5:
            return [Turn("Describe it in a few more words, please.", keep=keep)]
        draft["description"] = description[:MAX_TEXT]
        state["awaiting"] = "incident_loss"
        options = ([choice("incident_loss", f"The insured value, {usd(policy.insured_value_minor, policy.currency)}",
                           str(policy.insured_value_minor), style="primary")] if draft["kind"] == "death" else
                   [choice("incident_loss", f"Use {usd(SAMPLE_INJURY_LOSS, policy.currency)} (demo)",
                           str(SAMPLE_INJURY_LOSS))])
        return [Turn("What is the estimated loss in USD? Type an amount, for example 600. It is the farm's estimate; "
                     "the insurer assesses the loss.", choices=options, keep=keep)]
    if key == "incident_loss" or (awaiting == "incident_loss" and text is not None):
        loss = int(value) if key == "incident_loss" else parse_minor(text or "")
        if loss is None or loss <= 0:
            return [Turn("I need an amount like 600 or 1,200.00 to record the estimated loss.", keep=keep)]
        draft["loss_minor"] = loss
        state["awaiting"] = None
        if not all(k in draft for k in ("kind", "occurred_at", "description")):
            state["draft"] = {}
            return [_ask_kind(animal, product, state)]
        return _incident_and_claim(session, principal, animal, policy, state)
    # Continue with the open question.
    if awaiting == "incident_kind" or not draft.get("kind"):
        return [_ask_kind(animal, product, state)]
    if awaiting == "incident_when":
        return [Turn("When did it happen?", choices=[choice("incident_when", WHEN_WORDS[k], k)
                                                     for k in WHEN_OFFSETS], keep=keep)]
    if awaiting == "incident_description":
        return [Turn("Describe what happened in a sentence or two. Type it below.",
                     choices=[choice("incident_description", "Use the sample description (demo)",
                                     SAMPLE_DESCRIPTIONS[draft["kind"]])], keep=keep)]
    return [Turn("What is the estimated loss in USD? Type an amount, for example 600.", keep=keep)]


# Track a claim -------------------------------------------------------------------------------------------------

def _track_claim(session: Session, principal: Principal, animal: Animal, state: dict) -> list[Turn]:
    keep = [animal.name]
    state["awaiting"] = None
    query = select(Claim).where(Claim.farm_id == principal.farm_id, Claim.animal_id == animal.id)
    claim = session.get(Claim, state["claim_id"]) if state.get("claim_id") else None
    if claim is None:
        claim = session.scalar(query.where(Claim.status.not_in(claims.OPEN_CLAIM_STATUSES))
                               .order_by(Claim.created_at.desc()).limit(1)) or \
            session.scalar(query.order_by(Claim.created_at.desc()).limit(1))
    if claim is None:
        return [Turn(f"There is no claim on record for {animal.name}.",
                     choices=[link("Help me file a claim", _agent_href(animal.id, "file_claim"), style="primary")],
                     keep=keep)]
    state["claim_id"] = claim.id
    if claim.status in claims.OPEN_CLAIM_STATUSES:
        missing = claims.missing_keys(claims.compute_checklist(session, claim))
        labels = [claims.CHECKLIST_LABELS.get(k, k) for k in missing]
        text = f"Claim {claim.id} hasn't been submitted yet."
        text += f" Still missing: {', '.join(labels).lower()}." if missing else " Its checklist is complete."
        return [Turn(text, [claim_checklist_card(claims.claim_view(session, claim))],
                     [link("Continue the claim with the agent", _agent_href(animal.id, "file_claim"), style="primary")],
                     keep=keep)]
    policy = session.get(Policy, claim.policy_id)
    insurer = provider_name(load_catalog(), policy.provider_id)
    status = claim_status_card(session, claim)
    data = status["data"]
    ref = data["reference"]
    latest = data["timeline"][-1]
    received = (claim.receipt or {}).get("received_at", "")[:10]
    if latest["status"] == "assessment_pending":
        text = (f"{insurer} has not posted an update since it received claim {ref} on {received}. Status: "
                f"Submitted — Pending assessment. I can't predict the decision or a payout.")
    elif latest["status"] == "under_review":
        text = f"{insurer} reports claim {ref} is under review. No decision yet."
    elif latest["status"] == "more_info_requested":
        text = (f"{insurer} asked for more information on claim {ref}: {latest['note']} Send it to the insurer; "
                f"the claim waits until it does.")
    elif latest["status"] == "declined":
        text = f"{insurer} declined claim {ref}" + (f": {latest['note']}" if latest["note"] else ".")
    else:
        if latest["settlement_minor"] is not None:
            stated = f"states a settlement of {usd(latest['settlement_minor'], claim.currency)}"
        else:
            stated = "has not stated a settlement amount"
        disbursed = ("The insurer reports it as paid." if latest["disbursement"] == "paid" else
                     "Disbursement: scheduled by the insurer. VEYRA has no record of a payment yet.")
        text = f"{insurer} approved claim {ref} and {stated}. {disbursed}"
    cards = [status]
    if data["outstanding"]:
        cards.append(card("missing_items", claim_id=claim.id,
                          items=[{"key": "insurer_request", "label": "Requested by the insurer", "fix": note,
                                  "href": f"/claims/{claim.id}", "choice": None} for note in data["outstanding"]]))
    return [Turn(text, cards, [choice(CONTINUE, "Check for updates", style="primary"),
                               link("Open the claim", f"/claims/{claim.id}")], keep=keep + [insurer])]


# Conversation flow ---------------------------------------------------------------------------------------------

def _store(session: Session, conversation: AgentConversation, role: str, text: str, *, cards: list | None = None,
           choices: list | None = None, source: str = "simulated") -> AgentMessage:
    seq = (session.scalar(select(func.max(AgentMessage.seq)).where(
        AgentMessage.conversation_id == conversation.id)) or 0) + 1
    message = AgentMessage(id=new_id("msg"), conversation_id=conversation.id, seq=seq, role=role, text=text,
                           cards=list(cards or []), choices=list(choices or []), source=source,
                           created_at=clock.now())
    session.add(message)
    session.flush()
    return message


def _plan(session: Session, principal: Principal, conversation: AgentConversation, picked: dict | None,
          text: str | None, note: str | None) -> list[Turn]:
    animal = farm_animal(session, principal.farm_id, conversation.animal_id)
    state = dict(conversation.state or {})
    if conversation.intent == "find_insurance":
        turns = _find_insurance(session, principal, animal, state, picked, note)
    elif conversation.intent == "file_claim":
        turns = _file_claim(session, principal, animal, state, picked, text)
    else:
        turns = _track_claim(session, principal, animal, state)
    conversation.state = state
    conversation.updated_at = clock.now()
    return turns


@dataclass
class Stored:
    message_id: str
    text: str
    keep: list[str]


def _store_turns(session: Session, conversation: AgentConversation, turns: list[Turn]) -> list[Stored]:
    stored = []
    for turn in turns:
        message = _store(session, conversation, "agent", turn.text, cards=turn.cards, choices=turn.choices)
        stored.append(Stored(message.id, turn.text, turn.keep))
    return stored


def require_converser(principal: Principal) -> None:
    if principal.role not in CONVERSE_ROLES:
        raise DomainError("FORBIDDEN_ROLE", "Only a manager or an operator can work with the agent; a vet adds "
                          "findings on the claim.", {"required": list(CONVERSE_ROLES), "role": principal.role})


def start(session: Session, principal: Principal, animal_id: str, intent: str) -> tuple[AgentConversation,
                                                                                         list[Stored]]:
    """Open a conversation and write the agent's first turns. The caller commits."""
    require_converser(principal)
    if intent not in INTENTS:
        raise DomainError("VALIDATION_FAILED", "Unknown intent.", {"intent": intent, "allowed": list(INTENTS)})
    animal = farm_animal(session, principal.farm_id, animal_id)
    now = clock.now()
    conversation = AgentConversation(id=new_id("cnv"), farm_id=principal.farm_id, animal_id=animal.id, intent=intent,
                                     state={}, created_by=principal.user_id, created_at=now, updated_at=now)
    session.add(conversation)
    session.flush()
    summary, _ = _summary_turn(session, principal.farm_id, animal)
    turns = [summary, *_plan(session, principal, conversation, None, None, None)]
    return conversation, _store_turns(session, conversation, turns)


_YES = {"yes", "y", "yep", "yeah", "ya", "sure", "i do", "we do", "i have", "we have"}
_NO = {"no", "n", "nope", "not", "don't", "dont", "none", "no i don't"}


def match_choice(text: str, offered: list[dict]) -> dict | None:
    """Map typed text onto one of the offered choices by plain keywords. Text is data: no other effect."""
    words = re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split()
    phrase = " ".join(words)
    if not phrase:
        return None
    actionable = [c for c in offered if not c.get("href")]
    for option in actionable:
        value = (option.get("value") or "").lower()
        if value == "yes" and (phrase in _YES or words[0] in _YES):
            return option
        if value == "no" and (phrase in _NO or words[0] in _NO):
            return option
    for option in actionable:
        label = re.sub(r"[^a-z0-9' ]+", " ", option["label"].lower()).strip()
        value = (option.get("value") or "").lower().replace("_", " ")
        if label and (label == phrase or (len(phrase) >= 4 and f" {phrase} " in f" {label} ")
                      or f" {label} " in f" {phrase} "):
            return option
        if value and 4 <= len(value) <= 40 and f" {value} " in f" {phrase} ":
            return option
    return None


def _offered(session: Session, conversation_id: str) -> list[dict]:
    latest = _latest_agent_message(session, conversation_id)
    return list(latest.choices or []) if latest else []


def resolve_input(session: Session, conversation: AgentConversation, text: str | None,
                  picked: dict | None) -> tuple[dict | None, str | None, str]:
    """(choice to act on, free text, the user's words to store). A choice must be one the agent offered last."""
    offered = _offered(session, conversation.id)
    if picked is not None:
        key, value = picked.get("key"), picked.get("value")
        if key == CONTINUE:
            label = next((c["label"] for c in offered if c["key"] == CONTINUE), "Check status")
            return {"key": CONTINUE, "value": None}, None, label
        match = next((c for c in offered if c["key"] == key and c.get("value") == value and not c.get("href")), None)
        if match is None:
            raise DomainError("INVALID_STATE", "That option isn't offered now; choose one of the current options.",
                              {"key": key})
        return {"key": match["key"], "value": match.get("value")}, None, match["label"]
    clean = (text or "").strip()[:MAX_TEXT]
    if not clean:
        raise DomainError("VALIDATION_FAILED", "Send a text or a choice.")
    awaiting = (conversation.state or {}).get("awaiting")
    if awaiting in ("incident_description", "incident_loss"):
        return None, clean, clean
    match = match_choice(clean, offered)
    if match is not None:
        return {"key": match["key"], "value": match.get("value")}, None, clean
    return {"key": "_unmatched", "value": None}, clean, clean


def pre_turn(principal: Principal, conversation_id: str, picked: dict | None) -> str | None:
    """Steps that open their own sessions and must run before the turn's writing transaction (the insurer
    activation check). Returns a note for the agent's reply."""
    if not picked or picked.get("key") != "activation_check":
        return None
    if principal.role not in APPROVERS:
        return "Only a manager can ask the insurer again."
    try:
        actions.check_activation(principal, picked["value"])
    except DomainError as error:
        return f"The insurer check didn't run: {error.message}"
    return None


def reply(session: Session, principal: Principal, conversation_id: str, text: str | None, picked: dict | None,
          note: str | None = None) -> tuple[AgentConversation, list[Stored]]:
    """Store the user's turn, then the agent's next turns. The caller commits."""
    require_converser(principal)
    conversation = farm_conversation(session, principal.farm_id, conversation_id)
    acting, free_text, words = resolve_input(session, conversation, text, picked)
    _store(session, conversation, "user", words, source="user")
    if acting is not None and acting["key"] == "_unmatched":
        offered = [c for c in _offered(session, conversation.id)]
        turns = [Turn("I can only act on the options below; I kept your message in this conversation.",
                      choices=offered or [choice(CONTINUE, "Check status")])]
        conversation.updated_at = clock.now()
        return conversation, _store_turns(session, conversation, turns)
    if acting is not None and acting["key"] == "activation_check":
        acting = {"key": CONTINUE, "value": None}
    turns = _plan(session, principal, conversation, acting, free_text, note)
    return conversation, _store_turns(session, conversation, turns)


# Phrasing ------------------------------------------------------------------------------------------------------

REPHRASE_PROMPT = (
    "You rephrase one message from a livestock insurance agent inside a farm app, for the farmer, in plain and calm "
    "language. Rephrase only. Keep every number, amount, currency, date, ID, reference, terms reference, name, and "
    "status exactly as written. Add no facts, promises, advice, or guarantees; never say a payout is certain; do "
    "not change who must act. Keep it about as short as the original."
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_IDENT = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z0-9]+)+\b")
_TERMS = re.compile(r"§\s?\d+(?:\.\d+)?")


class Rephrased(BaseModel):
    text: str


def protected_tokens(text: str, keep: list[str]) -> set[str]:
    tokens = set(_NUMBER.findall(text)) | set(_TERMS.findall(text)) | set(keep)
    tokens |= {t for t in _IDENT.findall(text) if any(ch.isdigit() for ch in t)}
    return {t for t in tokens if t}


def preserves(template: str, output: str, keep: list[str]) -> bool:
    """Every figure, ID, terms ref, and kept name of the template appears in the output, and no new figure does."""
    if not output.strip() or len(output) > 2 * len(template) + 200:
        return False
    if any(token not in output for token in protected_tokens(template, keep)):
        return False
    return set(_NUMBER.findall(output)) <= set(_NUMBER.findall(template))


def rephrase(settings: Settings, text: str, keep: list[str], client: Any | None = None) -> tuple[str, str]:
    """(text, source): the model's wording when it kept every fact, else the template with `simulated`."""
    user = "Rephrase this message.\n<records>" + json.dumps({"message": text, "keep_exactly": sorted(
        protected_tokens(text, keep))}, ensure_ascii=False) + "</records>"
    result = structured_call(settings, system=REPHRASE_PROMPT, user=user, output_model=Rephrased, max_tokens=600,
                             client=client)
    if result.output is None:
        return text, "simulated"
    candidate = result.output.text.strip()
    if not preserves(text, candidate, keep):
        return text, "simulated"
    return candidate, "live"
