"""Sandbox insurer and payment providers.

Deterministic and idempotent: every request is stored in `provider_records` under (provider, operation,
idempotency key), and the same key returns the stored response without acting again. The caller owns the
session and commits; providers run in their own short session, never inside an action's write transaction.
Behavior switches come from the farm's `demo_settings` (`payment_mode`, `insurer_activation`).
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.ids import new_id
from persistence.models import DemoSettings, ProviderRecord


class ProviderTimeout(Exception):
    """The provider did not answer in time. The request may still have been acted on: reconcile by key."""


def lookup(session: Session, provider: str, operation: str, key: str) -> ProviderRecord | None:
    return session.scalar(select(ProviderRecord).where(ProviderRecord.provider == provider,
                                                       ProviderRecord.operation == operation,
                                                       ProviderRecord.idempotency_key == key))


def store(session: Session, provider: str, operation: str, key: str, request: dict, response: dict) -> dict:
    session.add(ProviderRecord(id=new_id("prv"), provider=provider, operation=operation, idempotency_key=key,
                               request=dict(request), response=dict(response)))
    session.flush()
    return response


def reference(prefix: str, key: str) -> str:
    """A stable provider reference derived from the idempotency key."""
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:10].upper()}"


def demo_settings(session: Session, farm_id: str) -> DemoSettings:
    row = session.get(DemoSettings, farm_id)
    return row if row is not None else DemoSettings(farm_id=farm_id, payment_mode="succeed",
                                                    insurer_activation="confirm")
