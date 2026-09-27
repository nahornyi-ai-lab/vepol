---
title: "Store money as integer cents with a currency code"
date: 2026-09-09
status: accepted
tags: [money, data-model]
---

# Store money as integer cents with a currency code

## Context

Order totals were floats. A three-way split of 100.00 produced 33.33 + 33.33 +
33.33 and one cent disappeared from the ledger.

## Decision

Every amount is an integer number of cents plus an ISO currency code. API strings
are converted once, at the edge, with banker's rounding. Splits hand the remainder
to the first shares.

## Consequences

- No float arithmetic anywhere near money; a lint rule flags `float(` in `app/`.
- The API keeps accepting "19.99" strings for acme-web; the conversion lives in `Money.parse`.
