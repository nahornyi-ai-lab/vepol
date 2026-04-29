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
  │  1. Doctor scan (daily)             │
  │     Auto-finds drift signals        │
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

A scheduled scan (daily, low-priority background task) goes through
the knowledge base looking for drift signals. Vepol's `kb-doctor`
runs the following audits:

- **Stale state files.** A `state.md` whose `Last updated:` line
  is more than 14 days old, in a project marked `live` in the
  registry. Either the project isn't live anymore (move to
  `seeded` or `archived`), or the state file needs an update.
- **Aging incidents.** An open incident with no action in 30+
  days. Flag for either resolution or escalation.
- **Backlog hygiene.** Items in `## Open` that are more than 60
  days old without movement. Either bump priority, defer
  explicitly, or close as "won't do."
- **Coordination headers.** Required sections (`## Open`,
  `## Done`, etc.) missing or malformed.
- **Wikilink graph health.** Pages that are referenced but don't
  exist; pages with no incoming references (orphans); cycles.
- **Real-slug-in-doc.** Real project names appearing in documents
  that should use placeholders (`<slug-a>`).
- **Coordination-triad symmetry.** Every project should have all
  three triad files (`backlog.md`, `escalations.md`,
  `incidents.md`); missing files get flagged.

Each finding gets a severity:

- **P0** — must fix immediately (broken structural invariant)
- **P1** — should fix soon (real drift detected)
- **P2** — advisory (minor inconsistency, fix when convenient)

### 2. Pending-curation queue

Findings from the doctor scan get written to a structured file
(`pending-curation.md`) in the hub. This file is the human-readable
queue of things that need attention.

Format:

```
## P1 findings — fix soon

- [ ] [project-foo] state.md last updated 2026-03-12 (43 days ago)
- [ ] [project-bar] incident "X failed" open since 2026-02-08

## P2 findings — advisory

- [ ] hub registry: project Z marked `live` but no log entries in 90 days
```

The queue is **append-only**: the doctor adds findings, the human
or agent removes items only after they've been actually addressed.
Items don't disappear silently because they're "old."

### 3. Curation pass

A human (or an agent under supervision) periodically works through
the queue:

- Read the finding
- Visit the page in question
- Either: update the page to reflect current reality, or: change
  the project's metadata (e.g., move from `live` to `archived`),
  or: explicitly mark the finding as a known-and-accepted state
- Remove the item from the queue

The cadence depends on the size of the knowledge base. For small
KBs (under 50 pages), once a month. For larger ones, weekly. The
discipline is to actually do the curation pass — not to let the
queue grow indefinitely. A 200-item curation queue is itself a
sign of drift in the freshness loop.

## The agents help, but the human decides

An AI agent can do the doctor scan automatically (the loop runs
unattended). For the curation pass:

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
- Its `Last updated:` date is recent enough relative to the
  page's volatility (a `goals.md` page can stay 6 months old; a
  client `state.md` should be days, not weeks)

Different pages have different volatility. The doctor scan
parameters are tunable per-page-class. The default thresholds
above (14 days for `state.md`, 30 days for incidents, 60 days for
backlog items) are reasonable starting points.

## Why this is a loop, not a one-time clean-up

The temptation when a knowledge base feels stale is to spend a
weekend cleaning everything up. This works once. Then drift starts
again. Six months later, you're back to where you started.

The loop is **not** a clean-up event. It's an ongoing low-amplitude
process:

- Daily: drift signals get auto-detected (zero human cost)
- Weekly: the human spends 30-60 minutes on the curation pass
- The result: drift never accumulates beyond a manageable buffer

The trick is to make the daily scan low-cost (so it actually runs)
and the curation pass focused (so it actually gets done). The
pending-curation queue is the buffer between them — drift waits
there for human attention, but doesn't get lost or forgotten.

## What the read-path looks like

When someone (you, an agent, a teammate) reads a page in the
knowledge base, they want to know if the page is fresh enough to
trust. Vepol's pages provide three signals:

1. **`Last updated:`** at the top of state-like files
2. **Frontmatter `status:`** for concept and methodology pages
   (`stable` / `draft` / `pending-review` / `retired`)
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
  is "I'll set up the doctor later." Then never do. The doctor
  must be wired up at install time and running from day one. The
  cost of starting late is high.

## In summary

Freshness is a property of the knowledge base, not a one-time
attribute of any page. It is maintained by:

- A scheduled drift-detection scan (the doctor)
- A queue of pending fixes (the curation queue)
- A regular curation pass (human + agent collaboration)

Without this loop, every Vepol installation degrades into a
plausible-but-wrong knowledge base on a 6-12 month timescale. With
it, the base stays trustworthy indefinitely.
