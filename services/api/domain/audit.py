"""The audit trail.

Every state change records one event in the caller's transaction: `record` only adds the row, and the caller
commits it together with the change it describes. Actor types are `user`, `agent`, `system`, and `provider`;
agent proposals, human decisions, and provider results are separate events. Events are read back in the order
they were written: by time, then by SQLite rowid, so events recorded at the same instant keep insert order.
"""

from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session

from domain import clock
from domain.auth import Principal, ServicePrincipal
from domain.ids import new_id
from persistence.models import AuditEvent, User

ACTOR_TYPES = ("user", "agent", "system", "provider")
AGENT_NAME = "VEYRA agent"
SYSTEM_NAME = "VEYRA"
SYSTEM_ACTOR_NAMES = {"seed": "Demo seed", "service-worker": "VEYRA worker", "camera-worker": "Camera worker"}
_ROWID = literal_column("audit_events.rowid")


def record(session: Session, *, farm_id: str, actor_type: str, actor_id: str, event_type: str, subject_type: str,
           subject_id: str, animal_id: str | None = None, data: dict | None = None) -> AuditEvent:
    if actor_type not in ACTOR_TYPES:
        raise ValueError(f"unknown actor_type {actor_type!r}; expected one of {', '.join(ACTOR_TYPES)}")
    event = AuditEvent(id=new_id("evt"), farm_id=farm_id, actor_type=actor_type, actor_id=actor_id,
                       event_type=event_type, subject_type=subject_type, subject_id=subject_id, animal_id=animal_id,
                       data=dict(data or {}), created_at=clock.now())
    session.add(event)
    return event


def actor_from(principal: Principal | ServicePrincipal) -> tuple[str, str]:
    if isinstance(principal, ServicePrincipal):
        return "system", principal.actor_id
    return "user", principal.user_id


def user_names(session: Session, farm_id: str) -> dict[str, str]:
    return dict(session.execute(select(User.id, User.name).where(User.farm_id == farm_id)).all())


# The sandbox providers in words (the insurer's name is the catalog's; demo/fixtures/policies.json).
PROVIDER_NAMES = {"sandbox-insurer": "Sandbox Mutual", "sandbox-payment": "Sandbox payments"}


def actor_ref(actor_type: str, actor_id: str, names: dict[str, str]) -> dict:
    if actor_type == "user":
        name = names.get(actor_id, actor_id)
    elif actor_type == "agent":
        name = AGENT_NAME
    elif actor_type == "system":
        name = SYSTEM_ACTOR_NAMES.get(actor_id, SYSTEM_NAME)
    elif actor_type == "provider":
        name = PROVIDER_NAMES.get(actor_id, actor_id)
    else:
        name = actor_id
    return {"type": actor_type, "id": actor_id, "name": name}


def list_events(session: Session, farm_id: str, *, animal_id: str | None = None, subject_type: str | None = None,
                subject_id: str | None = None, limit: int | None = None, newest_first: bool = False,
                ) -> list[AuditEvent]:
    query = select(AuditEvent).where(AuditEvent.farm_id == farm_id)
    for column, value in ((AuditEvent.animal_id, animal_id), (AuditEvent.subject_type, subject_type),
                          (AuditEvent.subject_id, subject_id)):
        if value is not None:
            query = query.where(column == value)
    order = (AuditEvent.created_at.desc(), _ROWID.desc()) if newest_first else (AuditEvent.created_at, _ROWID)
    return list(session.scalars(query.order_by(*order).limit(limit)))
