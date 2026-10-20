from types import SimpleNamespace

from adapters.llm.explain import ExplanationItemModel, PolicyExplanation, explain
from config import get_settings
from domain.catalog import get_product, load_catalog
from domain.insurance import evaluate_product

FACTS = {"identity_status": "confirmed", "age_months_low": 24, "age_months_high": 30, "valuation_confirmed": True,
         "ownership_document": None, "breed_category": "beef", "vet_health_check_days": None}
ANIMAL = {"id": "animal-demo-001", "name": "Sari", "breed": "Bali cattle"}


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _results():
    catalog = load_catalog()
    return [evaluate_product(p, FACTS, 249600, "USD") for p in catalog["products"]]


def _client(stop_reason="end_turn", parsed=None):
    return SimpleNamespace(messages=FakeMessages(SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5",
                                                                 parsed_output=parsed)))


def _explain(client=None):
    return explain(get_settings(), animal=ANIMAL, results=_results(), catalog=load_catalog(),
                   insured_value_minor=249600, currency="USD", client=client)


def test_grounding_drops_bogus_product_and_terms_ref():
    parsed = PolicyExplanation(summary="ok", caveats=["not a payout"], items=[
        ExplanationItemModel(product_id="basic-mortality", explanation="Eligible.",
                             terms_refs=["sample-v1 §2.1", "sample-v9 §99"]),
        ExplanationItemModel(product_id="platinum-unicorn", explanation="Made up.", terms_refs=["sample-v1 §2.1"]),
    ])
    client = _client(parsed=parsed)

    result = _explain(client)

    assert result["source"] == "live" and result["grounding_dropped"] is True
    assert [item["product_id"] for item in result["items"]] == ["basic-mortality"]
    assert result["items"][0]["terms_refs"] == ["sample-v1 §2.1"]
    call = client.messages.calls[0]
    assert "<records>" in call["messages"][0]["content"]
    assert "never change an outcome" in call["system"].lower()


def test_clean_live_output_is_not_flagged():
    parsed = PolicyExplanation(summary="ok", caveats=[], items=[
        ExplanationItemModel(product_id="mortality-theft", explanation="Needs a document.", terms_refs=["sample-v1 §2.4"])])
    result = _explain(_client(parsed=parsed))
    assert (result["source"], result["grounding_dropped"]) == ("live", False)


def test_refusal_falls_back_to_template():
    result = _explain(_client(stop_reason="refusal"))
    assert (result["source"], result["fallback_reason"]) == ("simulated", "refusal")
    assert len(result["items"]) == 3


def test_offline_template_states_outcomes_and_prices():
    result = _explain()

    assert (result["source"], result["fallback_reason"], result["grounding_dropped"]) == (
        "simulated", "llm_offline", False)
    items = {item["product_id"]: item for item in result["items"]}
    assert items["basic-mortality"]["explanation"].startswith("Basic Mortality & Accident: eligible")
    assert "87.36 USD" in items["basic-mortality"]["explanation"]
    assert "Add an ownership document reference" in items["mortality-theft"]["explanation"]
    assert items["mortality-theft"]["terms_refs"] == ["sample-v1 §2.4"]
    assert "not eligible" in items["dairy-health-plus"]["explanation"]
    assert items["dairy-health-plus"]["terms_refs"] == ["sample-v1 §2.5"]
    assert "1 eligible, 1 need review, and 1 not eligible" in result["summary"]
    assert any("not an insurer-agreed value" in caveat for caveat in result["caveats"])
    product = get_product(load_catalog(), "basic-mortality")
    assert product["premium"]["rate_bps"] == 350
