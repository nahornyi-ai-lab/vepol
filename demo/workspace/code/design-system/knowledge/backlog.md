# Backlog — design-system

## Backlog

- [ ] Dark theme tokens
  plan_item_id: ds-5
  priority: P2
  owner: unassigned
  created: 2026-09-09
  updated: 2026-09-09
  acceptance: |
    Every colour pair in the dark set passes WCAG AA.
  body: |
    A second token set; not before the migration guide is out.

## Ready

- [ ] Date picker component
  plan_item_id: ds-4
  priority: P2
  owner: unassigned
  created: 2026-09-17
  updated: 2026-09-17
  acceptance: |
    The date picker passes the contrast check and works with the keyboard only.
  body: |
    Needed later for delivery slots; keyboard and screen-reader friendly from the start.

## In Progress

- [>] Write the v2 to v3 migration guide
  plan_item_id: ds-2
  priority: P2
  owner: unassigned
  created: 2026-09-14
  updated: 2026-09-14T10:00:00Z
  claim_owner: codex
  claim_id: clm-ad07756cd461
  claim_expires_at: 2026-09-14T10:15:00Z
  acceptance: |
    billing-api can move its admin pages to v3 using only the guide.
  body: |
    Token renames, removed tokens and a find-and-replace list for the billing admin pages.

## Review

- [>] Accessible focus ring for inputs and buttons
  plan_item_id: ds-3
  priority: P2
  owner: unassigned
  created: 2026-09-15
  updated: 2026-09-19T15:00:00Z
  claim_owner: claude
  claim_id: clm-76270002f710
  claim_expires_at: 2026-09-15T10:15:00Z
  acceptance: |
    Keyboard-only checkout shows the focused element at every step.
  body: |
    2 px focus.ring outline on every interactive component.

## Done

- [x] Publish design tokens v3
  plan_item_id: ds-1
  priority: P2
  owner: unassigned
  created: 2026-09-09
  updated: 2026-09-13T17:00:00Z
  acceptance: |
    v3.0.0 published and acme-web builds against it.
  evidence: |
    closed
  body: |
    One JSON source; generated CSS variables and email JSON; contrast check in the build.
