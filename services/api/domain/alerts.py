"""Alert review (PRD M08): acknowledge, resolve, and record veterinary findings.

open -> acknowledged -> resolved, or open -> resolved. Resolved alerts are closed. Only a veterinarian records an
assessment, and the assessment is stored apart from the camera observation. Every change adds an evidence version.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from domain import audit, evidence
from domain.errors import APIError, ErrorCode
from persistence.models import Alert, User

FINDINGS = ("no_concern", "condition_observed", "referred_for_treatment", "inconclusive")
TRANSITIONS = {"open": {"acknowledged", "resolved"}, "acknowledged": {"acknowledged", "resolved"}}


def review(session: Session, alert: Alert, user: User, status: str | None, notes: str | None,
           assessment: dict | None):
    if alert.status == "resolved":
        raise APIError(ErrorCode.CONFLICT, "This alert is already resolved.")
    target = status or alert.status
    if target != alert.status and target not in TRANSITIONS[alert.status]:
        raise APIError(ErrorCode.CONFLICT, f"Cannot move an alert from '{alert.status}' to '{target}'.")
    if assessment is not None and user.role != "veterinarian":
        raise APIError(ErrorCode.FORBIDDEN, "Only a veterinarian can record an assessment.",
                       {"allowed_roles": ["veterinarian"]})
    if target == "resolved" and not (notes or assessment or alert.review_notes):
        raise APIError(ErrorCode.VALIDATION_FAILED, "Resolving an alert needs review notes or an assessment.")
    if status is None and notes is None and assessment is None:
        raise APIError(ErrorCode.VALIDATION_FAILED, "Nothing to update.")

    now = datetime.now(UTC)
    previous = alert.status
    alert.status = target
    if notes is not None:
        alert.review_notes = notes
    if assessment is not None:
        alert.assessment = {**assessment, "assessed_by": str(user.id), "assessed_at": now.isoformat()}
    alert.reviewed_by, alert.reviewed_at = user.id, now
    session.flush()
    pack = evidence.snapshot(session, alert, "review_updated")
    details = {"alert_id": str(alert.id), "from": previous, "to": target, "notes": notes,
               "assessment": assessment, "evidence_version": pack.version, "evidence_sha256": pack.manifest_sha256}
    audit.record(session, alert.farm_id, "alert.reviewed", "animal", alert.animal_id, actor_id=user.id, details=details)
    audit.record(session, alert.farm_id, "alert.reviewed", "alert", alert.id, actor_id=user.id, details=details)
    return pack
