# Backlog — terminal dependency fixture

## Ready

- [ ] Depends on terminal tasks
  plan_item_id: pi-terminal-dependent
  priority: P1
  owner: codex
  depends_on: [pi-terminal-done, pi-terminal-cancelled]
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Done and Cancelled dependencies count as existing resolved references.
  body: |
    Valid.

## Done

- [x] Terminal done
  plan_item_id: pi-terminal-done
  priority: P2
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Terminal.
  evidence: |
    Done.
  body: |
    Done.

## Cancelled

- [~] Terminal cancelled
  plan_item_id: pi-terminal-cancelled
  priority: P2
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Terminal.
  evidence: |
    Cancelled.
  body: |
    Cancelled.
