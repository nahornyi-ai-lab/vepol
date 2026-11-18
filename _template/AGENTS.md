# {{PROJECT_NAME}} — local wiki schema

> Inherits the master: [`~/knowledge/AGENTS.md`](~/knowledge/AGENTS.md). This file holds only what is specific to this project.

## About the project

_(1–3 sentences: what it is, why it exists, who it is for, what status it is in)_

## Project structure

```
{{PROJECT_SLUG}}/
├── AGENTS.md                # this file (canonical; read by Codex/Claude Code/Antigravity CLI)
├── knowledge/               # the WHOLE project wiki (kept separate from the code)
│   ├── README.md            # short description
│   ├── index.md             # page catalog
│   ├── log.md               # log
│   ├── state.md             # current state
│   ├── raw/                 # immutable sources
│   │   └── assets/          # images
│   ├── sources/             # summaries of raw documents
│   ├── agents/              # one project card: agent-card.md (shared by all runtimes; identity = project role, not vendor)
│   └── <categories>/        # project-specific
└── <code-dirs>/             # project code — siblings of knowledge/
```

## Categories (starter set)

_(list which subfolders of `knowledge/` make sense for this project. Examples:_
- _for a lead-gen project: `icp/`, `offers/`, `channels/`, `funnel/`, `metrics/`, `experiments/`, `agent-specs/`_
- _for a library project: `api/`, `patterns/`, `decisions/`_
- _for a pet experiment: maybe just `sources/` and `experiments/`)_

## Autonomy boundaries

What the agent may do without confirmation, and what only after review.

- **Freely:** create/update pages in `knowledge/`, update `log.md`, `state.md`, `index.md`.
- **With confirmation:** changes in the project's code dirs, new categories in `knowledge/`, deleting pages.
- **Never:** touch `knowledge/raw/`, push to git without being asked, delete other people's files outside `knowledge/`.

## Agent card

The project has **one card per role** (not one per runtime): `knowledge/agents/agent-card.md`. Identity is tied to the project role; Claude Code, Codex, Antigravity CLI and future runtimes all work from the same card. Runtime differences (what Claude can use, what Codex can use, …) live in the card's `## Operating notes` section.

