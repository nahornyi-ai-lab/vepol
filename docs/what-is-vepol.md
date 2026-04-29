# What Vepol actually is

> A long-form answer for people who looked at the README and want to
> understand whether Vepol is for them. Skip to the bottom for a 60-second
> summary.

## A second inner voice, not a memory tool

Most "AI memory" tools answer the wrong question. They solve "how do I make
the chatbot remember what I said yesterday?" — and stop there. The result is
a slightly smarter chatbot that still waits for you to ask it things.

Vepol answers a different question: **how do I work with an AI partner that
takes on more of my routine each day, on its own initiative, while I stay in
control of where it goes?**

That's the actual product. Memory is just one of the things that makes it
possible.

## What Vepol does for you

**Plans your day.** Each morning Vepol looks at your knowledge base — open
tasks, deadlines, what's overdue, what got done yesterday — and writes you a
short brief: what's actually important today, what to drop, what to push. It
doesn't ask "what do you want to do?" — it tells you what's worth doing,
based on what it has learned about your work and goals.

**Runs your routine in the background.** Tasks marked as low-judgment (`auto:
true`) — drafting follow-up emails, summarizing meeting notes, refreshing
research, updating the registry of projects — Vepol picks up and executes
without waiting for you to start them. By the time you get to your machine,
they're already done.

