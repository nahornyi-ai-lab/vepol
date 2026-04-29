---
title: "TRIZ for Design"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [spec-phase, design-decisions]
---

# TRIZ for Design

The design discipline Vepol applies at the spec phase: **formulate
the contradiction first, find the ideal final result, resolve via
separation — not compromise**.

This page distills [TRIZ](https://triz.org/) (Theory of Inventive
Problem Solving, developed by Genrich Altshuller) into the minimum
practical loop a developer needs when designing a non-trivial
change in collaboration with multiple AI agents and a human.

## The core idea in one paragraph

When you face a non-trivial design problem, your instinct is to
search for a compromise. TRIZ says: stop. Most engineering problems
are actually **contradictions** ("we need X **and** not-X at the
same time"). A good compromise softens both sides; a *good* solution
finds a way to give both sides full satisfaction. The way to do that
is **separation** in space, time, condition, or structure — not
splitting the difference.

## The loop

When designing anything non-trivial — a new feature, a refactor, an
infrastructure change, a workflow rewrite — apply this loop **inside**
the spec phase:

### 1. Formulate the contradiction explicitly

What's stopping you? Most often it's "we need X *and* not-X." Write
the contradiction in plain words. Examples:

- "Encrypted on the server **and** plaintext on the user's laptop"
- "Fast write **and** reliable index"
- "Flexible configuration **and** simple onboarding"
- "Local-first **and** accessible from anywhere"

If the problem doesn't reduce to a contradiction, you don't need a
compromise solution at all — just build it. Most real design
problems have a hidden contradiction, even when they look
straightforward.

### 2. Formulate the Ideal Final Result (IFR)

The IFR is what the system would do if it cost zero: it performs
its function without itself existing, or it exists without
consuming resources, or it has no side effects. The IFR is rarely
fully achievable, but it is the **direction** every design decision
should pull toward.

Examples:

- IFR for a backup system: "the data is recoverable instantly,
  costs zero storage, requires zero attention"
- IFR for a daily brief: "you wake up already knowing what's
  important today, having read nothing"

When you sketch the IFR explicitly, you make it visible how far any
specific design proposal falls short of it — and that gap is where
the contradiction's resolution will live.

### 3. Resolve through separation, not through compromise

Four primary axes for separation. Try them in this order:

- **In space.** X in one place, not-X in another. (Encrypted on the
  server, plaintext on the laptop. Hot data in RAM, cold data on
  disk.)
- **In time.** X now, not-X later. (Quick write, deferred index.
  Eager UI, lazy persistence.)
- **In condition / scale.** X under one condition, not-X under
  another. (Mount-on-demand. Dev versus prod. Hot path versus cold
  path.)
- **In structure.** X at one level, not-X at another. (Plugin
  sandbox. Layered storage. Public API versus private internals.)

If your draft solution is a halfway compromise on both sides of the
contradiction, you probably haven't actually resolved the
contradiction — you've softened it. Try again.

### 4. Check against the standard inventive principles

Altshuller compiled [40 principles](https://triz.org/principles/)
distilled from analyzing many patents. They aren't a checklist; they
are a palette to spark ideas. A few that come up often in software:

- **Segmentation.** Divide a monolith into independent units.
- **Asymmetry.** Replace symmetric structure with asymmetric (often
  unlocks performance gains).
- **Prior action.** Do work in advance to avoid blocking on it
  later (preprocessing, indexing, building cache).
- **Periodic action.** Replace continuous with periodic (polling,
  batching, snapshotting).
- **Dynamization.** Replace fixed with adjustable (config flags,
  runtime parameters).
- **Nesting.** Place objects inside other objects.
- **The other way around.** Invert the operation (push instead of
  pull, do less instead of more).

Use these to generate alternatives. Don't apply mechanically.

### 5. Reject "middle" solutions

If your proposed solution is a halfway compromise on both sides of
the contradiction — not a separation that gives both sides full
satisfaction — you probably haven't actually resolved it. Go back to
step 1, restate the contradiction, look for a separation axis you
haven't tried.

## Where this lives in the workflow

TRIZ isn't a separate process running parallel to
[`spec-driven-workflow.md`](spec-driven-workflow.md) — it's the
mode of thinking *inside* the spec phase. When you write the spec
for a non-trivial change:

- Formulate the contradiction explicitly, in words, in the spec
  document
- Sketch the IFR
- List which separation axes you tried before settling on the
  solution you're proposing
- Mark which of the 40 principles, if any, the solution applies

If you can't formulate the contradiction, that's an even more
valuable signal: it suggests the problem is wrongly framed, and the
spec needs rethinking before any code is written.

## When TRIZ does not help

- For trivial changes (typo fix, version bump) — overkill, skip it.
- When you don't yet know the problem well enough to formulate the
  contradiction. In that case, do more research first.
- When the constraint isn't actually X-vs-not-X but a missing piece
  of information (then you need to gather, not invent).

## Common mistake — confusing compromise with separation

A compromise sounds like: "We'll do half X and half not-X to
balance them." A separation sounds like: "We'll do X here / now /
in this condition / at this layer, and not-X there / then / under
that condition / at the other layer — both fully."

If you can't tell which one your proposal is, write down the
contradiction and try again to formulate the IFR. The IFR drags
the design toward separation, away from compromise, because by
construction it asks for full satisfaction on both sides.

## Why Vepol bakes this in

Vepol is built by multiple AI agents in collaboration with a
human. AI agents often produce fluent compromise solutions unless
the design process forces contradictions into view. TRIZ is the
minimum discipline that prevents this bias from compounding across
many design decisions. Without it, Vepol's spec quality degrades
over time toward "soft, plausible, slightly underperforming
designs that nobody objects to but nobody gets excited about."

With it, Vepol is forced to find the contradictions explicitly and
attempt separation before settling. The result is sharper specs and
fewer "we'll improve this later" follow-ups.

## Acknowledgments

TRIZ was developed by Genrich Altshuller (1926–1998) based on
analysis of hundreds of thousands of patents. Vepol uses a small
practical subset; the [official TRIZ site](https://triz.org/) and
[Altshuller Foundation](https://www.altshuller.ru/world/eng/triz1e.asp)
have the full body of work. The 40 principles are
[here](https://triz.org/principles/).
