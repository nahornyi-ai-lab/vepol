# Demo Hub — schema for the synthetic demo wiki

This is the schema file for the synthetic Vepol demo wiki at
`~/vepol/demo/knowledge/`. It mirrors the real hub schema in
`~/knowledge/CLAUDE.md` but acknowledges it's demo content.

## What's here

A complete fake "personal hub" populated with five archetypal life
domains: family, work, health, finance, and learning. The hub holds
cross-project files (registry, log, index, state, triad), and each
archetype is a separate project under `projects/`.

## Conventions used

The same conventions that the real Vepol hub uses (see
`../../knowledge/CLAUDE.md` in the repo for the master schema):

- **Three-file coordination triad** in every project + at the hub level:
  - `backlog.md` — what needs doing
  - `escalations.md` — what's blocked, awaiting your call
  - `incidents.md` — what broke, root cause, fix, prevention
- **Strategy file** — `strategies.md` — the working hypothesis about how
  Vepol should help in this domain, plus active and retired hypotheses
- **State + Index** — `state.md` (snapshot) and `index.md` (topical map)
- **Log** — `log.md` — append-only chronological event stream with
  grep-friendly prefixes (`## [YYYY-MM-DD] kind | slug | "..."`)
- **Cross-project categories** at the hub level — `concepts/`, `people/`,
  `companies/`, `solutions/`

## Why "demo" should never feel like real life

Every name, event, and detail in this demo is invented. If something
sounds plausible, that's intentional — synthetic-but-recognizable is the
sweet spot for a demo. But there's no actual person named "Maria
Rodriguez," no actual company called "Acme Industries," no actual
neighborhood school for a fictional Tom and Lily. They exist to show how
the *system* feels when populated.

## How a real user diverges from this demo

After installation, you run `kb-task "my first thing"` and immediately
your `~/knowledge/backlog.md` starts diverging from the demo. Within a
week your hub is yours, not ours. The demo wiki stays exactly as
shipped — it's a reference, not a starting point.

## What to read next

If you're exploring the demo to understand Vepol:

1. **`state.md`** — what's happening right now in the demo "user's"
   life
2. **`log.md`** — the last few weeks of events
3. **`backlog.md`** — current open work
4. Pick a project under `projects/` and drill in

If you're looking at the demo to learn the schema:

- **The real master schema** lives in the repo at
  `knowledge/CLAUDE.md` (sibling to this file's location)
- **Project template** at `_template/` shows the empty skeleton every
  project starts from
