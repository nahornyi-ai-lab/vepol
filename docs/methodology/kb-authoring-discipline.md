---
title: "KB-Authoring Discipline"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [ingest, init-kb, bulk-refresh]
---

# KB-Authoring Discipline

How Vepol writes durable project context without producing
**false-canonical** content. Eight rules an AI agent must follow when
turning sources, decisions, and project state into shared working
context — especially during the first onboarding of an existing
project.

## The problem

When an agent first sets up a knowledge base for a project, it
typically has access to:

- The project's `README.md` (which may be internally contradictory,
  outdated, or contain plans presented as facts)
- One or two other markdown files
- Its own training memory (which goes stale fast for things like
  pricing, deadlines, regulatory rules, evolving APIs)

What the agent **does not have**: independent sources of truth for
specific numbers, dates, statuses, eligibility rules, recent
decisions, or current product state.

Meanwhile, the empty project-context skeleton (`state.md`,
`strategies.md`, `templates/`, `index.md`) tempts the agent to
immediately fill files that *structurally look canonical* — as if
they had been approved as project policy.

The result without discipline: a **plausible knowledge base that
presents the model's guesses and the README's claims as approved
facts and project policy**. This is worse than an empty knowledge
base. An empty KB motivates verification. A false-canonical KB
*displaces* it.

## The eight rules

### R1. Separate "the README claims" from "verified"

In `state.md` and any reference table, keep explicit columns:

- What the primary source claims (README / tracker / external
  document) — quoted verbatim
- The **independent verification** of that claim (user answer,
  official portal opened, artifact inspected) — with a date
- Until verification is in place, the claim cannot be used in
  downstream work

Don't merge the columns. Don't write a summary that asserts more than
the verification column allows.

### R2. Partial verification ≠ green

If you verified something indirect (a file exists, a URL responds)
but not the exact claim in the adjacent column (`DRAFT READY`,
`SUBMITTED`, `BLOCKED`) — verification is **still failed**, and the
indirect observation goes in a separate neutral note with an
explicit "fact X does not confirm claim Y."

A green cell that rests on a not-quite-the-right observation is
**false-green**.

### R3. Concrete numbers only from verified sources

Amounts, deadlines, capital thresholds, minimum-employee counts,
rates, review weeks, budget caps — canonize them in the KB **only**
when both:

(a) there's a link to an official source, and
(b) there's a date when you checked it

The alternative is to not write the number at all — leave the URL
with a "verify pending" note. You cannot simultaneously declare "the
source is the official site" and populate the table with numbers from
the README or training memory. That's a self-contradicting sourcing
model.

### R4. Facts about the company come from the accounting system, not the project README

Legal details (registered capital, registration date, business
classification, founders, tax IDs, administrators) get canonized
through the project that owns them (typically a bookkeeping or
accounting project), not from the target project's README. Lists of
products or open-source artifacts: don't canonize from a README
without an explicit user confirmation.

### R5. The role of a document is canonized by its title and path, not just its content

Files named `strategies.md`, `policies/<x>.md`, `standards/<x>.md`,
`templates/<x>.md`, `decisions/<x>.md`, `principles.md` are by
default read as approved project artifacts. A disclaimer in the body
**does not undo** the implication of the title and path.

If init-time auto-population creates such a file without explicit
user approval:

- Add an explicit marker to the file's title: `(**PROPOSAL DRAFT**, not approved)`
- Add `(proposal)` to the top-level section heading
- In the project's `index.md`, put it in a separate `PROPOSAL DRAFTs`
  section, not mixed with approved content

The marker is removed only after the user has explicitly read and
approved (or rewritten) the file.

### R6. No secondary exceptions inside a PROPOSAL document

If a file is marked PROPOSAL, the **whole** file is PROPOSAL. You
can't exempt one section as "safe to use without approval" — even if
it looks like a universal discipline or an obvious rule. That
reproduces false-canonical at the section level instead of the file
level.

General meta-rules (like the rules on this page) live separately in
hub-level `concepts/` or `solutions/`, not in PROPOSAL pages of
projects. There they can be canonical as cross-project discipline,
but that's a decision about the concept, not about any specific
project.

### R7. The index doesn't decide replacement for the user

Don't claim that "file X has replaced file Y" unless the user has
confirmed the replacement. By default, both coexist; precedence
awaits a decision. The same rule applies to attempts to merge or
deduplicate pages.

### R8. Durable guardrails live in shared knowledge, not session memory

Lessons at the level of "how the agent should behave when populating
a KB" (this page itself) live in shared `~/knowledge/concepts/` or
`~/knowledge/solutions/`, so all agents read the same source.
Per-agent session memory may carry a summary or a pointer, but it
must not be the only place — otherwise a second agent acts without
the guardrail.

## Practical algorithm at first KB initialization

1. **Read the primary materials** (README, trackers, root markdown
   files). Note **where they're internally contradictory** (dates in
   the future, conflicting numbers) — that's the first piece of
   evidence that the materials cannot be canonized as-is.
2. **Set up `state.md`** following R1+R2. Every status starts as
   "not verified." The summary asserts no more than the table
   allows.
3. **All other pages start as PROPOSAL** (R5) or as scaffold-only
   reference pages with honest disclaimers (R3 — URLs without
   numbers).
4. **The first task in `backlog.md`** is a verification session
   with the user: walk through the `state.md` table, confirm /
   correct / reject each row; then approve / rewrite the PROPOSAL
   pages.
5. **Until the verification session happens**, block any task that
   would execute decisions based on unverified data (e.g., "submit
   application X by date Y," "start raising capital," "rule out
   program Z").
6. **Durable lessons about agent behavior** go in
   `~/knowledge/concepts/` (this page), not into per-project or
   per-agent artifacts.

## Why these rules exist

This concept is the direct result of an early hard lesson: an AI
agent without these rules will, when handed an existing project's
README and asked to "set up a knowledge base," produce a confidently
wrong description of the project — dates that haven't happened
declared as having passed, numbers from the model's training memory
presented as policy, deadlines that conflict with project facts
asserted as approved.

The cost of a false-canonical KB is high. Every downstream task
that consumes it inherits the wrong assumptions. Verifying the
claims requires re-reading source material the agent already
flattened — work the discipline above prevents.

The rules are not friction for friction's sake. They are the
minimum protocol for an agent that must produce content **and**
mark when that content has not yet been verified — without
collapsing the distinction.
