# design-system — log

Append-only. Format: `## [YYYY-MM-DD] <category> | design-system | "<summary>"` and a short body.

## [2026-09-08] milestone | design-system | "Tokens v3 planning started"

Three copies of the colour palette had drifted apart. Plan: one JSON source,
generated CSS and email output, a contrast check in CI.

## [2026-09-09] decision | design-system | "Tokens become plain JSON"

See decisions/tokens-as-json.md.

## [2026-09-11] fix | design-system | "Header text contrast fixed"

Muted text on the dark header measured 3.1:1, under the 4.5:1 AA minimum. The
header now uses text.inverse. The contrast check is now part of the build.

## [2026-09-13] release | design-system | "Tokens v3.0.0 published"

acme-web switched the same day. The billing admin pages stay on v2 for now.

## [2026-09-17] decision | design-system | "Proposed: components without CSS-in-JS"

Waiting for the owner. See decisions/no-css-in-js.md.

## [2026-09-19] review | design-system | "Focus ring for inputs sent to review"

Every input and button gets a 2 px focus.ring outline; keyboard-only checkout
now shows where focus is at every step.
