"""Incidents and professional findings (`/incidents`). Managers and operators record incidents;
vets and managers add findings; any role of the farm may read."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain import claims
from domain.auth import ENROLLERS, Principal
from persistence.db import get_read_session, get_session
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_finance import FindingRequest, IncidentDetail, IncidentRequest

router = APIRouter(prefix="/incidents", tags=["claims"])


@router.post("", response_model=IncidentDetail, status_code=201, responses=error_responses(401, 403, 404, 422))
def record_incident(body: IncidentRequest, principal: Principal = Depends(require_roles(*ENROLLERS)),
                    session: Session = Depends(get_session)) -> dict:
    incident = claims.record_incident(session, principal, **body.model_dump())
    session.commit()
    return claims.incident_view(session, incident)


@router.get("", response_model=list[IncidentDetail], responses=error_responses(401))
def list_incidents(animal_id: str | None = None, principal: Principal = Depends(current_principal),
                   session: Session = Depends(get_read_session)) -> list[dict]:
    return [claims.incident_view(session, i) for i in claims.list_incidents(session, principal.farm_id, animal_id)]


@router.get("/{incident_id}", response_model=IncidentDetail, responses=error_responses(401, 404))
def get_incident(incident_id: str, principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return claims.incident_view(session, claims.farm_incident(session, principal.farm_id, incident_id))


@router.post("/{incident_id}/findings", response_model=IncidentDetail, status_code=201,
             responses=error_responses(401, 403, 404, 422))
def add_finding(incident_id: str, body: FindingRequest,
                principal: Principal = Depends(require_roles(*claims.FINDING_AUTHORS)),
                session: Session = Depends(get_session)) -> dict:
    incident = claims.add_finding(session, principal, incident_id, **body.model_dump())
    session.commit()
    return claims.incident_view(session, incident)
