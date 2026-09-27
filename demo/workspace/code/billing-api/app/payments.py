"""Payment requests. A repeated idempotency key returns the first result."""
from __future__ import annotations


class DuplicatePayment(Exception):
    pass


def create_payment(db, provider, idempotency_key: str, order_id: str, cents: int, currency: str) -> dict:
    existing = db.fetch_one("SELECT result FROM payments WHERE idempotency_key = %s", (idempotency_key,))
    if existing:
        return existing["result"]
    result = provider.charge(order_id=order_id, cents=cents, currency=currency, key=idempotency_key)
    db.execute("INSERT INTO payments (idempotency_key, order_id, result) VALUES (%s, %s, %s)",
               (idempotency_key, order_id, result))
    return result
