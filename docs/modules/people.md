---
title: "Vepol People — extension of your memory of the people in your life"
status: draft-v1
type: module
parent: vepol
substrate: markdown
---

# Vepol People

People are the most consequential context you carry. Decisions you
make at work, calls you postpone, introductions you owe, the people
who change your life — none of that lives cleanly in a calendar, an
inbox, or a contact list. It lives in the parts of your memory that
are unreliable on purpose, because the brain prioritises what felt
important last.

Vepol People is the layer of Vepol that **extends your memory of
people, in markdown**, and lets every Vepol agent you work with read
that memory as part of one shared field of knowledge.

## What it is

Vepol People is a **person-context memory graph**: one markdown card
per person, sitting in your knowledge base next to your projects,
companies, decisions, and daily logs. Cards are linked. Agents read
them. You write to them. Sources (calendar today; mail and chat next)
quietly append observed interactions so the cards stay current
without you having to maintain them by hand.

This is one **module** of Vepol — the AI partner that plans your day,
runs routines, and leaves an auditable markdown trail. Other modules
cover projects, daily brief and retro, calendar, and so on. They all
share the same substrate. People is the slice that handles humans.

A few terms used below:

- **Knowledge base / wiki** — a folder of plain markdown files (the
  *Karpathy-style LLM wiki* pattern) that Vepol uses as its single
  source of truth. Humans edit it; agents read and propose changes
  through review gates.
- **Orchestrator** — Vepol's coordination layer. It runs scheduled
  jobs (brief, retro, plan dispatch), spawns task agents in the right
  working directory, and manages a write-ahead audit trail for every
  edit.
- **Vepol channel** — the place messages from the orchestrator surface
  to you. Today: Telegram. Tomorrow: a new chat surface, voice, or
  whatever you wire in. Reminders go through this channel.
- **Cross-agent review** — Vepol's principle that any non-trivial AI
  proposal is checked by a second AI before landing. Person-card
  edits proposed by an agent fall under the same gate as any other
  knowledge edit.

## Why markdown, and not a database with a UI

You could imagine the same feature as a SQLite database with a web
form on top. We chose markdown deliberately, because the same artifact
ends up serving four jobs at once:

1. **A human note.** You can open `people/marina-soto.md` in any
   editor and write a paragraph the way you would in a paper notebook.
2. **An audit trail.** The interactions section is a chronological
   table appended by sources, each row carrying its provenance. You
   can grep, diff, and inspect it without a query language.
3. **A source citation for the agent.** When the orchestrator quotes
   a fact about Marina in your morning brief, it cites the card. The
   card is the canonical reference — not a record id in a database
   you cannot read.
4. **Runtime context for agents.** When an agent works on a project
   that links to Marina, the card text is loaded into the agent's
   prompt. Markdown is what models read natively; there is no API
   adapter between "what the wiki contains" and "what the agent
   knows".

These four jobs collapse into one file. A database+UI design splits
them across forms, query results, exports, and prompt-shaping code,
and you spend energy keeping them aligned. Plain markdown removes
that alignment problem.

## What you actually do

You install Vepol. People appear in your knowledge base as you live
your life:

```
$ kb-contact add "Marina Soto" --email marina@example.com --met "Lisbon AI meetup, 2026-03"
$ kb-contact log marina-soto "Discussed her plans for a side project on causal inference."
$ kb-contact remind marina-soto --in 6w
$ kb-contact due
  • Marina Soto — due 2026-06-15  [colleague, ml]
  • Tomás Reyes — due 2026-06-18  [client]
```

Behind those commands, Vepol is just writing and updating files at
`knowledge/people/<slug>.md`. You can open them in any editor; you
can grep them; you can version or back them up separately if you
choose. They are yours.

