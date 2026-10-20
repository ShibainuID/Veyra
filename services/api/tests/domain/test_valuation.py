from datetime import date

import pytest
from sqlalchemy import select

from domain import valuation
from domain.auth import Principal
from domain.errors import DomainError
from persistence.db import SessionLocal
from persistence.models import AuditEvent, Estimate
from tests.support import MANAGER, OPERATOR, VET

MANAGER_PRINCIPAL = Principal(user_id="user-manager", farm_id="farm-wahyu", role="manager", name="W. Santoso")
PRICE = {"unit_price_minor_per_kg": 520, "price_source": "Demo reference price (fictional)",
         "price_date": date(2026, 10, 1)}


@pytest.mark.parametrize(("kg", "price", "expected"), [
    (480, 520, 249600), (560, 520, 291200), (480.5, 520, 249860), (0.333, 100, 33), (612.07, 333, 203819),
])
def test_value_is_floor_of_kg_times_price(kg, price, expected):
    assert valuation.value_minor(kg, price) == expected


def test_value_uses_decimal_not_float():
    # 0.1 * 30 in float is 3.0000000000000004; 1.1 * 3 is 3.3000000000000003. Decimal keeps the exact floor.
    assert valuation.value_minor(1.1, 3) == 3
    assert valuation.value_minor(0.29, 100) == 29  # float 0.29 * 100 == 28.999999999999996


def test_estimate_basis_uses_latest_weight_range_and_bumps_version(client):
    with SessionLocal() as session:
        first = valuation.confirm(session, MANAGER_PRINCIPAL, "animal-demo-002", weight_basis="estimate", **PRICE)
        second = valuation.confirm(session, MANAGER_PRINCIPAL, "animal-demo-002", weight_basis="estimate",
                                   **{**PRICE, "unit_price_minor_per_kg": 600})
        session.commit()
    assert (first.version, second.version) == (2, 3)  # the seed holds version 1
    assert (first.weight_low_kg, first.weight_high_kg) == (520, 600)
    assert (first.value_low_minor, first.value_high_minor) == (270400, 312000)
    assert (second.value_low_minor, second.value_high_minor) == (312000, 360000)
    assert first.confirmed_by == "user-manager" and first.estimate_id is not None


def test_override_keeps_original_estimate_in_audit(client):
    with SessionLocal() as session:
        row = valuation.confirm(session, MANAGER_PRINCIPAL, "animal-demo-002", weight_basis="override",
                                weight_low_kg=500, weight_high_kg=540, **PRICE)
        session.commit()
        event = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "valuation.confirmed")).one()
    assert (row.weight_basis, row.value_low_minor, row.value_high_minor) == ("override", 260000, 280800)
    assert event.actor_type == "user" and event.actor_id == "user-manager"
    assert event.data["override"] == {"low_kg": 500, "high_kg": 540}
    assert event.data["original_estimate"]["low_kg"] == 520
    assert event.data["original_estimate"]["high_kg"] == 600


@pytest.mark.parametrize(("low", "high"), [(600, 500), (0, 500), (None, 500)])
def test_override_range_is_validated(client, low, high):
    with SessionLocal() as session, pytest.raises(DomainError) as err:
        valuation.confirm(session, MANAGER_PRINCIPAL, "animal-demo-002", weight_basis="override",
                          weight_low_kg=low, weight_high_kg=high, **PRICE)
    assert err.value.code == "VALIDATION_FAILED"


def test_estimate_basis_without_estimate_is_invalid_state(client):
    with SessionLocal() as session:
        for estimate in session.scalars(select(Estimate).where(Estimate.animal_id == "animal-demo-002",
                                                               Estimate.kind == "weight")):
            estimate.range_low = estimate.range_high = None
        session.commit()
    with SessionLocal() as session, pytest.raises(DomainError) as err:
        valuation.confirm(session, MANAGER_PRINCIPAL, "animal-demo-002", weight_basis="estimate", **PRICE)
    assert err.value.code == "INVALID_STATE"


def test_other_farm_animal_is_not_found(client):
    with SessionLocal() as session, pytest.raises(DomainError) as err:
        valuation.confirm(session, MANAGER_PRINCIPAL, "animal-other-001", weight_basis="estimate", **PRICE)
    assert err.value.code == "NOT_FOUND"


def _body(**extra):
    return {"weight_basis": "estimate", "unit_price_minor_per_kg": 520, "price_source": "Demo reference price",
            "price_date": "2026-10-01", **extra}


def test_route_confirms_and_passbook_shows_valued_line(client):
    reset = client.post("/api/v1/demo/reset", params={"scenario": "post-enrollment"}, headers=MANAGER)
    assert reset.status_code == 200, reset.text
    response = client.post("/api/v1/animals/animal-demo-001/valuations", json=_body(), headers=OPERATOR)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["version"], body["value_low_minor"], body["value_high_minor"]) == (2, 249600, 291200)
    assert body["created_at"].endswith("Z")
    passport = client.get("/api/v1/animals/animal-demo-001/passport", headers=MANAGER).json()
    line = [line for line in passport["passbook"]["lines"] if line["event_type"] == "valuation.confirmed"][-1]
    assert line["title"] == "Valued"
    assert line["detail"] == "480–560 kg × 5.20 USD/kg = 2,496.00–2,912.00 USD · price 2026-10-01"
    assert line["amount_minor"] == 249600


def test_route_rejects_vet_and_other_farm(client):
    assert client.post("/api/v1/animals/animal-demo-002/valuations", json=_body(), headers=VET).status_code == 403
    other = client.post("/api/v1/animals/animal-other-001/valuations", json=_body(), headers=MANAGER)
    assert other.status_code == 404


def test_route_validates_override(client):
    response = client.post("/api/v1/animals/animal-demo-002/valuations", headers=MANAGER,
                           json=_body(weight_basis="override", weight_low_kg=600, weight_high_kg=500))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
