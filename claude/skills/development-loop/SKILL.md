---
name: development-loop
description: Use when starting any new development — a feature, a non-trivial or hard-to-undo change, infrastructure, or anything touching security/licensing/public artifacts. Runs Vepol's development loop (v2 quality gates). Skip only for trivial single-file/doc fixes (leave a one-line `research | skipped | trivial` note and still verify) — but security/auth, installers, hooks, board logic, migrations and public-contract docs are NEVER trivial.
---

# Vepol Development Loop

Thin adapter. The canonical, vendor-neutral process lives in
`docs/methodology/development-loop.md` (in the Vepol repo / `~/vepol/`) with
review mechanics in `docs/methodology/cross-agent-review.md`, mirrored compactly
in `AGENTS.md`. Read the canonical doc for full rationale; this skill is the
actionable trigger for Claude Code. Codex and Antigravity (`agy`) follow the
same loop from `AGENTS.md` natively.

## Do this, in order

0. **Scope + Definition of Done.** Classify and write what "done" means
   (acceptance criteria + how you'll verify). Trivial → skip phases 1 & 4, note
   `research | skipped | trivial` in `log.md`, still verify. **Never trivial:**
   security/auth, licensing, migrations/data deletion, install scripts, hooks,
   task-board/scheduler logic, user-facing behavior, public docs affecting
   install/usage/contract/claims/methodology.

1. **Research-first (reuse-or-build).** Find what exists to reuse/copy/adapt
   (KB, other projects, the wild). Record: `candidates / decision:
   reuse|adapt|build / why`. Don't build what exists.

2. **Design.** Full TRIZ (contradiction → IFR → separation) only for material
   decisions or a real trade-off conflict; otherwise "2–3 alternatives + why
   this one." Don't manufacture contradictions.

3. **Spec** before code into `knowledge/decisions/`, with acceptance criteria
   and failure modes. Reviews bind to the spec's content hash
   (`git hash-object` / `shasum -a 256`).

4. **Spec review — ≥2 independent reviewers (material decisions), before the
   human.** Reviewers exclude the author. Structured verdict required
   (`approve | approve-with-nits | block` + mandatory fields per
   `cross-agent-review.md`); incomplete reviews don't count. A `block` freezes
   until re-review — no text rebuttals of blockers; security blocks only the
   human lifts. **Final-version rule:** only verdicts on the exact final hash
   count; material edits invalidate prior approvals. Reviewer unavailable →
   `[Single-Agent Fallback]`; blocker unreachable for re-review after ≥2 logged
   attempts → `[Blocker-Re-Review-Unavailable]`. Never silently proceed.

5. **Tests → implementation.** Red first, green, revisions. Empty/failed
   output = real failure.

5.5. **Implementation review — the diff, not just the spec.** Non-trivial work
   that produced code/tests/configs: send the diff to ≥1 independent reviewer
   (≥2 for material), never the author. Handoff: approved spec + hash, diff
   ref, tests, acceptance criteria, "what I'm unsure about". Checklist lives in
   `cross-agent-review.md`; verdict binds to `spec:<algo>:<hash> diff:<ref>`.

6. **KB write-back to files, not memory.** Durable pages created before
   phase 7 carry `status: draft`, flipped to `stable` at close (append-only
   traces like `log.md` are exempt).

7. **Verify + close.** Acceptance matrix: criterion → evidence → verifier →
   verdict. Material work: verifier = one of the 5.5 reviewers (not the
   author), re-running key checks. Runtime-touching work needs a real-runtime
   smoke (clean install, fired hook, dry-run migration). Then `kb-doctor`
   (no fresh P0/P1) and `kb-board close ... --claim-id`. Evidence before the
   success claim — always.

8. **Showcase.** Shipped material user-visible work → NotebookLM video recap
   ("what/why/how to apply") for socials (TikTok, YouTube). Deliverable =
   notebook/artifact ID, no local downloads, the human posts. Internal
   plumbing → `showcase | skipped | internal` in `log.md`.

## When something shipped breaks

Incident entry must include `loop-phase-failed: <0…8|5.5>`, why the gates
missed it, and a prevention rule. Same phase fails twice → revise the loop.

## Don't
- Don't move a task to `In Progress` without a spec (material work: a reviewed one).
- Don't count a review without the mandatory verdict fields, and don't ship on
  verdicts from a stale spec/diff version.
- Don't treat gates as ceremony for tiny tactical choices inside an approved
  spec — and don't label never-trivial work as trivial.
- Don't put runtime-specific tricks here — they belong in `solutions/` or an
  `agent-card.md` `## Operating notes`.
