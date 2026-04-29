# Vepol

**Your AI partner that grows with you.** Plans your day, runs your routine, studies you, takes on more of your work each day — while you stay in control of every step.

[![License: FSL-1.1-MIT](https://img.shields.io/badge/License-FSL--1.1--MIT-blue.svg)](LICENSE)
[![Source-available](https://img.shields.io/badge/Source-available-orange.svg)](LICENSE-FUTURE.md)
[![Status: alpha](https://img.shields.io/badge/Status-alpha-yellow.svg)](#status)

> 📊 **Quick visual overview:** [docs/visuals/](docs/visuals/) — architecture, license model, methodology infographic, mind map, and briefing doc.
>
> 📖 **Long-form explanation:** [docs/what-is-vepol.md](docs/what-is-vepol.md) — what Vepol actually is, who it's for, who it's not for.

---

## What this actually is

Most "AI memory" tools answer the wrong question. They make a chatbot
remember yesterday and stop there — you still have a slightly smarter chatbot
that waits for you to ask things.

Vepol answers a different question:

> **How do I work with an AI partner that takes on more of my routine
> each day, on its own initiative, while I stay in control of where it
> goes?**

That's the actual product. Memory and a structured knowledge base are
infrastructure that makes it possible. The features below are what runs on
that infrastructure.

## What it does for you

- **Plans your day.** Each morning Vepol reads your knowledge base — open
  tasks, deadlines, what got done yesterday — and writes a short brief.
  Not "what do you want to do?" — "this is what's worth doing today,
  given what I know about your work."
- **Runs your routine in the background.** Tasks marked low-judgment
  (`auto: true`) — drafting follow-ups, refreshing research, updating the
  project registry — Vepol picks up and executes without prompting. By
  the time you sit down, they're done.
- **Studies you, doesn't just store you.** After each session, Vepol
  extracts decisions, lessons, action items, and ergonomic patterns
  ("sharper in the morning," "this kind of task always blocks for two
  days"), and uses them in tomorrow's plan.
- **Self-reflects and updates itself.** Once a week Vepol re-reads its own
  strategy file — assumptions about how to help you — and rewrites it
  if assumptions broke. You see the diff.
- **Proactive, not reactive.** Morning brief, evening retro, mid-day
  reminders, escalations when blocked — all initiated by Vepol over
  Telegram or whatever channel you wired up.
- **Aligned with your health and goals.** Pulls data from Garmin, Apple
  Health, scales — uses it as a constraint on your day plan, not a
  performance metric. If sleep dropped for three days, the plan loses
  intensity automatically.
- **Takes on more of your work each day.** This is the most important part:
  **Vepol's autonomy compounds over time.**
  - Day 1: drafts emails, you proofread and send.
  - Week 2: classifies routine emails, you only see exceptions.
  - Month 2: answers typical inquiries through your draft folder.
  - Month 6: half your operational routine runs without you.

  The progression is real because Vepol watches what you actually edited
  vs accepted, and adjusts autonomy per task type.

## What makes it different — visible discipline

Most AI assistants are black boxes: model decides, output appears, you can't
audit, you can't roll back. Vepol works the opposite way.

**Every meaningful action leaves a textual trace** in your knowledge base
that you can read, edit, override, or `grep` six months later.

- **Memory updates itself, in the open.** After each session, decisions /
  lessons / action items get auto-extracted into `daily/YYYY-MM-DD.md` and
  one-line summaries go into `log.md`. Daily, important items get **lifted**
  into permanent categories (`concepts/`, `people/`, `companies/`,
  `solutions/`). You see every lift; you can object, edit, roll back.
- **Knowledge cross-links and grows.** Pages reference each other through
  markdown wiki-links (`[[concept]]`, `[[person]]`). As you ingest more
  material, Vepol periodically re-reads the corpus, spots recurring
  patterns, and proposes new connections — sometimes lifting a topic
  that keeps coming up into its own page, sometimes noticing that two
  pages you wrote separately are actually about the same thing. The
  graph densifies as you work; you can see it visually in Obsidian or
  any tool that reads markdown links.
- **Tasks live in three files, each with one job.**
  - `backlog.md` — what needs doing (you and Vepol both add)
  - `escalations.md` — items Vepol can't proceed without you (Vepol writes,
    you respond)
  - `incidents.md` — what broke + root cause + fix + prevention rule
    (every error becomes an artefact, not a fleeting frustration)

  This isn't a task tracker. It's a **protocol for communication** between
  you and your AI partner, with one file per kind of message.
- **Strategy gets re-examined.** Each project carries `strategies.md`. Once
  a week Vepol re-reads its own log, checks which assumptions held, updates
  the file. You see the diff.
- **Plans go through cross-agent review.** Before any non-trivial
  implementation, Vepol writes a spec, has another configured AI agent
  check it, and only proceeds after concerns are addressed. You don't
  get one-shot answers for things that matter.
- **Every event → log entry.** Not "I did something" in a chat — a dated
  line in `log.md`. Six months later, `grep "decision"` returns every
  significant call you made, with context.

## How this differs from other AI assistants

| | Typical AI chatbot | Vepol |
|---|---|---|
| **Memory** | hosted by vendor, opaque to you | your text files, you can edit |
| **Context across sessions** | usually lost or summarized | survives — agent reads files each time |
| **Tasks** | in your head or external tracker | in a file the AI partner shares |
| **Decisions and lessons** | dissolve in chat history | auto-extracted into the log |
| **Autonomy** | reactive (answers prompts) | proactive (initiates work) |
| **Transparency** | "magic" inside the model | every step is text on disk |
| **Quality of plans** | one answer from one model | plan goes through cross-review by independent AI agents |
| **Growth over time** | each chat starts blank | each day, takes on more of your routine |
| **Health/goal alignment** | absent | present (devices feed in; pace adapts) |

## Quickstart

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
./install.sh
```

The installer detects what you have (Claude Code, Node, Bun, optionally
Codex), reports what's missing with exact install commands, and sets up
the rest. The Claude Code and Codex macOS apps install their CLI
binaries automatically, so either flow works. The installer does **not**
auto-install package managers — that decision stays with you.

After install, your first 5 minutes:

```bash
kb-doctor              # verify install is healthy
kb-task "first task"   # write your first item
kb-search "first"      # confirm retrieval works
kb-brief               # see what a synthesized brief looks like
```

That's the value loop. Methodology comes after, when you want it.

## Status

**Vepol is in alpha (v0.1.x).** What that means:

- ✅ The knowledge schema is stable and proven on the maintainer's
  daily-driver setup (16+ projects)
- ✅ Daily brief, evening retro, and tick (orchestrator pulse) work
- ✅ Privacy layers (4 of them) are in place and tested
- ⚠️ macOS 13+ only — Linux support is a Phase 2 candidate
- ⚠️ Pro-tier features (cloud-sync, advanced templates) not built yet
- ⚠️ Documentation is still being filled in during active alpha use
- ❌ Breaking changes in any 0.x → 0.(x+1) bump are possible

If you adopt now, expect to participate in shaping the API. We treat your
feedback as design input.

## Architecture in three sentences

1. **Core (this repo)** is universal — schema, scripts, methodology
   docs, install lifecycle. Same for everyone.
2. **User overlay** is in your `~/knowledge/` — your registry, your
   logs, your concepts, your projects. Never publishes anywhere.
3. The boundary is mechanical: a manifest file (`.managed.yaml`) tracks
   which files belong to the repo (overwriteable on upgrade) and which
   belong to you (never touched).

For details, see [`docs/visuals/vepol-architecture.png`](docs/visuals/vepol-architecture.png) (visual) or
the architecture sections in [`docs/what-is-vepol.md`](docs/what-is-vepol.md) (text).

## Methodology pages

Vepol embeds a small set of opinions about how to work with AI agents.
These live in [`docs/methodology/`](docs/methodology/) (added in a later release):

- **Orchestrated knowledge base** — root concept (Karpathy LLM Wiki + 7 extensions)
- **KB authoring discipline** — 8 rules to avoid false-canonical content
- **KB freshness loop** — how reads stay current
- **TRIZ for design** — contradiction → ideal-final-result → separation
- **Spec-driven workflow** — spec → tests → code → tests → revisions
- **Cross-agent review** — Claude ↔ Codex as a quality gate
- **Parallel orchestrators** — single source of truth for many agents

Read them in order if this is your first time. Skip if you just want
the tool.

## Dependencies

| Tool | Required | Why |
|---|---|---|
| macOS 13+ | Yes (v0.1) | launchd, paths, brew defaults |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) (macOS app or CLI) | Yes | Primary orchestrator |
| Node 18+ | Yes | Skills runtime |
| [Bun](https://bun.sh/) 1.0+ | Yes | Performance scripts |
| git, bash 5+, ripgrep | Yes | Scripts |
| [Codex](https://github.com/openai/codex) (macOS app or CLI) | Recommended | Cross-agent review |
| Telegram bot | Optional | Brief / retro channel |
| [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) | Optional | Auto-capture sessions |

The installer checks all of these and tells you exactly what to install.

## License

[FSL-1.1-MIT](LICENSE). Source-available now, MIT in 2 years.

In plain English:

- ✅ Personal use, internal company use, professional services to
  clients, modifications, forks, redistribution
- ❌ Hosted SaaS that competes with Vepol (until 2-year MIT
  conversion)
- 📅 Each release converts to MIT 2 years after its publish date

For details and edge cases, see
[LICENSE-FUTURE.md](LICENSE-FUTURE.md) and
[COMMERCIAL.md](COMMERCIAL.md).

## Funding

If Vepol saves you time, consider sponsoring:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink.svg)](https://github.com/sponsors/nahornyi-ai-lab)

Tiers:

- **$5/mo** — Supporter (helps cover infra costs)
- **$15/mo** — Advanced (early access to Pro module betas)
- **$50/mo** — Priority (we triage your issues first)
- **$250/mo** — Backer (logo in this README)

Or do nothing — the software is yours to use either way.

## Contributing

We accept PRs. Before opening one, please:

1. Read [`docs/methodology/spec-driven-workflow.md`](docs/methodology/spec-driven-workflow.md)
   for non-trivial changes — write the spec before the code
2. For architectural changes, ask for cross-agent review (we will run
   the spec through both Claude and Codex)
3. Use the issue templates in `.github/ISSUE_TEMPLATE/`

See `CONTRIBUTING.md` (when published) for the full process.

## Acknowledgments

- **Andrej Karpathy** for the [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) that gave us the initial pattern
- **Genrich Altshuller** for TRIZ and the substance-field model that gives Vepol its name
- **Sentry** for [FSL](https://fsl.software/) — a license model that's commercial-friendly without being permanently restrictive
- **Anthropic** and **OpenAI** for Claude and Codex respectively — two of the orchestrators Vepol can coordinate

## Reach out

- **Issues:** <https://github.com/nahornyi-ai-lab/vepol/issues>
- **Discussions:** <https://github.com/nahornyi-ai-lab/vepol/discussions>
- **Email:** vadym@nahornyi.ai
- **Security:** see [SECURITY.md](SECURITY.md)
- **Commercial license:** see [COMMERCIAL.md](COMMERCIAL.md)
- **Org:** <https://github.com/nahornyi-ai-lab>
