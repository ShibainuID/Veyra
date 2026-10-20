"""Herd list and Digital Livestock Passport (plan Section 5: `/animals`, `/animals/{id}/passport`). Any role may read;
every query is scoped to the principal's farm."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain import passport
from domain.auth import Principal
from persistence.db import get_read_session
from routes.deps import current_principal
from schemas import AnimalList, Passport, error_responses

router = APIRouter(prefix="/animals", tags=["animals"])


@router.get("", response_model=AnimalList, responses=error_responses(401, 422))
def list_animals(coverage: Literal["none", "active", "pending"] | None = None, alerts: Literal["open"] | None = None,
                 q: str | None = None, principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return passport.list_herd(session, principal.farm_id, coverage=coverage, alerts=alerts, q=q)


@router.get("/{animal_id}/passport", response_model=Passport, responses=error_responses(401, 404))
def get_passport(animal_id: str, principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return passport.build_passport(session, principal.farm_id, animal_id)
