"""In-app VEYRA agent conversations (`/agent/conversations`).

Managers and operators converse and let the agent prepare actions; only a manager approves (the existing
`/agent/actions/{id}/decision` and `/execute`, which the web's action review calls). Vets add findings on the claim,
not here; every farm role may read a conversation.

A turn runs as short steps, never holding a writing transaction across a slow call: an insurer activation check
(its own sessions), then one writing session that stores the farmer's turn, applies the domain step, and writes the
agent's template replies, then, only when the language model is live, a rephrase of each reply outside any
transaction and one more short write for the replies whose wording kept every figure.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import update
from sqlalchemy.orm import Session

import domain.claims  # noqa: F401  (registers CLAIM_SUBMISSION)
from adapters.llm import resolve_llm_mode
from config import get_settings
from domain import agent_chat
from domain.auth import Principal
from persistence.db import SessionLocal, get_read_session, read_session
from persistence.models import AgentMessage
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_agent import ConversationCreate, ConversationOut, MessageCreate

router = APIRouter(prefix="/agent/conversations", tags=["agent"])


def _rephrase(stored: list[agent_chat.Stored]) -> None:
    settings = get_settings()
    if not stored or resolve_llm_mode(settings) != "live":
        return
    phrased = []
    for item in stored:
        text, source = agent_chat.rephrase(settings, item.text, item.keep)
        if source == "live":
            phrased.append((item.message_id, text))
    if not phrased:
        return
    with SessionLocal() as session:
        for message_id, text in phrased:
            session.execute(update(AgentMessage).where(AgentMessage.id == message_id,
                                                       AgentMessage.source == "simulated")
                            .values(text=text, source="live"))
        session.commit()


def _view(principal: Principal, conversation_id: str) -> dict:
    with read_session() as session:
        conversation = agent_chat.farm_conversation(session, principal.farm_id, conversation_id)
        return agent_chat.conversation_view(session, conversation)


@router.post("", response_model=ConversationOut, status_code=201, responses=error_responses(401, 403, 404, 422))
def start_conversation(body: ConversationCreate,
                       principal: Principal = Depends(require_roles(*agent_chat.CONVERSE_ROLES))) -> dict:
    """Open a conversation about one animal with an intent: `find_insurance`, `file_claim`, or `track_claim`."""
    with SessionLocal() as session:
        conversation, stored = agent_chat.start(session, principal, body.animal_id, body.intent)
        session.commit()
    _rephrase(stored)
    return _view(principal, conversation.id)


@router.post("/{conversation_id}/messages", response_model=ConversationOut,
             responses=error_responses(401, 403, 404, 409, 422))
def post_message(conversation_id: str, body: MessageCreate,
                 principal: Principal = Depends(require_roles(*agent_chat.CONVERSE_ROLES))) -> dict:
    """Send the farmer's turn (typed text, or one of the choices the agent offered) and get the agent's next turns.
    `{"choice": {"key": "continue"}}` re-reads the records, for example after an approval."""
    picked = body.choice.model_dump() if body.choice else None
    with read_session() as session:
        conversation = agent_chat.farm_conversation(session, principal.farm_id, conversation_id)
        if picked is not None:
            agent_chat.resolve_input(session, conversation, None, picked)  # refuses a choice that wasn't offered
    note = agent_chat.pre_turn(principal, conversation_id, picked)
    with SessionLocal() as session:
        _, stored = agent_chat.reply(session, principal, conversation_id, body.text, picked, note)
        session.commit()
    _rephrase(stored)
    return _view(principal, conversation_id)


@router.get("/{conversation_id}", response_model=ConversationOut, responses=error_responses(401, 404))
def get_conversation(conversation_id: str, principal: Principal = Depends(current_principal),
                     session: Session = Depends(get_read_session)) -> dict:
    return agent_chat.conversation_view(session,
                                        agent_chat.farm_conversation(session, principal.farm_id, conversation_id))
