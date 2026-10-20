from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from domain import clock
from persistence.db import SessionLocal
from persistence.models import (
    Alert, Animal, AuditEvent, Camera, DemoSettings, Estimate, Farm, Observation, Policy, Valuation, WalletEntry,
)


def _animal_count(session, farm_id: str) -> int:
    return session.scalar(select(func.count()).select_from(Animal).where(Animal.farm_id == farm_id))


def _wallet_balance(session, farm_id: str) -> int:
    entries = session.scalars(select(WalletEntry).where(WalletEntry.farm_id == farm_id)).all()
    return sum(e.amount_minor if e.entry_type == "credit" else -e.amount_minor for e in entries)


def _assert_fresh_counts(session):
    assert _animal_count(session, "farm-wahyu") == 5
    assert _animal_count(session, "farm-other") == 1
    assert session.scalar(select(func.count()).select_from(Camera)) == 3
    active = session.scalars(select(Policy).where(Policy.status == "active")).all()
    assert sorted(p.animal_id for p in active) == ["animal-demo-002", "animal-demo-003"]
    assert _wallet_balance(session, "farm-wahyu") == 978638


def test_lifespan_seeds_empty_database(app):
    with TestClient(app):
        with SessionLocal() as session:
            _assert_fresh_counts(session)
            assert session.get(DemoSettings, "farm-wahyu").payment_mode == "succeed"
            alert = session.scalars(select(Alert)).one()
            assert (alert.animal_id, alert.kind, alert.status) == ("animal-demo-004", "observation_quality", "open")
            assert session.scalar(select(func.count()).select_from(Observation)
                                  .where(Observation.animal_id == "animal-demo-005")) == 0
            events = session.scalars(select(AuditEvent.event_type)).all()
            assert events.count("seed.animal_created") == 6
            assert events.count("seed.policy_created") == 2


def test_lifespan_does_not_reseed_existing_database(app):
    with TestClient(app):
        pass
    with SessionLocal() as session:
        session.get(Farm, "farm-wahyu").name = "Renamed Farm"
        session.commit()
    with TestClient(app):
        with SessionLocal() as session:
            assert session.get(Farm, "farm-wahyu").name == "Renamed Farm"
            assert _animal_count(session, "farm-wahyu") == 5


def test_foreign_keys_are_enforced(client):
    with SessionLocal() as session:
        session.delete(session.get(Camera, "cam-pen-a"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_seeded_valuation_uses_floor_of_weight_times_price(client):
    with SessionLocal() as session:
        valuation = session.scalars(select(Valuation).where(Valuation.animal_id == "animal-demo-002")).one()
    assert (valuation.version, valuation.weight_basis) == (1, "estimate")
    assert (valuation.value_low_minor, valuation.value_high_minor) == (270400, 312000)
    assert valuation.price_date == date(2026, 10, 1)


def test_seeded_age_estimates_come_from_ml_adapter(client):
    with SessionLocal() as session:
        ages = session.scalars(select(Estimate).where(Estimate.kind == "age")).all()
    assert len(ages) == 6
    assert {a.source for a in ages} == {"documented"}
    assert {a.method_version for a in ages} == {"birth_record_v1"}
    bima = next(a for a in ages if a.animal_id == "animal-demo-002")
    today = clock.now().date()
    months = (today.year - 2023) * 12 + today.month - 8 - (today.day < 14)
    assert (bima.range_low, bima.range_high, bima.unit) == (months, months, "months")


def test_reset_is_idempotent(client):
    for _ in range(2):
        response = client.post("/api/v1/demo/reset")
        assert response.status_code == 200
        assert response.json() == {"status": "reset", "scenario": "fresh", "animals": 5}
    with SessionLocal() as session:
        _assert_fresh_counts(session)


def test_reset_post_enrollment_adds_sari(client):
    response = client.post("/api/v1/demo/reset", params={"scenario": "post-enrollment"})

    assert response.status_code == 200
    assert response.json() == {"status": "reset", "scenario": "post-enrollment", "animals": 6}
    with SessionLocal() as session:
        sari = session.get(Animal, "animal-demo-001")
        assert (sari.name, sari.identity_status, sari.birth_date) == ("Sari", "confirmed", None)
        assert sari.enrollment_id is not None
        valuation = session.scalars(select(Valuation).where(Valuation.animal_id == sari.id)).one()
        assert (valuation.value_low_minor, valuation.value_high_minor) == (249600, 291200)
        age = session.scalars(select(Estimate).where(Estimate.animal_id == sari.id, Estimate.kind == "age")).one()
        assert (age.range_low, age.range_high, age.source) == (24, 30, "simulated")
        assert session.scalar(select(func.count()).select_from(Policy).where(Policy.animal_id == sari.id)) == 0


def test_reset_rejects_unknown_scenario(client):
    response = client.post("/api/v1/demo/reset", params={"scenario": "chaos"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_reset_wipes_media(client, settings_env):
    stray = settings_env.media_dir / "farm-wahyu" / "stray.bin"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"x")

    client.post("/api/v1/demo/reset")

    assert not stray.exists()


def test_demo_settings_round_trip(client):
    assert client.get("/api/v1/demo/settings").json()["payment_mode"] == "succeed"

    response = client.put("/api/v1/demo/settings", json={"payment_mode": "timeout", "insurer_activation": "withhold"})

    assert response.status_code == 200
    body = client.get("/api/v1/demo/settings").json()
    assert (body["payment_mode"], body["insurer_activation"]) == ("timeout", "withhold")


def test_demo_settings_reject_invalid_value(client):
    response = client.put("/api/v1/demo/settings", json={"payment_mode": "maybe", "insurer_activation": "confirm"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_demo_routes_hidden_outside_demo_mode(monkeypatch, settings_env):
    from config import get_settings
    from main import create_app

    monkeypatch.setenv("VEYRA_DEMO_MODE", "0")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        for method, path in [("post", "/api/v1/demo/reset"), ("get", "/api/v1/demo/settings"),
                             ("put", "/api/v1/demo/settings")]:
            response = client.request(method, path, json={"payment_mode": "succeed", "insurer_activation": "confirm"})
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "NOT_FOUND"
