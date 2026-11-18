---
title: "Vepol Idea Intake — catch every idea, act on the good ones"
status: stable
since: v0.3.0
type: process
parent: vepol
---

# Vepol Idea Intake

Never lose an idea, and never owe every idea your time. One command captures
a passing thought as a Markdown card. You decide what it is worth. The ready
ones show up in your morning brief, become a task on your board, or get a
block in your calendar once you approve it.

```bash
kb-idea capture "Build a tiny demo that proves this offer works"
```

## What you get

- **Capture in seconds.** `kb-idea capture` writes a card to
  `~/knowledge/personal/ideas/<idea-id>.md` and refreshes the dashboard,
  `~/knowledge/personal/ideas.md`. Captured means "not lost", not "must do".
- **Triage.** Set a priority, the smallest next step and the evidence that
  would prove the idea. Or park it, drop it, or mark it merged into another.
- **A duplicate check.** Triage compares the title with your other idea cards
  and names a likely duplicate before you promote it.
- **Ideas in your morning brief.** Up to three ready or promoted ideas, most
  urgent first, each with its next step, in the brief's 💡 Ideas section.
- **One step to a task.** Promotion creates a Ready task on your hub's or a
  project's `kb-board` and links it back to the card.
- **Calendar blocks you approve.** Propose a time block for an idea. The event
  appears in Google Calendar only when you approve it with `--apply`.
- **A closed loop.** Finish with the outcome, written back to the card.
- **Search.** `kb-search` finds your idea cards along with everything else.

## When it works

Right after install, once the Python packages from
[`requirements.txt`](../../requirements.txt) are installed (`kb-idea` needs
`python-frontmatter`). There is nothing to schedule: an idea arriving is the
trigger. Run `kb-idea capture` yourself, or ask your agent to run it for you.
Creating calendar events with `--apply` needs Google Calendar connected in
Claude Code.

## How an idea moves

```text
capture -> triage -> morning brief -> promote to a board task
  -> calendar block (after you approve) -> done, with the outcome
```

### Capture

```bash
kb-idea capture "Build a tiny demo that proves this offer works"
```

```text
id=idea-20261118-0950-build-a-tiny-demo-that path=/Users/you/knowledge/personal/ideas/idea-20261118-0950-build-a-tiny-demo-that.md
```

The title is the first few words; `--title` sets your own. `--source`
records where the idea came from (default `chat`).

### Triage

```bash
kb-idea triage <idea-id> \
  --priority P0 \
  --materiality cheap-test \
  --next-action "Ship one visible proof" \
  --evidence "One reply, click or explicit rejection"
```

