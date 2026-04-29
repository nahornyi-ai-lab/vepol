# Vepol Demo Wiki

This is a **synthetic, fully fictional** Vepol knowledge base. Every name,
project, person, company, and event in here is invented to demonstrate how
Vepol's structures look when populated. Use it to:

- See what `kb-brief`, `kb-retro`, `kb-search`, and `kb-task` produce when
  there's actual content to work against
- Browse the file conventions (triad, log format, project layout) before
  starting your own
- Test installations — running commands against `demo/knowledge/` doesn't
  touch your real `~/knowledge/`

## How to use

```bash
# From the repo root, point any Vepol command at the demo:
KB_HUB=$(pwd)/demo/knowledge bin/kb-brief
KB_HUB=$(pwd)/demo/knowledge bin/kb-search "client renewal"
KB_HUB=$(pwd)/demo/knowledge bin/kb-backlog --open
```

Or use the wrapper:

```bash
bin/kb-demo brief        # equivalent to KB_HUB=demo/knowledge kb-brief
bin/kb-demo search "..."
bin/kb-demo backlog --open
```

## What's in here

Five archetypal project areas chosen to cover the most common use of a
personal Vepol setup:

- **`projects/family/`** — household coordination, kids' school, planning a
  weekend. Shows how Vepol is useful for life that isn't your "work
  projects."
- **`projects/work/`** — typical small-business work: client deliverables,
  meetings, invoicing. Shows the registry/log/triad pattern in action.
- **`projects/health/`** — exercise, nutrition, sleep, doctor visits. Shows
  how Vepol can hold long-running personal data with privacy.
- **`projects/finance/`** — monthly review, savings goals, expense
  tracking. Shows recurring tasks and goal-tracking.
- **`projects/learning/`** — book notes, courses, certifications. Shows
  long-form ingestion of source material.

Plus the hub-level files (`registry.md`, `log.md`, `index.md`, `state.md`,
`backlog.md`, `escalations.md`, `incidents.md`, `strategies.md`) populated
to show what an active multi-project hub looks like, and a few example
pages under `concepts/`, `people/`, and `companies/` showing how
cross-project knowledge is captured.

## Reading order for a first-time user

1. **`knowledge/state.md`** — the current snapshot. What's the state of the
   demo "user" right now?
2. **`knowledge/index.md`** — the topical map of the whole knowledge base.
3. **`knowledge/log.md`** — the chronological event log. Read the last
   30-50 lines for a sense of the pace.
4. **`knowledge/backlog.md`** — what's open vs done across the whole hub.
5. **`projects/family/`** or any other archetype — drill into one project
   to see how the same conventions look at the project level.

## Why these archetypes (not real projects)

Vepol's value is the *system*, not any particular project. Choosing real
project names would make the demo feel like a portfolio review. Choosing
abstract names like "Project A" would make it feel like a unit test.
Generic life-domain archetypes (family, work, health, finance, learning)
are immediately legible to anyone — you can see how the system would map
to *your* life, not to ours.
