from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from domain import association
from domain.association import ObservationInput, decide_match, ingest
from domain.errors import DomainError
from persistence.db import SessionLocal, read_session
from persistence.models import Animal, AuditEvent, Observation, Track
from persistence.seed import reset_database

FARM = "farm-wahyu"
CAMERA = "cam-pen-a"
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def seeded():
    reset_database("post-enrollment")


def _feed(*items: ObservationInput) -> list[Observation]:
    with SessionLocal() as session:
        rows = [ingest(session, farm_id=FARM, camera_id=CAMERA, item=item) for item in items]
        session.commit()
    return rows


def _frame(key: str, s: float, visibility: float = 0.9) -> ObservationInput:
    return ObservationInput(track_key=key, observed_at=T0 + timedelta(seconds=s), bbox=[0.3, 0.3, 0.2, 0.2],
                            visibility=visibility)


def _match(key: str, s: float, animal_id: str, inliers: int = 23, quality: float = 0.86) -> ObservationInput:
    return ObservationInput(track_key=key, observed_at=T0 + timedelta(seconds=s), bbox=[0.3, 0.3, 0.2, 0.2],
                            visibility=0.9, event="muzzle_match", candidate_animal_id=animal_id, inliers=inliers,
                            quality=quality)


def _lost(key: str, s: float) -> ObservationInput:
    return ObservationInput(track_key=key, observed_at=T0 + timedelta(seconds=s), bbox=[0.3, 0.3, 0.2, 0.2],
                            visibility=0.5, event="track_lost", reason="occlusion")


def _track(key: str) -> Track:
    with read_session() as session:
        return session.scalar(select(Track).where(Track.track_key == key, Track.replay_id.is_(None)))


def _animal(**overrides) -> Animal:
    defaults = {"id": "x", "farm_id": FARM, "identity_status": "confirmed"}
    return Animal(**{**defaults, **overrides})


@pytest.mark.parametrize("animal, inliers, quality, reason", [
    (_animal(), 6, 0.6, None),
    (_animal(), 5, 0.9, "low_inliers"),
    (_animal(), None, 0.9, "low_inliers"),
    (_animal(), 30, 0.59, "low_quality"),
    (None, 30, 0.9, "candidate_not_registered"),
    (_animal(farm_id="farm-other"), 30, 0.9, "candidate_not_registered"),
    (_animal(identity_status="pending_review"), 30, 0.9, "candidate_unconfirmed"),
])
def test_match_rule(animal, inliers, quality, reason):
    decision = decide_match(candidate=animal, farm_id=FARM, inliers=inliers, quality=quality)
    assert (decision.accepted, decision.reason) == (reason is None, reason)


def test_new_track_key_starts_unassigned():
    first, = _feed(_frame("t-new", 0))
    track = _track("t-new")
    assert (track.association_status, track.animal_id) == ("unassigned", None)
    assert (first.association_status, first.animal_id) == ("unassigned", None)


def test_strong_match_associates_and_later_observations_carry_the_animal():
    before, match, after = _feed(_frame("t-01", 0), _match("t-01", 4, "animal-demo-001"), _frame("t-01", 5))
    track = _track("t-01")
    assert (track.association_status, track.animal_id, track.association_method) == (
        "associated", "animal-demo-001", "muzzle_match")
    assert track.association_evidence["inliers"] == 23 and track.association_evidence["decision"] == "associated"
    assert (before.animal_id, match.animal_id, after.animal_id) == (None, "animal-demo-001", "animal-demo-001")
    with read_session() as session:
        stored = session.get(Observation, before.id)
        assert (stored.animal_id, stored.association_status) == (None, "unassigned")  # never retroactive
        events = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "track.associated")).all()
        assert [(e.animal_id, e.data["inliers"]) for e in events] == [("animal-demo-001", 23)]


def test_low_inliers_leave_the_track_unassigned_with_evidence():
    _, match = _feed(_frame("t-02", 0), _match("t-02", 1, "animal-demo-002", inliers=5))
    track = _track("t-02")
    assert (track.association_status, track.animal_id) == ("unassigned", None)
    assert track.association_evidence["reason"] == "low_inliers"
    assert (match.event, match.animal_id, match.association_status) == ("muzzle_match", None, "unassigned")


