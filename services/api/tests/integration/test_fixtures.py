import json

import pytest

from config import get_settings


def _load(name: str) -> dict:
    return json.loads((get_settings().fixtures_dir / name).read_text(encoding="utf-8"))


def test_policy_catalog_is_complete():
    catalog = _load("policies.json")

    assert catalog["catalog_version"] == "sample-v1"
    assert catalog["provider"]["id"] == "sandbox-insurer"
    assert catalog["insured_value_rule"]["terms_ref"].startswith("sample-v1")
    products = {p["product_id"]: p for p in catalog["products"]}
    assert set(products) == {"basic-mortality", "mortality-theft", "dairy-health-plus"}
    for product in products.values():
        assert product["summary"]
        for key in ("eligibility", "premium", "deductible", "covered_perils", "exclusions", "claim_requirements"):
            assert product[key], (product["product_id"], key)
        assert "payout_formula" in product
        for rule in product["eligibility"]:
            assert {"field", "op", "value", "terms_ref", "text"} <= set(rule)
        for item in [*product["eligibility"], *product["exclusions"], product["premium"], product["deductible"]]:
            assert item["terms_ref"].startswith("sample-v1 §")
        assert {"identity_reference", "active_policy", "vet_assessment"} <= set(product["claim_requirements"])
    assert products["basic-mortality"]["premium"]["rate_bps"] == 350
    assert "ownership_document" in products["mortality-theft"]["claim_requirements"]
    assert "vet_health_record" in products["dairy-health-plus"]["claim_requirements"]


@pytest.mark.parametrize("key", ["sample-enrollment-001", "sample-enrollment-dup", "sample-enrollment-unclear"])
def test_enrollment_samples_are_complete(key):
    sample = _load("enrollment_samples.json")[key]

    assert {"label", "views", "identity", "weight", "proposed_animal"} <= set(sample)
    assert {"source", "method_version", "outcome", "candidates"} <= set(sample["identity"])
    weight = sample["weight"]
    assert {"source", "method_version", "range_low", "range_high", "unit"} <= set(weight)
    assert weight["range_low"] < weight["range_high"]
    assert {"name", "breed", "breed_category", "sex"} <= set(sample["proposed_animal"])
    assert ("muzzle" in sample["views"]) == (key != "sample-enrollment-unclear")


def test_demo_incident_is_complete():
    incident = _load("incidents.json")["demo-incident-001"]

    assert {"animal_id", "kind", "description", "estimated_loss_minor", "currency", "facts"} <= set(incident)
    assert incident["estimated_loss_minor"] == 60000


def test_herd_fixture_is_complete():
    herd = _load("herd.json")

    assert {"farms", "users", "cameras", "price", "animals", "wallet"} <= set(herd)
    assert {u["token"] for u in herd["users"]} == {
        "demo-manager", "demo-operator", "demo-vet", "demo-assessor", "other-farm-manager"}
