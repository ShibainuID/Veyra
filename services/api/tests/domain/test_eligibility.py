import pytest

from domain import premiums
from domain.catalog import get_product, load_catalog
from domain.eligibility import check_rule, evaluate

FULL_FACTS = {"identity_status": "confirmed", "age_months_low": 24, "age_months_high": 30,
              "valuation_confirmed": True, "ownership_document": "present", "breed_category": "beef",
              "vet_health_check_days": None}


def _rule(field, op, value):
    return {"field": field, "op": op, "value": value, "terms_ref": "sample-v1 §9", "text": "t"}


@pytest.mark.parametrize(("low", "high", "status"), [
    (24, 30, "pass"), (6, 120, "pass"), (2, 5, "fail"), (121, 130, "fail"), (3, 8, "unknown"), (110, 130, "unknown"),
    (None, None, "unknown"), (24, None, "unknown"),
])
def test_between_uses_the_whole_age_range(low, high, status):
    facts = {"age_months_low": low, "age_months_high": high}
    assert check_rule(_rule("age_months", "between", [6, 120]), facts)["status"] == status


@pytest.mark.parametrize(("low", "high", "status"), [
    (24, 30, "pass"), (90, 96, "pass"), (97, 110, "fail"), (90, 100, "unknown"),
])
def test_lte_on_age_passes_on_high_and_fails_on_low(low, high, status):
    facts = {"age_months_low": low, "age_months_high": high}
    assert check_rule(_rule("age_months", "lte", 96), facts)["status"] == status


@pytest.mark.parametrize(("value", "status"), [(10, "pass"), (30, "pass"), (31, "fail"), (None, "unknown")])
def test_lte_on_scalar_field(value, status):
    assert check_rule(_rule("vet_health_check_days", "lte", 30), {"vet_health_check_days": value})["status"] == status


@pytest.mark.parametrize(("fact", "status"), [("confirmed", "pass"), ("pending_review", "fail"), (None, "unknown")])
def test_eq(fact, status):
    assert check_rule(_rule("identity_status", "eq", "confirmed"), {"identity_status": fact})["status"] == status


def test_missing_fact_is_unknown_not_ineligible():
    result = evaluate(get_product(load_catalog(), "mortality-theft"), {**FULL_FACTS, "ownership_document": None})
    assert result["outcome"] == "unknown"
    assert result["needs_review"] == ["Add an ownership document reference"]
    status = {r["terms_ref"]: r["status"] for r in result["reasons"]}
    assert status["sample-v1 §2.4"] == "unknown"


def test_missing_valuation_needs_review():
    result = evaluate(get_product(load_catalog(), "basic-mortality"), {**FULL_FACTS, "valuation_confirmed": None})
    assert result["outcome"] == "unknown"
    assert result["needs_review"] == ["Confirm a valuation"]


def test_all_rules_pass_is_eligible():
    result = evaluate(get_product(load_catalog(), "basic-mortality"), FULL_FACTS)
    assert result["outcome"] == "eligible" and result["needs_review"] == []
    assert [r["terms_ref"] for r in result["reasons"]] == ["sample-v1 §2.1", "sample-v1 §2.2", "sample-v1 §2.3"]


def test_fail_dominates_unknown():
    # Dairy Health Plus: beef breed fails, missing vet health check is unknown → ineligible.
    result = evaluate(get_product(load_catalog(), "dairy-health-plus"), FULL_FACTS)
    assert result["outcome"] == "ineligible"
    statuses = {r["field"]: r["status"] for r in result["reasons"]}
    assert statuses["breed_category"] == "fail" and statuses["vet_health_check_days"] == "unknown"


def test_premium_rounding_half_up():
    assert premiums.premium_minor(228800, 520) == 11898  # 11897.6
    assert premiums.premium_minor(270400, 350) == 9464
    assert premiums.premium_minor(100, 50) == 1  # 0.5 rounds up
    assert premiums.premium_minor(300, 50) == 2  # 1.5 rounds up (not banker's)
    assert premiums.premium_minor(249600, 350) == 8736


def test_deductible_bases():
    catalog = load_catalog()
    assert premiums.deductible_minor(270400, get_product(catalog, "basic-mortality")["deductible"]) == 27040
    assert premiums.deductible_minor(270400, get_product(catalog, "mortality-theft")["deductible"]) == 15000
    assert premiums.deductible_minor(249601, get_product(catalog, "dairy-health-plus")["deductible"]) == 12480


def test_illustrative_payout():
    assert premiums.illustrative_payout(60000, 249600, 24960) == 35040
    assert premiums.illustrative_payout(300000, 249600, 24960) == 224640
    assert premiums.illustrative_payout(10000, 249600, 24960) == 0
