---
title: "Development Loop"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [new-development, features, non-trivial-changes, infrastructure-work]
---

# Development Loop

The single process every Vepol agent follows for new development. It is
vendor-neutral: the rules live here and in `AGENTS.md`; runtime skills are thin
adapters.

Related pages:

- [TRIZ for Design](triz-for-design.md) — design discipline (Phase 2)
- [Spec-Driven Workflow](spec-driven-workflow.md) — spec → tests → code
- [Lightweight Spec Review](cross-agent-review.md) — the single review pass
- [Orchestrated Knowledge Base](orchestrated-knowledge-base.md) — the substrate

## The loop

**0. Scope + Definition of Done.** Classify the work and write acceptance
criteria plus verification evidence.

- **Trivial:** typo/doc fix, dependency bump with no behavior change, or another
  single small change with zero blast radius. Skip research and the lightweight
  review; log `research | skipped | trivial | <what>` and still verify.
- **Never trivial:** security/auth, licensing, migrations/data deletion,
  installers/hooks, task-board/scheduler logic, user-facing behavior, or public
  docs that affect install, usage, claims, methodology, or contracts.
- **Non-trivial:** anything over roughly 30 minutes, a new feature/dependency,
  infrastructure, cross-subsystem work, hard-to-undo work, or a never-trivial
  category. Run the full loop.

**1. Research-first (reuse-or-build).** Find reusable work in the KB, other
projects, and external primary sources. Fan out only genuinely independent
questions. Record:

```
candidates: <what was checked>
decision: reuse | adapt | build
why: <one line>
```

**2. Design.** Use full TRIZ only for a material trade-off: contradiction →
ideal final result → resolution by separation. Otherwise record two or three
alternatives and why the smallest suitable one won.

**3. Specification.** Before code, write `knowledge/decisions/<spec>.md` with
product context, Place in Vepol, Software 3.0 fit, scope, acceptance criteria,
failure modes, mandatory E2E, and the concrete code/API/schema files the design
relies on. The `spec-contract` hash binds owner approval and makes later drift
detectable. The lightweight review is bound to the stated scenario, not to
byte-identical prose.

**4. Lightweight spec review — exactly one independent reviewer, exactly one
pass, before the human.** The reviewer excludes the author and reads both the
spec and the relevant code, API contract, schemas, migrations, and integration
points. The only output is `GO / QUESTIONS / BLOCK`:

- `GO`: the stated path is physically workable.
- `QUESTIONS`: at most three short questions about a gross logic gap, mismatched
  parameters, selection between existing paths/addresses, or an undefined
  branch inside the stated scenario.
- `BLOCK`: a concrete `file:line` or contract citation proves that the stated
  scenario cannot be implemented by the described path.

The reviewer asks how to make the path work as simply as possible; questions do
not create requirements. Do not expand scope through security hardening,
observability, scaling, rollback, future scenarios, style, documentation, or
extra tests unless the stated scenario explicitly includes them. If unsure
between `QUESTIONS` and `BLOCK`, choose `QUESTIONS`; if unsure between
`QUESTIONS` and `GO`, choose `GO`.

After `GO` or the author's answers to `QUESTIONS`, review is complete.
**A changed spec hash alone never triggers another review.** A genuine `BLOCK`
permits one narrow delta check of that same blocker (`RESOLVED / STILL BLOCKED`);
new findings are not accepted during the delta check. If the reviewer is
unavailable, record the attempt and let the owner decide instead of starting a
replacement cascade. The canonical prompt is in
[cross-agent-review.md](cross-agent-review.md).

**4.5. Owner approval.** Put the reviewed spec in
`knowledge/spec-approvals.md`. The owner approves the exact `spec-contract` hash
in chat; the active agent records the decision as scribe. No RED tests or
implementation begin before approval.

**4.6. Build plan.** After approval, write ordered steps, the file/artifact
list, concrete RED tests, mandatory E2E, and verification commands. If planning
changes scope, acceptance, risk, public behavior, security/privacy, migration,
or the E2E path, return to one lightweight spec review and owner approval.

**5. Tests → implementation.** Write RED tests including E2E/process-smoke
coverage, run them and preserve the failure, then implement to green. Empty or
failed output is a real failure.

**6. KB write-back.** Durable truth goes to files: decisions, sources,
concepts, solutions, state, strategies, and `log.md`. Long-lived pages created
before Phase 7 stay `status: draft`; flip them to `stable` only after verified
close. Append-only logs/incidents are exempt.

**7. Verify + close.** The author builds the acceptance matrix: every Phase-0
criterion → reproducible evidence → verdict. Runtime behavior needs a real
smoke, not only unit/lint. Run `kb-doctor`, require no fresh P0/P1, then close
the board claim. Evidence comes before the success claim.

**8. Showcase.** Shipped material user-visible work gets a NotebookLM video
recap for later human publishing. Internal plumbing logs
`showcase | skipped | internal`.

## When shipped work breaks

The incident must include `loop-phase-failed: <0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8>`,
why the spec/lightweight review/tests/verification missed it, and the prevention
rule. Two escapes from the same phase require revising the loop.

## Enforcement

- Hub/project `AGENTS.md` carries the compact loop for every runtime.
- Before `In Progress`, require a spec, exactly one lightweight independent
  review, and owner approval. Otherwise the first task is writing the spec.
- Owner approval binds to the exact content hash. The lightweight review does
  not restart for wording or hash churn.
- RED/E2E tests, live smoke, `kb-doctor`, and board close remain mandatory.
- Empty output from a reviewer/tool is a tool failure, never `GO`.

## Kept and dropped

Kept: research-first, evidence-before-completion, root-cause-before-fix,
RED/green tests, mandatory E2E, owner approval, and durable KB write-back.

Dropped: multiple review agents, Layer 1/Layer 2 passes, exact-hash re-review,
implementation/diff review, reviewer-owned final verification, and automatic
stop-time review. Those mechanisms produced delay and scope expansion without
being required to catch gross logical errors before code.
