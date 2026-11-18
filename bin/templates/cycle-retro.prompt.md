# Cycle retro — project {{SLUG}}

You are running an evening retro cycle inside project **{{SLUG}}**.

Working directory: `{{KNOWLEDGE_PATH}}` (this is `<project>/knowledge/`).

## What to read (in this order)

1. **`backlog.md`** — your current open and recently-closed items.
2. **`log.md`** (last 80 lines) — what happened today and recent days.
3. **`~/knowledge/daily-plan/{{DATE}}.md`** if it exists — the hub's plan for
   today; this project's items are the lines tagged `({{SLUG}})`.
4. **`state.md`** — current snapshot of the project.
{{CHILD_REPORTS_BLOCK}}

## What to write — MANDATORY

You **MUST** completely overwrite `reports/{{DATE}}.md` with a full
report. The file currently contains a `status: pending` scaffold from
the pre-cycle pass — your job is to replace it with real content.

Even if the project had **zero activity today**, you must still write
the full report — explicitly note `What was done: nothing today` and
explain why (project idle, on hold, weekend, etc.). Do NOT leave the
pending scaffold in place. Do NOT exit without writing.

Frontmatter must use `report_id: {{SLUG}}-{{DATE}}`, `slug: {{SLUG}}`,
`date: {{DATE}}`, `cycle: evening`, `parent: {{PARENT_SLUG}}`,
`children_rolled_up: {{CHILDREN_LIST}}`, `status: done`,
`run_id: {{RUN_ID}}`. The `status: done` field is what tells the cycle
your report is real — without it, the cycle will mark you `partial`.

Sections:

- **What was done today** — concrete bullet items with refs to `backlog.md:N`
  or `log.md` entries.
- **What was planned** — your `({{SLUG}})` items from
  `~/knowledge/daily-plan/{{DATE}}.md` and any top-down tasks from parent.
- **Delta (plan − actual)** — closed: N, dropped: list, carried: list.
- **Candidates** — what could be done tomorrow, with priority and `auto:` flag.
- **Escalations** — blockers requiring `{{PARENT_SLUG}}`, owner, or external action.
- **Entity / asset deltas** — see below; mandatory section, never skip.

### Entity / asset deltas (new today)

Grep today's lines in `log.md` with this regex:
```
^## \[{{DATE}}\] (publish|account|subscription|person|company|asset) \|
```
plus freshly closed tasks in `backlog.md` with the same category prefixes. For each hit, write **one line** in this format, copying the identifying data verbatim:

```
- [<category>:<action>] <slug>: <description> [→ <provider>:<external_ref>] [@ source: log.md:<N> | backlog.md:<N>]
```

If there is nothing today, write:

```
(none)
```

**Do not interpret or add to the data**: this section feeds the deterministic hub rollup. If an entry in `log.md` is badly formatted, copy it as is; the hub parser decides what to do with it.

The categories are defined in `~/knowledge/_template/AGENTS.md` (Significant external state changes); the full spec, if the hub keeps one, is `~/knowledge/concepts/entity-extraction-cycle-pass.md`.

## Rules

- Write **only** to `reports/{{DATE}}.md` in this project. Do not touch
  any other file.
- If the report already exists with the same `run_id` ({{RUN_ID}}), skip.
- Be concise — one line per bullet, no padding.
- If a child report exists, **roll up its `Escalations` section** into your
  own (preserve attribution: `(from <child-slug>)`).

## Output

Print exactly one of these as your last non-empty stdout line:

    OUTCOME: closed: <one-line summary of what you put in the report>
    OUTCOME: failed: <reason if you couldn't generate a valid report>

Do not emit OUTCOME more than once. Do not write anything to stdout after it.
