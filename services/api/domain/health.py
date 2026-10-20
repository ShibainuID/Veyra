"""Health status per animal (handoff: `monitoring.health()`): a plain monitoring state, never a diagnosis.

Derived only from records (alerts, their review notes, and associated observations), checked in this order:
1. `needs_inspection`: an open reduced_movement alert.
2. `under_review`: an acknowledged alert that is not resolved yet.
3. `observation_gap`: an open observation_quality alert, or the last associated observation is older than 24 h.
4. `veterinary_reviewed`: the latest alert is resolved and carries a vet assessment note.
5. `normal`: an associated observation within 24 h and no open alerts.
6. `not_monitored`: no associated observation ever.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain import clock
from persistence.models import Alert, Animal, Observation

HEALTH_STATUSES = ("needs_inspection", "under_review", "observation_gap", "veterinary_reviewed", "normal",
                   "not_monitored")
OBSERVATION_WINDOW = timedelta(hours=24)


def classify(alerts: list[Alert], last_observed_at: datetime | None, now: datetime) -> dict:
    """The status from an animal's alerts (newest first) and its last associated observation time."""
    def state(status: str, reason: str, since: datetime | None) -> dict:
        return {"status": status, "reason": reason, "since": since}

    open_movement = [a for a in alerts if a.status == "open" and a.kind == "reduced_movement"]
    if open_movement:
        oldest = min(open_movement, key=lambda a: a.window_start)
        return state("needs_inspection", "Open reduced-movement alert; inspect the animal.", oldest.window_start)
    acknowledged = [a for a in alerts if a.status == "acknowledged"]
    if acknowledged:
        newest = max(acknowledged, key=lambda a: a.updated_at)
        return state("under_review", "An alert is acknowledged and not yet resolved.", newest.updated_at)
    open_quality = [a for a in alerts if a.status == "open" and a.kind == "observation_quality"]
    if open_quality:
        oldest = min(open_quality, key=lambda a: a.window_start)
        return state("observation_gap", "Open observation-quality alert; the camera view was poor.",
                     oldest.window_start)
    if last_observed_at is not None and now - last_observed_at > OBSERVATION_WINDOW:
        return state("observation_gap", "No associated observation in the last 24 hours.", last_observed_at)
    latest = alerts[0] if alerts else None
    if latest is not None and latest.status == "resolved" and any(
            (note or {}).get("kind") == "assessment" for note in latest.notes or []):
        return state("veterinary_reviewed", "The latest alert was resolved after a vet assessment.",
                     latest.updated_at)
    if last_observed_at is not None:
        return state("normal", "Observed in the last 24 hours with no open alerts.", last_observed_at)
    return state("not_monitored", "No associated camera observation on record.", None)


def health_status(session: Session, animal: Animal) -> dict:
    """`{status, reason, since}` for one animal, read from its alerts and associated observations."""
    alerts = list(session.scalars(select(Alert).where(Alert.farm_id == animal.farm_id, Alert.animal_id == animal.id)
                                  .order_by(Alert.created_at.desc(), Alert.id)))
    last = session.scalar(select(func.max(Observation.observed_at)).where(
        Observation.farm_id == animal.farm_id, Observation.animal_id == animal.id))
    if last is not None and last.tzinfo is None:  # func.max skips the column type's tz handling
        last = last.replace(tzinfo=clock.now().tzinfo)
    return classify(alerts, last, clock.now())
