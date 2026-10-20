"""Policy catalog, recommendations, and farm policies (plan Section 5: `/policies/*`,
`/animals/{id}/insurance-recommendations`).

Recommendations read in a short read session and call the language model after it closes, so no transaction is
held across the model call.
"""

from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from adapters.llm.explain import explain
from config import get_settings
from domain import actions, insurance
from domain.auth import APPROVERS, ENROLLERS, Principal
from domain.catalog import load_catalog
from persistence.db import get_read_session, read_session
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_finance import PolicyDetail, PolicyList, RecommendationsOut

router = APIRouter(tags=["insurance"])


@router.get("/policies/catalog", response_model=dict[str, Any], responses=error_responses(401))
def get_catalog(principal: Principal = Depends(current_principal)) -> dict:
    catalog = load_catalog()
    return {**catalog, "version": catalog["catalog_version"]}


@router.post("/animals/{animal_id}/insurance-recommendations", response_model=RecommendationsOut,
             responses=error_responses(401, 403, 404))
def recommend(animal_id: str, principal: Principal = Depends(require_roles(*ENROLLERS))) -> dict:
    with read_session() as session:
        result = insurance.recommend(session, principal.farm_id, animal_id)
    result["explanation"] = explain(get_settings(), animal=result.pop("animal"), results=result["results"],
                                    catalog=load_catalog(), insured_value_minor=result["insured_value_minor"],
                                    currency=result["currency"])
    result.pop("facts")
    return result


@router.get("/policies", response_model=PolicyList, responses=error_responses(401, 422))
def list_policies(animal_id: str | None = None, principal: Principal = Depends(current_principal),
                  session: Session = Depends(get_read_session)) -> dict:
    return {"items": insurance.list_policies(session, principal.farm_id, animal_id)}


@router.post("/policies/{policy_id}/activation-check", response_model=PolicyDetail,
             responses=error_responses(401, 403, 404, 409))
def activation_check(policy_id: str, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                     principal: Principal = Depends(require_roles(*APPROVERS))) -> dict:
    """Ask the sandbox insurer again whether a paid policy is active. Opens its own short sessions."""
    actions.check_activation(principal, policy_id, idempotency_key)
    with read_session() as session:
        return insurance.policy_view(insurance.farm_policy(session, principal.farm_id, policy_id))
