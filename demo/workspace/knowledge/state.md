# Vepol hub — current state

> Permanent contract: present-tense, overwrite-only. This file answers
> "where are we right now?" It is not a log, report, proof list, or archive.
> Historical dates, completed work, review results, test proof, resolved
> blockers, and old snapshots belong in `log.md`, `reports/`, `decisions/`,
> `sources/`, or thematic pages. Current deadlines, active offers, metric
> timestamps, source freshness, and `Last Updated` dates are allowed.

## Current Snapshot

Three projects are active for Acme's shop: acme-web is rolling out checkout v2, billing-api is unblocking Apple Pay and then refunds, and design-system is finishing the v3 migration guide.

## Active Focus

- One release calendar for acme-web and billing-api, so checkout changes and API changes land together.
- The cross-project dependency: acme-web's Apple Pay button waits on billing-api.

## Key Facts And Constraints

- Each project keeps its own memory in `code/<project>/knowledge/`; the hub links them under `projects/`.
- Agents change boards only through `kb-board`.

## Next Actions

1. Agree the release calendar with both teams.
2. Collect the prevention rules that apply to more than one project into the hub.
3. Write an onboarding note for the next developer.

## Waiting / Blockers

_(none at hub level; see each project)_

## Open Questions

- Should the billing admin pages move to design tokens v3 before or after refunds ship?

## References

- [acme-web](projects/acme-web/state.md)
- [design-system](projects/design-system/state.md)
- [billing-api](projects/billing-api/state.md)

## Last Updated

2026-09-25 — weekly review done.
