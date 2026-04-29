# Vepol

**Two agents, one field.** Local AI operating environment for durable knowledge and action.

> **Pronunciation:** Vepol [VEH-pol] — from Russian *Веполь*, the TRIZ
> "substance-field" model: two interacting elements plus a field that
> binds them. In Vepol, you are the first element, your AI agents
> (Claude, Codex, future ones) are the second, and your markdown
> knowledge base is the field. The whole system is the smallest
> functional unit that makes knowledge into action.

[![License: FSL-1.1-MIT](https://img.shields.io/badge/License-FSL--1.1--MIT-blue.svg)](LICENSE)
[![Source-available](https://img.shields.io/badge/Source-available-orange.svg)](LICENSE-FUTURE.md)
[![Status: alpha](https://img.shields.io/badge/Status-alpha-yellow.svg)](#status)

---

## What this is

Vepol is a **personal operating environment** that turns your local
markdown files into a living knowledge base, then layers an active
orchestrator on top. Both Claude Code and Codex CLI work against the
**same** files — there is no separate "Claude memory" and "Codex
memory." They are interchangeable interfaces over one source of truth.

Concretely, after a one-line install you get:

- A structured knowledge base (`~/knowledge/`) with conventions for
  state, logs, backlog, escalations, incidents, and strategies
- Daily briefings every morning, retros every evening (via Telegram or
  any channel)
- Automatic capture of every Claude Code session into your daily log
- Cross-agent review as a default gate for non-trivial changes
- TRIZ-grounded design discipline ("formulate the contradiction first")
- A privacy-aware sync mechanism that lets you publish curated parts
  of your knowledge without leaking the rest

It's opinionated. The opinions are written down in
[`docs/methodology/`](docs/methodology/).

## Who this is for

- Power users of Claude Code who want a **persistent** layer beneath
  their sessions
- Builders who already write things down in markdown but want them to
  *act* — not just sit there
- Small teams who want a shared playbook embedded in code, not in a
  wiki nobody reads
- Anyone who has tried to use AI agents seriously and run into the
  "every session starts blank" problem

## Who this is NOT for

- People who want a polished GUI app — Vepol is CLI + markdown +
  optional Telegram
- People who want a managed cloud service — there isn't one (by design;
  this is *your local* environment)
- People who don't already use Claude Code — Vepol assumes it as the
  primary interface

## Quickstart

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
./install.sh
```

The installer detects what you have (Claude CLI, Node, Bun, optionally
Codex CLI), reports what's missing with exact install commands, and
sets up the rest. It does **not** auto-install package managers.

After install, your first 5 minutes:

```bash
kb-doctor              # verify install is healthy
kb-demo brief          # see a synthesized brief from the demo wiki
kb-task "first task"   # write your first item
kb-search "first"      # see how retrieval works
```

That's the value loop. Methodology comes after.

## Status

**Vepol is in alpha (v0.1.x).** What that means:

- ✅ The core knowledge schema is stable and proven on the maintainer's
  daily-driver setup (16+ projects)
- ✅ Daily brief, evening retro, and tick (orchestrator pulse) work
- ✅ Privacy layers (4 of them) are in place and tested
- ⚠️ macOS 13+ only — Linux support is a Phase 2 candidate
- ⚠️ Pro tier and cloud-sync features are not built yet
- ⚠️ Documentation gaps exist; we will plug them as people hit them
- ❌ Breaking changes in any 0.x → 0.(x+1) bump are possible

If you adopt now, expect to participate in shaping the API. We will
treat your feedback as gold.

## Architecture in three sentences

1. **Core (this repo)** is universal — schema, scripts, methodology
   docs, install lifecycle. Same for everyone.
2. **User overlay** is in your `~/knowledge/` — your registry, your
   logs, your concepts, your projects. Never publishes anywhere.
3. The boundary is mechanical: a manifest file (`.managed.yaml`) tracks
   which files belong to the repo (overwriteable on upgrade) and which
   belong to you (never touched).

For details, see [`docs/architecture.md`](docs/architecture.md) once
populated.

## Methodology pages

Vepol embeds a small set of opinions about how to work with AI agents.
These live in [`docs/methodology/`](docs/methodology/):

- **Orchestrated knowledge base** — root concept (Karpathy LLM Wiki + 7 extensions)
- **KB authoring discipline** — 8 rules to avoid false-canonical content
- **KB freshness loop** — how reads stay current
- **TRIZ for design** — contradiction → ideal-final-result → separation
- **Spec-driven workflow** — spec → tests → code → tests → revisions
- **Cross-agent review** — Claude ↔ Codex as a quality gate
- **Parallel orchestrators** — single source of truth for two agents

Read them in order if this is your first time. Skip if you just want
the tool.

## Dependencies

| Tool | Required | Why |
|---|---|---|
| macOS 13+ | Yes (v0.1) | launchd, paths, brew defaults |
| [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) | Yes | Primary orchestrator |
| Node 18+ | Yes | Skills runtime |
| [Bun](https://bun.sh/) 1.0+ | Yes | Performance scripts |
| git, bash 5+, ripgrep | Yes | Scripts |
| [Codex CLI](https://github.com/openai/codex) | Recommended | Cross-agent review |
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
- **Anthropic** and **OpenAI** for Claude and Codex respectively, the two orchestrators Vepol coordinates

## Reach out

- **Issues:** <https://github.com/nahornyi-ai-lab/vepol/issues>
- **Discussions:** <https://github.com/nahornyi-ai-lab/vepol/discussions>
- **Email:** vadym@nahornyi.ai
- **Security:** see [SECURITY.md](SECURITY.md)
- **Commercial license:** see [COMMERCIAL.md](COMMERCIAL.md)
- **Org:** <https://github.com/nahornyi-ai-lab>
