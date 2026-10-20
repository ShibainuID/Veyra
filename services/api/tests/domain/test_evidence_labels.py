from sqlalchemy import select

from domain import clock
from domain.evidence import animal_items
from domain.ids import new_id
from persistence.db import SessionLocal, init_db
from persistence.models import Animal, Estimate
from persistence.seed import reset_database


def test_an_estimate_without_a_range_is_labeled_as_needing_review():
    init_db()
    reset_database("post-enrollment")
    with SessionLocal() as session:
        animal = session.scalars(select(Animal).where(Animal.id == "animal-demo-001")).one()
        session.add(Estimate(id=new_id("est"), animal_id=animal.id, kind="weight", range_low=None, range_high=None,
                             point=None, unit="kg", source="simulated", method_version="none", evidence={},
                             review_required=True, review_reason="weight_unavailable",
                             created_at=clock.now()))
        session.commit()
        labels = [i["label"] for i in animal_items(session, animal) if i["type"] == "weight_estimate"]
    assert labels == ["Weight estimate · no range, review required (simulated)"]
    assert "None" not in labels[0]
