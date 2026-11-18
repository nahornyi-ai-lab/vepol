---
title: "KB Freshness Loop"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [knowledge-maintenance, lint, drift-detection]
---

# KB Freshness Loop

How Vepol keeps the working context aligned with reality as
projects change. The longer the partnership runs, the more chance
that pages drift out of sync with what's actually true. The
freshness loop is the discipline and tooling that catches drift
before it becomes invisible.

## The problem

A knowledge base is most useful when its claims match reality.
After three months of active use, a Vepol knowledge base has
hundreds of pages, dozens of concepts, dozens of project states. It
is not realistic for the human or the agent to re-verify every page
on every read.

What happens without discipline:

- A `state.md` says "client X is in negotiation" — but the
  negotiation closed three weeks ago and the page never got
  updated
- A `concepts/` page describes a tool's API as it was a year ago,
  before the tool's v2 release
- An `incidents.md` prevention rule references a workflow that no
  longer exists (it was replaced)
- Half the cross-references in `index.md` point to pages that have
  since been renamed or merged

Each individually is small. In aggregate, the knowledge base
becomes **plausibly wrong** — confident-looking, internally
consistent, and increasingly out of date. This is worse than an
incomplete knowledge base, because it actively misleads anyone
(human or agent) who consults it.

## The loop in three pieces

The freshness loop has three pieces that work together:

```
  ┌─────────────────────────────────────┐
  │  1. Doctor scan (regular)           │
  │     Finds drift signals             │
  └────────────┬────────────────────────┘
               ▼
  ┌─────────────────────────────────────┐
  │  2. Pending-curation queue          │
  │     A human-readable list of        │
  │     things that need attention      │
  └────────────┬────────────────────────┘
               ▼
  ┌─────────────────────────────────────┐
  │  3. Curation pass (weekly)          │
  │     The human (or agent under       │
  │     supervision) works through the  │
  │     queue                           │
  └─────────────────────────────────────┘
```

### 1. Doctor scan

`kb-doctor` goes through the knowledge base looking for drift
signals. Vepol does not schedule it: run it yourself, or ask your
agent to run it. Plain `kb-doctor` checks every active project in
the hub registry:

- **Stale state files.** A `live` project's `state.md` whose newest
  date is more than 14 days old (P2) or more than 30 days old (P1).
  In any active project, a `state.md` that trails the newest
  `log.md` entry by more than three days (P1 when `live`, P2
  otherwise).
  Either the project isn't live anymore (move to `seeded` or
  `archived`), or the state file needs an update.
- **Aging incidents.** An incident under `## Ongoing` in
  `incidents.md` that was opened more than 7 days ago (P1). Flag
  for either resolution or escalation.
- **Backlog hygiene.** In a one-line backlog, an open item whose
  `due:` date has passed (P0) and an item that has been in
  progress for more than two days (P1). Either bump priority,
  defer explicitly, or close as "won't do."
- **Core files and headers.** A project missing one of its core
  files (`README.md`, `index.md`, `state.md`, `log.md`, and the
  triad `backlog.md`, `escalations.md`, `incidents.md`) (P0), or a
  triad file missing a required section such as `## Ongoing` in
  `incidents.md` (P1).

`kb-doctor graph-audit` checks **wikilink graph health**: links to
pages that don't exist, links that match more than one page, and
pages with no incoming links (orphans).

Each finding gets a severity:

- **P0** — must fix immediately (broken structural invariant)
- **P1** — should fix soon (real drift detected)
- **P2** — advisory (minor inconsistency, fix when convenient)

### 2. Pending-curation queue

`kb-doctor --write` writes the findings to
`~/knowledge/pending-curation.md`. This file is the human-readable
queue of things that need attention.

Format (shortened):

```
## Automated freshness audit

<!-- managed by kb-doctor; do not edit inside block -->
Generated: 2026-04-24

- [ ] P1 project-foo: live project state.md has no recent internal date — detected 2026-04-24 — evidence: state_date=2026-03-12 age_days=43 — file: `…/state.md` — doctor-id: …
- [ ] P1 project-bar: open incident is older than 7 days — detected 2026-04-24 — evidence: opened=2026-02-08 … — file: `…/incidents.md` — doctor-id: …

<!-- /managed by kb-doctor -->
```

Each `--write` run replaces only this block, from the latest scan,
and leaves the rest of the file alone. A problem stays in the queue
for as long as the doctor still sees it, however old it is. It
drops out on the first run after it is actually fixed, or after you
tick it off (`- [x]`).

### 3. Curation pass

A human (or an agent under supervision) periodically works through
the queue:

