---
title: "Spec-Driven Workflow"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [non-trivial-changes, design-decisions, infrastructure-work]
---

# Spec-Driven Workflow

Vepol's discipline for non-trivial work: **specification first, then
red tests, then code, then tests pass, then revisions when
needed**. This page explains the cycle and when it applies.

## When to use it

Apply the full cycle for:

- Any change requiring more than ~30 minutes of implementation
- Any design decision that crosses subsystems
- Any new infrastructure (a script, a service, a hook, a workflow)
- Any change that will be hard to undo

For trivial fixes (typos, single-line bug fixes, version bumps), skip
the cycle. But if you're uncertain whether a change is trivial,
write a two-line mini-spec — that's enough to expose whether the
change is actually trivial or you've underestimated it.

## The five phases

```
  1. Specification              ← what we're building, scope (in/out),
                                   acceptance criteria, failure modes
                                ▼
  2. Tests-before-code (RED)    ← write acceptance tests; they should
                                   all fail at this point
                                ▼
  3. Code                       ← written to make the tests pass,
                                   nothing wider
                                ▼
  4. Test run                   ← if green, done; if red, go to 5
                                ▼
  5. Revisions                  ← fix the code, OR realize the spec
                                   was wrong and revise both code AND
                                   spec; loop back to 4 until green
```

### 1. Specification

A spec lives in a markdown file (in your knowledge base for project-
specific specs, or in `concepts/` for cross-project concerns). It
must contain:

- **What we're building.** One paragraph in plain language.
- **Scope (in / out).** What's included, what's explicitly excluded.
  Out-of-scope is as important as in-scope — it constrains the
  surface area.
- **Acceptance criteria.** Specific, testable conditions for "done."
  Not "the system is fast" — "operations under 1KB return in <50ms
  at the p95."
- **Failure modes.** What could go wrong, and what the system does
  when it does. (This catches half the bugs before they're written.)
- **Open questions.** Things you didn't decide. Each gets a default
  position so the spec can move forward; the open question is
  marked for later resolution.

If you can't write the spec — if the acceptance criteria are vague
and the failure modes are "we'll see what happens" — you don't
understand the problem well enough to build it yet. Stop and learn
more.

### 2. Tests before code (RED)

For every acceptance criterion in the spec, write a test that
encodes it. Run the tests. They should all **fail** — RED — because
no implementation exists yet.

Why before code:

- Writing tests forces you to be specific about what "done" means.
  A vague spec produces vague tests, which exposes the vagueness
  in time to fix it.
- Tests written *after* code are biased toward what the code
  happens to do, not what the spec required. Pre-tests stay
  honest.
- The RED state is a checkpoint: if a test you expected to fail
  passes, the test is wrong (or trivial), not the code.

For non-code changes (a new workflow, a documentation overhaul,
a methodology page), the equivalent is: write the acceptance
checklist as a markdown checklist before doing the work.

### 3. Code

Write the code to make the tests pass. Resist the urge to expand
beyond what the tests require ("while I'm here, let me also fix
this other thing"). The discipline is: pass the tests *and only the
tests* in this pass.

If you find a real second issue, write a second spec and second
tests for it as a separate cycle. Two RED-cycles in flight at once
is fine; coupling them is not.

### 4. Test run

Run the full suite (not just the new tests — all of them). Outcomes:

- **All green.** Done with this cycle. Commit.
- **Red on the new tests.** The code doesn't yet match the spec.
  Continue refining the code.
- **Red on existing tests.** You broke something else. Either fix
  it or recognize that the new spec conflicts with an existing
  invariant — in which case, see phase 5.

### 5. Revisions

If tests are red because the spec was incomplete or wrong:

- Update the spec
- Update the tests to match
- Update the code

All three move together. You **never** quietly change the code to
pass tests it shouldn't pass under the original spec — that produces
silent specification drift. If the spec needs to change, change it
explicitly and re-run from phase 4.

Loop until green.

## Why each phase matters

| Phase | What it prevents |
|---|---|
| Spec | Vague problems building vague systems |
| RED tests | "It works on my machine" without knowing what "works" means |
| Code | Scope creep ("while I'm here…") |
| Test run | Silent regressions |
| Revisions | Specification drift (code passes tests for a different spec than was written) |

## How AI agents fit in

Vepol assumes you're working with one or more AI agents (Claude,
Codex, and future agents). The agents apply this workflow
automatically for any non-trivial work:

- They write the spec first when prompted to make a non-trivial
  change
- They write the tests before the implementation
- For changes that cross the [cross-agent review](cross-agent-review.md)
  threshold, the spec is also reviewed by an independent agent
  before any code is written
- The spec gets versioned in your knowledge base so the next
  session — yours or another agent's — picks up the same context

The discipline is not role-based ("the human writes specs, the
agent writes code"). Any human or agent producing significant work
follows the same cycle. Specs live in the knowledge base; tests
and code live in the repository; the spec links the chain so the
next actor can audit how the change came together.

## Common shortcuts and why they fail

- **"Skip the spec, the change is small."** If it really is small,
  skipping costs you nothing. If it isn't, you've just bypassed the
  one phase that catches mis-scoped work — when correction was
  cheap.
- **"Write tests after code, more efficient."** Tests after code
  encode what the code does, not what was required. Bugs that are
  in the spec stay in the tests. RED-first catches this.
- **"The spec evolved during implementation, no need to update it."**
  Yes there is. The next person reading the spec (you, six months
  from now; or another agent picking up the project) needs the
  spec that matches the code. Keeping them in sync is part of the
  cycle, not a cleanup task.
- **"Tests pass on my machine, ship it."** Run the full suite, not
  just the new tests. Existing tests are protective regression
  guards; ignoring them is exactly how regressions slip through.

## Connection to other Vepol disciplines

- **At the spec phase**, apply [TRIZ](triz-for-design.md):
  formulate the contradiction explicitly, sketch the IFR, look for
  resolution through separation
- **For non-trivial specs**, run [cross-agent
  review](cross-agent-review.md) at the spec stage and again at
  significant revision points
- **In the knowledge base**, store the spec as a markdown file so
  future agents and humans can audit the chain: spec → tests →
  code → revisions
