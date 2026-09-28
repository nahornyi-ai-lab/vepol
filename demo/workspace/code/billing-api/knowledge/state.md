# billing-api — current state

> Permanent contract: present-tense, overwrite-only. This file answers
> "where are we right now?" It is not a log, report, proof list, or archive.
> Historical dates, completed work, review results, test proof, resolved
> blockers, and old snapshots belong in `log.md`, `reports/`, `decisions/`,
> `sources/`, or thematic pages. Current deadlines, active offers, metric
> timestamps, source freshness, and `Last Updated` dates are allowed.

## Current Snapshot

Invoices and card payments run on the new ledger. Next up are the Apple Pay verification file for acme-web and the refunds endpoint; webhook retries wait on the payment provider.

## Active Focus

- Publish the Apple Pay domain verification file (acme-web is blocked on it).
- Refunds endpoint: design agreed, not started.

## Key Facts And Constraints

- Money is integer cents plus a currency code ([decision](decisions/money-as-integer-cents.md)).
- Invoices write to an append-only ledger ([decision](decisions/ledger-tables.md)).
- Every POST /payments carries an idempotency key; repeats return the first result.

## Next Actions

1. Publish the Apple Pay verification file and tell acme-web.
2. Build POST /refunds on top of the ledger (a refund is a negative row).
3. Draft the nightly reconciliation report.

## Waiting / Blockers

- Webhook retries: the payment provider has to enable signed retries on our account (support ticket open).

## Open Questions

- Partial refunds in the first version, or full refunds only?

## References

- [Money as integer cents](decisions/money-as-integer-cents.md)
- [Append-only ledger](decisions/ledger-tables.md)

## Last Updated

2026-09-24 — Apple Pay file moved to the top of the list.