- Read the finding
- Visit the page in question
- Either: update the page to reflect current reality, or: change
  the project's metadata (e.g., move from `live` to `archived`),
  or: tick the line (`- [x]`) to accept the finding as known. The
  next `--write` moves ticked lines to a resolved list and keeps that
  finding out of the queue for as long as its evidence stays the
  same. Findings that carry an age in their evidence come back the
  next day, so for those, fix the page.
- Run `kb-doctor --write` again; fixed items leave the queue

The cadence depends on the size of the knowledge base. For small
KBs (under 50 pages), once a month. For larger ones, weekly. The
discipline is to actually do the curation pass — not to let the
queue grow indefinitely. A 200-item curation queue is itself a
sign of drift in the freshness loop.

## The agents help, but the human decides

An AI agent can run the doctor scan for you and read the queue.
For the curation pass:

- The agent can propose updates ("here's what I think state.md
  should now say")
- The human approves, edits, or rejects each proposal
- For low-stakes items (typo fixes, link updates), the human can
  delegate to the agent under a "fix and report" mode

For high-stakes items (revising a project's strategic direction,
canonicalizing a new concept, archiving a project), the human
decides. Agents act within delegated authority; humans set
boundaries and approve high-stakes changes.

## What "freshness" means concretely

A page is **fresh** when:

- Its claims match reality at the time of the latest curation pass
- Its references all resolve
- It is connected to the rest of the knowledge graph (not
  orphaned)
- Its newest date is recent enough relative to the
  page's volatility (a `goals.md` page can stay 6 months old; a
  client `state.md` should be days, not weeks)

Different pages have different volatility. Today the thresholds
are fixed in `kb-doctor`: 14 and 30 days for a live project's
`state.md`, 7 days for an open incident, two days for an item in
progress.

## Why this is a loop, not a one-time clean-up

The temptation when a knowledge base feels stale is to spend a
weekend cleaning everything up. This works once. Then drift starts
again. Six months later, you're back to where you started.

The loop is **not** a clean-up event. It's an ongoing low-amplitude
process:

- Regularly: `kb-doctor --write` collects drift signals (a few
  seconds of your time)
- Weekly: the human spends 30-60 minutes on the curation pass
- The result: drift never accumulates beyond a manageable buffer

The trick is to make the regular scan low-cost (so it actually runs)
and the curation pass focused (so it actually gets done). The
pending-curation queue is the buffer between them — drift waits
there for human attention, but doesn't get lost or forgotten.

## What the read-path looks like

When someone (you, an agent, a teammate) reads a page in the
knowledge base, they want to know if the page is fresh enough to
trust. Vepol's pages provide three signals:

1. **The newest date in a state-like file.** `kb-doctor` reads the
   latest date it finds in `state.md`, and falls back to the file's
   modification time
2. **Frontmatter `status:`** for concept and methodology pages
   (`draft` until the work is verified, then `stable`)
3. **The wider freshness loop status** — if there's an unresolved
   item about this page in `pending-curation.md`, the curation
   queue is the place to check before relying on the page

A page that is `status: stable` and recently curated is trustworthy.
A page that is `status: draft` or has open curation items needs
verification.

## Anti-patterns

- **Skipping curation passes.** The queue grows; eventually it's
  too big to ever finish in one sitting. Then it stops being a
  queue and becomes just a noisy file. Solution: small, frequent
  passes; if you missed last week, do this week, don't try to
  catch up.
- **Auto-fixing without human review on high-stakes content.**
  "I'll let the agent resolve all P2 items automatically" sounds
  efficient. In practice, unsupervised content edits drift toward
  agent-flavored phrasing (homogenizing the writing). The right
  rule: **require review for high-stakes content changes, allow
  pre-approved fix-and-report for low-risk mechanical updates**
  (typo fixes, broken-link updates, formatting). The line between
  "high-stakes" and "low-risk" is set explicitly per project.
- **Tuning thresholds away from drift.** When the doctor flags
  too many P1s, the temptation is to relax the threshold. That
  hides drift instead of catching it. The right move is to do a
  bigger curation pass once, and then keep the threshold.
- **Not running the doctor at all.** The most common failure mode
  is "I'll set up the doctor later." Then never do. The installer
  only checks that the install is healthy; the freshness audit is
  yours to run, from day one. The cost of starting late is high.

## In summary

Freshness is a property of the knowledge base, not a one-time
attribute of any page. It is maintained by:

- A regular drift-detection scan (`kb-doctor`)
- A queue of pending fixes (the curation queue)
- A regular curation pass (human + agent collaboration)

Without this loop, every Vepol installation degrades into a
plausible-but-wrong knowledge base on a 6-12 month timescale. With
it, the base stays trustworthy indefinitely.
