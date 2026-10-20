"""Job status (processing endpoints return `202 {job_id}`, polled here). Any role; farm-scoped."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain.auth import Principal
from persistence.db import get_read_session
from routes.deps import current_principal
from schemas import error_responses
from schemas_enrollment import JobOut
from workers import jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut, responses=error_responses(401, 404))
def get_job(job_id: str, principal: Principal = Depends(current_principal),
            session: Session = Depends(get_read_session)) -> dict:
    return jobs.job_out(jobs.get_job(session, principal.farm_id, job_id))