You do not have to add people manually for the system to know about
them. Sources you have connected (calendar today; mail and chat
later) add new people to your knowledge base automatically. When the
source has high-confidence identity — typically an email match against
an existing card, or a unique email among current attendees — the
new card is added directly. When dedup is ambiguous (a name that
might collide with an existing card, no email available, etc.), the
source creates a **draft** card flagged with `draft: true` and a
`possible_duplicate_of:` link, waiting for human review. Drafts are
visible, never act on your behalf, and stay in your knowledge base
until you confirm or merge them.

## Cross-pollination, concretely

The interesting property of People is what it does for **other**
modules. Concrete trace:

1. You write a project note at `projects/orderflow/state.md` and you
   wiki-link a person: `Lead reviewer: [[people/marina-soto]]`.
2. The next time the orchestrator works on the orderflow project —
   say, generating tomorrow's plan — it follows that link as part of
   loading project context. Marina's card lands in the same prompt
   alongside the project state.
3. The morning brief mentions: *"Orderflow review is on the agenda
   tomorrow; Marina is the reviewer; you talked about causal
   inference with her in March."* The brief cites the card it pulled
   the fact from, so you can verify.
4. After your call with Marina, the daily-log mentions her by name.
   The next retro-time interactions extractor appends a row to her
   card under `## Interactions`, with the source being today's daily
   log.

The graph closes. The orchestrator never forgot Marina existed; it
read her card every time she was relevant; and what you and Vepol
agreed about her after the fact got back into her card without you
typing it anywhere special.

This loop only works because People shares a substrate with the rest
of the wiki. A separate CRM database would not deliver step 3 or
step 4 cleanly — you'd be writing glue between systems.

## How it works under the hood

Three concerns, three pieces.

### 1. Cards — markdown with a stable structure

Each person is a file at `knowledge/people/<slug>.md`. The frontmatter
holds machine-readable identity: a stable UUID, the canonical name,
aliases, channels (email, Telegram, LinkedIn, phone), company, role,
when you first met, last seen, the next time you owe a follow-up,
tags, and a draft flag. The body has two clearly-bounded regions:

- **Manual notes** — between `<!-- MANUAL-NOTES-BEGIN -->` and
  `<!-- MANUAL-NOTES-END -->`. Anything you write yourself. Free-form.
  Never rewritten by automation.
- **Interactions** — between `<!-- DERIVED-SIGHTINGS-BEGIN -->` and
  `<!-- DERIVED-SIGHTINGS-END -->`. A chronological table appended by
  sources: meetings, mail, mentions in your daily log. Each row
  carries its source so you can audit.

The two regions never collide. If you write in the manual section, no
agent edits it. If a source appends to the interactions table, no
manual notes are touched.

The full schema lives in the project at
`_template/knowledge/people/_example.md`. Cards generated by the CLI
or sources start sparse — only fields with actual values are written —
and grow as you (or sources) add information. A sparse card is just
as valid as a fully-filled one; missing fields mean "no data yet",
not "broken". The example template shows every possible field for
reference, but you should not expect every card to have every field.

### 2. Sources — the world feeds the cards

A source is a small adapter that reads from somewhere external and
returns candidate interactions or candidate people. The first one
shipped is **calendar**: it scans the last *N* days of your Google
Calendar, groups attendees by email, and either updates the existing
card or creates a draft.

Sources are pluggable on purpose. Mail and chat are natural next
ones. Sources never write outside the cards they own; sources never
delete; sources never act without dedup arbitration.

### 3. Dedup — one person, one card

Identity is the hard problem. Vepol People resolves it through layers:

- **Stable UUID** — the canonical key. Once assigned, never changes.
- **Email-first deterministic match** — same email = same person.
- **Name fuzzy match** (Jaro-Winkler distance) — cards without an
  email match are compared by name against existing cards using a
  simple, inspectable string distance. A score ≥ 0.92 is treated
  as the same person; between 0.85 and 0.92 the new card is kept as
  a draft with `possible_duplicate_of: <other>` so a human (or an
  agent under explicit policy) can confirm the merge. Names shorter
  than 4 characters are skipped from fuzzy matching entirely — they
  carry too little signal. Telegram and other soft signals are stored
  on the card but not yet used as match tiers; that's planned but not
  in v1.

