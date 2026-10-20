"""Record IDs: `<prefix>-<uuid4 hex[:12]>`, e.g. `act-1a2b3c4d5e6f`."""

from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"
