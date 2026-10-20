"""Insurance recommendations and policy reads (plan Section 4: eligibility; Section 5: `/policies`).

A recommendation is the deterministic evaluation of every catalog product plus its price. Insured value is the
lower bound of the latest confirmed valuation (`insured_value_rule: valuation_low`). Prices are computed for
`eligible` and `unknown` products only, and only when a valuation exists.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain import eligibility, premiums
from domain.catalog import load_catalog
from domain.errors import DomainError
from domain.passbook import product_name
from domain.valuation import farm_animal, latest_valuation
from persistence.models import Animal, Policy, Valuation

PRICED_OUTCOMES = ("eligible", "unknown")


def insured_value(catalog: dict, valuation: Valuation | None) -> int | None:
    if valuation is None:
        return None
    if catalog["insured_value_rule"]["basis"] != "valuation_low":
        raise ValueError(f"unsupported insured value basis {catalog['insured_value_rule']['basis']!r}")
    return valuation.value_low_minor


def evaluate_product(product: dict, facts: dict, insured: int | None, currency: str) -> dict:
    result = eligibility.evaluate(product, facts)
    price = premiums.price(product, insured) if insured is not None and result["outcome"] in PRICED_OUTCOMES else None
    return {
        **result,
        "product_name": product["name"],
        "premium_minor": price["premium_minor"] if price else None,
        "deductible_minor": price["deductible_minor"] if price else None,
        "currency": currency,
        "covered_perils": list(product["covered_perils"]),
        "exclusions": [dict(item) for item in product["exclusions"]],
        "payout_formula": product["payout_formula"],
    }


def animal_brief(animal: Animal) -> dict:
    return {"id": animal.id, "name": animal.name, "breed": animal.breed, "breed_category": animal.breed_category,
            "sex": animal.sex, "identity_status": animal.identity_status}


def recommend(session: Session, farm_id: str, animal_id: str) -> dict:
    animal = farm_animal(session, farm_id, animal_id)
    catalog = load_catalog()
    valuation = latest_valuation(session, animal.id)
    insured = insured_value(catalog, valuation)
    facts = eligibility.facts_for(session, animal)
    currency = catalog["currency"]
    return {
        "animal": animal_brief(animal),
        "animal_id": animal.id,
        "catalog_version": catalog["catalog_version"],
        "insured_value_minor": insured,
        "currency": currency,
        "valuation_id": valuation.id if valuation else None,
        "facts": facts,
        "results": [evaluate_product(product, facts, insured, currency) for product in catalog["products"]],
    }


def policy_view(policy: Policy) -> dict:
    return {column.name: getattr(policy, column.name) for column in Policy.__table__.columns} | {
        "product_name": product_name(policy.product_id)}


def list_policies(session: Session, farm_id: str, animal_id: str | None = None) -> list[dict]:
    query = select(Policy).where(Policy.farm_id == farm_id)
    if animal_id is not None:
        query = query.where(Policy.animal_id == animal_id)
    return [policy_view(p) for p in session.scalars(query.order_by(Policy.created_at.desc(), Policy.id))]


def farm_policy(session: Session, farm_id: str, policy_id: str) -> Policy:
    policy = session.get(Policy, policy_id)
    if policy is None or policy.farm_id != farm_id:
        raise DomainError("NOT_FOUND", "Policy not found.", {"policy_id": policy_id})
    return policy
