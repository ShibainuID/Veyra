import json
from datetime import UTC, datetime, timedelta

import pytest

from config import get_settings
from domain.movement import (
    DEFAULT_CONFIG, MovementConfig, Sample, alert_summary, assess, in_cooldown, rule_json, speed, window_applies,
    window_stats, windows,
)

FPS = 2
WINDOW = 30


def _walk(start: float, end: float, step_per_s: float, visibility: float = 0.9, every: float = 0.5) -> list[Sample]:
    samples, t, x = [], start, 0.1
    while t < end - 1e-9:
        samples.append(Sample(t, [x, 0.4, 0.2, 0.2], visibility))
        x += step_per_s * every
        t += every
    return samples


def _stats(samples, start=0.0):
    return window_stats(samples, start_s=start, window_s=WINDOW, fps=FPS)


def test_speed_is_mean_centroid_displacement_per_second():
    samples = [Sample(0, [0.1, 0.1, 0.2, 0.2], 1), Sample(0.5, [0.11, 0.1, 0.2, 0.2], 1),
               Sample(1.0, [0.11, 0.13, 0.2, 0.2], 1)]
    assert speed(samples) == pytest.approx((0.02 + 0.06) / 2)
    assert speed(samples[:1]) is None


def test_windows_align_to_scenario_time():
    assert windows(180, 30) == [(0, 30), (30, 60), (60, 90), (90, 120), (120, 150), (150, 180)]


def test_usable_window_needs_visibility_and_coverage():
    full = _stats(_walk(0, 30, 0.01))
    assert (full.frames, full.expected_frames, full.coverage, full.usable) == (60, 60, 1.0, True)

    dim = _stats(_walk(0, 30, 0.01, visibility=0.55))
    assert (dim.usable, dim.reasons) == (False, ("low_visibility",))

    sparse = _stats(_walk(0, 30, 0.01, every=1.0))  # 30 of 60 expected frames
    assert (sparse.coverage, sparse.usable, sparse.reasons) == (0.5, False, ("low_coverage",))

    # Exactly 70% coverage and visibility exactly 0.6 is still usable.
    edge = _stats([Sample(s.t, s.bbox, 0.6) for s in _walk(0, 21, 0.01)])
    assert (edge.coverage, edge.mean_visibility, edge.usable) == (0.7, 0.6, True)

    empty = _stats([])
    assert (empty.usable, empty.mean_visibility, empty.speed) == (False, None, None)


def test_first_usable_window_is_the_baseline():
    stats = _stats(_walk(0, 30, 0.01))
    assert assess(stats, associated=True, baseline=None).outcome == "baseline"


def test_reduced_movement_below_baseline_times_one_minus_threshold():
    baseline = _stats(_walk(0, 30, 0.010))
    slow = _stats(_walk(30, 60, 0.0035), start=30)  # 65% lower
    slightly_slow = _stats(_walk(30, 60, 0.0045), start=30)  # 55% lower

    reduced = assess(slow, associated=True, baseline=baseline)
    assert reduced.outcome == "reduced_movement" and reduced.raises_alert
    assert reduced.score == pytest.approx(0.65, abs=0.01)
    assert assess(slightly_slow, associated=True, baseline=baseline).outcome == "normal"
    stricter = MovementConfig(threshold=0.5)
    assert assess(slightly_slow, associated=True, baseline=baseline, config=stricter).outcome == "reduced_movement"


def test_unassociated_track_never_raises_reduced_movement():
    baseline = _stats(_walk(0, 30, 0.010))
    slow = _stats(_walk(30, 60, 0.001), start=30)
    assert assess(slow, associated=False, baseline=baseline).outcome == "unassessed"


def test_unusable_window_warns_the_animal_or_the_track():
    dim = _stats(_walk(0, 30, 0.01, visibility=0.4))
    on_animal = assess(dim, associated=True, baseline=None)
    on_track = assess(dim, associated=False, baseline=None)
    assert (on_animal.outcome, on_animal.subject) == ("observation_quality", "animal")
    assert (on_track.outcome, on_track.subject) == ("observation_quality", "track")


def test_window_associated_partway_is_skipped_unless_its_associated_frames_are_usable():
    short = _stats(_walk(20, 30, 0.01))  # associated at 20 s: 20 of 60 frames
    assert assess(short, associated=True, baseline=None, partial_association=True).outcome == "unassessed"
    assert assess(short, associated=True, baseline=None).outcome == "observation_quality"
    enough = _stats(_walk(4, 30, 0.01))  # associated at 4 s: 52 of 60 frames
    assert assess(enough, associated=True, baseline=None, partial_association=True).outcome == "baseline"


def test_partial_windows_at_track_start_or_loss_are_not_assessed():
    kwargs = {"start_s": 60, "end_s": 90, "frame_interval_s": 0.5}
    assert window_applies(first_seen_s=0, lost_at_s=None, **kwargs)
    assert window_applies(first_seen_s=60, lost_at_s=90, **kwargs)
    assert not window_applies(first_seen_s=75, lost_at_s=None, **kwargs)
    assert not window_applies(first_seen_s=0, lost_at_s=70, **kwargs)


