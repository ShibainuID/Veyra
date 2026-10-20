"""Append-only audit events. Callers add the event in the same transaction as the change it records."""

import uuid

from sqlalchemy.orm import Session

from persistence.models import AuditEvent


def record(
    session: Session,
    farm_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    actor_type: str = "user",
    actor_id: uuid.UUID | str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        farm_id=farm_id,
        actor_type=actor_type,
        actor_id=str(actor_id) if actor_id else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
    )
    session.add(event)
    return event
