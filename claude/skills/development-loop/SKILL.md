---
name: development-loop
description: Use when starting any new development — a feature, a non-trivial or hard-to-undo change, infrastructure, or anything touching security/licensing/public artifacts. Runs Vepol's development loop. Skip only for trivial single-file/doc fixes (leave a one-line `research | skipped | trivial` note and still verify).
---

# Vepol Development Loop

Thin adapter. The canonical, vendor-neutral process lives in
`docs/methodology/development-loop.md` (in the Vepol repo / `~/vepol/`) and is
mirrored in `AGENTS.md`. Read the canonical doc for the full rationale; this
skill is the actionable trigger for Claude Code. Codex and Antigravity (`agy`)
follow the same loop from `AGENTS.md` natively.

## Do this, in order

0. **Scope + Definition of Done.** Classify the work and write what "done" means
   (acceptance criteria + how you'll verify). Trivial (typo/doc, dep bump, one
   file, zero blast radius) → skip phases 1 & 4, note `research | skipped | trivial`
   in `log.md`, still verify. Non-trivial (>~30 min, new feature/dependency/infra,
   cross-subsystem, hard-to-undo, security/licensing/public) → full loop.

1. **Research-first (reuse-or-build).** Find what already exists to reuse/copy/adapt
   (KB, other projects, the wild). Fan out to other agents only for genuinely
   independent questions. Record: `candidates / decision: reuse|adapt|build / why`.
   Don't build what exists.

2. **Design with TRIZ.** Contradiction → ideal final result → resolve by
   separation, not compromise. (`docs/methodology/triz-for-design.md`)

3. **Spec.** Write the spec before code into `knowledge/decisions/`, with
   acceptance criteria and failure modes. (`docs/methodology/spec-driven-workflow.md`)

4. **Cross-agent review — ≥2 independent reviewers, before the human.** Material
   decisions only (architecture, dependency, migration, security, public artifact,
   methodology, big spec revision). Reviewers exclude the author (you authored →
   Codex + agy). Layer 1 direction first, Layer 2 details second. Address or rebut
   each concern. Only escalate an open decision to the human after the 2-agent pass.
   Reviewer unavailable → log the failed attempt, escalate with
   `[Single-Agent Fallback: <reason>]`; never silently proceed.

5. **Tests → implementation.** Red tests, implement to green, revisions. Small
   verifiable steps. Empty/failed output = real failure, not "no result."

6. **KB write-back to files, not memory.** decision/spec → `knowledge/decisions/`;
   facts → `sources/`/`concepts/`/`solutions/`/`state.md`/`strategies.md`; trace →
   `log.md`. Memory only mirrors what's already in a file.

7. **Verify + close.** Run tests/build/lint + `kb-doctor` (no fresh P0/P1), confirm
   EVERY acceptance criterion with real output, then `kb-board close ... --claim-id`.
   Evidence before the success claim — always.

## Don't
- Don't move a task to `In Progress` without a spec (material work: a reviewed one).
- Don't treat the 2-agent gate as ceremony for tiny tactical choices inside an
  approved spec.
- Don't put runtime-specific tricks here — they belong in `solutions/` or an
  `agent-card.md` `## Operating notes`.