def test_cooldown_dedupes_within_ten_minutes_either_side():
    end = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    assert in_cooldown([end - timedelta(minutes=9, seconds=59)], end)
    assert in_cooldown([end + timedelta(minutes=2)], end)
    assert not in_cooldown([end - timedelta(minutes=10)], end)
    assert not in_cooldown([], end)
    assert DEFAULT_CONFIG.cooldown == timedelta(minutes=10)


def test_rule_json_and_summary_are_transparent_and_not_a_diagnosis():
    baseline = _stats(_walk(0, 30, 0.010))
    slow = _stats(_walk(90, 120, 0.0022), start=90)
    assessment = assess(slow, associated=True, baseline=baseline)
    rule = rule_json(assessment, slow, WINDOW)
    assert rule["name"] == "reduced_movement_v1"
    assert (rule["threshold"], rule["window_s"], rule["source"], rule["coverage"]) == (0.6, 30, "simulated", 1.0)
    assert rule["baseline"] == pytest.approx(0.01, abs=1e-4) and rule["score"] == pytest.approx(0.78, abs=0.01)
    assert rule["text"] == "reduced tracked movement versus this animal's earlier window"
    start = datetime(2026, 10, 20, 9, 31, tzinfo=UTC)
    text = alert_summary(kind="reduced_movement", rule=rule, camera_name="Pen A · feed line", window_start=start,
                         window_end=start + timedelta(seconds=30), animal_name="Sari")
    assert text == ("Movement 78% below Sari's earlier window on Pen A · feed line (09:31–09:31 UTC). "
                    "Inspection recommended; this is not a diagnosis.")

    dim = _stats(_walk(0, 30, 0.01, visibility=0.45))
    quality = rule_json(assess(dim, associated=False, baseline=None), dim, WINDOW)
    assert (quality["name"], quality["reasons"], quality["mean_visibility"]) == (
        "observation_quality_v1", ["low_visibility"], 0.45)
    warning = alert_summary(kind="observation_quality", rule=quality, camera_name="Pen B · water trough",
                            window_start=start, window_end=start, track_key="t-14")
    assert "unidentified track t-14" in warning and "mean visibility 45%" in warning
    assert "not a diagnosis" in warning


def _scenario(name: str) -> dict:
    return json.loads((get_settings().scenarios_dir / f"{name}.json").read_text(encoding="utf-8"))


def _track_windows(scenario: dict, key: str) -> list:
    track = next(t for t in scenario["tracks"] if t["track_key"] == key)
    samples = [Sample(f["t"], f["bbox"], f["visibility"]) for f in track["frames"]]
    return [window_stats(samples, start_s=a, window_s=scenario["window_s"], fps=scenario["fps"])
            for a, _ in windows(scenario["duration_s"], scenario["window_s"])]


@pytest.mark.parametrize("name, camera", [("healthy", "cam-pen-a"), ("anomaly", "cam-pen-a"),
                                          ("lost_identity", "cam-pen-b")])
def test_scenario_fixture_format(name, camera):
    scenario = _scenario(name)
    assert (scenario["id"], scenario["camera_id"], scenario["source"]) == (name, camera, "simulated")
    assert (scenario["duration_s"], scenario["fps"], scenario["window_s"], scenario["clip"]) == (180, 2, 30, None)
    for track in scenario["tracks"]:
        for frame in track["frames"]:
            x, y, w, h = frame["bbox"]
            assert 0 <= x and 0 <= y and x + w <= 1 and y + h <= 1 and 0 <= frame["visibility"] <= 1


def test_healthy_scenario_movement_stays_above_the_threshold():
    scenario = _scenario("healthy")
    for key in ("t-01", "t-02"):
        stats = _track_windows(scenario, key)
        assert all(s.usable for s in stats)
        assert all(assess(s, associated=True, baseline=stats[0]).outcome == "normal" for s in stats[1:])


def test_anomaly_scenario_drops_more_than_seventy_percent_from_ninety_seconds():
    stats = _track_windows(_scenario("anomaly"), "t-01")
    baseline = stats[0]
    outcomes = [assess(s, associated=True, baseline=baseline).outcome for s in stats[1:]]
    assert outcomes == ["normal", "normal", "reduced_movement", "reduced_movement", "reduced_movement"]
    assert all(s.speed < baseline.speed * 0.3 and s.mean_visibility >= 0.8 for s in stats[3:])


def test_lost_identity_scenario_has_one_low_visibility_window_for_the_new_track():
    scenario = _scenario("lost_identity")
    t14 = next(t for t in scenario["tracks"] if t["track_key"] == "t-14")
    assert t14["events"] == [] and t14["frames"][0]["t"] == 75
    stats = _track_windows(scenario, "t-14")
    assert [s.usable for s in stats[3:]] == [False, True, True]
    t03 = next(t for t in scenario["tracks"] if t["track_key"] == "t-03")
    assert [e["type"] for e in t03["events"]] == ["muzzle_match", "track_lost"]
    assert t03["events"][1] == {"t": 70, "type": "track_lost", "reason": "occlusion"}
