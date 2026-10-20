"""Who is signed in (`/auth/whoami`): the user, role, and farm behind the bearer token."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from domain.auth import Principal
from persistence.db import get_read_session
from persistence.models import Farm
from routes.deps import current_principal
from schemas import WhoAmI, error_responses

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/whoami", response_model=WhoAmI, responses=error_responses(401))
def whoami(principal: Principal = Depends(current_principal), session: Session = Depends(get_read_session)) -> dict:
    farm = session.get(Farm, principal.farm_id)
    return {"user_id": principal.user_id, "name": principal.name, "role": principal.role,
            "farm": {"id": farm.id, "name": farm.name}}
