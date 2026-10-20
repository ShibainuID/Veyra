"""UTC clock with a test override (time is UTC, ISO 8601 with `Z`)."""

from collections.abc import Callable
from datetime import UTC, datetime


def _system_now() -> datetime:
    return datetime.now(UTC)


_now: Callable[[], datetime] = _system_now


def now() -> datetime:
    return _now()


def set_now(fn: Callable[[], datetime]) -> None:
    global _now
    _now = fn


def reset() -> None:
    set_now(_system_now)


def isoformat(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not allowed; use domain.clock.now()")
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