Dedup is conservative on purpose: a wrong merge is harder to undo
than a duplicate.

## Reminders, not nudges

Each card has an optional `next_touch_due` field. You can set it
explicitly (`kb-contact remind <slug> --in 6w`); future versions may
let the orchestrator propose it from observed cadence. When the date
is reached, **kb-people-remind** surfaces it through your Vepol
channel — a single message, batched if many are due, never spammy.

The reminder is not a gamified streak. It is a small acknowledgement
that you owe a person something — usually a message, sometimes a
favour, sometimes just attention. Vepol's job is to make sure your
better intentions are visible to your future self at the right time.

## What Vepol People is not

Because the surface looks superficially similar to other tools, it is
worth being explicit about what is not in scope.

- **It is not a CRM.** Sales pipelines, deal stages, lead scoring,
  team-shared dashboards — none of that. CRMs are databases with user
  interfaces; Vepol People is markdown that an AI partner reads.
- **It is not a contact-management SaaS.** No backend, no proprietary
  format, no service to subscribe to. Your data lives in your
  knowledge base. The day you decide to leave Vepol you keep all of
  it; markdown does not lock in.
- **It is not a quantified-self loop.** Counting interactions per
  week is not a goal. The goal is that you do not forget a person
  who matters at the moment when remembering them changes a
  decision.
- **It is not a hands-free auto-mailer.** Vepol drafts and proposes;
  the human approves; explicit policy governs anything automatic.
  The default is *propose, don't dispatch*.

## Limits, honestly

Vepol People v1 ships with the following boundary:

In v1:
- Calendar source for ingest
- CLI for add / log / remind / search / due / show
- Markdown card schema with manual-notes + auto-interactions
- UUID + email + name dedup
- Reminders via Vepol channel
- A demo card and a card template

Not in v1, and noted as future work:
- Mail and chat sources
- LinkedIn enrichment beyond manual fields
- Voice-call transcription into interactions
- Smart suggestion of who to introduce to whom
- Group / household / family modelling beyond individual cards
- Confidence scoring on extracted facts
- Cross-agent review specifically scoped to person-card writes (today
  the general review discipline applies; there is no person-specific
  policy yet)

The goal of v1 is to make the substrate work end-to-end: a card you
can read, an agent that can read it, a reminder that lands at the
right time, and an interaction history that is honest about its
sources. Everything else lands when there is concrete reason for it.

## Public status

Spec status: **draft-v1** — open to changes after first cohort of
users provides feedback.

Implementation: **shipping** in `bin/_kb_people/`, `bin/kb-contact`,
`bin/kb-calendar-sync`, `bin/kb-people-remind`. Tests in
`bin/tests/test-people.sh`. Card template in
`_template/knowledge/people/_example.md`. Channel send wrapper in
`bin/kb-channel-send`. Reminder LaunchAgent template in
`launchd/com.knowledge.people-remind.plist.template`.

Python dependencies (`python-frontmatter`, `click`, `PyYAML`,
`jellyfish`) are listed in the project root `requirements.txt`.

The calendar source fetches data through the configured MCP host —
see [MCP-first for external sources](../methodology/mcp-first-sources.md).
No vendor SDK or OAuth client library is required; the user
configures Google Calendar access once in their MCP host.

If you find an unfamiliar term in this page (orchestrator, channel,
cross-agent review), it is documented in the methodology pages at
`docs/methodology/`.

## See also

- [Orchestrated Knowledge Base](../methodology/orchestrated-knowledge-base.md) — the substrate philosophy
- [KB Authoring Discipline](../methodology/kb-authoring-discipline.md) — how facts enter the wiki
- [KB Freshness Loop](../methodology/kb-freshness-loop.md) — how stale facts get re-touched
- [Cross-Agent Review](../methodology/cross-agent-review.md) — the second-AI gate on non-trivial proposals
