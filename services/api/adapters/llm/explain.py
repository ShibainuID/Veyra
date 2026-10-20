"""Grounded policy explanations (plan Section 6: language model, grounding check).

Claude explains eligibility and price results that the rules already computed; it never changes an outcome or a
number. Its output is checked against the inputs: items for products that were not supplied are dropped, and
terms references that are not in the catalog are removed (`grounding_dropped`). Offline, or on any failure, a
deterministic template says the same facts with `source: simulated`.
"""

import json
from typing import Any

from pydantic import BaseModel

from adapters.llm.client import structured_call
from config import Settings
from domain.catalog import terms_refs

SYSTEM_PROMPT = (
    "You explain livestock insurance options to a farm manager in plain language. The application has already "
    "computed every eligibility outcome, premium, and deductible with deterministic rules. Explain the supplied "
    "results using only the supplied policy terms. Never change an outcome, an amount, or a rule, and never "
    "introduce a product, peril, or number that is not in the records. For each product, cite the terms_ref "
    "values of the rules and terms you rely on, copied exactly. State in the caveats that the indicative value "
    "is an estimate from the animal's records and is not an insurer-agreed value or a payout, and that the "
    "terms are a fictional sample. Money amounts are integer minor units of the given currency (cents)."
)


class ExplanationItemModel(BaseModel):
    product_id: str
    explanation: str
    terms_refs: list[str]


class PolicyExplanation(BaseModel):
    summary: str
    items: list[ExplanationItemModel]
    caveats: list[str]


OFFLINE_CAVEATS = [
    "The indicative value comes from the animal's estimated weight and a reference price; it is not an "
    "insurer-agreed value or a payout.",
    "These are fictional sample terms for demonstration, not a market quote.",
]


def _money(minor: int | None, currency: str) -> str:
    if minor is None:
        return "not priced"
    whole, cents = divmod(minor, 100)
    return f"{whole:,}.{cents:02d} {currency}"


def _product_refs(result: dict, statuses: tuple[str, ...]) -> list[str]:
    refs = [reason["terms_ref"] for reason in result["reasons"] if reason["status"] in statuses]
    return list(dict.fromkeys(refs))


def offline_explanation(animal_name: str, results: list[dict], currency: str) -> PolicyExplanation:
    items = []
    for result in results:
        name = result["product_name"]
        price = (f" Indicative premium {_money(result['premium_minor'], currency)} a year, deductible "
                 f"{_money(result['deductible_minor'], currency)}." if result["premium_minor"] is not None else
                 " A premium is shown once a valuation is confirmed.")
        if result["outcome"] == "eligible":
            text = f"{name}: eligible under the sample terms; every rule passes.{price}"
            refs = _product_refs(result, ("pass",))
        elif result["outcome"] == "unknown":
            text = f"{name}: needs review before it can be offered ({'; '.join(result['needs_review'])}).{price}"
            refs = _product_refs(result, ("unknown",))
        else:
            failed = "; ".join(r["text"] for r in result["reasons"] if r["status"] == "fail")
            text = f"{name}: not eligible. Rule not met: {failed}"
            refs = _product_refs(result, ("fail",))
        items.append(ExplanationItemModel(product_id=result["product_id"], explanation=text, terms_refs=refs))
    counts = {outcome: sum(r["outcome"] == outcome for r in results) for outcome in ("eligible", "unknown", "ineligible")}
    summary = (f"Of {len(results)} sample products for {animal_name}, {counts['eligible']} eligible, "
               f"{counts['unknown']} need review, and {counts['ineligible']} not eligible.")
    return PolicyExplanation(summary=summary, items=items, caveats=list(OFFLINE_CAVEATS))


def ground(explanation: PolicyExplanation, product_ids: set[str], catalog: dict) -> tuple[PolicyExplanation, bool]:
    """Drop items for unknown products and terms references the catalog does not contain."""
    known_refs = terms_refs(catalog)
    dropped = False
    items = []
    for item in explanation.items:
        if item.product_id not in product_ids:
            dropped = True
            continue
        refs = [ref for ref in item.terms_refs if ref in known_refs]
        dropped = dropped or len(refs) != len(item.terms_refs)
        items.append(item.model_copy(update={"terms_refs": refs}))
    return explanation.model_copy(update={"items": items}), dropped


def records_for(animal: dict, results: list[dict], catalog: dict, insured_value_minor: int | None,
                currency: str) -> dict:
    return {
        "animal": animal,
        "catalog_version": catalog["catalog_version"],
        "provider": catalog["provider"],
        "insured_value_rule": catalog["insured_value_rule"],
        "insured_value_minor": insured_value_minor,
        "currency": currency,
        "results": results,
    }


def explain(settings: Settings, *, animal: dict, results: list[dict], catalog: dict,
            insured_value_minor: int | None, currency: str, client: Any | None = None) -> dict:
    records = records_for(animal, results, catalog, insured_value_minor, currency)
    user = ("Explain these deterministic insurance results for the farm manager.\n"
            f"<records>{json.dumps(records, sort_keys=True, default=str)}</records>")
    result = structured_call(settings, system=SYSTEM_PROMPT, user=user, output_model=PolicyExplanation,
                             client=client)
    if result.output is None:
        offline = offline_explanation(animal.get("name") or animal["id"], results, currency)
        return {"source": "simulated", "model": result.model, "fallback_reason": result.fallback_reason,
                **offline.model_dump(), "grounding_dropped": False}
    grounded, dropped = ground(result.output, {r["product_id"] for r in results}, catalog)
    return {"source": "live", "model": result.model, "fallback_reason": None, **grounded.model_dump(),
            "grounding_dropped": dropped}
