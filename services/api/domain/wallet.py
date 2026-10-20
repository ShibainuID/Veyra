"""The sandbox wallet ledger.

Entries are append-only: `credit` and `debit` move the balance; `hold` reserves funds for an executing payment
and `release` returns the reservation. A successful payment releases its hold and posts the debit; a declined one
only releases. Available = credits − debits − holds + releases (same signs as the herd summary).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.ids import new_id
from persistence.models import WalletEntry

ENTRY_TYPES = ("credit", "debit", "hold", "release")
CURRENCY = "USD"


def totals(session: Session, farm_id: str) -> dict[str, int]:
    rows = session.execute(select(WalletEntry.entry_type, func.sum(WalletEntry.amount_minor))
                           .where(WalletEntry.farm_id == farm_id).group_by(WalletEntry.entry_type)).all()
    found = {entry_type: int(total or 0) for entry_type, total in rows}
    return {entry_type: found.get(entry_type, 0) for entry_type in ENTRY_TYPES}


def summary(session: Session, farm_id: str) -> dict:
    t = totals(session, farm_id)
    balance = t["credit"] - t["debit"]
    held = t["hold"] - t["release"]
    return {"balance_minor": balance, "held_minor": held, "available_minor": balance - held, "currency": CURRENCY}


def balance(session: Session, farm_id: str) -> int:
    """The available balance: credits − debits − holds + releases."""
    return summary(session, farm_id)["available_minor"]


def post(session: Session, farm_id: str, entry_type: str, amount_minor: int, description: str,
         action_id: str | None = None, currency: str = CURRENCY) -> WalletEntry:
    if entry_type not in ENTRY_TYPES:
        raise ValueError(f"unknown wallet entry type {entry_type!r}")
    if amount_minor <= 0:
        raise ValueError("wallet entries carry a positive amount")
    entry = WalletEntry(id=new_id("wal"), farm_id=farm_id, entry_type=entry_type, amount_minor=amount_minor,
                        currency=currency, action_id=action_id, description=description)
    session.add(entry)
    return entry


def entries(session: Session, farm_id: str) -> list[WalletEntry]:
    return list(session.scalars(select(WalletEntry).where(WalletEntry.farm_id == farm_id)
                                .order_by(WalletEntry.created_at.desc(), WalletEntry.id.desc())))
