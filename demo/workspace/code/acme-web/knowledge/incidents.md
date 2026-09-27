# Incidents — acme-web

Every error, broken deploy or surprise that needed a manual fix is written down
here. After the fix, ask what would stop it from happening again, and add a rule
or an automated guard below.

## Ongoing

_(none)_

## Resolved

### [2026-09-12] Double charge on slow networks

- Symptoms: two shoppers were charged twice for one order on 2026-09-11.
- Root cause: the "Pay" button stayed active while the request was in flight; a
  second tap sent a second payment.
- Fix: the button locks on the first click and every attempt carries one
  idempotency key; billing-api rejects a repeated key.
- Prevention: see the first rule below.

## Prevention rules

- Lock every payment submit button on the first click and send an idempotency key with each payment request — source: [2026-09-12 double charge]
- Raise a rollout flag only after the error rate has held under 0.5% for 3 days — source: [2026-09-19 checkout v2 at 5%]

## Automated guards

- A checkout test clicks "Pay" twice and expects exactly one payment — where: `tests/checkout.spec.ts` — from: [2026-09-12]