At every new session start — before the first substantive answer or action — the agent must have startup context: the agent card, `knowledge/state.md`, a recent `knowledge/log.md` slice, active work/open escalations, and a compact incident slice. The normal path is the hook-injected `Startup Context Manifest`; when the manifest is present, the slices it lists count as already read, and the agent does not reread `knowledge/index.md`, the full `knowledge/incidents.md`, or the whole `knowledge/backlog.md` just as a formality. If there is no manifest (hook-less runtime), run `~/knowledge/bin/kb-session-start --print --cwd "$PWD"` or read manually: the card along the hierarchy `knowledge/agents/agent-card.md` → `~/knowledge/agents/agent-card.md` → explicit "no card" fallback, `knowledge/state.md`, `tail -n 80 knowledge/log.md` (fallback 160 when there are <3 dated entries), active work via `kb-board`, open escalations, and `## Prevention rules` / `## Ongoing` from `knowledge/incidents.md` when present. `knowledge/index.md` and the full `knowledge/incidents.md` are on-demand navigation/diagnostics, not startup load. A "who are you / introduce yourself" question is not a trigger to read anything: answer from the already-read `## Self-introduction`, not with a generic vendor description. Full schema: [`~/knowledge/AGENTS.md`](~/knowledge/AGENTS.md#session-startup-context).

If the project has no card yet, the agent says so explicitly and offers to create one. The sample is `~/knowledge/_template/knowledge/agents/_example.md` (`new-wiki` copies it to `knowledge/agents/_example.md` automatically). First step: `cp knowledge/agents/_example.md knowledge/agents/agent-card.md`, then fill it in for the project.

## State contract

`knowledge/state.md` is the project's current dashboard, not a log and not an archive. Write it overwrite-only: when reality changes, record the event in `knowledge/log.md` (if it is durable), then replace the stale line in `state.md`. Historical dates, proof, review results, resolved blockers and old snapshots go to `log.md`, `reports/`, `decisions/`, `sources/` or thematic pages. Current deadlines, active offers, metrics, date freshness and `Last Updated` are allowed.

## Owner-approved spec gate

For non-trivial work, the path is mandatory: research -> one lightweight independent spec review -> owner-approved spec -> `knowledge/spec-approvals.md` with exact `spec-contract` hash -> build plan -> RED tests with mandatory E2E path -> implementation. The reviewer reads the relevant code/API and returns `GO`, at most three questions, or a proven logical `BLOCK`. A changed hash alone never triggers another review. The owner can approve in chat; the active agent records the decision as scribe. Material scope drift after approval returns to one lightweight review and owner approval.

## Cross-orchestrator CLI launch

Agents on this machine can launch local CLIs (Claude Code, Codex, Antigravity `agy`, Grok, OpenCode, NotebookLM). The **live roster** — which of them are actually installed here and when to call which — is [`~/knowledge/.active-roster.md`](~/knowledge/.active-roster.md) (this project's copy: `knowledge/.active-roster.md`). `kb-cli-roster` generates it and the SessionStart hook injects it into every Claude/Codex session; orchestrators without the hook read the file themselves. No versions, gitignored. The launch rule is in the hub contract: [`~/knowledge/AGENTS.md`](~/knowledge/AGENTS.md#cross-orchestrator-cli-launch-matrix).

## Project metrics

_(which numbers we measure, where they come from, how often they update → see `knowledge/metrics/` if it exists)_

## Related projects in the hub

_(symlinks to other projects this one overlaps with — update as connections appear)_

## Significant external state changes (entity events)

Any significant change to the project's external state must be recorded in `knowledge/log.md` as a line with a greppable prefix:

```
## [YYYY-MM-DD] <category> | <action> | <project_slug> | <one-line description> [→ <provider>:<external_ref>]
```

- **Categories:** `publish | account | subscription | person | company | asset`
- **Actions:** `created | updated | renamed | deprecated | cancelled | closed | transferred | deleted`
- `<project_slug>` — this project's slug (the one it lives under in `~/knowledge/registry.md`).
- `<provider>:<external_ref>` — optional, but **strongly** recommended when there is a stable external referent (domain/handle/bundle-id/url). It is the key for the deterministic upsert during the hub rollup.

**When to write:**

- `publish` — an artifact is published (App Store / Play Store / npm / pypi / production domain) or unpublished.
- `account` — a new developer account is registered (Apple Dev, Google Play, Cloudflare, Stripe, Vercel, GitHub Org, etc.), an account is closed, ownership is transferred.
- `subscription` — a new paid subscription/SaaS (Holded, MS365, OpenAI API, Linear, etc.), a plan change, a cancellation.
- `person` — a key person appears (client, colleague, broker, fundraising contact), a role changes, exactly one alias merge on `renamed`.
- `company` — client / partner / provider / competitor / target investor.
- `asset` — hardware (Mac/iPhone/watch/scale/router), virtual asset (domain, IP, physical key), key/token (metadata only: provider, scope, location-of-secret-file, rotation-date — **never** the token value).

**Examples:**

```
## [2026-04-22] account | created | <slug-a> | dev-account active → vendor.com:user [at] example.com
## [2026-04-25] publish | created | <slug-a> | v2.1.2 published → store.example.com:com.example.app
## [2026-04-30] subscription | cancelled | <slug-b> | service-name → service.example.com:user [at] example.com
## [2026-05-01] person | renamed | <slug-c> | alias-a ≡ Alias B (alias merge)
## [2026-05-03] asset | created | <slug-b> | device-model → vendor.com:<device-uuid>
```

**Why:** the hub's evening cron (`kb-orchestrator-cycle` retro pass) collects these lines → updates `~/knowledge/personal/assets.md` / `people/<slug>.md` / `companies/<slug>.md`. Without the prefix, the event is not picked up. If the hub keeps a full spec at `~/knowledge/concepts/entity-extraction-cycle-pass.md` (optional; the installer does not ship one), it has the details.
