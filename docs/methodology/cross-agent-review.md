---
title: "Cross-Agent Review"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [non-trivial-plans, design-decisions, refactors]
---

# Cross-Agent Review

The quality gates Vepol applies around implementation: **a material
plan is reviewed by independent agents before code is written** (the
spec gate), and for non-trivial work **the resulting diff is reviewed
again before it ships** (the implementation-review gate below).
Concerns get addressed at the spec stage and again at the diff stage.
This is not optional ceremony — it's the mechanism that catches bias
and tunnel vision that single-agent flows produce.

## When it applies

Any of the following triggers a cross-review:

- An architectural decision document
- A specification for a new feature
- A migration proposal (data, schema, infrastructure)
- A significant refactor across multiple files
- Adding a new dependency
- A change to security-sensitive code
- A licensing decision
- A new public-facing artefact (README, docs, marketing copy)

For trivial fixes that don't have a design document, cross-review is
not required. Trivial means: a single small change with a clear
right answer, low blast radius if wrong.

## Two-layer review

The review happens in two distinct passes, and they should not be
combined:

### Layer 1 — concept

The first pass asks: **is this needed at all? Is the path optimal?**

Concerns:
- Does the proposed work solve the right problem?
- Is there a simpler alternative we're missing?
- What's the cost of *not* doing it?
- Are there assumptions baked in that should be questioned?

The output is a verdict on the *direction*, not on implementation
details. If Layer 1 returns "blocker — the direction is wrong," no
amount of implementation polish in Layer 2 fixes it.

### Layer 2 — implementation

After Layer 1 approves the direction, the second pass asks: **given
we're doing this, are the implementation details correct?**

Concerns:
- Schema design (data shapes, error cases, edge cases)
- Algorithm correctness
- Failure modes and rollback
- Testing coverage
- Specific phrasing in user-facing copy

The output is concrete redlines: "replace section X with Y because
Z." The verdict uses the structured format below.

## Structured verdict — what counts toward the gate

A review only counts toward a review gate (the ≥2 spec gate, or the
implementation-review gate below) if it contains **all** mandatory
fields:

- `verdict: approve | approve-with-nits | block`
- `reviewed: spec:<algo>:<hash>` — always; for implementation review
  additionally `diff:<git ref | patch ref>`. Hash portably:
  `git hash-object <file>` or `shasum -a 256 <file>`; the reviewer
  hashes the bytes they actually read.
- What was concretely checked
- Top risks (≥2)
- At least one failure mode or negative test case
- Whether the mandatory E2E path is present, proportionate, and strong
  enough to prove the user/process outcome
- What was NOT checked
- Findings, each tagged `[blocker]` or `[nit]`

The full field set applies to **every** counting review — including a
single-reviewer implementation review of non-material work. There is
no lighter form. A review missing mandatory fields does not count.
Empty output is a tool failure, not a review.

**Legacy vocabulary mapping** (older review records are not
rewritten): `blocker` / `request-changes` → `block`;
`concern` / minor remarks → `approve-with-nits`.

## Disagreement and the final-version rule

- Any `block` freezes the task: the author revises and requests
  re-review. Blockers cannot be argued away in text; only
  non-blocking remarks can be rebutted with a reason.
- **Final-version rule:** a gate is satisfied only by the required
  number of approve/approve-with-nits verdicts bound to the **exact
  final version** (spec hash / diff ref) at close time. A material
  edit during the cycle (scope, acceptance criteria, failure modes,
  dependencies, security posture, public behavior) invalidates all
  prior verdicts — the author must obtain refreshed verdicts on the
  final version, at minimum re-engaging the reviewers whose areas the
  edit touched. Cosmetic edits (typos, formatting) don't invalidate;
  when in doubt, treat the edit as material.
- A security/data-loss `block` is a veto only the human lifts.
- Reviewers split approach-X-vs-Y → third-agent tie-break or human;
  the conflict and resolution are recorded in the decision file.
- **Re-review deadlock:** if the blocking reviewer is unavailable for
  re-review after ≥2 attempts logged in `log.md`, escalate to the
  human with `[Blocker-Re-Review-Unavailable: <who, original verdict,
  what was fixed, risk>]`. The human lifts the block, appoints a
  third agent for the tie-break, or waits. A non-security lift is
  recorded in the decision file; if a defect ships later, the
  incident RCA must reference it.

## Implementation review (Phase 5.5)

The spec gate is *before* code; this gate is *after* — specs don't
ship, diffs do. For non-trivial work that produced code/tests/configs,
the diff is reviewed by ≥1 independent reviewer (≥2 for material
work), never the author, after tests are green and before
verify+close.

**Handoff package from the author:** the approved spec + its hash,
the diff ref, the tests, the acceptance criteria, and "what I'm
unsure about."

**Reviewer checklist (mandatory concerns):**

1. The diff matches the approved spec — nothing beyond scope
2. Side effects: durable KB pages, hooks/installers/scheduler,
   the public contract, other agents/rollouts
3. Tests: every acceptance criterion is covered by a test or an
   explicit manual check; negative cases exist
4. Regressions in adjacent behavior

The verdict's "what was checked" field must enumerate which checklist
items were actually exercised against this diff. The verdict binds to
`spec:<algo>:<hash> diff:<ref>`.

## Owner approval handoff

After the spec review gate is non-blocking, the author hands the owner the
reviewed spec path, exact contract hash, and approval queue row in
`knowledge/spec-approvals.md`. The queue status moves to owner approval only for
the reviewed contract hash. The owner may approve, reject, or request `Changes requested`
in chat; the active agent records the owner decision as scribe in the
queue and spec. A build plan and RED tests are not started until the owner
approval is recorded for the same contract hash.

