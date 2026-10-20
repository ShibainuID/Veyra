"""Claims (plan Section 5: `/claims`). Managers and operators draft from an incident; only a manager confirms the
farmer declaration; any role of the farm (including the assessor) may read. Submission is a `CLAIM_SUBMISSION`
agent action."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain import claims
from domain.auth import APPROVERS, ENROLLERS, Principal
from persistence.db import get_read_session, get_session
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_finance import ClaimDetail, ClaimDraftRequest, ClaimList, ClaimPatch

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/drafts", response_model=ClaimDetail, responses=error_responses(401, 403, 404, 409, 422))
def draft_claim(body: ClaimDraftRequest, principal: Principal = Depends(require_roles(*ENROLLERS)),
                session: Session = Depends(get_session)) -> dict:
    claim = claims.draft_claim(session, principal, body.incident_id)
    session.commit()
    return claims.claim_view(session, claim)


@router.get("", response_model=ClaimList, responses=error_responses(401))
def list_claims(animal_id: str | None = None, principal: Principal = Depends(current_principal),
                session: Session = Depends(get_read_session)) -> dict:
    return {"items": [claims.claim_view(session, c) for c in claims.list_claims(session, principal.farm_id, animal_id)]}


@router.get("/{claim_id}", response_model=ClaimDetail, responses=error_responses(401, 404))
def get_claim(claim_id: str, principal: Principal = Depends(current_principal),
              session: Session = Depends(get_read_session)) -> dict:
    return claims.claim_view(session, claims.farm_claim(session, principal.farm_id, claim_id))


@router.patch("/{claim_id}", response_model=ClaimDetail, responses=error_responses(401, 403, 404, 409, 422))
def patch_claim(claim_id: str, body: ClaimPatch, principal: Principal = Depends(require_roles(*APPROVERS)),
                session: Session = Depends(get_session)) -> dict:
    claim = claims.confirm_declaration(session, principal, claim_id)
    session.commit()
    return claims.claim_view(session, claim)
