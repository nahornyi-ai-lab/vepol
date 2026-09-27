# design-system — current state

> Permanent contract: present-tense, overwrite-only. This file answers
> "where are we right now?" It is not a log, report, proof list, or archive.
> Historical dates, completed work, review results, test proof, resolved
> blockers, and old snapshots belong in `log.md`, `reports/`, `decisions/`,
> `sources/`, or thematic pages. Current deadlines, active offers, metric
> timestamps, source freshness, and `Last Updated` dates are allowed.

## Current Snapshot

Design tokens v3 are published. acme-web already uses them; the billing admin pages still use v2, and the v2 to v3 migration guide is half written.

## Active Focus

- The v2 to v3 migration guide (in progress, codex).
- The accessible focus ring for inputs is waiting for review.

## Key Facts And Constraints

- Tokens are plain JSON, one source for web and email ([decision](decisions/tokens-as-json.md)).
- Every colour pair must pass WCAG AA contrast before a release.
- v2 tokens stay published until the billing admin pages have moved.

## Next Actions

1. Finish the migration guide and send it to billing-api.
2. Review and merge the focus ring change.
3. Start the date picker once the guide is out.

## Waiting / Blockers

_(none)_

## Open Questions

- Should components move off inline styles now, or after the migration? (see the proposed decision)

## References

- [Tokens are plain JSON](decisions/tokens-as-json.md)
- [Components ship without CSS-in-JS](decisions/no-css-in-js.md) (proposed)

## Last Updated

2026-09-19 — focus ring sent to review.
