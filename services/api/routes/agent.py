"""Agent Wallet routes (`/agent/actions`).

Managers and operators prepare and cancel; only managers approve and execute. Execution opens its own short
sessions (claim, provider call, apply), so it takes no request session and holds no transaction across the call.
"""

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

import domain.claims  # noqa: F401  (registers CLAIM_SUBMISSION and the claim passbook lines)
from domain import actions
from domain.auth import APPROVERS, ENROLLERS, Principal
from persistence.db import get_read_session, get_session, read_session
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_finance import ActionList, ActionOut, ActionStatus, DecisionRequest, ProposeRequest

router = APIRouter(prefix="/agent/actions", tags=["agent"])
T = TypeVar("T")


def commit_or_raise(session: Session, fn: Callable[[], T]) -> T:
    """Run a domain step and commit. A `CommitThenRaise` keeps its recorded state, then reports its error."""
    try:
        result = fn()
    except actions.CommitThenRaise as blocked:
        session.commit()
        raise blocked.error from None
    session.commit()
    return result


@router.get("", response_model=ActionList, responses=error_responses(401, 422))
def list_actions(status: ActionStatus | None = None, animal_id: str | None = None,
                 principal: Principal = Depends(current_principal),
                 session: Session = Depends(get_read_session)) -> dict:
    return {"items": actions.list_actions(session, principal.farm_id, status=status, animal_id=animal_id)}


@router.post("", response_model=ActionOut, status_code=201, responses=error_responses(401, 403, 404, 409, 422))
def propose(body: ProposeRequest, principal: Principal = Depends(require_roles(*ENROLLERS)),
            session: Session = Depends(get_session)) -> dict:
    refs = body.model_dump(exclude={"rationale"})
    action = commit_or_raise(session, lambda: actions.propose(session, principal, refs, body.rationale))
    return actions.action_view(session, action)


@router.get("/{action_id}", response_model=ActionOut, responses=error_responses(401, 404))
def get_action(action_id: str, principal: Principal = Depends(current_principal),
               session: Session = Depends(get_read_session)) -> dict:
    return actions.action_view(session, actions.farm_action(session, principal.farm_id, action_id))


@router.post("/{action_id}/decision", response_model=ActionOut, responses=error_responses(401, 403, 404, 409, 422))
def decide(action_id: str, body: DecisionRequest, principal: Principal = Depends(require_roles(*APPROVERS)),
           session: Session = Depends(get_session)) -> dict:
    action = commit_or_raise(session, lambda: actions.decide(session, principal, action_id, **body.model_dump()))
    return actions.action_view(session, action)


@router.post("/{action_id}/execute", response_model=ActionOut, responses=error_responses(400, 401, 403, 404, 409))
def execute(action_id: str, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
            principal: Principal = Depends(require_roles(*APPROVERS))) -> dict:
    actions.execute(principal, action_id, idempotency_key)
    with read_session() as session:
        return actions.action_view(session, actions.farm_action(session, principal.farm_id, action_id))


@router.post("/{action_id}/reconcile", response_model=ActionOut, responses=error_responses(401, 403, 404, 409))
def reconcile(action_id: str, principal: Principal = Depends(require_roles(*APPROVERS))) -> dict:
    """Re-ask the sandbox provider about an `unknown` action under its stored Idempotency-Key and apply the answer."""
    actions.reconcile(principal, action_id)
    with read_session() as session:
        return actions.action_view(session, actions.farm_action(session, principal.farm_id, action_id))


@router.post("/{action_id}/revise", response_model=ActionOut, status_code=201,
             responses=error_responses(401, 403, 404, 409, 422))
def revise(action_id: str, principal: Principal = Depends(require_roles(*ENROLLERS)),
           session: Session = Depends(get_session)) -> dict:
    """Prepare the action again from its own references; the new version needs a fresh approval."""
    action = commit_or_raise(session, lambda: actions.revise(session, principal, action_id))
    return actions.action_view(session, action)


@router.post("/{action_id}/cancel", response_model=ActionOut, responses=error_responses(401, 403, 404, 409))
def cancel(action_id: str, principal: Principal = Depends(require_roles(*ENROLLERS)),
           session: Session = Depends(get_session)) -> dict:
    action = commit_or_raise(session, lambda: actions.cancel(session, principal, action_id))
    return actions.action_view(session, action)
