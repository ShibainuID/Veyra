"""Eligibility reads open health alerts: dairy-health-plus needs no open reduced-movement alert at application."""

from tests.integration.test_financial_flow import API, SARI, _alert, sari
from tests.support import OPERATOR

__all__ = ["sari"]  # the fixture is imported for use here


def _results(client) -> dict:
    response = client.post(f"{API}/animals/{SARI}/insurance-recommendations", headers=OPERATOR)
    assert response.status_code == 200, response.text
    return {r["product_id"]: r for r in response.json()["results"]}


def _rule(result: dict) -> dict:
    return next(reason for reason in result["reasons"] if reason["field"] == "open_health_alerts")


def test_open_reduced_movement_alert_fails_the_dairy_health_rule(sari):
    before = _results(sari)
    assert _rule(before["dairy-health-plus"])["status"] == "pass"

    _alert(SARI)
    after = _results(sari)

    rule = _rule(after["dairy-health-plus"])
    assert rule["status"] == "fail" and rule["terms_ref"] == "sample-v1 §2.8"
    assert rule["detail"] == "open_health_alerts is 1"
    assert after["dairy-health-plus"]["outcome"] == "ineligible"
    for product_id in ("basic-mortality", "mortality-theft"):
        assert after[product_id]["outcome"] == before[product_id]["outcome"]
        assert all(reason["field"] != "open_health_alerts" for reason in after[product_id]["reasons"])
