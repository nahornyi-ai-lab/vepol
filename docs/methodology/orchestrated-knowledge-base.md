---
title: "Orchestrated Knowledge Base"
status: stable
type: root-concept
parent: vepol
extends: karpathy-llm-wiki-pattern
---

# Orchestrated Knowledge Base

The root concept Vepol is built on: **a Karpathy-style personal LLM
wiki as the substrate, with an active orchestrator on top**. This page
explains why both layers are needed, and which guardrails the
combination has to respect.

## The thesis

Vepol is not a memory tool or document librarian — a passive
accumulator that waits for you to ask questions. It is **an
autonomous AI partner that can plan, execute, review, and
escalate**. But a partner without reliable shared context is just
empty talk. So:

- **Knowledge (the LLM-wiki pattern) is the foundation.** What you
  know, where you're going, what you've decided.
- **Orchestration is the layer above.** What you're doing today,
  who delegates to whom, what the calendar checked, what went
  wrong.

Both layers live in the same file structure, under one protocol
(markdown + append-only log + wiki-links), distributed across
projects, with no central registry-god.

## Four invariants from Karpathy (guardrails)

These are non-negotiable. Violating any of them is a smell that
demands a rethink.

1. **Markdown-first.** The wiki is markdown + wiki-links + `index.md`
   (catalog) + `log.md` (chronology). Nothing more exotic without a
   strong reason.
2. **Metadata next to content.** A fact about project X lives in
   project X's pages, not in a central registry. A single central
   registry that overrides project-local truth is the biggest no.
3. **The LLM does the bookkeeping; the human curates raw material
   and strategy.** The agent keeps alive what the human would let
   slip. The human decides direction and supplies the source
   material.
4. **Lint as a ritual.** Health-check is not an optional luxury
   but a recurring obligation (see [`kb-freshness-loop.md`](kb-freshness-loop.md)).

## Seven extensions (where Vepol goes beyond Karpathy)

Karpathy's pattern is single-user, single-LLM, passive, offline. Vepol
extends it on seven axes:

1. **Active scheduling.** Background services (LaunchAgent + tick)
   wake the system in the morning and evening, on its own — no
   human prompt required.
2. **Task delegation.** A multi-level project tree where each node
   can spawn children with assignments and propagate results
   upward.
3. **External inputs as first-class.** Calendar, email, Telegram —
   not raw material to ingest later but live signals that adjust
   the day's plan in real time.
4. **Feedback loops.** Not lint as a one-off health check, but a
   daily `retro → plan → execute → retro` cycle that catches drift
   inside 24 hours.
5. **Plan as artifact.** `roadmap.md`, `daily-plan/<date>.md`, sprint
   cadence — the plan and its lifecycle are materialized as files,
   not held in memory.
6. **Multi-orchestrator symmetry.** Multiple AI agents (Claude,
   Codex, future ones) work against the same knowledge base; no
   single point of failure; significant plans get cross-reviewed by
   another agent (see [`cross-agent-review.md`](cross-agent-review.md)).
7. **Reproducibility as product.** The setup is not a one-off
   personal hack — it's a turnkey kit anyone can clone and run
   themselves with their own knowledge base.

## The four layers

```
  ┌──────────────────────────────────────────────────────┐
  │  External signals                                    │
  │  Calendar · Email · Telegram · Web                   │
  └─────────────────────────┬────────────────────────────┘
                            ▼ (inputs)
  ┌──────────────────────────────────────────────────────┐
  │  Orchestration                                       │
  │  Daily brief · evening retro · tick · cycle          │
  │  Background services · Multi-agent broker            │
  │  Project spawn · auto-execute                        │
  └─────────────────────────┬────────────────────────────┘
                            ▼ (reads/writes)
  ┌──────────────────────────────────────────────────────┐
  │  Knowledge (Karpathy)                                │
  │  index.md · log.md · concepts/ · solutions/          │
  │  per-project knowledge/ folders                      │
  │  markdown + wiki-links + decentralized metadata      │
  └─────────────────────────┬────────────────────────────┘
                            ▼ (read-only)
  ┌──────────────────────────────────────────────────────┐
  │  Raw                                                 │
  │  raw/ · sources · transcripts · attachments          │
  └──────────────────────────────────────────────────────┘
```

Access rule: each layer reads/writes the layer immediately below
it. Raw is read-only — never modified once captured. Orchestration
never writes to raw directly; knowledge never spawns processes.

## Authoritative artifacts (one writer per fact)

Each kind of information has exactly one writable home. Everything
else is either derived from it or a read-only mirror.

