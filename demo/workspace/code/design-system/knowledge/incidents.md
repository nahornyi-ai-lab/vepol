# Incidents — design-system

Every error, broken deploy or surprise that needed a manual fix is written down
here. After the fix, ask what would stop it from happening again, and add a rule
or an automated guard below.

## Ongoing

_(none)_

## Resolved

### [2026-09-11] Header text failed contrast

- Symptoms: muted text on the dark header was hard to read; measured 3.1:1.
- Root cause: a new header colour was published without checking text on it.
- Fix: the header uses text.inverse; the build runs a contrast check.
- Prevention: see the rule below.

## Prevention rules

- Run the contrast check on every new colour token before publishing it — source: [2026-09-11 header contrast]

## Automated guards

- `npm run contrast` fails the build on any pair under WCAG AA — where: CI — from: [2026-09-11]