## Why two layers, not one

Combining concept and implementation review in one pass produces
*worse* outcomes than running them separately:

- The reviewer's attention gets pulled to specific implementation
  details, missing structural concerns about the direction itself
- The author defends specific phrasing instead of reconsidering
  the approach
- "It looks technically correct" passes when the right verdict is
  "this is the wrong thing to build"

By running concept review first, with the explicit instruction "do
not give implementation feedback," the reviewer is forced to take
a position on the direction. Implementation review then happens with
the direction settled.

## How an AI-to-AI review works in practice

The author agent writes the spec or plan. The reviewer agent reads
the spec and is given clear evaluation criteria.

For Layer 1, the prompt asks:

- Is the work needed at all?
- Is the chosen path optimal compared to two or three obvious
  alternatives?
- What's missing that should have been considered?
- Per item: verdict (`approve` / `concern` / `blocker`) with brief
  reasoning

For Layer 2, the prompt asks:

- Per implementation detail: verdict + concrete redline if needed
- Top-3 must-fix issues before publishing
- Top-3 nice-to-fix issues
- Specific phrasing suggestions for any user-visible copy

The reviewer agent's output gets pasted back into the spec
document as a `## Cross-review <date>` section, so the spec
preserves the audit trail.

## Knowledge-gap delegation as the review's twin

If during a review the reviewer hits a fact it doesn't know (an
external API, library behavior, market data, a project convention)
— it is required to **delegate the missing knowledge into the
shared knowledge base**, not just answer in chat.

The pattern: "I don't know X. Look it up and write a summary in
`sources/` or `concepts/` that any future agent can read." The
result is a markdown file with the resolved fact, plus a one-line
summary back to the original conversation.

This prevents the same knowledge gap from being looked up twice. It
also means the *next* review of *another* spec can rely on the
same documented fact without re-discovering it.

## What the reviewer cannot do

The reviewer cannot:

- Approve its own changes (no self-review)
- Ratify a plan that was already half-implemented before review
  (the *spec* gate is before code; the only legitimate post-code
  gate is the explicit implementation review of the diff above)
- Skip Layer 1 and go straight to Layer 2 — even when the author
  insists "the direction is obviously right"
- Decline to review without a recorded reason

If the second agent is unavailable (rate-limited, broken, in
maintenance), the author can either wait or proceed with a recorded
"review attempted, blocked, escalated to human" note. Silently
skipping the review is the only forbidden path.

## Why both directions

Vepol can host multiple AI orchestrators: Claude Code, Codex,
Antigravity CLI, and future agents. Each can act as author or reviewer.
Cross-review goes both ways:

- Plans authored by Claude Code get reviewed by Codex, Antigravity CLI,
  or another configured agent
- Plans authored by Codex get reviewed by Claude Code, Antigravity CLI,
  or another configured agent
- Plans authored by Antigravity CLI or any additional agent get reviewed
  by one of the others

Symmetry matters because the bias profiles of different model
families are different — what one model glosses over, another
catches. A single-agent review of a single-agent plan inherits a
single bias profile.

## What a good review feels like

A good cross-review:

- Catches at least one structural issue the author hadn't seen
- Surfaces at least one assumption that should be questioned
- Suggests at least one specific alternative phrasing or approach
- Never devolves into nitpicking commas while ignoring direction
- Is short and concrete — the reviewer's job is to be useful, not
  exhaustive

A bad cross-review:

- Approves everything without engaging with the direction (the
  reviewer wasn't actually reading)
- Bikesheds phrasing while missing structural problems
- Returns "looks good to me" with no reasoning
- Disagrees with the author's choices without proposing
  alternatives

If you get a bad review, don't apply it — re-run with sharper
prompting (clearer evaluation criteria, explicit "what to focus
on" instructions).

## Documenting the review

Every cross-review leaves a trail in the spec document:

Current (structured) format:

```
## Cross-review 2026-06-09 (Layer 2)
Reviewer: Codex
verdict: approve-with-nits
reviewed: spec:git-blob:4b96bad1...
checked: A1-A11 consistency, gate operationality, deadlock paths
top_risks: (1) manual enforcement until guards land; (2) hash format drift
failure_mode: reviewer copies shorthand hash syntax, verdict fails audit
not_checked: seed copies, board/log evidence
findings:
1. [nit] align A1 example with canonical hash syntax
Resolution: nit fixed (cosmetic, verdicts stay valid).
```

Legacy format (pre-2026-06 records, kept as-is for the audit trail):

```
## Cross-review 2026-04-29 (Layer 1)
Reviewer: Codex
Verdict: concern
Findings:
- Issue 1: ...
Resolution: spec section X rewritten; section Y deferred to phase 2.
```

The audit trail matters because three months later, when someone
asks "why does this work this way?", the answer is in the spec —
not in chat history that's been lost.

## A note on overhead

Cross-review adds overhead. For Vepol's scope, that overhead is
worth it because the cost of a bad design decision compounds:

- A wrong direction in a spec → a wrong implementation → wrong
  data structures → harder-than-expected migrations later
- A subtle bug catch at review time → 5 minutes' work
- The same bug caught after deployment → an incident report and a
  fix and a regression test and probably a new prevention rule

The discipline is "spend more time at the spec gate to spend less
time later." It's not about being slow; it's about being honest
that one round of review by an independent reviewer pays for itself
many times over in mid-sized engineering work.
