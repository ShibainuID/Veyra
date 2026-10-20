"""Sandbox wallet (plan Section 5: `GET /wallet`). Any role of the farm may read it."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain import wallet
from domain.auth import Principal
from persistence.db import get_read_session
from routes.deps import current_principal
from schemas import error_responses
from schemas_finance import WalletEntryOut, WalletOut

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=WalletOut, responses=error_responses(401))
def get_wallet(principal: Principal = Depends(current_principal), session: Session = Depends(get_read_session)) -> dict:
    entries = [{field: getattr(entry, field) for field in WalletEntryOut.model_fields}
               for entry in wallet.entries(session, principal.farm_id)]
    return {**wallet.summary(session, principal.farm_id), "entries": entries}
