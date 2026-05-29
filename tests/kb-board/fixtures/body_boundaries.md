# Backlog — body boundary fixture

## Ready

- [ ] Boundary task
  plan_item_id: pi-boundary
  priority: P1
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    Parser keeps body lines inside this task.
  body: |
    ### Not a task boundary
    ## Not a status boundary because it is indented literal body
    - [ ] indented body checklist item
    A body line may mention plan_item_id: fake without creating metadata.

- [ ] Next real task
  plan_item_id: pi-after-boundary
  priority: P2
  owner: codex
  created: 2026-05-29
  updated: 2026-05-29
  acceptance: |
    This is the second real task.
  body: |
    Separate task.
