import pytest
from sqlalchemy import delete

from persistence.db import SessionLocal
from persistence.models import Valuation
from tests.support import MANAGER, OPERATOR, OTHER_FARM, VET


@pytest.fixture
def post_enrollment(client):
    response = client.post("/api/v1/demo/reset", params={"scenario": "post-enrollment"}, headers=MANAGER)
    assert response.status_code == 200, response.text
    return client


def _recommend(client, animal_id="animal-demo-001", headers=MANAGER):
    return client.post(f"/api/v1/animals/{animal_id}/insurance-recommendations", headers=headers)


def test_catalog_is_readable_by_any_role(client):
    response = client.get("/api/v1/policies/catalog", headers=VET)
    assert response.status_code == 200
    assert response.json()["version"] == "sample-v1"
    assert client.get("/api/v1/policies/catalog").status_code == 401


def test_recommendations_for_sari(post_enrollment):
    response = _recommend(post_enrollment, headers=OPERATOR)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["insured_value_minor"], body["catalog_version"], body["currency"]) == (249600, "sample-v1", "USD")
    results = {r["product_id"]: r for r in body["results"]}
    basic = results["basic-mortality"]
    assert basic["outcome"] == "eligible"
    assert (basic["premium_minor"], basic["deductible_minor"]) == (8736, 24960)
    assert basic["covered_perils"] == ["accidental_injury", "death"]
    assert basic["payout_formula"]["terms_ref"] == "sample-v1 §5.1"
    theft = results["mortality-theft"]
    assert theft["outcome"] == "unknown" and theft["needs_review"] == ["Add an ownership document reference"]
    assert (theft["premium_minor"], theft["deductible_minor"]) == (12979, 15000)
    dairy = results["dairy-health-plus"]
    assert dairy["outcome"] == "ineligible" and dairy["premium_minor"] is None
    explanation = body["explanation"]
    assert explanation["source"] == "simulated" and explanation["fallback_reason"] == "llm_offline"
    assert {item["product_id"] for item in explanation["items"]} == set(results)


def test_recommendations_without_valuation_need_review(post_enrollment):
    with SessionLocal() as session:
        session.execute(delete(Valuation).where(Valuation.animal_id == "animal-demo-001"))
        session.commit()

    body = _recommend(post_enrollment).json()

    assert body["insured_value_minor"] is None and body["valuation_id"] is None
    basic = next(r for r in body["results"] if r["product_id"] == "basic-mortality")
    assert basic["outcome"] == "unknown" and basic["needs_review"] == ["Confirm a valuation"]
    assert basic["premium_minor"] is None


def test_recommendations_scope_and_roles(post_enrollment):
    assert _recommend(post_enrollment, headers=VET).status_code == 403
    assert _recommend(post_enrollment, headers=OTHER_FARM).status_code == 404


def test_policies_list_is_farm_scoped(client):
    body = client.get("/api/v1/policies", headers=MANAGER).json()
    assert sorted(p["animal_id"] for p in body["items"]) == ["animal-demo-002", "animal-demo-003"]
    one = client.get("/api/v1/policies", params={"animal_id": "animal-demo-003"}, headers=MANAGER).json()
    assert [p["product_name"] for p in one["items"]] == ["Mortality + Theft"]
    assert client.get("/api/v1/policies", headers=OTHER_FARM).json()["items"] == []