| Information | Lives in | Who writes |
|---|---|---|
| Long-term goals | `personal/goals.md` | human |
| Roadmap | `personal/roadmap.md` | human + agent suggestions |
| Daily plan | `daily-plan/<date>.md` | orchestrator (approved by human) |
| Daily retro | `daily/<date>.md` | orchestrator (aggregated from per-project reports) |
| Per-project state | `<project>/knowledge/state.md` | self |
| Per-project tasks | `<project>/knowledge/backlog.md` | hub (dispatch) + self (planning) + human (ad-hoc) |
| Asks upward | `<project>/knowledge/escalations.md` | self |
| Incidents | `<project>/knowledge/incidents.md` | self after errors |
| Per-project strategy + hypotheses | `<project>/knowledge/strategies.md` | self |
| Per-project reports | `<project>/knowledge/reports/<date>.md` | cycle (evening) |
| Hub registry | `registry.md` (derived block + hub-managed block) | derived from per-project frontmatter; manual entries for archived/no-wiki |
| Chronology | `log.md` (hub + per-project) | append by all |

Conflicts where two writers touch the same file are implementation
bugs and get caught by the lint cycle.

## The coordination triad

Every project gets three coordination files, each with one job:

- **`backlog.md`** — what needs doing
- **`escalations.md`** — items the project can't proceed without
  a human or upstream decision
- **`incidents.md`** — what broke, root cause, fix, prevention rule

This is not a task tracker. It's a **protocol for communication**
between you, your AI partner, and the upstream coordinator (the
hub). One file per kind of message. The hub reads escalations to
know what's blocked; projects read backlog to know what's been
delegated; everyone reads incidents to avoid repeating mistakes.

## Cross-orchestrator symmetry

Vepol can host more than one AI agent (Claude, Codex, and future
ones). The discipline keeping them coherent:

- **One substrate.** `~/knowledge/` plus per-project `knowledge/`.
  No agent has private memory.
- **One broker.** A scheduler routes new work to whichever agent
  is healthy. If one is rate-limited or crashed, the other picks
  up.
- **One discipline.** Any plan above a trivial threshold goes
  through cross-review by a second agent (see
  [`cross-agent-review.md`](cross-agent-review.md)).
- **One spec.** This page. Both agents read it as a guardrail, both
  see it in the same knowledge base.

## Anti-patterns to avoid

- **Over-centralization.** Tempted to add another authoritative
  file? First check: can it live next to the content instead?
  (Invariant 2.)
- **Double-booking.** A single fact in two writable places. Pick
  one writable; the rest must be derivable or read-only mirrors.
- **Silent session memory.** After every significant piece of work,
  a file. Otherwise the agents fork — what one knows, the other
  doesn't.
- **Over-automation without a kill switch.** Every automated thing
  has a per-project disable flag and a hub-level "stop everything"
  command.
- **A central registry that overrides project-local truth.** The
  biggest no. Project metadata lives in projects.
- **A spec without tests.** Any non-trivial spec requires
  acceptance tests written before the code (see
  [`spec-driven-workflow.md`](spec-driven-workflow.md)).
- **A plan without cross-review.** See cross-orchestrator symmetry
  above.
- **Stubs, MVP-with-promised-v2, draft milestones.** If a feature
  is on the roadmap, it ships fully or not at all. Phased "MVP
  now, real version later" accumulates tech debt that one-person
  operations don't have the slack to retire. Allowed exceptions:
  safety toggles during rollout (per-project disable, dry-run
  modes), and explicit deferred questions in an "Open questions"
  spec section.

## How this concept relates to the others

- [`kb-authoring-discipline.md`](kb-authoring-discipline.md) — eight
  rules for the **ingest** operation (avoiding false-canonical
  content during initial knowledge-base population)
- [`kb-freshness-loop.md`](kb-freshness-loop.md) — instrumentation
  for the **lint** operation (keeping pages from going stale
  silently)
- [`triz-for-design.md`](triz-for-design.md) — the design discipline
  applied at the spec phase (formulate the contradiction first)
- [`spec-driven-workflow.md`](spec-driven-workflow.md) — the build
  discipline (spec → tests → code → tests → revisions)
- [`cross-agent-review.md`](cross-agent-review.md) — the quality
  gate before any non-trivial change goes live
- [`parallel-orchestrators.md`](parallel-orchestrators.md) — the
  rules for keeping multiple AI agents working from the same
  source of truth without forking

## Acknowledgments

Vepol's knowledge layer is a direct extension of Andrej Karpathy's
[LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
The orchestration layer above it (active scheduling, multi-agent
brokering, cross-review, automated retrospectives) is original to
Vepol; the four guardrails are Vepol's adaptation of the LLM Wiki
pattern.
