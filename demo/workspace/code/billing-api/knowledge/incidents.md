# Incidents — billing-api

Every error, broken deploy or surprise that needed a manual fix is written down
here. After the fix, ask what would stop it from happening again, and add a rule
or an automated guard below.

## Ongoing

_(none)_

## Resolved

### [2026-09-08] Lost cent on split payments

- Symptoms: the daily ledger total was one cent short of the provider payout.
- Root cause: the split helper divided a float amount and rounded each share down.
- Fix: money is integer cents; splits hand the remainder to the first shares.
- Prevention: see the rule below.

## Prevention rules

- Never use floats for money; convert to integer cents once, at the API edge — source: [2026-09-08 lost cent]
- Never UPDATE or DELETE a ledger row; write a correcting row instead — source: [2026-09-18 ledger decision]

## Automated guards

- A lint rule flags `float(` inside `app/` — where: CI — from: [2026-09-08]
