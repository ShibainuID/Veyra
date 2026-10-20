from datetime import date

import pytest
from sqlalchemy import func, select

from adapters.sandbox import ProviderTimeout, insurer, lookup, payment
from domain import wallet
from domain.actions import payload_hash
from domain.canonical import canonical_json
from persistence.db import SessionLocal
from persistence.models import DemoSettings, ProviderRecord


def test_payload_hash_is_stable_regardless_of_key_order():
    a = {"animal_id": "animal-demo-001", "premium_minor": 8736, "disclosed_fields": ["a", "b"], "currency": "USD"}
    b = {"currency": "USD", "disclosed_fields": ["a", "b"], "premium_minor": 8736, "animal_id": "animal-demo-001"}
    assert payload_hash(a) == payload_hash(b)
    assert canonical_json(a) == '{"animal_id":"animal-demo-001","currency":"USD","disclosed_fields":["a","b"],' \
                                '"premium_minor":8736}'
    assert payload_hash({**a, "premium_minor": 8737}) != payload_hash(a)
    assert len(payload_hash(a)) == 64


def test_one_year_cover():
    assert insurer.one_year_cover(date(2026, 10, 20)) == date(2027, 10, 19)
    assert insurer.one_year_cover(date(2028, 2, 29)) == date(2029, 2, 28)


def _set_mode(session, **values):
    row = session.get(DemoSettings, "farm-wahyu")
    for key, value in values.items():
        setattr(row, key, value)


PAYLOAD = {"amount_minor": 8736, "currency": "USD"}


def test_charge_is_idempotent_per_key(client):
    with SessionLocal() as session:
        first = payment.charge(session, "key-1", PAYLOAD, farm_id="farm-wahyu")
        again = payment.charge(session, "key-1", PAYLOAD, farm_id="farm-wahyu")
        other = payment.charge(session, "key-2", PAYLOAD, farm_id="farm-wahyu")
        session.commit()
        count = session.scalar(select(func.count()).select_from(ProviderRecord))
    assert first == again and first["status"] == "succeeded"
    assert other["payment_ref"] != first["payment_ref"]
    assert count == 2


def test_charge_decline_is_recorded(client):
    with SessionLocal() as session:
        _set_mode(session, payment_mode="fail")
        response = payment.charge(session, "key-f", PAYLOAD, farm_id="farm-wahyu")
        assert response == {"status": "declined", "code": "SANDBOX_DECLINED",
                            "message": "The sandbox payment was declined."}
        assert lookup(session, payment.PROVIDER, payment.OPERATION, "key-f").response["status"] == "declined"


def test_charge_timeout_records_a_landed_charge(client):
    with SessionLocal() as session:
        _set_mode(session, payment_mode="timeout")
        with pytest.raises(ProviderTimeout):
            payment.charge(session, "key-t", PAYLOAD, farm_id="farm-wahyu")
        record = lookup(session, payment.PROVIDER, payment.OPERATION, "key-t")
        assert record.request == PAYLOAD and record.response["status"] == "succeeded"
        # A repeat with the same key returns the stored result instead of charging or timing out again.
        assert payment.charge(session, "key-t", PAYLOAD, farm_id="farm-wahyu")["status"] == "succeeded"


def test_wallet_balance_counts_holds_and_releases(client):
    with SessionLocal() as session:
        assert wallet.balance(session, "farm-wahyu") == 978638
        wallet.post(session, "farm-wahyu", "hold", 1000, "hold")
        assert wallet.summary(session, "farm-wahyu") == {"balance_minor": 978638, "held_minor": 1000,
                                                          "available_minor": 977638, "currency": "USD"}
        wallet.post(session, "farm-wahyu", "release", 1000, "release")
        wallet.post(session, "farm-wahyu", "debit", 1000, "debit")
        session.flush()
        assert wallet.summary(session, "farm-wahyu")["available_minor"] == 977638
        assert wallet.summary(session, "farm-wahyu")["held_minor"] == 0
        with pytest.raises(ValueError):
            wallet.post(session, "farm-wahyu", "debit", 0, "zero")