Priorities run from `P0` (most urgent) to `P3`. Materiality is `trivial`,
`cheap-test` or `material`. A triaged idea becomes `ready`; a `material` one
goes to `critique` first (see [Material Idea Path](#material-idea-path)).
Other options:

- `--status parked`, `killed` or `merged` sets the idea aside instead.
- `--why "..."` fills the card's "Why it matters" section.
- `--line <name>` tags the idea with a strategic line (repeatable).

You can triage an idea again at any time. Each triage sets the priority,
materiality, lines, next step and evidence anew, so pass all of them again.
If you leave them out, priority falls back to `P2` and materiality to
`cheap-test`.

### See what reaches the brief

```bash
kb-idea brief
```

```text
Idea proposals:
- P0 idea-20261118-0950-build-a-tiny-demo-that: Build a tiny demo that
  Step: Ship one visible proof
  Evidence: One reply, click or explicit rejection
```

This is exactly what the morning brief receives: the top three ready or
promoted ideas, highest priority first (`--limit` shows more). The brief turns
them into one line each. The morning audio digest includes them with the rest
of the brief.

### Promote to a task

```bash
kb-idea promote <idea-id> --project hub --create-task
```

`--project hub` uses your hub's board, `~/knowledge/backlog.md`.
`--project <slug>` uses that project's board through
`~/knowledge/projects/<slug>/backlog.md`. The new task lands in Ready, with the
idea's priority, and its evidence as the task's acceptance. Running the
command again never creates a second task. To link a task that already exists
instead, pass `--plan-item-id <id>` without `--create-task`.

### Block time in your calendar

Propose a block. Nothing touches your calendar yet:

```bash
kb-idea calendar propose <idea-id> \
  --title "Idea proof block" \
  --start "2026-11-20T15:00:00+01:00" \
  --end "2026-11-20T15:45:00+01:00"
```

```text
id=<idea-id> proposal_id=cal-20261120-01
```

The time zone is `KB_TZ`, else your Mac's own; `--timezone` overrides it.
Approve the block and create the event:

```bash
kb-idea calendar approve <idea-id> cal-20261120-01 --apply
```

Vepol creates the event in Google Calendar through Claude Code's Google
Calendar connector and writes the event ID back to the card. If you made the
event yourself, record it instead:

```bash
kb-idea calendar approve <idea-id> cal-20261120-01 --event-id <calendar-event-id>
```

### Close the loop

```bash
kb-idea done <idea-id> --outcome "Ran the test; three replies, one paid pilot."
```

If you edit a card by hand, `kb-idea render` rebuilds the dashboard.

## Card schema

Each card has YAML frontmatter for state and Markdown sections for the
thinking.

Core fields:

```yaml
id: idea-YYYYMMDD-HHMM-short-slug
title: "..."
created_at: 2026-06-20T10:35:00+02:00
source: chat
status: captured
priority: P2
materiality: cheap-test
plan_item_id: null
calendar_event_ids: []
calendar_proposals: []
```

Triage adds `next_action` and `expected_evidence`; promotion adds
`promoted_at` and `project_slug`. Status is one of `captured`, `triage`,
`critique`, `ready`, `promoted`, `parked`, `killed`, `merged` or `done`.

Sections:

- `Raw idea`: your words, kept as written
- `Interpretation`
- `Why it matters`
- `Dedupe`: the duplicate check's result
- `Critique`
- `Priority`
- `Next action`: the step and its evidence
- `Promotion`: the task pointer and calendar proposals
- `Outcome`

## Material Idea Path

Most ideas are cheap to test. Some are not: a new way of working, anything
other people will see, infrastructure, security-sensitive work, or anything
beyond a small fix. Triage those with `--materiality material`. The card then
waits in `critique` until you have weighed it. To move it on, triage it again
with `--materiality material --status ready` (or `parked`, or `killed`).

Before you build a material idea, Vepol's working method adds research and
your approval:

```text
capture -> triage -> research -> owner-approved specification
  -> approval recorded in knowledge/spec-approvals.md with the exact spec-contract hash
  -> post-approval build plan
  -> RED tests including E2E
  -> kb-board task owns execution state
  -> verification -> outcome
```

The spec-contract hash is a fingerprint of the approved spec, so any later
change to the spec shows. "RED tests including E2E" means the tests are written
first and fail (red) until the work is done, and at least one of them checks
the whole path end to end (E2E). The
[Spec-Driven Workflow](../methodology/spec-driven-workflow.md) explains each
step.

This path is a method you and your agents follow. `kb-idea` does not enforce
it, and the card has no fields for it. Link the research, spec and plan from
the card's sections if you want them there.

## Source of truth

Before promotion, the idea card owns the idea's state. After promotion, the
`kb-board` task owns the execution state. The card keeps only the pointer
(`plan_item_id`) and the outcome you record with `kb-idea done`. The card does
not track progress, so it never contradicts the board.

## What this is not

- Not an inbox that fills itself. Nothing picks ideas out of your chats on its
  own; you capture them, or ask your agent to.
- Not a scheduled job in `processes.yaml`.
- Not a replacement for `kb-board`.
- Not a calendar bot. No event is created without your `approve --apply`.
- Not a promise that every idea deserves work.

## If something does not work

- **Ready ideas never reach the brief.** Run `kb-idea brief`. The error
  `ModuleNotFoundError: No module named 'frontmatter'` means the Python
  packages are missing; the brief skips ideas silently in that case. Scheduled
  runs use the first `python3` on `/opt/homebrew/bin:/usr/local/bin:/usr/bin`,
  so install them for that Python: from your Vepol folder, run
  `python3 -m pip install --user -r requirements.txt` (if pip refuses, see
  [Python packages](../dependency-matrix.md#python-packages)).
- **Promotion fails with `EORIGINAL`.** The board is not in `kb-board`'s
  format. Check it with `kb-board check <path-to-backlog.md>`, then follow the
  fix the message names.
- **`approve --apply` fails.** Check that Google Calendar is connected in
  Claude Code, or create the event yourself and record it with `--event-id`.

The first job stays simple: when an idea arrives, Vepol does not lose it.