**Studies you, doesn't just store you.** Standard AI memory is a passive
log. Vepol's memory is **interpreted**. After each session, it pulls out
decisions, lessons, action items, ergonomic patterns ("you're sharper in
the morning," "this kind of task always blocks for two days"). It uses what
it learns to plan better the next day.

**Self-reflects and updates itself.** Once a week, Vepol re-reads its own
strategy — the assumptions it has been making about how to help you — and
rewrites the strategy file if it sees gaps. You see this happen. The file is
right there in your knowledge base.

**Proactive, not reactive.** It doesn't wait for prompts. Morning brief,
evening retro, mid-day reminders, escalations when it can't make progress
without you — all initiated by Vepol, sent through Telegram or whatever
channel you wired up.

**Aligned with your health and goals.** Vepol pulls health data from your
devices (Garmin, Apple Health, scales) and uses it as a constraint, not a
performance metric. If your sleep dropped for three days, the day plan loses
intensity — you don't have to ask. If you're approaching a goal that requires
a sustained pace, Vepol smooths the workload.

**Does part of your work, more each day.** This is the most important part:
**Vepol's autonomy compounds over time.**

- **Day 1:** drafts emails — you proofread and send.
- **Week 2:** classifies routine emails — you only see exceptions.
- **Month 2:** answers typical inquiries through your draft folder — you
  spot-check.
- **Month 6:** half your operational routine runs without you, and you
  spend that time on what only you can do.

The progression is real because Vepol watches what you actually edited vs
accepted, and adjusts the autonomy level per task type accordingly.

## What makes Vepol different — visible discipline

Most "AI assistant" products are black boxes: the model decides something,
remembers something, the output appears in a chat window. You can't audit
it, you can't roll back, you can't trust it for important work because you
can't *see* it.

Vepol works the opposite way. **Every meaningful action leaves a textual
trace in your knowledge base** that you can read, edit, override, or grep
six months later.

### Memory updates itself, in the open

After each supported agent session, Vepol's session-capture pipeline:

1. Reads the full session transcript
2. Extracts decisions / lessons / action items / context shifts
3. Appends them to `<project>/knowledge/daily/YYYY-MM-DD.md`
4. Adds a one-line summary to the project's `log.md`

Then once a day, Vepol re-reads recent dailies and decides what should be
**lifted** from raw chronology into permanent categories (`concepts/`,
`people/`, `companies/`, `solutions/`). You see the lifting happen — you
can object, you can edit, you can roll back.

### The knowledge graph is alive — pages cross-link and the network grows

Vepol's knowledge base is not a flat collection of independent notes. Pages
reference each other through markdown wiki-links: `[[concept]]`,
`[[person]]`, `[[company]]`, `[[solution]]`. When you write about a
project, the project page links to the people involved; people pages
link back to the projects they touched; concepts link to the source
documents that introduced them.

This network grows itself, in two ways:

- **Lifting from chronology.** Daily session captures are scanned for
  recurring entities and ideas. When something appears across multiple
  days — a recurring problem, a person you keep mentioning, a tool that
  came up four times in two weeks — Vepol proposes promoting it from raw
  daily notes into a dedicated page in the appropriate category.
- **Synthesis between existing pages.** Periodically Vepol re-reads
  the corpus and proposes new cross-links: "this concept page and this
  solution page seem to be about the same thing — should they merge?",
  "this person works at this company; the link is missing."

You see every proposal. You accept, edit, or reject. Over time the graph
densifies — a knowledge base that started as a flat set of notes becomes
a richly interconnected network. You can browse it in Obsidian (where the
graph view is built in) or any other tool that reads markdown wiki-links.

This matters for the partnership: when Vepol plans your day or drafts a
response, it doesn't just look at the file you're writing — it traverses
the graph from there, picking up context from connected pages. The
denser the graph, the better its judgments.

### Tasks live in three files, each with one job

The standard knowledge-base layout includes a coordination triad:

- **`backlog.md`** — what needs doing. You add to it; Vepol adds to it.
  Each entry has a status: open, in-progress, done.
- **`escalations.md`** — items where Vepol can't proceed without you.
  Decisions, blocked branches, things that need your judgment. Vepol writes
  here; you read and respond.
- **`incidents.md`** — what broke, what was the root cause, what's the
  fix, what's the prevention rule. Every error becomes an artifact, not a
  fleeting frustration.

This isn't a task-tracker. It's a **protocol for communication between you
and your AI partner**, with one file per kind of message.

### Strategy gets re-examined, automatically

Each project carries a `strategies.md` file with the current working
hypothesis about how Vepol should help you in that project, plus active and
retired hypotheses. Once a week (or after a pivot), Vepol re-reads its log,
checks which assumptions held, and updates the strategy file. You see the
diff. You can revert.

### Plans go through cross-agent review

Before any non-trivial implementation, Vepol writes a specification, has
**an independent configured AI agent** check it, and only proceeds after
concerns are addressed. You never get a one-shot answer for something that
matters — you get something that survived independent scrutiny.

### Every meaningful event → log entry

Not "I did something" in a chat window — a dated, categorized line in the
project's `log.md`. Six months later, you can `grep "decision"` and see every
significant call you made, with context. Your AI partner shares this
chronicle; you both refer to the same record.

## How this differs from other AI assistants

| | Typical AI chatbot | Vepol |
|---|---|---|
| **Memory** | hosted by vendor, opaque to you | in your text files, you can edit |
| **Context across sessions** | usually lost or summarized | survives — agent reads files each time |
| **Tasks** | in your head or an external tracker | in a file the AI partner shares |
| **Decisions and lessons** | dissolve in chat history | auto-extracted into the log |
| **Autonomy** | reactive (answers your prompts) | proactive (initiates work) |
| **Transparency** | "magic" inside the model | every step is text on disk |
| **Quality of plans** | one answer from one model | plan goes through cross-review by independent AI agents |
| **Growth over time** | each chat starts blank | each day, takes on more of your routine |
| **Health/goal alignment** | absent | present (devices feed in; pace adapts) |

## How Vepol stays yours

- Everything runs on **your machine**. There is no Vepol cloud.
- Knowledge files are **plain markdown**. Open in any editor, search with
  grep, view as graph in Obsidian.
- Privacy is enforced by **four layers** before anything gets published —
  pattern matching, allowlist, structural audit, semantic LLM scan. The
  user-overlay folder (`~/knowledge/`) is fundamentally never touched by
  upgrades.
- License is [FSL-1.1-MIT](../LICENSE) — source-available now, automatic
  conversion to MIT in 2 years. Free for personal use, internal company
  use, and consulting work; restricted only against hosted competing
  services.

## Who this is for

- Power users of Claude Code who already write in markdown and want their
  notes to *act*, not just sit there
- Founders, builders, and consultants who can't afford to start every AI
  conversation from scratch
- Engineers who don't trust black-box assistants for important work and
  need an audit trail
- Anyone managing several active projects in parallel where context-switching
  costs are real

## Who this is *not* for

- People who want a managed cloud service — by design, this is your
  local environment
- People who don't already use Claude Code or a similar AI agent —
  Vepol works *through* the agent's interface (Claude Code's macOS
  app, Codex's macOS app, or their respective CLIs); if you're not
  in that flow yet, start there first
- People who prefer their AI to be reactive only — Vepol's whole
  point is initiative

## 60-second summary

Vepol is your second inner voice — an AI partner that plans your day, runs
your routine, studies you, self-reflects, monitors your health, and **takes
on more of your work each day**. Its memory and decisions live as plain
markdown files on your machine, so you can audit, edit, or roll back
anything. Configured AI agents review each other's plans before any significant
change. Free for personal and internal use under FSL-1.1-MIT;
auto-converts to MIT in 2 years.
