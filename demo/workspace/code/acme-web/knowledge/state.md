# acme-web — current state

> Permanent contract: present-tense, overwrite-only. This file answers
> "where are we right now?" It is not a log, report, proof list, or archive.
> Historical dates, completed work, review results, test proof, resolved
> blockers, and old snapshots belong in `log.md`, `reports/`, `decisions/`,
> `sources/`, or thematic pages. Current deadlines, active offers, metric
> timestamps, source freshness, and `Last Updated` dates are allowed.

## Current Snapshot

Checkout v2 is live for 20% of shoppers behind the checkout-v2 flag. Card payments work; saved addresses are the last missing piece before a full rollout.

## Active Focus

- Saved addresses in checkout v2 (in progress, claude).
- Checkout error rate on the dashboard: it must hold under 0.5% for 3 days before the flag goes to 50%.

## Key Facts And Constraints

- Checkout pages are server-rendered ([decision](decisions/checkout-server-rendering.md)).
- Feature flags live in `config/flags.json` and ship with the deploy ([decision](decisions/flags-in-config.md)).
- Prices, tax and payments come from billing-api; the storefront only displays them.
- The address form reuses the design-system text inputs (tokens v3).

## Next Actions

1. Finish saved addresses and request review.
2. Raise checkout-v2 to 50% once the error rate holds under 0.5% for 3 days.
3. Add the Apple Pay button as soon as billing-api publishes the domain verification file.
4. Remove the old checkout one week after v2 reaches 100%.

## Waiting / Blockers

- Apple Pay: waiting for billing-api to publish the domain verification file.

## Open Questions

- Do guest shoppers get saved addresses, or only signed-in ones?

## References

- [Server-render the checkout pages](decisions/checkout-server-rendering.md)
- [Feature flags live in a config file](decisions/flags-in-config.md)
- [Prevention rules](incidents.md#prevention-rules)

## Last Updated

2026-09-26 — saved addresses started; checkout-v2 at 20%.
