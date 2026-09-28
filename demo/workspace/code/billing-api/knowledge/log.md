# billing-api — log

Append-only. Format: `## [YYYY-MM-DD] <category> | billing-api | "<summary>"` and a short body.

## [2026-09-08] fix | billing-api | "Lost cent on split payments"

A three-way split of 100.00 left the ledger one cent short. Traced to float
arithmetic in the split helper. Incident written up.

## [2026-09-09] decision | billing-api | "Money becomes integer cents"

See decisions/money-as-integer-cents.md.

## [2026-09-12] milestone | billing-api | "Idempotency keys on POST /payments"

Needed by acme-web after its double-charge incident. A repeated key returns the
first result instead of charging again.

## [2026-09-18] decision | billing-api | "Invoices move to an append-only ledger"

See decisions/ledger-tables.md.

## [2026-09-21] milestone | billing-api | "Invoices run on the ledger"

All new invoices write ledger rows; old invoices were copied over and the totals
match to the cent.

## [2026-09-22] blocker | billing-api | "Webhook retries wait on the payment provider"

Signed retries have to be enabled on the provider side. Support ticket open.

## [2026-09-24] planning | billing-api | "Apple Pay verification file first"

acme-web is blocked on it, and it is a one-hour job. Refunds come right after.
