# Cycle plan decompose — project {{SLUG}}

You are running a morning plan-decompose pass for project **{{SLUG}}**.

Working directory: `{{KNOWLEDGE_PATH}}` (this is `<project>/knowledge/`).

## Context

The hub has just received an approved daily plan. It already grouped
plan items by immediate-child slug and added each immediate-child's
batch as `decompose:` marker lines in their backlogs.

For YOU (slug `{{SLUG}}`) the marker line is at lineno
`{{DECOMPOSE_LINENO}}`:

```
{{DECOMPOSE_LINE}}
```

The marker carries `plan_item_ids: [{{PLAN_ITEM_IDS}}]` referencing the
original approved-plan items, and `cycle_source_id: {{CYCLE_SOURCE_ID}}`
for idempotent retry.

## Targets

These items target your descendants (one level deeper):

{{TARGETS_BLOCK}}

## What to do

For each target item:

1. Decide which of your direct children it lands in.
2. If the target is for THIS project (not a descendant): close the
   marker as `[x] decomposed: handled inline by {{SLUG}} on {{DATE}}`
   and add a regular open task to your own backlog via:
   ```
   kb-backlog append {{SLUG}} "<task body>" --plan-item-id <uuid> --cycle-source-id <uuid>
   ```
3. If the target is for a direct child:
   - **Leaf child**: `kb-backlog append <child-slug> "<task body>" --plan-item-id ... --cycle-source-id ...`
     (carried-item handling — open/closed/parent-moved/duplicate — is the
     hub-side concern; you just append).
   - **Intermediate child** with multiple descendant targets: append ONE
     `decompose:` marker to that child's backlog, listing the relevant
     plan_item_ids; the cycle will spawn the child to expand.
4. After all targets are dispatched, close YOUR marker line:
   ```
   kb-backlog close {{SLUG}} --line {{DECOMPOSE_LINENO}} --claim-id <token-from-claim> --outcome closed
   ```
   (You'll need to claim it first: `kb-backlog claim {{SLUG}} --line {{DECOMPOSE_LINENO}}`)

## Rules

- Use ONLY the `kb-backlog` CLI for backlog mutations. Never edit
  backlog.md by hand.
- Each `kb-backlog append` MUST include `--plan-item-id` and
  `--cycle-source-id` so re-runs are idempotent.
- If a plan_item_id already has an open row in the target backlog,
  `kb-backlog append` will skip with `status: skipped`. That's expected
  — the hub-side carried-item logic handles updates separately.
- Don't escalate unless you're truly blocked. Most "I don't know which
  child handles this" cases mean: pick the most plausible direct child,
  let it escalate up if wrong.

## Output

Print exactly one of these as your last non-empty stdout line:

    OUTCOME: closed: decomposed N items into M children
    OUTCOME: escalated: <reason>
    OUTCOME: failed: <reason>

Do not emit OUTCOME more than once. Do not write anything to stdout
after it.
