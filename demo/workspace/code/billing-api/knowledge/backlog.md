# Backlog — billing-api

## Backlog

- [ ] Nightly ledger reconciliation report
  plan_item_id: ba-6
  priority: P2
  owner: unassigned
  created: 2026-09-21
  updated: 2026-09-21
  acceptance: |
    The report lists any difference with the rows that cause it.
  body: |
    Compare the ledger total with the provider payout every night.

## Ready

- [ ] Publish the Apple Pay domain verification file for acme-web
  plan_item_id: ba-3
  priority: P2
  owner: unassigned
  created: 2026-09-24
  updated: 2026-09-24
  acceptance: |
    The file is served from the shop domain and acme-web confirms.
  body: |
    acme-web's Apple Pay button is blocked on it.

- [ ] Refunds endpoint
  plan_item_id: ba-4
  priority: P2
  owner: unassigned
  created: 2026-09-21
  updated: 2026-09-21
  acceptance: |
    A refund shows up as a negative row and the order balance is zero.
  body: |
    POST /refunds writes a negative ledger row; full refunds first.

## Blocked

- [ ] Webhook retries with signed payloads
  plan_item_id: ba-5
  priority: P2
  owner: unassigned
  created: 2026-09-19
  updated: 2026-09-22T16:00:00Z
  blocked_reason: |
    the payment provider has to enable signed retries on our account
  acceptance: |
    A dropped webhook is retried and processed once.
  body: |
    Retry failed provider webhooks and verify their signatures.

## Done

- [x] Idempotency keys on POST /payments
  plan_item_id: ba-1
  priority: P2
  owner: unassigned
  created: 2026-09-12
  updated: 2026-09-12T17:00:00Z
  acceptance: |
    Two identical requests with one key create one payment.
  evidence: |
    closed
  body: |
    A repeated key returns the first result instead of charging again.

- [x] Move invoices onto the ledger
  plan_item_id: ba-2
  priority: P2
  owner: unassigned
  created: 2026-09-18
  updated: 2026-09-21T17:00:00Z
  acceptance: |
    Old and new totals match to the cent for every invoice.
  evidence: |
    closed
  body: |
    New invoices write ledger rows; copy old invoices over and compare totals.
