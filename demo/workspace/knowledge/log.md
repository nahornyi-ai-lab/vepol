# Vepol hub — log

Append-only. Format: `## [YYYY-MM-DD] <category> | <project> | "<summary>"` and a short body.

## [2026-09-08] milestone | hub | "Workspace set up with three projects"

acme-web, design-system and billing-api linked under projects/. Each keeps its
own state, log, backlog, decisions and incidents.

## [2026-09-12] cross-project | billing-api | "Idempotency keys requested by acme-web"

acme-web's double-charge fix needs billing-api to reject repeated payment keys.
Done the same day.

## [2026-09-13] release | design-system | "Design tokens v3 published"

acme-web switched the same day; the billing admin pages stay on v2 until the
migration guide is out.

## [2026-09-18] review | hub | "Weekly review"

acme-web on track for a 5% rollout; design-system v3 published; billing-api
moving invoices to the ledger. No blockers at hub level.

## [2026-09-22] blocker | billing-api | "Webhook retries wait on the payment provider"

Not urgent for checkout; tracked on billing-api's board.

## [2026-09-25] review | hub | "Weekly review"

acme-web at 20% and blocked on Apple Pay by billing-api; billing-api moved the
verification file to the top. Started the shared release calendar.
