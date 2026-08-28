---
name: development-loop
description: Use when starting any new development — a feature, non-trivial or hard-to-undo change, infrastructure, security/licensing work, installers/hooks, migrations, or public-contract docs. Runs Vepol's research -> spec -> one lightweight review -> owner approval -> RED/E2E -> implementation -> verification loop. Skip only truly trivial work.
---

# Vepol Development Loop

Thin Claude Code adapter. The vendor-neutral canon lives in
`docs/methodology/development-loop.md`, with the exact reviewer prompt in
`docs/methodology/cross-agent-review.md`, and a compact copy in `AGENTS.md`.

## Run in this order

0. **Scope + Definition of Done.** Record acceptance criteria and verification.
   Trivial work skips research/review but still logs and verifies. Never trivial:
   security/auth, licensing, migrations/data deletion, installers/hooks,
   task-board/scheduler logic, user-facing behavior, and public docs affecting
   install/usage/contracts/claims/methodology.

1. **Research-first.** Find what can be reused or adapted. Record
   `candidates / decision: reuse|adapt|build / why`.

2. **Design.** Use TRIZ only for a real material trade-off; otherwise compare two
   or three alternatives and choose the smallest suitable one.

3. **Spec before code.** Write `knowledge/decisions/<spec>.md` with scope,
   acceptance, failure modes, mandatory E2E, and the concrete code/API/schema
   files the design relies on. Compute `spec-contract` for owner approval.

4. **One lightweight spec review.** Use exactly one independent reviewer,
   exactly one pass, before owner approval. The reviewer must read the spec and
   relevant real code/API. Output is `GO`, maximum three short questions, or
   `BLOCK` only when a concrete `file:line` or contract citation proves the
   stated path impossible. Pull toward the simplest working path. Do not expand
   security hardening, observability, scaling, rollback, future scenarios,
   style, docs, or tests unless explicitly in scope.

   After `GO` or author answers, review is complete.
   A changed hash alone never triggers another review. A genuine `BLOCK` permits one delta check of that
   same blocker (`RESOLVED / STILL BLOCKED`) with no new findings. Reviewer
   unavailable -> log it and let the owner decide; do not start a replacement
   cascade.

4.5. **Owner approval.** Record the exact approved hash in
   `knowledge/spec-approvals.md`. No RED tests or implementation before it.

4.6. **Build plan.** List ordered steps, files, concrete RED tests, mandatory
   E2E, and verification commands. Material scope drift returns to one
   lightweight review and owner approval.

5. **Tests -> implementation.** Preserve RED evidence, implement to green, and
   run the mandatory E2E/process smoke. Empty output is failure.

6. **KB write-back.** Store durable decisions and outcomes in files. Keep
   long-lived pages `status: draft` until verified close.

7. **Verify + close.** The author builds the acceptance matrix with reproducible
   evidence, runs a real smoke for runtime behavior, runs `kb-doctor`, and
   closes the board claim. There is no mandatory implementation/diff reviewer.

8. **Showcase.** User-visible material work gets the configured NotebookLM recap;
   internal plumbing logs `showcase | skipped | internal`.

## When shipped work breaks

Record `loop-phase-failed: <0…8>`, why the spec/lightweight
review/tests/verification missed it, and the new prevention rule.

## Do not

- Do not use multiple reviewers, Layer 1/Layer 2 passes, or repeated full review.
- Do not restart review for wording or hash churn.
- Do not turn reviewer questions into new requirements.
- Do not reintroduce an automatic stop-time review gate.
- Do not weaken owner approval, RED/E2E, live smoke, evidence, or KB write-back.
