---
title: "Cross-Agent Review"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [non-trivial-plans, design-decisions, refactors]
---

# Cross-Agent Review

The quality gate Vepol applies before any non-trivial change goes
into implementation: **a non-trivial plan is reviewed by an
independent agent before implementation**. Concerns get addressed
before code is written. This is not optional ceremony — it's the
mechanism that catches bias and tunnel vision that single-agent
flows produce.

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
Z." The reviewer can flag "blocker," "request-changes," or
"approve."

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
  (the gate is *before* code, not after)
- Skip Layer 1 and go straight to Layer 2 — even when the author
  insists "the direction is obviously right"
- Decline to review without a recorded reason

If the second agent is unavailable (rate-limited, broken, in
maintenance), the author can either wait or proceed with a recorded
"review attempted, blocked, escalated to human" note. Silently
skipping the review is the only forbidden path.

## Why both directions

Vepol can host multiple AI orchestrators: Claude, Codex, and future
agents. Each can act as author or reviewer. Cross-review goes
both ways:

- Plans authored by Claude get reviewed by Codex (or another
  agent)
- Plans authored by Codex get reviewed by Claude (or another
  agent)
- Plans authored by any additional agent get reviewed by one of
  the others

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

```
## Cross-review 2026-04-29 (Layer 1)
Reviewer: Codex
Verdict: concern
Findings:
- Issue 1: ...
- Issue 2: ...
Resolution: spec section X rewritten; section Y deferred to phase 2.

## Cross-review 2026-04-29 (Layer 2)
Reviewer: Codex
Verdict: request-changes
Redlines applied: 7 of 8.
One redline rejected: "the chosen phrasing is the maintainer's
deliberate decision (preserved with reason)."
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
