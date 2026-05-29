# Backlog — dependency cycle fixture

## Ready

- [ ] Cycle A
  plan_item_id: pi-cycle-a
  priority: P1
  owner: codex
  depends_on: [pi-cycle-b]
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Must reject cycle.
  body: |
    A.

- [ ] Cycle B
  plan_item_id: pi-cycle-b
  priority: P1
  owner: codex
  depends_on: [pi-cycle-a]
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Must reject cycle.
  body: |
    B.
