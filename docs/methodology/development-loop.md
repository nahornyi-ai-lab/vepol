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
- [Cross-Agent Review](cross-agent-review.md) — the review gates (Phases 4, 5.5)
- [Orchestrated Knowledge Base](orchestrated-knowledge-base.md) — the substrate

## The loop

**0. Scope + Definition of Done.** First classify the work and write down what
"done" means (the acceptance criteria + how they'll be verified). This gates how
much of the loop applies.

- **Trivial** — typo/doc fix, dependency version bump with no code change, a
  single-file change with no new file, no public-interface change, blast radius
  zero. → Skip research and the review gates. Leave a one-line note in `log.md`:
  `research | skipped | trivial | <what>`. Still verify before claiming done.
- **Never trivial, regardless of diff size:** security/auth, licensing,
  migrations and data deletion, install scripts and hooks, task-board/scheduler
  logic, user-facing behavior, and public docs/artifacts that affect install,
  usage, the public contract, claims, security/compliance, or methodology.
  Pure typo/formatting fixes in docs stay trivial-eligible.
- **Non-trivial** — anything > ~30 min, a new feature, a new dependency, new
  infra, a cross-subsystem change, a hard-to-undo change, or anything on the
  never-trivial list. → Run the full loop.

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

**2. Design.** For material decisions — or when research surfaced a real
trade-off conflict — run the full TRIZ pass: contradiction → ideal final result →
resolve by separation, not compromise ([triz-for-design.md](triz-for-design.md)).
For other non-trivial work a lightweight block is enough: 2–3 alternatives
considered + why this one won. Manufacturing a "contradiction" to tick the box
is an anti-pattern.

**3. Specification.** Write the spec before code, into `knowledge/decisions/`
(decision + spec live together). Include acceptance criteria and known failure
modes. The spec is versioned: reviews bind to its content hash (Phase 4), so a
material edit after approval is detectable. See
[spec-driven-workflow.md](spec-driven-workflow.md).

**4. Cross-agent review of the spec — ≥2 independent reviewers, before the
human.** A material decision's spec/plan is reviewed by **at least two
independent agents, excluding the author** (self-review never counts). Keep the
two layers from [cross-agent-review.md](cross-agent-review.md): **Layer 1 —
direction/need** first, **Layer 2 — implementation details** second. Verdicts
use the structured format defined there (`approve | approve-with-nits | block`,
bound to `spec:<algo>:<hash>`); a review missing the mandatory fields does not
count toward the gate.

- **Material decisions only** (architecture, new dependency, migration, security,
  public artifact, cross-project methodology, significant spec revision). Small
  tactical choices inside an already-approved spec do **not** re-trigger the gate.
- **Blocks freeze.** Any `block` freezes the task until the author revises and
  the gate is re-satisfied. Non-blocking remarks may be rebutted with a reason;
  blockers may not. A security/data-loss block is a veto only the human lifts.
- **Final-version rule.** The gate is satisfied only by the required number of
  approve/approve-with-nits verdicts bound to the **exact final version** (spec
  hash / diff ref) at close time. A material edit during the cycle invalidates
  all prior verdicts — get refreshed verdicts on the final version.
- **Disagreement.** Reviewers split approach-X-vs-Y → third-agent tie-break or
  human; record the conflict and resolution in the decision file.
- **Reviewer unavailable** (first review): try the configured reviewers, record
  each failed attempt in `log.md`, then escalate to the human with
  `[Single-Agent Fallback: <who failed + evidence, risk class, scope, expiry>]`
  for an explicit waiver — never silently proceed. For security / public-install
  work the waiver cannot skip Phase 5.5. A blocking reviewer unavailable for
  **re-review** is a different path: after ≥2 logged attempts escalate with
  `[Blocker-Re-Review-Unavailable: <who, original verdict, what was fixed,
  risk>]` — the human lifts the block, appoints a third agent, or waits.

**5. Tests → implementation.** Red tests first, implement to green, then
revisions. Small verifiable steps; empty/failed output is a real failure, not
"no result." See [spec-driven-workflow.md](spec-driven-workflow.md).

**5.5. Implementation review.** Specs don't ship — diffs do. For non-trivial
work whose Phase 5 produced code/tests/configs: after green and before
verify+close, the diff goes to **≥1 independent reviewer (≥2 for material work),
never the author**. The author hands over the approved spec + its hash, the diff
ref, the tests, the acceptance criteria, and "what I'm unsure about"; the
reviewer works through the implementation-review checklist in
[cross-agent-review.md](cross-agent-review.md) and returns a structured verdict
bound to `spec:<algo>:<hash> diff:<ref>`. This gate deliberately covers more
than the material-only spec gate: implementation defects are the dominant class
of escaped defects, and the trivial threshold (Phase 0) keeps the cost where it
pays.

**6. KB write-back — to files, not memory.** The source of truth is files:
decision/spec → `knowledge/decisions/`; facts → `knowledge/sources/`, `concepts/`,
`solutions/`, `state.md`, or `strategies.md`; one-line trace → `log.md`. Runtime
memory may only mirror what was already written to a file. **Draft until
verified:** durable pages (long-lived claims or decisions — `decisions/`,
`sources/`, `concepts/`, `solutions/`, `strategies.md`, `state.md`, methodology
docs; *not* append-only traces like `log.md`, `backlog.md`, incident entries)
created or materially updated before Phase 7 passes carry `status: draft` in
frontmatter and flip to `stable` at close. Failed work must not canonize
unverified claims.

**7. Verify + close.** Build the **acceptance matrix**: every Phase-0 criterion →
evidence (real output) → verifier → verdict. For material work the verifier is
one of the Phase 5.5 reviewers (never the author), re-running the key checks
after the 5.5 verdict and before close — the 5.5 verdict and the matrix are two
distinct traces. For other non-trivial work the author may self-verify, but the
evidence must be re-runnable by any agent (commands + output attached). If the
work touches runtime behavior (installer, hook, scheduler, CLI integration, UX),
run a real-runtime smoke — a clean install pass, a fired hook, a dry-run
migration — not just unit/lint. Then `kb-doctor` (no fresh P0/P1) and
`kb-board close ... --claim-id <id>`. Evidence before the success claim — always.

**8. Showcase.** Shipped material work with user-visible value gets a NotebookLM
**video recap** after close ("what we built / why / how to apply it") as raw
material for social channels — TikTok, YouTube. The deliverable is the
notebook/artifact ID — no local downloads; the human reviews and posts. Internal
plumbing (refactors, guards, infra) skips with a one-line
`showcase | skipped | internal` note in `log.md`. Known limit: NotebookLM video
is landscape — ready for YouTube; vertical re-cuts for TikTok happen human-side.

## When something shipped breaks anyway

The loop learns from its escapes. The incident entry in `incidents.md` must
include `loop-phase-failed: <0 | 1 | 2 | 3 | 4 | 5 | 5.5 | 6 | 7 | 8>`, why the
review/tests/verification missed it, and the prevention rule added. The same
phase failing twice means the loop itself gets revised, not just the incident
closed.

## Enforcement (so every agent actually follows it)

- `AGENTS.md` (hub + project) carries the compact loop, so Codex and `agy` — which
  have no skill system — obey it from the file they already read. `agy` must be
  launched with `agy --add-dir "$PWD"` so it loads project `AGENTS.md`.
- **Task-board trigger:** before moving a task to `In Progress`, an agent must
  confirm a spec exists in `knowledge/decisions/` and (for material work) passed
  ≥2-agent review. If not, the first subtask is "write the spec."
- Verdicts bind to content hashes (`git hash-object <file>` or `shasum -a 256`,
  recorded as `spec:<algo>:<hash>`), so stale approvals are detectable by audit.
- Deterministic guards (`kb-board` claim/close checks, `kb-doctor dev-loop-audit`)
  are tracked as a separate task; until they land, the rules above are enforced
  by instruction and by the owner.
- The clean-session probe and `kb-doctor agent-entrypoint` guard keep `AGENTS.md`
  actually loaded across runtimes.

## What we kept from generic dev skills (and what we dropped)

Kept (durable, vendor-neutral): evidence-before-completion, root-cause-before-fix,
red/green tests, no placeholders in plans, skeptical handling of review feedback
(verify, don't perform agreement), parallel agents only for independent work.

Dropped: "invoke a skill on a 1% chance" and hard universal gates that block
trivial work. Runtime-specific heuristics live in `solutions/` or a project
`agent-card.md` `## Operating notes`, not in this canonical loop.
