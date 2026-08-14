# Backlog — kb-board valid fixture

## Backlog

- [ ] Backlog task
  plan_item_id: pi-backlog
  priority: P2
  owner: unassigned
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Ready when triaged.
  body: |
    Backlog details.

## Ready

- [ ] Ready task
  plan_item_id: pi-ready
  priority: P1
  owner: codex
  depends_on: [pi-done]
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Claim moves it to In Progress and mints a lease.
  body: |
    Ready details.

## In Progress

- [>] Active task
  plan_item_id: pi-active
  priority: P1
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  claim_owner: codex
  claim_id: clm-active
  claim_expires_at: 2026-05-29T10:15:00Z
  acceptance: |
    Request review preserves provenance.
  body: |
    Active details.

- [>] Expired task
  plan_item_id: pi-expired
  priority: P2
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  claim_owner: claude-code
  claim_id: clm-expired
  claim_expires_at: 2026-05-29T08:00:00Z
  acceptance: |
    Sweep moves it back to Ready.
  body: |
    Expired details.

## Blocked

- [ ] Blocked task
  plan_item_id: pi-blocked
  priority: P2
  owner: antigravity
  created: 2026-05-29
  updated: 2026-05-29
  blocked_reason: |
    waiting on dependency
  acceptance: |
    Unblock can move it to In Progress.
  body: |
    Blocked details.

## Review

- [>] Review task
  plan_item_id: pi-review
  priority: P1
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  claim_owner: claude-code
  claim_id: clm-review
  claim_expires_at: 2026-05-29T09:00:00Z
  acceptance: |
    Review provenance is checked before close or return.
  body: |
    Review details.

## Done

- [x] Done task
  plan_item_id: pi-done
  priority: P2
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Done stays terminal until explicit reopen.
  evidence: |
    Finished in fixture.
  body: |
    Done details.

## Cancelled

- [~] Cancelled task
  plan_item_id: pi-cancelled
  priority: P3
  owner: unassigned
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Cancelled stays terminal until explicit reopen.
  evidence: |
    Cancelled in fixture.
  body: |
    Cancelled details.
