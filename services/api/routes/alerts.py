"""Alert endpoints (PRD Section 6, M08): list, detail with evidence, review, evidence versions."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from domain import alerts as review_flow, evidence
from persistence.models import Alert, Animal, EvidencePack, User
from routes.deps import SessionDep, UserDep, get_owned, require_roles

router = APIRouter(prefix="/alerts", tags=["alerts"])
Reviewer = Annotated[User, Depends(require_roles("manager", "operator", "veterinarian"))]


class AssessmentIn(BaseModel):
    finding: Literal[review_flow.FINDINGS]
    details: str = Field(min_length=3, max_length=2000)


class ReviewIn(BaseModel):
    status: Literal["acknowledged", "resolved"] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    assessment: AssessmentIn | None = None


def _pack(p: EvidencePack | None, full: bool) -> dict | None:
    if p is None:
        return None
    out = {"id": str(p.id), "version": p.version, "manifest_sha256": p.manifest_sha256, "created_at": p.created_at}
    return {**out, "manifest": p.manifest} if full else out


def alert_out(session, a: Alert, full: bool = False) -> dict:
    animal = a.animal_id and session.get(Animal, a.animal_id)
    return {"id": str(a.id), "kind": a.kind, "status": a.status, "source": a.source,
            "animal_id": a.animal_id and str(a.animal_id), "display_id": animal and animal.display_id,
            "track_id": a.track_id, "window_start": a.window_start, "window_end": a.window_end, "rule": a.rule,
            "evidence_media_ids": a.evidence_media_ids, "review_notes": a.review_notes,
            "reviewed_by": a.reviewed_by and str(a.reviewed_by), "reviewed_at": a.reviewed_at,
            "assessment": a.assessment, "created_at": a.created_at,
            "evidence": _pack(evidence.latest(session, a.id), full)}


@router.get("")
def list_alerts(session: SessionDep, user: UserDep, status: str | None = None, kind: str | None = None,
                animal_id: uuid.UUID | None = None) -> list[dict]:
    q = select(Alert).where(Alert.farm_id == user.farm_id)
    if status:
        q = q.where(Alert.status == status)
    if kind:
        q = q.where(Alert.kind == kind)
    if animal_id:
        q = q.where(Alert.animal_id == animal_id)
    return [alert_out(session, a) for a in session.scalars(q.order_by(Alert.created_at.desc()))]


@router.get("/{alert_id}")
def get_alert(alert_id: uuid.UUID, session: SessionDep, user: UserDep) -> dict:
    return alert_out(session, get_owned(session, Alert, alert_id, user), full=True)


@router.patch("/{alert_id}")
def review_alert(alert_id: uuid.UUID, body: ReviewIn, session: SessionDep, user: Reviewer) -> dict:
    alert = get_owned(session, Alert, alert_id, user)
    review_flow.review(session, alert, user, body.status, body.notes,
                       body.assessment and body.assessment.model_dump())
    session.commit()
    return alert_out(session, alert, full=True)


@router.get("/{alert_id}/evidence")
def list_evidence(alert_id: uuid.UUID, session: SessionDep, user: UserDep) -> list[dict]:
    alert = get_owned(session, Alert, alert_id, user)
    packs = session.scalars(select(EvidencePack).where(EvidencePack.alert_id == alert.id).order_by(EvidencePack.version))
    return [_pack(p, True) for p in packs]
