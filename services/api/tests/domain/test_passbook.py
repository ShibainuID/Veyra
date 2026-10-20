from datetime import timedelta

import pytest

from domain import audit, clock, passbook
from domain.passbook import build_passbook, generic_title, register_formatter
from persistence.db import SessionLocal, init_db, read_session
from persistence.seed import seed_if_empty

ANIMAL = "animal-demo-006"


@pytest.fixture(autouse=True)
def seeded():
    init_db()
    seed_if_empty()


@pytest.fixture
def formatters(monkeypatch):
    monkeypatch.setattr(passbook, "_FORMATTERS", dict(passbook._FORMATTERS))


def _record(event_type: str, data: dict | None = None, actor=("user", "user-vet")) -> None:
    with SessionLocal() as session:
        audit.record(session, farm_id="farm-wahyu", actor_type=actor[0], actor_id=actor[1], event_type=event_type,
                     subject_type="animal", subject_id=ANIMAL, animal_id=ANIMAL, data=data)
        session.commit()


def _lines() -> list[dict]:
    with read_session() as session:
        return build_passbook(session, "farm-wahyu", ANIMAL)


@pytest.mark.parametrize("event_type, title", [
    ("seed.policy_created", "Policy created"),
    ("alert.created", "Alert created"),
    ("claim.ready_for_review", "Claim ready for review"),
    ("weigh_in", "Weigh in"),
])
def test_generic_title(event_type, title):
    assert generic_title(event_type) == title


def test_unknown_event_gets_a_generic_line():
    _record("health.check_recorded", {"note": "ok"})

    line = _lines()[-1]

    assert (line["title"], line["detail"], line["stamp"], line["amount_minor"]) == (
        "Health check recorded", None, None, None)
    assert (line["kind"], line["status"], line["event_type"]) == ("event", "posted", "health.check_recorded")
    assert line["actor"] == {"type": "user", "id": "user-vet", "name": "dr. R. Lestari"}


def test_registered_formatter_shapes_the_line(formatters):
    @register_formatter("health.check_recorded")
    def _check(event, ctx):
        return {"title": f"Health check · {event.data['result']}", "amount_minor": 2500, "currency": "USD",
                "stamp": {"kind": "confirmed"}}

    _record("health.check_recorded", {"result": "fit"})

    line = _lines()[-1]

    assert (line["title"], line["amount_minor"], line["currency"]) == ("Health check · fit", 2500, "USD")
    assert line["stamp"] == {"kind": "confirmed", "by": "dr. R. Lestari", "at": line["at"]}


def test_register_formatter_as_a_call(formatters):
    register_formatter("health.void_entry", lambda event, ctx: {"title": "Voided", "status": "void"})
    _record("health.void_entry")

    assert (_lines()[-1]["title"], _lines()[-1]["status"]) == ("Voided", "void")


def test_formatter_with_an_unknown_field_is_a_bug(formatters):
    register_formatter("health.bad", lambda event, ctx: {"titel": "typo"})
    _record("health.bad")

    with pytest.raises(ValueError, match="titel"):
        _lines()


def test_events_with_the_same_time_keep_insert_order():
    frozen = clock.now() + timedelta(hours=1)
    clock.set_now(lambda: frozen)
    for step in ("first", "second", "third"):
        _record(f"test.{step}")

    titles = [line["title"] for line in _lines()]

    assert titles[-3:] == ["Test first", "Test second", "Test third"]
    assert [line["no"] for line in _lines()] == list(range(1, len(titles) + 1))


def test_other_farm_events_are_not_in_the_passbook():
    with SessionLocal() as session:
        audit.record(session, farm_id="farm-other", actor_type="system", actor_id="seed", event_type="test.leak",
                     subject_type="animal", subject_id=ANIMAL, animal_id=ANIMAL)
        session.commit()

    assert "test.leak" not in {line["event_type"] for line in _lines()}


def test_record_rejects_unknown_actor_type():
    with SessionLocal() as session:
        with pytest.raises(ValueError, match="actor_type"):
            audit.record(session, farm_id="farm-wahyu", actor_type="robot", actor_id="r2", event_type="x.y",
                         subject_type="animal", subject_id=ANIMAL)
