"""The natural-language locator (plan Section 5: `POST /assistant/query`). Any role may ask about its own farm.

Claude (when live) only parses the question; the answer text and every fact come from the farm's records.
"""

from fastapi import APIRouter, Depends

from config import get_settings
from domain import assistant
from domain.auth import Principal
from routes.deps import current_principal
from schemas import error_responses
from schemas_monitoring import AssistantAnswer, AssistantQuery

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantAnswer, responses=error_responses(401, 422))
def query(body: AssistantQuery, principal: Principal = Depends(current_principal)) -> dict:
    return assistant.ask(get_settings(), principal.farm_id, body.text)
