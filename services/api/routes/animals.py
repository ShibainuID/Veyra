"""Animal and passport endpoints (PRD Section 6): list, passport, estimate confirmation, valuation."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from domain import passport
from persistence.models import Alert, Animal, Policy, User
from routes.deps import SessionDep, UserDep, get_owned, require_roles

router = APIRouter(prefix="/animals", tags=["animals"])
Manager = Annotated[User, Depends(require_roles("manager"))]
ILLUSTRATIVE_PRICE_SOURCE = "Illustrative demo price, not a market quote"


class AnimalOut(BaseModel):
    id: uuid.UUID
    display_id: str
    identity_status: str
    sex: str | None
    breed: str | None
    has_open_alert: bool
    has_active_policy: bool
    created_at: datetime


class ConfirmEstimateIn(BaseModel):
    range_low: float | None = Field(default=None, ge=0)
    range_high: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def both_or_neither(self):
        if (self.range_low is None) != (self.range_high is None):
            raise ValueError("Provide both range_low and range_high to override, or neither to confirm as is.")
        return self


class ValuationIn(BaseModel):
    weight_estimate_id: uuid.UUID
    unit_price_minor_per_kg: int | None = Field(default=None, gt=0)
    price_source: str | None = Field(default=None, max_length=200)
    price_date: datetime | None = None


@router.get("", response_model=list[AnimalOut])
def list_animals(session: SessionDep, user: UserDep, identity_status: str | None = None,
                 has_open_alert: bool | None = None, has_active_policy: bool | None = None) -> list[AnimalOut]:
    q = select(Animal).where(Animal.farm_id == user.farm_id)
    if identity_status:
        q = q.where(Animal.identity_status == identity_status)
    animals = list(session.scalars(q.order_by(Animal.display_id)))
    ids = [a.id for a in animals]
    alerting = set(session.scalars(select(Alert.animal_id).where(Alert.animal_id.in_(ids), Alert.status == "open")))
    insured = set(session.scalars(select(Policy.animal_id).where(Policy.animal_id.in_(ids), Policy.status == "active")))
    out = [AnimalOut(id=a.id, display_id=a.display_id, identity_status=a.identity_status, sex=a.sex, breed=a.breed,
                     has_open_alert=a.id in alerting, has_active_policy=a.id in insured, created_at=a.created_at)
           for a in animals]
    if has_open_alert is not None:
        out = [a for a in out if a.has_open_alert == has_open_alert]
    if has_active_policy is not None:
        out = [a for a in out if a.has_active_policy == has_active_policy]
    return out


@router.get("/{animal_id}/passport")
def get_passport(animal_id: uuid.UUID, session: SessionDep, user: UserDep) -> dict:
    return passport.build(session, get_owned(session, Animal, animal_id, user))


@router.post("/{animal_id}/estimates/{estimate_id}/confirm")
def confirm_estimate(animal_id: uuid.UUID, estimate_id: uuid.UUID, body: ConfirmEstimateIn, session: SessionDep,
                     user: Manager) -> dict:
    animal = get_owned(session, Animal, animal_id, user)
    estimate = passport.get_estimate(session, animal, estimate_id)
    override = None if body.range_low is None else (body.range_low, body.range_high)
    confirmed = passport.confirm_estimate(session, animal, estimate, user, override, body.note)
    session.commit()
    return passport._estimate(confirmed)


@router.post("/{animal_id}/valuations", status_code=201)
def create_valuation(animal_id: uuid.UUID, body: ValuationIn, request: Request, session: SessionDep, user: Manager) -> dict:
    animal = get_owned(session, Animal, animal_id, user)
    estimate = passport.get_estimate(session, animal, body.weight_estimate_id)
    price = body.unit_price_minor_per_kg or request.app.state.settings.demo_price_minor_per_kg
    valuation = passport.value_animal(session, animal, estimate, user, price,
                                      body.price_source or ILLUSTRATIVE_PRICE_SOURCE,
                                      body.price_date or datetime.now(UTC))
    session.commit()
    return passport._valuation(valuation)
