"""Demo controls: reset to a scenario and the sandbox provider switches (plan Section 5: `/demo/*`).

Hidden (`NOT_FOUND`) unless `VEYRA_DEMO_MODE` is on.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import get_settings
from domain import clock
from domain.errors import DomainError
from persistence.db import get_session
from persistence.models import DemoSettings
from persistence.seed import DEMO_FARM_ID, reset_database

Scenario = Literal["fresh", "post-enrollment"]
PaymentMode = Literal["succeed", "fail", "timeout"]
InsurerActivation = Literal["confirm", "withhold"]


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise DomainError("NOT_FOUND", "Resource not found.")


# B3: require manager
router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(require_demo_mode)])


class ResetResult(BaseModel):
    status: Literal["reset"]
    scenario: Scenario
    animals: int


class DemoSettingsUpdate(BaseModel):
    payment_mode: PaymentMode
    insurer_activation: InsurerActivation


class DemoSettingsOut(DemoSettingsUpdate):
    farm_id: str
    updated_at: datetime


def _settings_row(session: Session) -> DemoSettings:
    row = session.get(DemoSettings, DEMO_FARM_ID)
    if row is None:
        raise DomainError("NOT_FOUND", "Demo settings are not seeded; reset the demo first.")
    return row


def _out(row: DemoSettings) -> DemoSettingsOut:
    return DemoSettingsOut(farm_id=row.farm_id, payment_mode=row.payment_mode,
                           insurer_activation=row.insurer_activation, updated_at=row.updated_at)


@router.post("/reset")
def reset(scenario: Scenario = "fresh") -> ResetResult:
    return ResetResult(status="reset", scenario=scenario, animals=reset_database(scenario))


@router.get("/settings")
def get_demo_settings(session: Session = Depends(get_session)) -> DemoSettingsOut:
    return _out(_settings_row(session))


@router.put("/settings")
def put_demo_settings(body: DemoSettingsUpdate, session: Session = Depends(get_session)) -> DemoSettingsOut:
    row = _settings_row(session)
    row.payment_mode = body.payment_mode
    row.insurer_activation = body.insurer_activation
    row.updated_at = clock.now()
    session.commit()
    return _out(row)
