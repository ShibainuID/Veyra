from datetime import timedelta
from types import SimpleNamespace

import pytest

from adapters.llm.query import QueryIntent
from config import get_settings
from domain import assistant, clock
from domain.assistant import ParsedQuery, parse, parse_offline, resolve, validate_refs
from persistence.db import read_session
from persistence.seed import reset_database

ANIMALS = [{"id": "animal-demo-001", "name": "Sari"}, {"id": "animal-demo-002", "name": "Bima"},
           {"id": "animal-demo-003", "name": "Melati"}, {"id": "animal-demo-005", "name": "Dewi"}]


@pytest.mark.parametrize("text, intent, refs, wants, unmatched", [
    ("Show me animal-demo-002", "animal_lookup", ["animal-demo-002"], ["passport"], []),
    ("Where was animal-demo-001 last seen, and what coverage is active?", "location_lookup", ["animal-demo-001"],
     ["location", "coverage"], []),
    ("Which animals have open alerts?", "alert_lookup", [], ["alerts"], []),
    ("Where is Dewi?", "location_lookup", ["animal-demo-005"], ["location"], []),
    ("where is 002", "location_lookup", ["animal-demo-002"], ["location"], []),
    ("Is BIMA insured, and does melati have alerts?", "coverage_lookup", ["animal-demo-002", "animal-demo-003"],
     ["coverage", "alerts"], []),
    ("bima", "animal_lookup", ["animal-demo-002"], ["passport"], []),
    ("Where is Bobo?", "location_lookup", [], ["location"], ["Bobo"]),
    ("Show me animal-demo-042", "animal_lookup", [], ["passport"], ["animal-demo-042"]),
    ("What's the weather?", "unknown", [], [], []),
])
def test_offline_parser(text, intent, refs, wants, unmatched):
    parsed, missing = parse_offline(text, ANIMALS)
    assert (parsed.intent, parsed.animal_refs, parsed.wants, missing) == (intent, refs, wants, unmatched)


def test_refs_are_validated_against_the_farm():
    assert validate_refs(["Sari", "animal-demo-002", "005", "animal-other-001", "sari"], ANIMALS) == (
        ["animal-demo-001", "animal-demo-002", "animal-demo-005"], ["animal-other-001"])


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _client(output):
    return SimpleNamespace(messages=FakeMessages(SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                                                                  parsed_output=output)))


def test_live_parser_output_is_used_and_refs_outside_the_farm_are_dropped():
    client = _client(QueryIntent(intent="location_lookup", animal_refs=["Sari", "animal-other-001"],
                                 wants=["location", "coverage"]))
    parsed = parse(get_settings(), "where's the brown one and is she covered", ANIMALS, client=client)
    assert (parsed.parsed_by, parsed.fallback_reason) == ("live", None)
    assert (parsed.intent.intent, parsed.intent.animal_refs, parsed.intent.wants) == (
        "location_lookup", ["animal-demo-001"], ["location", "coverage"])
    assert parsed.unmatched_refs == ["animal-other-001"]
    call = client.messages.calls[0]
    assert call["output_format"] is QueryIntent
    assert "<user_text>\nwhere's the brown one and is she covered\n</user_text>" in call["messages"][0]["content"]
    assert '"animal-demo-005"' in call["messages"][0]["content"] and "<records>" in call["messages"][0]["content"]


def test_live_parser_defaults_wants_from_the_intent():
    parsed = parse(get_settings(), "bima?", ANIMALS,
                   client=_client(QueryIntent(intent="animal_lookup", animal_refs=["animal-demo-002"], wants=[])))
    assert parsed.intent.wants == ["passport"]


def test_live_failure_falls_back_to_the_offline_parser():
    refusal = SimpleNamespace(messages=FakeMessages(SimpleNamespace(stop_reason="refusal", model="m",
                                                                    parsed_output=None)))
    parsed = parse(get_settings(), "Where is Dewi?", ANIMALS, client=refusal)
    assert (parsed.parsed_by, parsed.fallback_reason, parsed.intent.animal_refs) == (
        "simulated", "refusal", ["animal-demo-005"])


def test_offline_mode_reports_the_fallback_reason():
    parsed = parse(get_settings(), "Where is Dewi?", ANIMALS)
    assert (parsed.parsed_by, parsed.fallback_reason) == ("simulated", "llm_offline")


@pytest.fixture
def herd():
    reset_database("post-enrollment")


def _resolve(intent: str, refs: list[str], wants: list[str], unmatched: list[str] | None = None) -> dict:
    parsed = ParsedQuery(QueryIntent(intent=intent, animal_refs=refs, wants=wants), unmatched or [])
    with read_session() as session:
        return resolve(session, "farm-wahyu", parsed)


def test_resolver_reports_missing_observation_evidence(herd):
    result = _resolve("location_lookup", ["animal-demo-005"], ["location"])
    assert result["answer"] == "No camera observation is on record for Dewi (animal-demo-005)."
    assert result["missing"] == ["last_observation"]
    assert result["records"]["last_observations"] == []


def test_resolver_location_states_camera_and_time_and_flags_staleness(herd):
    fresh = _resolve("location_lookup", ["animal-demo-002"], ["location"])
    assert fresh["answer"].startswith("Bima (animal-demo-002) was last observed on Pen A · feed line at ")
    assert fresh["answer"].endswith("(2 min ago).")
    assert {f["record_type"] for f in fresh["facts"]} == {"camera", "observation"}

    stale = _resolve("location_lookup", ["animal-demo-004"], ["location"])
    assert "Pen B · water trough" in stale["answer"] and stale["answer"].endswith("It may have moved since.")


def test_resolver_coverage_and_unknown_animal(herd):
    covered = _resolve("coverage_lookup", ["animal-demo-002"], ["coverage"])
    assert covered["answer"].startswith("Active coverage for Bima: Basic Mortality & Accident with sandbox-insurer, "
                                        "insured value USD 2,704.00, 2026-09-01 to 2027-08-31.")
    assert [f["record_type"] for f in covered["facts"]] == ["policy", "policy", "policy"]

    none = _resolve("coverage_lookup", ["animal-demo-001"], ["coverage"])
    assert none["answer"] == "Sari has no active coverage." and none["missing"] == ["active_policy"]

    unknown = _resolve("location_lookup", [], ["location"], unmatched=["Bobo"])
    assert unknown["answer"] == "I couldn't find an animal matching 'Bobo' in this farm."


def test_resolver_unknown_intent_explains_what_it_can_answer(herd):
    result = _resolve("unknown", [], [])
    assert result["answer"] == assistant.FALLBACK_ANSWER and result["facts"] == []


def test_resolver_uses_the_clock(herd):
    clock.set_now(lambda: clock._system_now() + timedelta(hours=2))
    result = _resolve("location_lookup", ["animal-demo-002"], ["location"])
    assert result["answer"].endswith("It may have moved since.")
