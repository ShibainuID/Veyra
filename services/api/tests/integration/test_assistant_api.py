"""The scripted assistant queries plus the missing-evidence query, offline (PRD verification)."""

import pytest

from tests.support import ASSESSOR, MANAGER, OPERATOR, OTHER_FARM, VET

API = "/api/v1"


@pytest.fixture
def farm(client):
    assert client.post(f"{API}/demo/reset?scenario=post-enrollment", headers=MANAGER).status_code == 200
    return client


def _ask(client, text: str, headers=VET) -> dict:
    response = client.post(f"{API}/assistant/query", json={"text": text}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _facts(body: dict) -> dict[str, tuple]:
    return {f["label"]: (f["value"], f["record_type"], f["record_id"]) for f in body["facts"]}


def test_show_me_animal_002_returns_passport_facts(farm):
    body = _ask(farm, "Show me animal-demo-002")
    assert (body["intent"], body["parsed_by"], body["fallback_reason"]) == ("animal_lookup", "simulated",
                                                                            "llm_offline")
    facts = _facts(body)
    assert facts["Name"] == ("Bima", "animal", "animal-demo-002")
    assert facts["Breed"][0] == "Ongole" and facts["Identity status"][0] == "confirmed"
    assert facts["Indicative value"][0] == "2,704.00–3,120.00 USD"
    assert body["answer"].startswith("Bima (animal-demo-002) is a male Ongole (beef); identity confirmed.")
    assert body["records"]["animals"][0]["id"] == "animal-demo-002" and body["missing"] == []


def test_where_was_001_last_seen_and_what_coverage_after_the_anomaly(farm):
    assert farm.post(f"{API}/demo/replays/anomaly/start", headers=OPERATOR).status_code == 200
    body = _ask(farm, "Where was animal-demo-001 last seen, and what coverage is active?")
    assert body["intent"] == "location_lookup"
    facts = _facts(body)
    assert facts["Last observed on"] == ("Pen A · feed line", "camera", "cam-pen-a")
    assert facts["Last observed at"][1] == "observation"
    assert facts["Coverage"] == ("none", "animal", "animal-demo-001")
    assert body["answer"].startswith("Sari (animal-demo-001) was last observed on Pen A · feed line at ")
    assert body["answer"].endswith("Sari has no active coverage.")
    assert "It may have moved since." not in body["answer"]
    assert body["missing"] == ["active_policy"]
    assert body["records"]["last_observations"][0]["camera_id"] == "cam-pen-a"
    assert body["records"]["coverage"] == [{"animal_id": "animal-demo-001", "status": "none", "policy_id": None,
                                            "product_id": None, "policy_status": None}]


def test_location_and_active_coverage_from_seeded_data(farm):
    body = _ask(farm, "Where was Bima last seen, and what coverage is active?")
    facts = _facts(body)
    assert facts["Last observed on"][2] == "cam-pen-a"
    assert facts["Active policy"][0] == "Basic Mortality & Accident" and facts["Active policy"][1] == "policy"
    assert facts["Insured value"][0] == "2,704.00 USD"
    assert facts["Coverage period"][0] == "2026-09-01 to 2027-08-31"
    assert body["missing"] == []


def test_which_animals_have_open_alerts(farm):
    body = _ask(farm, "Which animals have open alerts?", headers=ASSESSOR)
    assert body["intent"] == "alert_lookup"
    assert body["answer"] == "1 animal has open alerts: Gatot (animal-demo-004): 1 open (observation quality)."
    assert [f["record_type"] for f in body["facts"]] == ["alert"]
    assert body["records"]["alerts"][0]["animal_id"] == "animal-demo-004"

    assert farm.post(f"{API}/demo/replays/anomaly/start", headers=OPERATOR).status_code == 200
    assert farm.post(f"{API}/demo/replays/lost_identity/start", headers=OPERATOR).status_code == 200
    after = _ask(farm, "Which animals have open alerts?")
    assert after["answer"].startswith("2 animals have open alerts: ")
    assert "Sari (animal-demo-001): 1 open (reduced movement)" in after["answer"]
    assert after["answer"].endswith("1 open warning concerns an unidentified camera track (t-14), not a registered "
                                    "animal.")


def test_where_is_dewi_reports_missing_evidence(farm):
    body = _ask(farm, "Where is Dewi?")
    assert body["intent"] == "location_lookup"
    assert body["answer"] == "No camera observation is on record for Dewi (animal-demo-005)."
    assert body["missing"] == ["last_observation"] and body["facts"] == []


def test_assistant_is_farm_scoped_and_needs_auth(farm):
    body = _ask(farm, "Show me animal-demo-002", headers=OTHER_FARM)
    assert body["answer"] == "I couldn't find an animal matching 'animal-demo-002' in this farm."
    assert body["records"]["animals"] == []
    assert farm.post(f"{API}/assistant/query", json={"text": "hi"}).status_code == 401
    assert farm.post(f"{API}/assistant/query", json={"text": ""}, headers=VET).status_code == 422
    unknown = _ask(farm, "What is the weather like?")
    assert unknown["intent"] == "unknown" and "Which animals have open alerts?" in unknown["answer"]
