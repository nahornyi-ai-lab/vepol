---
title: "Development Loop"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [new-development, features, non-trivial-changes, infrastructure-work]
---

# Development Loop

The single process **any** Vepol agent (Claude Code, Codex, Antigravity/`agy`,
or any future CLI agent) follows for new development. It is vendor-neutral: the
rules live here and in `AGENTS.md` so every agent obeys them natively; per-runtime
files (a Claude skill, etc.) are thin adapters that only point here.

It ties together the methodology Vepol already documents — it does **not** replace
those pages, it sequences them:

- [TRIZ for Design](triz-for-design.md) — the design discipline (Phase 2)
- [Spec-Driven Workflow](spec-driven-workflow.md) — spec → tests → code (Phases 3, 5)
- [Cross-Agent Review](cross-agent-review.md) — the review gate (Phase 4)
- [Orchestrated Knowledge Base](orchestrated-knowledge-base.md) — the substrate

## The loop

**0. Scope + Definition of Done.** First classify the work and write down what
"done" means (the acceptance criteria + how they'll be verified). This gates how
much of the loop applies.

- **Trivial** — typo/doc fix, dependency version bump with no code change, a
  single-file change with no new file, no public-interface change, blast radius
  zero. → Skip research and the review gate. Leave a one-line note in `log.md`:
  `research | skipped | trivial | <what>`. Still verify before claiming done.
- **Non-trivial** — anything > ~30 min, a new feature, a new dependency, new
  infra, a cross-subsystem change, a hard-to-undo change, or anything touching
  security / licensing / public artifacts. → Run the full loop.

**1. Research-first (reuse-or-build).** Before designing, find what already
exists that can be reused, copied, or adapted — in our KB, in other projects, in
the wild. Fan out to other agents **only for genuinely independent questions or
external uncertainty** (e.g. `grok` when current X/Reddit context matters); don't
require every agent for every feature. Produce a small **reuse-or-build record**:

```
candidates: <what was checked> (with KB paths / source links)
decision: reuse | adapt | build
why: <one line>
```

Do not build what already exists. No record (for non-trivial work) = research
not actually done.

**2. Design with TRIZ.** Formulate the contradiction → ideal final result →
resolve by separation, not compromise. See [triz-for-design.md](triz-for-design.md).

**3. Specification.** Write the spec before code, into `knowledge/decisions/`
(decision + spec live together). Include acceptance criteria and known failure
modes. See [spec-driven-workflow.md](spec-driven-workflow.md).

**4. Cross-agent review — ≥2 independent reviewers, before the human.** A
material decision's spec/plan is reviewed by **at least two independent agents,
excluding the author** (Claude authored → Codex + `agy`; Codex authored → Claude +
`agy`; self-review never counts). Keep the two layers from
[cross-agent-review.md](cross-agent-review.md): **Layer 1 — direction/need**
first, **Layer 2 — implementation details** second. Address each concern or
rebut it with a reason. Only escalate an open decision to the human **after** the
two-agent consultation.

- **Material decisions only** (architecture, new dependency, migration, security,
  public artifact, cross-project methodology, significant spec revision). Small
  tactical choices inside an already-approved spec do **not** re-trigger the gate.
- **Reviewer unavailable** (rate limit, no key, failure): try the configured
  reviewers, record each failed attempt in `log.md`, then escalate to the human
  with `[Single-Agent Fallback: <reason>]` for an explicit waiver — never silently
  proceed. A tool that can't spawn agents requests review by creating a `backlog.md`
  task that mentions the reviewer role and moving the task to `Review`.

**5. Tests → implementation.** Red tests first, implement to green, then
revisions. Small verifiable steps; empty/failed output is a real failure, not
"no result." See [spec-driven-workflow.md](spec-driven-workflow.md).

**6. KB write-back — to files, not memory.** The source of truth is files:
decision/spec → `knowledge/decisions/`; facts → `knowledge/sources/`, `concepts/`,
`solutions/`, `state.md`, or `strategies.md`; one-line trace → `log.md`. Runtime
memory may only mirror what was already written to a file.

**7. Verify + close.** Run the relevant tests / build / lint and `kb-doctor`
(no fresh P0/P1), confirm **every** acceptance criterion from Phase 0 with real
output, then close the task via `kb-board close ... --claim-id <id>`. Evidence
before the success claim — always.

## Enforcement (so every agent actually follows it)

- `AGENTS.md` (hub + project) carries the compact loop, so Codex and `agy` — which
  have no skill system — obey it from the file they already read. `agy` must be
  launched with `agy --add-dir "$PWD"` so it loads project `AGENTS.md`.
- **Task-board trigger:** before moving a task to `In Progress`, an agent must
  confirm a spec exists in `knowledge/decisions/` and (for material work) passed
  ≥2-agent review. If not, the first subtask is "write the spec."
- The clean-session probe and `kb-doctor agent-entrypoint` guard keep `AGENTS.md`
  actually loaded across runtimes.

## What we kept from generic dev skills (and what we dropped)

Kept (durable, vendor-neutral): evidence-before-completion, root-cause-before-fix,
red/green tests, no placeholders in plans, skeptical handling of review feedback
(verify, don't perform agreement), parallel agents only for independent work.

Dropped: "invoke a skill on a 1% chance" and hard universal gates that block
trivial work. Runtime-specific heuristics live in `solutions/` or a project
`agent-card.md` `## Operating notes`, not in this canonical loop.
