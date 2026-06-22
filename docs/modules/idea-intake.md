---
title: "Vepol Idea Intake — event-driven idea capture and execution"
status: stable
version: 0.3.0
type: process
parent: vepol
substrate: markdown
---

# Vepol Idea Intake

Vepol Idea Intake is the always-available process for ideas you do not want to
lose.

It is not a scheduled background job. It starts when you write, paste, or dictate
an idea. Vepol captures the raw thought into a structured markdown card, then
lets agents triage it, critique it, rank it, surface it in the daily brief,
promote it into a task, propose a calendar block, and write back the outcome.

```text
text or voice event
  -> capture card
  -> dashboard render
  -> triage / priority
  -> optional critique
  -> daily brief proposal
  -> research
  -> owner-approved specification
  -> post-approval build plan
  -> RED tests including E2E
  -> kb-board task
  -> calendar approval
  -> outcome
```

## What It Is

Idea Intake is an **event-driven Vepol process** backed by plain markdown:

- `personal/ideas/<idea-id>.md` is the canonical card for one idea.
- `personal/ideas.md` is a rendered dashboard from those cards.
- `kb-idea` is the CLI surface agents and humans can call.
- `kb-brief` reads ready/promoted ideas and can include them in the daily plan.
- `kb-board` owns execution state after promotion.

The process is always available because the store is always there. The trigger is
not a timer; the trigger is an idea arriving.

## Why This Exists

Ideas usually disappear in chat history, voice notes, or mental backlog. Vepol
needs a durable intake layer so a useful thought can become work without turning
every thought into an obligation.

The controls are explicit:

- captured means "not lost", not "must do";
- triage can kill, park, merge, or ready an idea;
- material ideas can require critique before commitment;
- ready ideas can enter the brief;
- promotion creates a normal markdown `kb-board` task;
- calendar writes require explicit approval.

## Basic Commands

Capture an idea:

```bash
kb-idea capture "Build a tiny demo that proves this offer works" --source chat
```

Triage it:

```bash
kb-idea triage <idea-id> \
  --priority P0 \
  --materiality cheap-test \
  --next-action "Ship one visible proof" \
  --evidence "one reply, click, or explicit rejection"
```

Show ideas that are ready for the daily brief:

```bash
kb-idea brief
```

Promote a ready idea into the markdown task board:

```bash
kb-idea promote <idea-id> --project hub --create-task
```

Propose a calendar block without writing to the calendar:

```bash
kb-idea calendar propose <idea-id> \
  --title "Idea proof block" \
  --start "2026-06-20T15:00:00+02:00" \
  --end "2026-06-20T15:45:00+02:00"
```

Record an approved calendar event:

```bash
kb-idea calendar approve <idea-id> cal-20260620-01 --event-id <calendar-event-id>
```

Close the loop:

```bash
kb-idea done <idea-id> --outcome "Ran the test; result was ..."
```

## Card Schema

Each card has YAML frontmatter for machine-readable state and markdown sections
for human-readable context.

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
```

Required sections:

- `Raw idea`
- `Interpretation`
- `Why it matters`
- `Dedupe`
- `Critique`
- `Priority`
- `Next action`
- `Promotion`
- `Outcome`

## Source Of Truth

Before promotion, the idea card owns the idea state. After promotion, the
markdown `kb-board` task owns execution state. The card stores only the pointer
and the terminal outcome mirror.

This prevents a split-brain state where one file says "in progress" and another
file says "done".

## Material Idea Path

Cheap or reversible ideas can still be triaged, killed, parked, or promoted as
small tasks. Material ideas — new methodology, public behavior, infrastructure,
security-sensitive work, scheduler/task-board logic, user-facing claims, or work
that needs more than a trivial fix — must pass through the owner-approved
specification gate before execution.

For those ideas the path is:

```text
capture -> triage -> research -> owner-approved specification
  -> knowledge/spec-approvals.md exact spec-contract hash
  -> post-approval build plan
  -> RED tests including E2E
  -> kb-board task owns execution state
  -> verification -> outcome
```

The card can point to the research, spec, approval hash, build plan, and
`plan_item_id`, but the kb-board task owns execution state once work starts.

## What This Is Not

- Not a generic note-taking inbox.
- Not a periodic `processes.yaml` job.
- Not a replacement for `kb-board`.
- Not a calendar bot that writes events without approval.
- Not a promise that every idea deserves work.

The first job is simple: when an idea arrives, Vepol does not lose it.
