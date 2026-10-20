"""Valuation confirmation (`POST /animals/{id}/valuations`). Managers and operators confirm."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain import valuation
from domain.auth import ENROLLERS, Principal
from persistence.db import get_session
from routes.deps import require_roles
from schemas import ValuationOut, error_responses
from schemas_finance import ValuationRequest

router = APIRouter(prefix="/animals", tags=["valuation"])


def valuation_out(row, confirmed_by_name: str) -> dict:
    return {column: getattr(row, column) for column in ValuationOut.model_fields} | {"confirmed_by": confirmed_by_name}


@router.post("/{animal_id}/valuations", response_model=ValuationOut, status_code=201,
             responses=error_responses(401, 403, 404, 409, 422))
def confirm_valuation(animal_id: str, body: ValuationRequest, principal: Principal = Depends(require_roles(*ENROLLERS)),
                      session: Session = Depends(get_session)) -> dict:
    row = valuation.confirm(session, principal, animal_id, **body.model_dump())
    session.commit()
    return valuation_out(row, principal.name)
