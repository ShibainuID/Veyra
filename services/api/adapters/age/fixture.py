"""Age adapter for the demo (PRD Section 4.2): precomputed estimates, never live inference.

Priority: documented birth date > precomputed fixture for the selected sample > review required.
The teeth frame from the enrollment video is always attached as evidence, because the passport must
show what an assessor would inspect even when the number itself is simulated.
"""

import json
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[4] / "demo" / "fixtures" / "age_estimates.json"


def _months_between(born: date, on: date) -> int:
    return (on.year - born.year) * 12 + on.month - born.month - (on.day < born.day)


def estimate_age(
    sample_key: str,
    teeth_frame_ids: list[str],
    documented_birth_date: date | None = None,
    observed_on: date | None = None,
    fixtures_path: Path = FIXTURES,
) -> dict:
    base = {"evidence_frame_ids": teeth_frame_ids, "unit": "months", "review_required": False, "review_reason": None}
    if documented_birth_date:
        months = _months_between(documented_birth_date, observed_on or date.today())
        return {**base, "source": "documented", "method_version": "birth_record_v1",
                "range_low": months, "range_high": months, "dentition_stage": None}

    fixtures = json.loads(fixtures_path.read_text()) if fixtures_path.exists() else {}
    entry = fixtures.get(sample_key)
    if entry is None:
        return {**base, "source": "simulated", "method_version": "age_fixture_v1", "range_low": None, "range_high": None,
                "dentition_stage": None, "review_required": True, "review_reason": "no_fixture_for_sample"}
    result = {**base, "source": "simulated", "method_version": "age_fixture_v1",
              "range_low": entry["months_low"], "range_high": entry["months_high"],
              "dentition_stage": entry["dentition_stage"], "fixture_note": entry["note"]}
    if not teeth_frame_ids:
        result.update(review_required=True, review_reason="teeth_view_missing")
    return result
