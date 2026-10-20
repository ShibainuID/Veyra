"""The farm's audit trail, newest first (`/audit-events`). Any role may read; actor names are
resolved."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from domain.audit import actor_ref, list_events, user_names
from domain.auth import Principal
from persistence.db import get_read_session
from routes.deps import current_principal
from schemas import AuditEventOut, error_responses

MAX_LIMIT = 500

router = APIRouter(tags=["audit"])


@router.get("/audit-events", response_model=list[AuditEventOut], responses=error_responses(401, 422))
def list_audit_events(animal_id: str | None = None, subject_type: str | None = None, subject_id: str | None = None,
                      limit: int = Query(100, ge=1, le=MAX_LIMIT), principal: Principal = Depends(current_principal),
                      session: Session = Depends(get_read_session)) -> list[dict]:
    events = list_events(session, principal.farm_id, animal_id=animal_id, subject_type=subject_type,
                         subject_id=subject_id, limit=limit, newest_first=True)
    names = user_names(session, principal.farm_id)
    return [{"id": e.id, "created_at": e.created_at, "actor": actor_ref(e.actor_type, e.actor_id, names),
             "event_type": e.event_type, "subject_type": e.subject_type, "subject_id": e.subject_id,
             "animal_id": e.animal_id, "data": e.data} for e in events]
