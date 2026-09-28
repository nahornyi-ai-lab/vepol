# Backlog — hub

## Backlog

- [ ] Onboarding note for the next developer
  plan_item_id: hub-4
  priority: P2
  owner: unassigned
  created: 2026-09-18
  updated: 2026-09-18
  acceptance: |
    A new developer can start a session in any project using only the note.
  body: |
    Where each project's memory lives, how the boards work, what to read first.

## Ready

- [ ] Collect cross-project prevention rules into the hub
  plan_item_id: hub-3
  priority: P2
  owner: unassigned
  created: 2026-09-25
  updated: 2026-09-25
  acceptance: |
    Hub incidents.md lists every rule that applies to more than one project.
  body: |
    The idempotency rule appears in both acme-web and billing-api; keep one copy in the hub.

## In Progress

- [>] Shared release calendar for acme-web and billing-api
  plan_item_id: hub-2
  priority: P2
  owner: unassigned
  created: 2026-09-25
  updated: 2026-09-25T10:00:00Z
  claim_owner: codex
  claim_id: clm-657c5be848d4
  claim_expires_at: 2026-09-25T10:15:00Z
  acceptance: |
    Both projects' state.md link the calendar and name the next release day.
  body: |
    Checkout changes and billing-api changes should land in the same weekly window.

## Done

- [x] Weekly review of all three projects
  plan_item_id: hub-1
  priority: P2
  owner: unassigned
  created: 2026-09-18
  updated: 2026-09-25T17:00:00Z
  acceptance: |
    Hub log has a review entry and every blocker names the project that owns it.
  evidence: |
    closed
  body: |
    Read every project's state, log and board; note cross-project blockers in the hub log.
