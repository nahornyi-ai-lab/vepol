"""Invoices are rows in the append-only ledger; corrections are new rows."""
from __future__ import annotations

import datetime as dt
import uuid

from .money import Money


def issue_invoice(db, order_id: str, lines: list[tuple[str, Money]]) -> str:
    invoice_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.timezone.utc)
    with db.transaction():
        for description, amount in lines:
            db.execute(
                "INSERT INTO ledger (invoice_id, order_id, description, cents, currency, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (invoice_id, order_id, description, amount.cents, amount.currency, now),
            )
    return invoice_id
