"""Sandbox payments: charges a premium from the farm's sandbox wallet. No real money moves.

`payment_mode` from `demo_settings`: `succeed` charges; `fail` declines with `SANDBOX_DECLINED`; `timeout` stores
the request and a succeeded response (a charge that landed) and then raises `ProviderTimeout`, so the caller
must reconcile by key instead of charging again.
"""

from sqlalchemy.orm import Session

from adapters.sandbox import ProviderTimeout, demo_settings, lookup, reference, store
from domain import clock

PROVIDER = "sandbox-payment"
OPERATION = "charge"


def charge(session: Session, key: str, payload: dict, *, farm_id: str) -> dict:
    existing = lookup(session, PROVIDER, OPERATION, key)
    if existing is not None:
        return dict(existing.response)
    mode = demo_settings(session, farm_id).payment_mode
    if mode == "fail":
        return store(session, PROVIDER, OPERATION, key, payload, {
            "status": "declined", "code": "SANDBOX_DECLINED", "message": "The sandbox payment was declined."})
    response = {"status": "succeeded", "payment_ref": reference("SBX-PAY", key),
                "amount_minor": payload["amount_minor"], "currency": payload["currency"],
                "charged_at": clock.isoformat(clock.now())}
    store(session, PROVIDER, OPERATION, key, payload, response)
    if mode == "timeout":
        raise ProviderTimeout("sandbox payment timed out after the charge was recorded")
    return response
