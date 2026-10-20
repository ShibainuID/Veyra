"""Alert review (plan Section 5: `/alerts`). Any role may read its farm's alerts; managers, operators, and vets
review them under the rules in `domain/alerts.py`."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import domain.monitoring_passbook  # noqa: F401  (registers the passbook formatters)
from domain import alerts as alert_rules
from domain.auth import ALERT_REVIEWERS, Principal
from persistence.db import get_read_session, get_session
from routes.deps import current_principal, require_roles
from schemas import error_responses
from schemas_monitoring import AlertKind, AlertList, AlertReview, AlertStatus, AlertView

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertList, responses=error_responses(401, 422))
def list_alerts(status: AlertStatus | None = None, kind: AlertKind | None = None, animal_id: str | None = None,
                principal: Principal = Depends(current_principal),
                session: Session = Depends(get_read_session)) -> dict:
    rows = alert_rules.list_alerts(session, principal.farm_id, status=status, kind=kind, animal_id=animal_id)
    return {"items": alert_rules.views(session, principal.farm_id, rows)}


@router.get("/{alert_id}", response_model=AlertView, responses=error_responses(401, 404))
def get_alert(alert_id: str, principal: Principal = Depends(current_principal),
              session: Session = Depends(get_read_session)) -> dict:
    alert = alert_rules.farm_alert(session, principal.farm_id, alert_id)
    return alert_rules.views(session, principal.farm_id, [alert])[0]


@router.patch("/{alert_id}", response_model=AlertView, responses=error_responses(401, 403, 404, 409, 422))
def review_alert(alert_id: str, body: AlertReview, principal: Principal = Depends(require_roles(*ALERT_REVIEWERS)),
                 session: Session = Depends(get_session)) -> dict:
    alert = alert_rules.review(session, farm_id=principal.farm_id, alert_id=alert_id, principal=principal,
                               status=body.status, note=body.note)
    view = alert_rules.views(session, principal.farm_id, [alert])[0]
    session.commit()
    return view