def test_unregistered_or_other_farm_candidate_leaves_the_track_unassigned():
    _feed(_match("t-03", 0, "animal-demo-999"), _match("t-04", 0, "animal-other-001"))
    for key in ("t-03", "t-04"):
        track = _track(key)
        assert (track.association_status, track.animal_id) == ("unassigned", None)
        assert track.association_evidence["reason"] == "candidate_not_registered"


def test_track_lost_makes_the_track_uncertain_and_later_observations_anonymous():
    rows = _feed(_match("t-05", 0, "animal-demo-002"), _frame("t-05", 1), _lost("t-05", 2), _frame("t-05", 3),
                 _match("t-05", 4, "animal-demo-002"))
    track = _track("t-05")
    assert (track.association_status, track.animal_id) == ("uncertain", None)
    assert track.association_evidence["previous_animal_id"] == "animal-demo-002"
    assert [(r.association_status, r.animal_id) for r in rows] == [
        ("associated", "animal-demo-002"), ("associated", "animal-demo-002"), ("uncertain", None),
        ("uncertain", None), ("uncertain", None)]
    with read_session() as session:
        lost = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "track.lost")).all()
        assert [(e.animal_id, e.data["reason"]) for e in lost] == [("animal-demo-002", "occlusion")]


def test_conflicting_match_makes_the_track_uncertain():
    _feed(_match("t-06", 0, "animal-demo-002"), _match("t-06", 1, "animal-demo-003"))
    track = _track("t-06")
    assert (track.association_status, track.animal_id, track.association_evidence["reason"]) == (
        "uncertain", None, "conflicting_match")


def test_human_review_associates_and_unassigns():
    _feed(_frame("t-07", 0))
    track_id = _track("t-07").id
    with SessionLocal() as session:
        association.review(session, farm_id=FARM, track_id=track_id, animal_id="animal-demo-003", note="Ear tag seen",
                           actor=("user", "user-operator"))
        session.commit()
    after, = _feed(_frame("t-07", 1))
    assert (_track("t-07").association_method, after.animal_id) == ("human_review", "animal-demo-003")
    with SessionLocal() as session:
        association.review(session, farm_id=FARM, track_id=track_id, animal_id=None, note=None,
                           actor=("user", "user-operator"))
        session.commit()
    assert (_track("t-07").association_status, _track("t-07").animal_id) == ("unassigned", None)


def test_human_review_is_farm_scoped_and_needs_a_confirmed_animal():
    _feed(_frame("t-08", 0))
    track_id = _track("t-08").id
    with SessionLocal() as session:
        with pytest.raises(DomainError) as other_animal:
            association.review(session, farm_id=FARM, track_id=track_id, animal_id="animal-other-001", note=None,
                               actor=("user", "user-operator"))
        with pytest.raises(DomainError) as other_farm:
            association.review(session, farm_id="farm-other", track_id=track_id, animal_id=None, note=None,
                               actor=("user", "user-other-manager"))
        session.get(Animal, "animal-demo-005").identity_status = "pending_review"
        session.flush()
        with pytest.raises(DomainError) as unconfirmed:
            association.review(session, farm_id=FARM, track_id=track_id, animal_id="animal-demo-005", note=None,
                               actor=("user", "user-operator"))
        session.rollback()
    assert (other_animal.value.code, other_farm.value.code, unconfirmed.value.code) == (
        "NOT_FOUND", "NOT_FOUND", "IDENTITY_UNCONFIRMED")


def test_invalid_observation_is_refused():
    bad = ObservationInput(track_key="t-09", observed_at=T0, bbox=[0.5, 0.5, 1.2, 0.2], visibility=0.9)
    with SessionLocal() as session, pytest.raises(DomainError) as error:
        ingest(session, farm_id=FARM, camera_id=CAMERA, item=bad)
    assert error.value.code == "VALIDATION_FAILED"
