---
title: "Invoices write to an append-only ledger"
date: 2026-09-18
status: accepted
tags: [ledger, data-model]
---

# Invoices write to an append-only ledger

## Context

Invoices were updated in place. When support corrected an amount, the history of
what the customer was first charged was lost.

## Decision

Invoices, payments and refunds are rows in one `ledger` table that is never
updated or deleted. A correction or a refund is a new row with a negative amount.

## Consequences

- Any balance is a sum over rows; the reconciliation report is a single query.
- The database role used by the API has no UPDATE or DELETE on `ledger`.
