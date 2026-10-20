"""Scan-zone handoff and identity continuity (handoff_v2, ml/results/handoff_policy.md) on cam-pen-a's seeded zone."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from domain import association
from domain.association import ObservationInput, ZoneScanInput, ingest, zone_scan
from domain.errors import DomainError
from persistence.db import SessionLocal, read_session
from persistence.models import AuditEvent, Observation, Track
from persistence.seed import reset_database

FARM = "farm-wahyu"
CAMERA = "cam-pen-a"
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
IN_ZONE = [0.52, 0.68, 0.12, 0.1]  # centre (0.58, 0.73): inside cam-pen-a's scan zone
IN_ZONE_2 = [0.6, 0.72, 0.08, 0.08]  # centre (0.64, 0.76): also inside, barely overlapping IN_ZONE
ON_TOP = [0.53, 0.69, 0.12, 0.1]  # IoU with IN_ZONE ~0.71
OUTSIDE = [0.1, 0.1, 0.2, 0.2]


@pytest.fixture(autouse=True)
def seeded():
    reset_database("post-enrollment")


def _feed(*items: ObservationInput) -> list[Observation]:
    with SessionLocal() as session:
        rows = [ingest(session, farm_id=FARM, camera_id=CAMERA, item=item) for item in items]
        session.commit()
    return rows


def _at(key: str, s: float, bbox: list[float]) -> ObservationInput:
    return ObservationInput(track_key=key, observed_at=T0 + timedelta(seconds=s), bbox=bbox, visibility=0.9)


def _scan(s: float, animal_id: str | None = "animal-demo-001", inliers: int = 31, quality: float = 0.88,
          camera: str = CAMERA):
    with SessionLocal() as session:
        result = zone_scan(session, farm_id=FARM, camera_id=camera, scan=ZoneScanInput(
            observed_at=T0 + timedelta(seconds=s), animal_id=animal_id, inliers=inliers, quality=quality))
        session.commit()
    return result


def _track(key: str) -> Track:
    with read_session() as session:
        return session.scalar(select(Track).where(Track.track_key == key, Track.replay_id.is_(None)))


def _stored(rows: list[Observation], track_id: str) -> list[tuple[float, str | None]]:
    with read_session() as session:
        found = [session.get(Observation, r.id) for r in rows]
    return [(round((o.observed_at - T0).total_seconds(), 2), o.animal_id) for o in found if o.track_id == track_id]


def test_policy_constants_match_handoff_v2():
    assert (association.MAX_GAP_S, association.CROWD_IOU, association.CROWD_S) == (1.0, 0.6, 0.25)
    assert association.HANDOFF_POLICY == "handoff_v2"


def test_one_track_in_the_zone_is_identified_by_the_scan():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, OUTSIDE))
    result = _scan(0.4)
    assert (result.outcome, result.track_keys) == ("associated", ["z-1"])
    track = _track("z-1")
    assert (track.association_status, track.animal_id, track.association_method) == (
        "associated", "animal-demo-001", "zone_handoff")
    evidence = track.association_evidence
    assert (evidence["tracks_in_zone"], evidence["inliers"], evidence["quality"]) == (1, 31, 0.88)
    assert evidence["zone"][0] == [0.4781, 0.6611]
    with read_session() as session:
        stored = session.get(Observation, result.observation.id)
        event = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "track.associated"))
        scan = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "camera.zone_scan"))
    assert (stored.event, stored.animal_id) == ("zone_scan", "animal-demo-001")
    assert (event.data["method"], event.data["tracks_in_zone"]) == ("zone_handoff", 1)
    assert (scan.data["outcome"], scan.subject_id) == ("associated", CAMERA)
    after, = _feed(_at("z-1", 0.5, IN_ZONE))
    assert after.animal_id == "animal-demo-001"
    assert _track("z-2").association_status == "unassigned"


def test_two_tracks_in_the_zone_identify_nobody_and_become_uncertain():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, IN_ZONE_2))
    result = _scan(0.4)
    assert (result.outcome, result.track_keys, result.observation) == ("crowded", ["z-1", "z-2"], None)
    for key in ("z-1", "z-2"):
        track = _track(key)
        assert (track.association_status, track.animal_id) == ("uncertain", None)
        assert track.association_evidence["message"] == "2 animals in the scan zone — scan one animal at a time."
        assert track.association_evidence["tracks_in_zone"] == 2
    later = _feed(_at("z-1", 0.5, IN_ZONE), _at("z-2", 0.5, OUTSIDE))
    assert all(o.animal_id is None and o.association_status == "uncertain" for o in later)
    # Never re-attached automatically: z-1 alone in the zone later is still not identified.
    assert _scan(0.8).outcome == "track_uncertain"
    assert _track("z-1").animal_id is None


def test_an_empty_zone_identifies_nobody():
    _feed(_at("z-2", 0, OUTSIDE))
    result = _scan(0.4)
    assert (result.outcome, result.reason, result.track_keys) == ("no_track", "no_track_in_zone", [])
    assert _track("z-2").association_status == "unassigned"


def test_a_track_seen_too_long_before_the_scan_is_not_in_the_zone():
    _feed(_at("z-1", 0, IN_ZONE))
    assert _scan(1.5).outcome == "no_track"


@pytest.mark.parametrize("animal_id, inliers, quality, reason", [
    ("animal-demo-001", 5, 0.9, "low_inliers"),
    ("animal-demo-001", 30, 0.59, "low_quality"),
    ("animal-other-001", 30, 0.9, "candidate_not_registered"),
    (None, 30, 0.9, "candidate_not_registered"),
])
def test_a_weak_or_foreign_scan_identifies_nobody(animal_id, inliers, quality, reason):
    _feed(_at("z-1", 0, IN_ZONE))
    result = _scan(0.4, animal_id=animal_id, inliers=inliers, quality=quality)
    assert (result.outcome, result.reason, result.observation) == ("rejected", reason, None)
    track = _track("z-1")
    assert (track.association_status, track.animal_id, track.association_evidence["reason"]) == (
        "unassigned", None, reason)


def test_a_camera_without_a_scan_zone_refuses_scans():
    with pytest.raises(DomainError) as error:
        _scan(0.0, camera="cam-pen-b")
    assert error.value.code == "VALIDATION_FAILED"


def test_identity_is_released_when_the_track_is_missing_more_than_one_second():
    first, = _feed(_at("z-1", 0, IN_ZONE))
    _scan(0.2)
    on_time, = _feed(_at("z-1", 1.0, IN_ZONE))
    late, = _feed(_at("z-1", 2.1, IN_ZONE))  # missing 1.1 s: released at its last sighting
    assert (first.animal_id, on_time.animal_id, late.animal_id) == (None, "animal-demo-001", None)
    track = _track("z-1")
    assert (track.association_status, track.association_evidence["reason"]) == ("uncertain", "track_missing")
    assert track.association_evidence["released_at"] == "2026-10-20T09:00:01Z"
    assert _stored([on_time], track.id) == [(1.0, "animal-demo-001")]  # trusted up to its last sighting
    with read_session() as session:
        lost = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "track.lost"))
    assert (lost.animal_id, lost.data["reason"], lost.data["policy"]) == (
        "animal-demo-001", "track_missing", "handoff_v2")


def test_a_gap_of_exactly_one_second_keeps_the_identity():
    _feed(_at("z-1", 0, IN_ZONE))
    _scan(0.0)
    kept, = _feed(_at("z-1", 1.0, IN_ZONE))
    assert kept.animal_id == "animal-demo-001"


def test_a_missing_track_is_released_when_another_track_reports():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, OUTSIDE))
    _scan(0.2)
    _feed(_at("z-2", 0.5, OUTSIDE), _at("z-2", 1.0, OUTSIDE))
    assert _track("z-1").association_status == "associated"
    _feed(_at("z-2", 1.5, OUTSIDE))
    assert (_track("z-1").association_status, _track("z-1").association_evidence["reason"]) == (
        "uncertain", "track_missing")


def _walk_together(start: float, end: float) -> list[ObservationInput]:
    """10 fps for 1.5 s: z-1 stays in the zone; z-2 sits on top of it in the frames from `start` to before `end`."""
    items = []
    for i in range(1, 16):
        s = round(i / 10, 2)
        items += [_at("z-1", s, IN_ZONE), _at("z-2", s, ON_TOP if start <= s < end else OUTSIDE)]
    return items


def test_identity_is_released_on_a_sustained_overlap_from_its_start():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, OUTSIDE))
    _scan(0.0)
    rows = _feed(*_walk_together(0.5, 0.85))  # overlapping frames 0.5 … 0.8: 0.3 s
    track = _track("z-1")
    assert (track.association_status, track.association_evidence["reason"]) == ("uncertain", "overlap")
    assert track.association_evidence["released_at"] == "2026-10-20T09:00:00.500000Z"
    assert track.association_evidence["overlap_with"] == "z-2"
    carried = _stored(rows, track.id)
    assert [a for t, a in carried if t < 0.5] == ["animal-demo-001"] * 4
    assert all(animal is None for t, animal in carried if t >= 0.5)  # from the overlap's start, downgraded


def test_the_overlap_release_works_whichever_track_reports_first():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, OUTSIDE))
    _scan(0.0)
    items = _walk_together(0.5, 0.85)
    _feed(*[item for pair in zip(items[1::2], items[0::2]) for item in pair])  # z-2's frame first at each instant
    assert (_track("z-1").association_status, _track("z-1").association_evidence["reason"]) == (
        "uncertain", "overlap")


def test_a_brief_brush_does_not_release_the_identity():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, OUTSIDE))
    _scan(0.0)
    rows = _feed(*_walk_together(0.5, 0.75))  # overlapping frames 0.5, 0.6, 0.7: 0.2 s
    track = _track("z-1")
    assert (track.association_status, track.animal_id) == ("associated", "animal-demo-001")
    assert "continuity" not in track.association_evidence  # the overlap clock reset once it ended
    assert all(animal == "animal-demo-001" for _, animal in _stored(rows, track.id))


def test_two_brushes_with_a_clear_frame_between_do_not_add_up():
    _feed(_at("z-1", 0, IN_ZONE), _at("z-2", 0, OUTSIDE))
    _scan(0.0)
    items = []
    for i in range(1, 16):
        s = round(i / 10, 2)
        on_top = s in (0.3, 0.4, 0.5, 0.7, 0.8, 0.9)  # 0.2 s, a clear frame at 0.6, then 0.2 s
        items += [_at("z-1", s, IN_ZONE), _at("z-2", s, ON_TOP if on_top else OUTSIDE)]
    _feed(*items)
    assert _track("z-1").association_status == "associated"


def test_muzzle_matched_tracks_follow_the_same_continuity_policy():
    _feed(ObservationInput(track_key="t-20", observed_at=T0, bbox=OUTSIDE, visibility=0.9, event="muzzle_match",
                           candidate_animal_id="animal-demo-002", inliers=23, quality=0.86),
          _at("t-20", 0.5, OUTSIDE))
    late, = _feed(_at("t-20", 2.0, OUTSIDE))
    track = _track("t-20")
    assert (late.animal_id, track.association_evidence["previous_method"]) == (None, "muzzle_match")


def test_iou_and_polygon_geometry():
    assert association.iou([0, 0, 0.2, 0.2], [0, 0, 0.2, 0.2]) == pytest.approx(1.0)
    assert association.iou([0, 0, 0.2, 0.2], [0.5, 0.5, 0.1, 0.1]) == 0.0
    assert association.iou(IN_ZONE, ON_TOP) > association.CROWD_IOU
    assert association.iou(IN_ZONE, IN_ZONE_2) < association.CROWD_IOU
    zone = [[0.4781, 0.6611], [0.7021, 0.6611], [0.7021, 0.8463], [0.4781, 0.8463]]
    assert association.point_in_polygon(0.58, 0.73, zone) and not association.point_in_polygon(0.2, 0.2, zone)
