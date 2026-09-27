# billing-api

Prices, invoices, payments and refunds for Acme's shop (fictional sample project
for the Vepol demo).

- `app/money.py` — integer-cent money type.
- `app/invoices.py` — invoices written to the append-only ledger.
- `app/payments.py` — payment requests with idempotency keys.

```sh
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/pytest
```
