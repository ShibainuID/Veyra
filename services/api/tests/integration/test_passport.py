from datetime import timedelta

import pytest
from sqlalchemy import select

from domain import clock
from persistence.db import SessionLocal
from persistence.models import AgentAction, Valuation
from tests.support import MANAGER, VET

ANIMAL_IDS = ["animal-demo-002", "animal-demo-003", "animal-demo-004", "animal-demo-005", "animal-demo-006"]
HASH = "abcdef0123456789" * 4


def _herd(client, **params) -> dict:
    response = client.get("/api/v1/animals", headers=MANAGER, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _passport(client, animal_id: str) -> dict:
    response = client.get(f"/api/v1/animals/{animal_id}/passport", headers=MANAGER)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def pending_payment(client):
    with SessionLocal() as session:
        action = AgentAction(
            id="act-000000000001", farm_id="farm-wahyu", action_type="PREMIUM_PAYMENT", animal_id="animal-demo-005",
            subject_type="policy_application", subject_id="app-000000000001",
            payload={"animal_id": "animal-demo-005", "amount_minor": 15142, "currency": "USD", "mode": "sandbox"},
            payload_hash=HASH, status="pending_approval", rationale="Pay the premium to start cover.",
            proposed_by_type="agent", proposed_by_id="veyra-agent", expires_at=clock.now() + timedelta(minutes=30),
        )
        session.add(action)
        session.commit()
        return action


def test_herd_lists_every_animal_with_its_state(client):
    items = {item["id"]: item for item in _herd(client)["items"]}

    assert sorted(items) == ANIMAL_IDS
    assert {k: v["coverage"]["status"] for k, v in items.items()} == {
        "animal-demo-002": "active", "animal-demo-003": "active", "animal-demo-004": "none",
        "animal-demo-005": "none", "animal-demo-006": "none"}
    assert items["animal-demo-003"]["coverage"]["product_id"] == "mortality-theft"
    assert items["animal-demo-003"]["coverage"]["policy_status"] == "active"
    assert items["animal-demo-004"]["alerts"] == {"open_count": 1, "kinds": ["observation_quality"]}
    assert items["animal-demo-002"]["alerts"] == {"open_count": 0, "kinds": []}
    last = items["animal-demo-002"]["last_observation"]
    assert (last["camera_id"], last["camera_name"], last["association_status"]) == (
        "cam-pen-a", "Pen A · feed line", "associated")
    assert last["observed_at"].endswith("Z")
    assert items["animal-demo-005"]["last_observation"] is None
    bima = items["animal-demo-002"]
    assert (bima["name"], bima["breed"], bima["sex"], bima["identity_status"]) == ("Bima", "Ongole", "M", "confirmed")
    assert bima["weight"] == {"range_low": 520, "range_high": 600, "unit": "kg", "source": "simulated"}
    assert (bima["age"]["unit"], bima["age"]["source"]) == ("months", "documented")
    assert bima["valuation"] == {"value_low_minor": 270400, "value_high_minor": 312000, "currency": "USD",
                                 "price_date": "2026-10-01", "version": 1}
    assert bima["pending_actions"] == 0


@pytest.mark.parametrize("params, expected", [
    ({"coverage": "none"}, ["animal-demo-004", "animal-demo-005", "animal-demo-006"]),
    ({"coverage": "active"}, ["animal-demo-002", "animal-demo-003"]),
    ({"coverage": "pending"}, []),
    ({"alerts": "open"}, ["animal-demo-004"]),
    ({"q": "bima"}, ["animal-demo-002"]),
    ({"q": "DEMO-006"}, ["animal-demo-006"]),
    ({"coverage": "none", "alerts": "open"}, ["animal-demo-004"]),
])
def test_herd_filters(client, params, expected):
    assert sorted(item["id"] for item in _herd(client, **params)["items"]) == expected


def test_herd_rejects_unknown_filter(client):
    response = client.get("/api/v1/animals", headers=MANAGER, params={"coverage": "partial"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_herd_summary(client):
    with SessionLocal() as session:
        valuations = session.scalars(select(Valuation)
                                     .where(Valuation.animal_id.in_(ANIMAL_IDS))).all()

    summary = _herd(client, q="bima")["summary"]

    assert summary == {
        "animal_count": 5,
        "exposure_low_minor": sum(v.value_low_minor for v in valuations),
        "exposure_high_minor": sum(v.value_high_minor for v in valuations),
        "insured_minor": 270400 + 228800,
        "uncovered_count": 3,
        "open_alerts": 1,
        "pending_approvals": 0,
        "wallet_balance_minor": 978638,
        "currency": "USD",
    }


def test_passport_joins_the_animal_record(client):
    passport = _passport(client, "animal-demo-003")

    animal = passport["animal"]
    assert (animal["id"], animal["name"], animal["birth_date"]) == ("animal-demo-003", "Melati", "2024-04-02")
    assert animal["ownership_doc_refs"] == ["doc-ownership-003"]
    assert animal["confirmed_by"] == "A. Pratama"
    assert animal["confirmed_at"].endswith("Z")
    assert animal["coverage"]["status"] == "active"
    assert sorted(ref["view"] for ref in passport["references"]) == ["body", "muzzle", "teeth"]
    assert {(ref["media_url"], ref["crop_url"]) for ref in passport["references"]} == {(None, None)}
    assert {e["kind"]: e["source"] for e in passport["estimates"]} == {"age": "documented", "weight": "simulated"}
    [valuation] = passport["valuations"]
    assert (valuation["version"], valuation["weight_basis"], valuation["value_low_minor"]) == (1, "estimate", 228800)
    assert valuation["estimate_id"] == next(e["id"] for e in passport["estimates"] if e["kind"] == "weight")
    assert valuation["confirmed_by"] == "W. Santoso"
    [policy] = passport["policies"]
    assert (policy["product_id"], policy["product_name"], policy["status"]) == (
        "mortality-theft", "Mortality + Theft", "active")
    assert policy["insured_value_minor"] == 228800
    assert passport["applications"] == []
    assert passport["observations"]["count"] == 1
    assert passport["observations"]["last"]["camera_id"] == "cam-pen-b"
    assert [c["camera_id"] for c in passport["observations"]["cameras"]] == ["cam-pen-b"]
    assert (passport["alerts"], passport["incidents"], passport["claims"], passport["pending_actions"]) == (
        [], [], [], [])


def test_passport_passbook_reads_in_order(client):
    passbook = _passport(client, "animal-demo-003")["passbook"]

    lines = passbook["lines"]
    assert [line["no"] for line in lines] == list(range(1, len(lines) + 1))
    assert [line["at"] for line in lines] == sorted(line["at"] for line in lines)
    assert [line["title"] for line in lines] == ["Registered in herd", "Policy active · Mortality + Theft"]
    policy_line = lines[1]
    assert (policy_line["amount_minor"], policy_line["currency"], policy_line["status"]) == (228800, "USD", "posted")
    assert policy_line["stamp"] == {"kind": "posted", "by": "Demo seed", "at": policy_line["at"]}
    assert policy_line["actor"] == {"type": "system", "id": "seed", "name": "Demo seed"}
    assert policy_line["subject_type"] == "policy"
    assert {line["kind"] for line in lines} == {"event"}
    assert passbook["summary"] == {"exposure_low_minor": 228800, "exposure_high_minor": 266240,
                                   "insured_minor": 228800, "uninsured_low_minor": 0, "currency": "USD"}


def test_passport_shows_an_awaiting_action_last(client, pending_payment):
    passport = _passport(client, "animal-demo-005")

    last = passport["passbook"]["lines"][-1]
    assert last["no"] == len(passport["passbook"]["lines"])
    assert (last["kind"], last["status"], last["title"]) == ("awaiting", "awaiting", "Premium payment")
    assert (last["amount_minor"], last["currency"], last["stamp"]) == (15142, "USD", None)
    assert (last["action_id"], last["payload_hash_prefix"]) == ("act-000000000001", "abcdef01")
    assert last["expires_at"].endswith("Z")
    assert last["actor"] == {"type": "agent", "id": "veyra-agent", "name": "VEYRA agent"}
    [pending] = passport["pending_actions"]
    assert (pending["id"], pending["action_type"], pending["amount_minor"]) == (
        "act-000000000001", "PREMIUM_PAYMENT", 15142)
    assert passport["animal"]["pending_actions"] == 1
    assert passport["animal"]["coverage"] == {"status": "pending", "policy_id": None, "product_id": None,
                                              "policy_status": None}
    assert passport["passbook"]["summary"]["uninsured_low_minor"] == 291200


def test_pending_action_shows_in_the_herd(client, pending_payment):
    herd = _herd(client, coverage="pending")

    assert [item["id"] for item in herd["items"]] == ["animal-demo-005"]
    assert herd["summary"]["pending_approvals"] == 1
    assert herd["summary"]["uncovered_count"] == 2


def test_decided_actions_leave_the_passbook(client, pending_payment):
    with SessionLocal() as session:
        session.get(AgentAction, pending_payment.id).status = "declined"
        session.commit()

    passport = _passport(client, "animal-demo-005")

    assert {line["kind"] for line in passport["passbook"]["lines"]} == {"event"}
    assert passport["animal"]["coverage"]["status"] == "none"


def test_audit_events_newest_first_with_actor_names(client):
    response = client.get("/api/v1/audit-events", headers=VET, params={"animal_id": "animal-demo-002"})

    assert response.status_code == 200
    events = response.json()
    assert [e["event_type"] for e in events] == ["seed.policy_created", "seed.animal_created"]
    assert events[0]["actor"] == {"type": "system", "id": "seed", "name": "Demo seed"}
    assert events[0]["created_at"].endswith("Z")
    assert events[0]["data"]["product_id"] == "basic-mortality"


def test_audit_events_filters_and_limit(client):
    all_events = client.get("/api/v1/audit-events", headers=MANAGER).json()
    policies = client.get("/api/v1/audit-events", headers=MANAGER, params={"subject_type": "policy"}).json()
    one = client.get("/api/v1/audit-events", headers=MANAGER,
                     params={"subject_type": "policy", "subject_id": policies[0]["subject_id"]}).json()
    limited = client.get("/api/v1/audit-events", headers=MANAGER, params={"limit": 2}).json()

    assert len(all_events) == 7
    assert {e["event_type"] for e in policies} == {"seed.policy_created"}
    assert len(policies) == 2
    assert [e["id"] for e in one] == [policies[0]["id"]]
    assert [e["id"] for e in limited] == [e["id"] for e in all_events[:2]]
    assert client.get("/api/v1/audit-events", headers=MANAGER, params={"limit": 0}).status_code == 422
