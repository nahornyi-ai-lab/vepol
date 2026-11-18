# Vepol hub — master contract

## Session startup context

At the start of every new session, before the first substantive answer or action, the agent must have the startup context: agent card, `state.md`, recent `log.md`, active work/open escalations, and a compact incident slice.

The normal path is the `~/knowledge/bin/kb-session-start` hook, which returns a markdown bundle with `## Startup Context Manifest`. If the manifest is already in the input context:

- treat the listed slices as already read;
- do not re-read `knowledge/index.md`, the full `knowledge/incidents.md` or the whole `knowledge/backlog.md` just as a formality;
- use `knowledge/index.md` only on demand, to navigate or find relevant pages;
- open the full `knowledge/incidents.md` only for diagnostics, risky work, or when the startup slice points to an ongoing incident.

If there is no manifest (a hook-less runtime), run `__HOME__/knowledge/bin/kb-session-start --print --cwd "$PWD"` before substantive work. Manual fallback if the script is unavailable: read the agent card following the hierarchy `knowledge/agents/agent-card.md` → `~/knowledge/agents/agent-card.md` → an explicit "no card" fallback; `knowledge/state.md`; the last **80 physical lines** of `knowledge/log.md` (`tail -n 80`; widen to 160 if those 80 lines hold fewer than 3 dated `## [` entries); active work via `kb-board`; open escalations; and only `## Prevention rules` / `## Ongoing` from `knowledge/incidents.md`, if present.

A "who are you / introduce yourself" question is not a trigger to read the card or the log: by then the startup context must already be loaded. The number 80 comes from a local measurement of 24 real project logs: `tail -20` gives a median of 8 recent events, `tail -40` gives 14, `tail -80` gives 20; `tail -120/160` noticeably bloats the context without a proportional benefit.

This is the central hub of the personal knowledge base (a "second brain"). The pattern is [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): the LLM incrementally builds and maintains a linked set of markdown files; the human curates the sources and asks the questions.

## Telegram messaging — mention placement (hard rule)

A Telegram user mention token (`at` sign + bot username, for example `user_<role>_bot`) goes **only at the end of the message**, after the full context. Never at the start or in the middle. Reason: Telegram splits long messages → if the mention token is in the first chunk, the bot triggers before the context from the later chunks arrives, and works on partial context (incident 2026-05-16). When you only mention an agent in a plan or discussion without calling it, write the name without the trigger token ("project-bot", "hub", "family"). **The rule also applies to the supervisor prefix:** `_kb_multibot/reply.py::append_user_mention()` now puts the trigger user's mention token at the end of the reply, not at the start (fix 2026-05-17, incident `supervisor-prefix-half-fix`).

## Architecture

Three layers:

1. **Raw sources** — immutable sources (articles, exports, transcripts, PDFs, images). The LLM reads them and never changes them.
2. **Wiki (knowledge)** — markdown that the LLM writes and maintains.
   - **Local project wiki**: `<project>/knowledge/` — physically lives inside the project, next to the project's code.
   - **Global hub categories**: `~/knowledge/{concepts,people,companies,solutions}/` — whatever cuts across projects.
3. **Schema (Universal Agent Entrypoint, 2026-05-19; Antigravity CLI rollout 2026-05-21)** — the rules:
   - **Canonical, vendor-neutral**: `~/knowledge/AGENTS.md` (this file) — the hub-level contract; `<project>/AGENTS.md` — a project overlay with project-specific rules. The full policy lives here, not in runtime files.
   - **Adapter files (thin, ≤ 30 lines)**: `CLAUDE.md` (Claude Code — only the hub keeps one, `~/knowledge/CLAUDE.md`; Claude Code 2.1.277+ reads a project's `AGENTS.md` natively when no `CLAUDE.md` or `CLAUDE.local.md` sits in the project or a folder above it, so `new-wiki` creates no project `CLAUDE.md`), `.github/copilot-instructions.md` (Copilot), `.cursor/rules/*.mdc` (Cursor), `.windsurf/rules/*.md` (Windsurf), `.clinerules/` (Cline), `.aider.conf.yml` (Aider, via `read: AGENTS.md`). Each one is a bootloader that only points to the canonical `AGENTS.md` and holds **only** runtime-specific caveats. Not a separate policy. **Antigravity CLI (`agy`)** reads the project `AGENTS.md` natively when started with `--add-dir <path>` (verified 2026-05-22 by a marker test: agy v1.0.0 with `--add-dir` pre-loads both `AGENTS.md` and `GEMINI.md` from the given directory into the system prompt via cascadeManager; without `--add-dir` the workspace is ignored and only the global `~/.gemini/GEMINI.md` loads). For convenience there is a shell function `agy-here() { __HOME__/.local/bin/agy --add-dir "$PWD" "$@"; }` in `~/.zshrc`. A project `GEMINI.md` adapter is redundant (the canonical AGENTS.md loads the same way); removed 2026-05-21.
   - **Identity layer (a separate artifact)**: `<project>/knowledge/agents/agent-card.md` — the project's role card. It does not replace AGENTS.md; it complements it.
   - **Full specification** of the rollout — `example-project/knowledge/decisions/universal-agent-entrypoint-2026-05-19.md` + `universal-agent-entrypoint-rollout-spec.md`. Rolled out 2026-05-19. Migration from Gemini CLI to Antigravity CLI (`agy`) — `example-project/knowledge/decisions/antigravity-cli-migration-2026-05-21.md` (Gemini CLI free/Pro/Ultra deprecated by 2026-06-18). Guard — `kb-doctor agent-entrypoint --strict`.

## Hub structure

```
~/knowledge/
├── AGENTS.md          # master contract (this file)
├── registry.md        # registry of all projects with paths and status
├── index.md           # global topic index
├── log.md             # global activity log
├── raw/               # hub-level sources (not tied to a project)
├── concepts/          # cross-project concepts (outreach, pricing, UX, patterns…)
├── people/            # people who show up across projects
├── companies/         # clients, partners, competitors
├── solutions/         # "interesting solutions": snippets, finds, reusable pieces
├── projects/          # SYMLINKS to each project's knowledge/
│   └── <slug> → /absolute/path/to/<project>/knowledge
├── _template/         # template for a new project
└── bin/
    ├── new-wiki       # script: bootstrap a wiki in a new project
    └── kb-search      # script: ripgrep across the whole knowledge base
```

## Local project wiki structure

**The whole project wiki lives in one subfolder, `<project>/knowledge/`**, separate from the code. This lets the hub symlink point only at `knowledge/` without dragging in `node_modules`, `.git` and the rest.

```
<project>/
├── AGENTS.md                # local schema (inherits ~/knowledge/AGENTS.md); Claude Code, Codex and agy read it directly
├── knowledge/               # ALL wiki content — isolated from the code
│   ├── README.md            # 1–2 sentences: what this is, what state it is in
│   ├── index.md             # page catalog
│   ├── log.md               # project log
│   ├── state.md             # current state
│   ├── backlog.md           # tasks from the hub/owner — the project executes them
│   ├── escalations.md       # the project's asks upward (to the hub/owner)
│   ├── incidents.md         # errors, root cause, fixes, prevention rules, automations
│   ├── strategies.md        # strategy + active hypotheses + project principles (updated by the agent)
│   ├── raw/                 # immutable sources
│   │   └── assets/          # images (Obsidian Web Clipper)
│   ├── sources/             # a summary for each raw document
│   ├── agents/              # one project card: agent-card.md (shared by Claude Code / Codex / Antigravity CLI / any future runtime; identity is tied to the project role, not the vendor)
│   └── <categories>/        # project-specific: icp/, offers/, channels/, …
└── <code-dirs>/             # site/, … — project code, kept as siblings of knowledge/
```

**`backlog.md` / `escalations.md` / `incidents.md`** — the mandatory coordination triad. The master description of the format and of the rules that tell them apart lives in this `AGENTS.md`; runtime-native files (`CLAUDE.md` and others) are only adapters to it.

### Task board protocol

`backlog.md` is the task board and the only task-state source of truth. It uses multiline `kb-board` task blocks under exact status sections:

`Backlog` → `Ready` → `In Progress` → `Review` → `Done`, with side states `Blocked` and `Cancelled`.

Rules:

- Use `~/knowledge/bin/kb-board` for all task mutations. Do not manually edit task status/claim fields.
- Legacy `kb-backlog` is read/legacy-only after migration and fail-fast exits for mutations on multiline boards.
- Claiming a task moves `Ready` to `In Progress` and mints `claim_owner`, `claim_id`, `claim_expires_at`.
- Long work must heartbeat about every 5 minutes: `kb-board heartbeat <backlog.md> --plan-item-id <id> --claim-id <claim_id> --actor <agent>`.
- Finish through `Review`: `request-review` preserves claim provenance; `close` checks the same `claim_id`.
- `Review` is the testing/verification state; do not create separate `Testing` or `Verification` sections.
- Run `kb-board check <backlog.md>` before ending substantive board work.

### Owner-approved spec gate

For non-trivial work, the path is mandatory: research -> one lightweight independent spec review -> owner-approved spec -> `knowledge/spec-approvals.md` with exact `spec-contract` hash -> build plan -> RED tests with mandatory E2E path -> implementation. The reviewer reads the relevant code/API and returns `GO`, at most three questions, or a proven logical `BLOCK`. A changed hash alone never triggers another review. The owner can approve in chat; the active agent records the decision as scribe. Material scenario drift after approval returns to one lightweight review and owner approval.

**`strategies.md`** — "where we are heading and why" + testable hypotheses about the agent's own work. The project updates it itself (not the hub): once a week via the `agent-review` skill (once that skill exists), or on a significant pivot. Format — in `_template/knowledge/strategies.md`. Log convention for strategy/hypotheses/experiments: `## [YYYY-MM-DD] strategy | <project> | ...`, `## [YYYY-MM-DD] hypothesis | <project> | ...`, `## [YYYY-MM-DD] experiment | <project> | start|result | ...`.

**`agents/`** — the project's role card. The full schema, the file name, session-start behavior, the project→baseline→generic hierarchy and the multi-orchestrator edit protocol are in the ["Agent self-identification"](#agent-self-identification) section below. Short version: **one `agent-card.md` file per project**, identity is tied to the role (not the runtime), and runtime differences (Claude Code / Codex / Antigravity CLI) live in the `## Operating notes` section inside the card.

### State contract

`state.md` is the project's current dashboard, not a log and not an archive. It answers one question: **where are we now?**

- Write in the present tense, overwrite-only: when reality changes, replace the outdated line.
- Historical dates, `since`, `fixed`, `shipped`, test proof, review result, incident narrative, resolved blockers and old snapshots go to `log.md`, `reports/`, `decisions/`, `strategies.md`, `sources/`, or entity pages.
- Current dates are allowed for `Last Updated`, active deadlines, active offers, metric timestamps, and source freshness.
- State edit rule: first record the event in `log.md` when it matters, then leave only the current truth in `state.md`.

**Key rule**: everything the LLM writes or reads as "knowledge" lives inside `knowledge/`. Everything that is working code, content or an artifact sits next to `knowledge/` as a sibling.

**Why you must not mix them**: through the symlinks, the hub's Obsidian vault sees exactly `knowledge/`. If wiki files are scattered outside this folder, Obsidian will not see them (or will see them together with `node_modules`).

## Universal Agent Entrypoint

The canonical contract was adopted on 2026-05-19 (`example-project/knowledge/decisions/universal-agent-entrypoint-2026-05-19.md`, cross-reviewed by Codex/Claude/Gemini); its rollout is documented alongside it (`...-rollout-spec.md`, `...-implementation-plan-2026-05-19.md`). This section is the machine-wide master wording.

### Canonical vs adapter

- **Canonical** = `AGENTS.md` (hub + project). Vendor-neutral, holds **all** of the shared policy. Every runtime reads it and follows it.
- **Adapter** = a runtime-native file (`CLAUDE.md`, `.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, `.windsurf/rules/*.md`, `.clinerules/`, `.aider.conf.yml`, …). A thin bootloader: it points to the canonical `AGENTS.md` and contains **only** runtime-specific caveats. **Not** a separate policy and **not** a copy of AGENTS.md.
- **Antigravity CLI (`agy`)** — no project-level adapter is needed: the canonical `AGENTS.md` loads natively via `agy --add-dir <path>` (verified 2026-05-22). The standard launch is the `agy-here` shell function = `agy --add-dir "$PWD"`. The global `~/.gemini/GEMINI.md` stays as a fallback for launches without `--add-dir`.

### Adapter contract

An adapter is valid only if:

- It exists because the runtime has a native instruction-file convention.
- It points to (or imports) the relevant canonical `AGENTS.md`.
- It contains **only** runtime-specific caveats.
- It does not duplicate large blocks of policy from AGENTS.md.
- **≤ 30 non-empty lines.** A hard cap, with no escape hatch.

Required adapters right now: only the hub's `~/knowledge/CLAUDE.md` (installed by `install.sh`; it imports `AGENTS.md`). A project needs no Claude Code adapter: Claude Code 2.1.277+ reads the project `AGENTS.md` natively when no `CLAUDE.md` or `CLAUDE.local.md` sits in the project or a folder above it, so `new-wiki` stopped creating a project `CLAUDE.md` on 2026-10-01. On an older Claude Code, copy `~/knowledge/_template/CLAUDE.md` into the project and put the project name in its title. Optional ones (created only when the matching runtime is actually used in the project): Copilot / Cursor / Windsurf / Cline / Aider — see the list above. **Antigravity CLI (`agy`)** needs no project-level adapter — it reads the project `AGENTS.md` natively via `agy --add-dir <path>` (canonical). The legacy `GEMINI.md` adapter was removed on 2026-05-21 (Gemini CLI free/Pro/Ultra deprecated by 2026-06-18; agy inherited the GEMINI.md loader, but duplicating it when AGENTS.md exists makes no sense).

### Precedence (6 levels)

When instructions conflict, the more local one wins, except where that would break safety, KB write-back discipline, or an explicit user direction:

1. Explicit user instruction for the current task.
2. Nearest subdirectory `AGENTS.md`.
3. Project root `AGENTS.md`.
4. Hub `~/knowledge/AGENTS.md`.
5. Runtime adapter caveats (`CLAUDE.md`, …).
6. Personal/global vendor defaults (`~/.claude/CLAUDE.md`, `~/.config/codex/AGENTS.md`, `~/.gemini/GEMINI.md` for Antigravity CLI, etc.).

**KB wins**: durable KB facts (`~/knowledge/`, `<project>/knowledge/`) **always** win over transient runtime memory. If something recalled from runtime memory conflicts with what the files say, trust the files and update or delete the stale memory.

### Clean-session probe for a new runtime

Before connecting a new runtime/CLI to a project, run the probe from the project's cwd:

```text
Before doing any work, answer in one paragraph:
1. What is the durable source of truth?
2. Which project instruction file is canonical?
3. Where do you write durable outcomes before stopping?
4. What should you do if your runtime memory conflicts with the KB?
```

Acceptance: the answer must contain all of these substrings:

- hub `~/knowledge/`
- project `knowledge/`
- `AGENTS.md`
- one durable write-back point — `log.md`, `backlog.md` or `incidents.md`
- the literal `KB wins`

If the runtime is not installed — a `backlog.md` follow-up. If it is installed and fails — an incident in `incidents.md`, and **the rollout does not count as complete**.

### Onboarding a new runtime

1. Find the native instruction mechanism in the runtime's official documentation.
2. Create a thin adapter under the contract above **or** configure the runtime to read `AGENTS.md` directly.
3. Add a row to the KB adapter registry (see `~/knowledge/concepts/`, if one is registered).
4. Run the clean-session probe.
5. Record the result in the project's `log.md`.

### Guard

`kb-doctor agent-entrypoint --strict` is a deterministic lint check of the hub. It verifies that:

- The hub `~/knowledge/AGENTS.md` (P0 when missing) and `~/knowledge/_template/AGENTS.md` exist.
- The one required adapter, the hub `~/knowledge/CLAUDE.md`, exists. Other adapters it finds (`~/knowledge/_template/CLAUDE.md`, a legacy `GEMINI.md`) are checked the same way when present.
- Each adapter is ≤ 30 non-empty lines (the cap keeps policy from being duplicated into it) and references the canonical `AGENTS.md`.
- There are no bare `@` tokens in the hub or template `AGENTS.md`, which Antigravity CLI loads — a bare at-sign + identifier is interpreted as a file import.
- `new-wiki` and `kb-bootstrap-manifest` still carry `AGENTS.md` into new projects and the install manifest.

Run it after changing a contract, an adapter or a template. Exit code: 2 on any P0; with `--strict`, 1 on any P1. **Any fresh P0/P1 blocks the merge / the `rollout completed` entry in log.md.**

### Failure modes

| Scenario | Symptom | Mitigation |
|----------|---------|-----------|
| Adapter drift | The runtime file grows into a separate policy | `kb-doctor agent-entrypoint`: adapter-line-cap + content-check |
| Double-load | `CLAUDE.md` and `AGENTS.md` duplicate the same long rules | Adapter contract: no duplication; policy lives only in AGENTS.md |
| Missing hub master | Project files reference `~/knowledge/AGENTS.md`, but it does not exist | Hub AGENTS.md created 2026-05-19; doctor checks that it exists |
| Antigravity at-sign import false positive | A bare at-sign + identifier in `~/.gemini/GEMINI.md` or in any file that `agy` reads is interpreted as a file import (inherited from Gemini CLI) | doctor: regex for bare at-sign tokens in the hub and template `AGENTS.md` (code spans included); reword, or escape as `` `@`-mention `` |
| Antigravity skips workspace context | `agy` started without `--add-dir` → the workspace `AGENTS.md`/`GEMINI.md` is ignored (verified 2026-05-22, `workspaceDirs=[]` in the log) | Always launch through `agy-here` (alias for `agy --add-dir "$PWD"`); the canonical hub is reachable through the `~/.gemini/GEMINI.md` import as a fallback |
| Seed/install drift | Live hub is fine, but fresh installs get the old `CLAUDE.md`-centric schema | `~/knowledge/_template/`, the Vepol repo's `_template/`, `install.sh`, `new-wiki`, `kb-bootstrap-manifest` — all covered by tests |
| Silent non-loading | The runtime supports AGENTS.md only in some modes/versions | clean-session probe at onboarding; incident on failure |
| Precedence ambiguity | Nested files or global memory conflict with project rules | The six precedence levels above; KB wins in a conflict with runtime memory |

## Parallel orchestration

The hub allows **several orchestrators at once**: Claude Code, Codex, Antigravity CLI (`agy`) and future CLI agents work not as separate "minds" but as different interfaces to **one and the same** knowledge system.

Hard rules follow from this:

- There is no separate memory per orchestrator. There is always one source of truth: `~/knowledge/` and the project `knowledge/` folders.
- Before working, every agent uses the same startup bundle that `kb-session-start` builds: agent card, project state, recent log, active work/open escalations, compact prevention/ongoing incident slice, and the CLI roster/recent daily when available. If the bundle already came with a `Startup Context Manifest`, these slices count as read; `index.md` and the full `incidents.md` are opened on demand.
- After significant work, every agent must leave a trace in the same system: `log.md` for events and decisions, `state.md` for a changed status, topic pages for new knowledge, `incidents.md` for breakages and manual workarounds.
- If a tool has no automatic SessionStart/SessionEnd hooks, the agent makes up for it by hand. Missing automation does not excuse anyone from memory discipline.
- The goal is **zero split-brain**: any second orchestrator must be able to continue the work from the files alone, without access to the previous chat.

## Cross-Orchestrator CLI Launch Matrix

Every project agent on this machine must know that Vepol can already launch local CLI tools: Claude Code, Codex, Antigravity CLI (`agy`), OpenCode, Grok and NotebookLM. Before answering "I can't launch another agent/tool", the agent must open the live roster `~/knowledge/.active-roster.md` (see below), check the local binary with a smoke probe, and pick a suitable launcher using the rule below. If this hub also keeps a local launch matrix at `~/knowledge/solutions/cli-agent-runtime-launch.md` (optional; the installer does not ship one), read it for the exact invocations and flags.

Short rule: Claude Code — MCP/skills/project execution; Codex — adversarial review/code diagnosis; Antigravity — Gemini-family independent pass with `--add-dir`; Grok CLI — canonical current/social/X/Reddit research pass and explicit Grok pass; OpenCode — non-canonical fallback/legacy surface only; NotebookLM — production recap/audio/artifacts after synthesis. For delegated research, the prompt must require durable write-back to `knowledge/sources/` or `knowledge/reports/`, rather than returning the knowledge only in the chat.

**Live CLI roster (per machine).** Which of these tools are actually installed on THIS machine, and when to call which, is in the auto-generated file `knowledge/.active-roster.md` (for the hub, `~/knowledge/.active-roster.md`). `kb-cli-roster` builds it from the declarative registry `~/knowledge/.orchestrator/cli-tools.tsv` and injects it into every Claude/Codex session through the SessionStart hook. Orchestrators without the hook (agy and others) read `.active-roster.md` directly at startup. The file is not tracked by git (ignored under `knowledge/`), so there is no git churn. Adding a future CLI = one line in the registry. Exact invocations/flags — in the local launch matrix above, when it exists.

## Agent self-identification

An "agent card" is one Markdown page that describes the **project's role**: what I do here, what I specialize in, which skills I have, whom I call as subagents, and what I don't do. At the start of every new session, any orchestrator must find and read the card following the hierarchy below, before the first substantive answer. This is not a lazy action triggered by a "who are you / introduce yourself" question: such a question only reuses the card's already-read `## Self-introduction` instead of the vendor's generic description.

`agent-card.md` is the full, startup-loaded passport of the project's role. Do not deliberately trim it during normal work. Generic process policy belongs in `AGENTS.md`; the card contains project-specific identity, scope, boundaries, skills, subagents, and runtime deltas. `inherits: hub-baseline@<version>` is a provenance/policy pointer, not runtime merge semantics: if project card exists, it still must stand alone.

This section is the single canonical convention for every project on the machine.

### Where the card lives

```
<project>/knowledge/agents/agent-card.md   # fixed name
```

- **One card per project, not one per runtime.** Identity is tied to the role in the project; there can be several executors (Claude Code, Codex, Antigravity CLI, any future runtime).
- Runtime differences, if they matter, go into `## Operating notes` inside the card. No separate per-runtime files.
- The project's `index.md` gets an `## Agents` section with one link to `agents/agent-card.md`.
- The project's `AGENTS.md` **does not duplicate** the card — it gives one or two sentences and links to it.

### Frontmatter (required fields)

| Field | Type | Purpose |
|------|-----|-----------|
| `schema_version` | string | card schema marker for new cards, currently `agent-card/v1` |
| `inherits` | string | provenance/policy pointer in the form `hub-baseline@<version>` (for example, hub-baseline version 0.4.0); not runtime merge |
| `name` | string (slug) | project/role id in `knowledge/agents/`, lowercase-kebab, matches `<slug>` or `<slug>-<role>` |
| `display_name` | string | human-readable role name ("example-project orchestrator", not "Claude Code in example-project") |
| `version` | string | card semver; **bump patch on any frontmatter edit** |
| `description` | string | **routing trigger**, starts with a verb ("Use proactively when…"). It is not a label. |
| `role` | string | position in the team (one sentence) |
| `goal` | string | what we are achieving (one sentence) |
| `boundaries` | string[] | what it does **not** do (explicit boundaries) |
| `skills` | array | `id` / `name` / `description` / `tags` — discrete capabilities |
| `subagents` | array | `name` / `purpose` — whom we call (the runtime-specific roster goes in Operating notes) |
| `tools` | string[] | tools the role relies on |

Optional (for future A2A exportability): `provider.organization`, `provider.url`, `url`, `documentation_url`, `capabilities.*`, `security_schemes`, `default_input_modes`, `default_output_modes`.

### Body (required sections, exact-match headings)

```markdown
# <display_name>

## Self-introduction
One or two first-person sentences: "I am <role>. I work on <goal>." After the mandatory startup read of the card, this text is the canonical self-introduction, including for an explicit "who are you?" question. State explicitly: "there is one card, there can be several executors; runtime differences are in Operating notes".

## Specialization
3-7 lines: what the agent specializes in **in this project specifically** (not in general). What sets the work here apart from work in other projects on the machine.

## Skills
Expands `frontmatter.skills` — one paragraph per skill: trigger, action, result.

## Subagents
Whom we call and what for. Mirrors `frontmatter.subagents`. The runtime-specific roster goes in Operating notes.

## Boundaries
Expands `frontmatter.boundaries` — why exactly these boundaries and what to do instead.

## Operating notes
Optional. Where state/log/incidents live, project habits, **runtime-specific notes** (what is available to Claude Code, what to Codex, what to Antigravity CLI). If there is nothing to say, omit the section.
```

Contract: a section heading is exactly `## <Name>`, with no suffixes ("(detailed)", "(opt.)"). Notes about a section being optional go in the body, not in the heading. Lint test: `^## (Self-introduction|Specialization|Skills|Subagents|Boundaries)$`.

### Session-start hierarchy (project → baseline → generic)

1. `<project>/knowledge/agents/agent-card.md` — project level, **wins**.
2. `~/knowledge/agents/agent-card.md` — the machine baseline (fallback). _Optional, may be absent._
3. If neither exists — the vendor's generic description **with an explicit note**: "There is no agent card in this project. Create one?".

The policy is **replace, not merge**: if a project-level card exists, the baseline is not mixed in. Merge semantics — future.

### Multi-orchestrator edit protocol

Only agents edit the card (through an `@`-mention of the matching bot in Telegram; the human does not edit the file by hand). Rules:

1. **Append/patch scope.** An edit is targeted (one skill, one boundary, one field). Not a full rewrite.
2. **Version bump.** On **any** frontmatter edit, increment `version` (semver patch). This makes a conflict detectable in a diff.
3. **Conflict resolution.** If two orchestrators edit at the same time and the file shows a conflict, nobody overwrites it silently. The conflict is recorded in `knowledge/incidents.md` as the line `agent-card conflict: <runtime>, <date>, <fields>`; the resolution is worked out with a human or escalated to `escalations.md`.
4. **Ownership.** The first version has no formal ownership: any orchestrator may edit the card. Pin down "Codex owns X, Claude owns Y" only when real conflicts appear, not before.

### Startup enforcement

Reading `agent-card.md` at startup is a mandatory startup contract, not a troubleshooting escalation. Runtimes with a SessionStart hook must put the card they find into the system context before the first turn. Runtimes without a hook must read the card directly at the start of the session, before answering the user or doing the task. A "who are you / introduce yourself" question must never be the first time the card is loaded: by then it must already be read, or the missing card must be explicitly recorded.

### Failure modes

| Scenario | Symptom | Mitigation |
|----------|---------|-----------|
| Card is missing | Identity drift | At startup the agent says explicitly "there is no agent card, create one?" |
| `description` is a label, not a trigger | Auto-delegation does not work | Lint `kb-doctor agent-cards` (future): check that `description` starts with a verb |
| Card duplicates `AGENTS.md` | Drift between two sources | `AGENTS.md` links to the card and does not duplicate it |
| Card copies generic policy instead of project identity | Card bloat, stale duplicated rules | Replace copied policy with a link or `inherits`; keep only project-specific meaning |
| Per-runtime files (legacy) | Split-brain between Claude and Codex | Merge into `agent-card.md`, delete the old files, version bump, entry in `log.md` |
| Card tied to a vendor in `display_name` ("Codex — X") | Identity breaks when the runtime changes | `display_name` = the project role; the vendor only in `## Operating notes` |
| Frontmatter breaks YAML | The card cannot be read | `python -c "import yaml; yaml.safe_load(open('....md').read().split('---')[1])"` |

### When to create a card

- New project via `new-wiki` → `knowledge/agents/_example.md` is created automatically. The first agent at session start sees "no card" → copies `_example.md` → `agent-card.md`, fills it in for the project, and saves it in the wiki.
- Existing project without a card → at the first substantive task the agent asks: "Create `agent-card.md` now?". If yes, it fills it in; if no, it notes this in `backlog.md`.

## Development Loop

One process for **any** agent (Claude Code / Codex / Antigravity / any future one) doing new development. The canon is [`docs/methodology/development-loop.md`](https://github.com/nahornyi-ai-lab/vepol/blob/main/docs/methodology/development-loop.md) in the Vepol repo; here is the compact version that agents follow natively from this file. The Claude skill `development-loop` is a thin adapter for the same process.

0. **Scope + Definition of Done.** Classify the work and write down what "done" means (acceptance + how we will check it). *Trivial* (typo/doc, dependency bump, one file, blast radius=0) → skip phases 1 and 4, add the line `research | skipped | trivial` to `log.md`, but still verify. **Never trivial, whatever the diff size:** security/auth, licensing, migrations/data deletion, install scripts and hooks, task-board/scheduler logic, user-facing behavior, public docs/artifacts that affect install/usage/contract/claims/methodology (pure doc typo fixes are trivial-eligible). *Non-trivial* (>~30 min, a new feature/dependency/infra, cross-subsystem, hard to roll back, or on the never-trivial list) → the full loop.
1. **Research-first (reuse-or-build).** Find what already exists to reuse or copy (KB, other projects, the world). Fan out to agents **only for truly independent questions** (`grok` when you need current X/Reddit). Record: `candidates / decision: reuse|adapt|build / why`. Do not build what already exists.
2. **Design.** Full TRIZ (contradiction → ideal final result → resolution, `triz-for-design.md`) only for material decisions or an explicit trade-off conflict found in research; otherwise a light "2–3 alternatives + why this one" block. Artificial "contradictions" just to tick a box are an anti-pattern.
3. **Specification** before code → `knowledge/decisions/`, with acceptance, failure modes, a mandatory E2E and a list of the code/API/schema files that were read (`spec-driven-workflow.md`).
4. **Lightweight spec review — exactly one independent reviewer, one pass, before owner approval.** The reviewer must read the spec and the real code/API it relates to. The reviewer checks only: whether the stated path is feasible, whether the parameters match, the choice between existing addresses/paths, and undefined branches of the current scenario. Format: `GO / QUESTIONS / BLOCK`; at most three questions. `BLOCK` is allowed only for a direct, provable logical incompatibility, cited as `file:line`, that makes the scenario impossible. Do not expand the scope with security hardening, observability, scaling, rollback, future scenarios, style, documentation or extra tests unless they are part of the stated scope. After `GO`, or after the author answers the `QUESTIONS`, a repeat review is forbidden: a new hash by itself invalidates nothing. After a genuine `BLOCK`, one delta check of only the original item is allowed (`RESOLVED / STILL BLOCKED`), with no new findings. Reviewer unavailable → record the attempt and hand the decision to the owner; do not start a cascade of replacement reviewers.
5. **Tests → implementation.** Red → green → revisions. Small, verifiable steps. Empty or failed output = failure, not "no result".
6. **KB write-back to files, not to memory.** decision/spec → `knowledge/decisions/`; facts → `sources/`/`concepts/`/`solutions/`/`state.md`/`strategies.md`; a line → `log.md`. Durable pages created before phase 7 passes get `status: draft`, switched to `stable` at close (append-only traces in log/backlog/incidents carry no marker).
7. **Verify + close.** The author builds an acceptance matrix: each criterion → reproducible evidence → verdict. Runtime behavior (installer/hook/scheduler/UX) is checked with a live smoke, not only unit/lint. Then `kb-doctor` (no fresh P0/P1) and `kb-board close ... --claim-id`. Evidence comes before claiming "done".
8. **Showcase.** Shipped material work with user-visible value → a NotebookLM video recap ("what / why / how to apply it") as raw material for social media (TikTok, YouTube). Deliverable = notebook/artifact ID; do not download it locally; the human does the posting. Internal plumbing → `showcase | skipped | internal` in `log.md`.

**Incidents teach the loop:** an `incidents.md` entry about broken shipped work must contain `loop-phase-failed: <0…8>`, why the spec/lightweight review/tests/verification missed the defect, and a prevention rule. If one phase fails twice → fix the loop itself.

**Task-board trigger (enforcement for non-Claude runtimes):** before moving a task to `In Progress`, the agent must make sure the spec exists in `knowledge/decisions/`, has passed exactly one lightweight independent review and has owner approval; otherwise the first subtask is to write the spec. Launch `agy` as `agy --add-dir "$PWD"` so that it reads the project `AGENTS.md`. Deterministic guards (`kb-board`/`kb-doctor dev-loop-audit`) are a separate tracked task; until they exist, the rules are enforced by instruction and by the owner.

## Operations

### Ingest — add a new source

1. Read the source in full.
2. Discuss the key takeaways (not silently).
3. Write a summary to `knowledge/sources/<slug>.md` with frontmatter:
   ```yaml
   ---
   title: "..."
   source: "url or path to raw/"
   date_ingested: 2026-04-13
   type: article|paper|transcript|dataset|image|conversation
   tags: [...]
   ---
   ```
4. Update the relevant pages (entities, concepts, state). One source usually touches 5–15 pages.
5. If the source concerns several projects → also update the hub (`~/knowledge/concepts/`, `companies/`, etc.).
6. Add a line to `knowledge/log.md` (local + hub, if cross-project).
7. Update `knowledge/index.md` if a new page appeared.

### Query — answer a question

1. Read `index.md` (the local one first, then the hub's if the question is cross-project).
2. You can use `~/knowledge/bin/kb-search "<query>"` for a fast ripgrep across the whole base.
3. Go through the pages found, read the relevant ones, check their "Sources" section for staleness.
4. Answer with citations (`[[wiki-link]]` or path + anchor).
5. **If the answer is valuable, file it back into the wiki** as a new page (comparison, synthesis, analysis). Do not let knowledge disappear into chat history.
6. Update `log.md`.

### Lint — periodic health check

On the user's command ("lint the wiki"):

- Find contradictions between pages.
- Find orphan pages (no incoming links).
- Find concepts that are mentioned but have no page of their own.
- Find outdated claims.
- Suggest research questions and missing sources.
- Write the report to `log.md` as a `lint` entry.

## Log format

Every entry starts with the same prefix — the log must be grep-friendly:

```
## [2026-04-13] ingest | <slug> | "Karpathy LLM Wiki gist"
## [2026-04-13] query | <slug> | "how to measure outreach conversion"
## [2026-04-13] experiment | <slug> | start | "Cold email v2 with case studies"
## [2026-04-13] experiment | <slug> | result | "Cold email v2: reply rate 4.2% (was 1.8%)"
## [2026-04-13] lint | <slug> | "3 orphan pages, 1 contradiction"
## [2026-04-13] hub | hub | "Created the ~/knowledge hub"
```

Quick view: `grep "^## \[" ~/knowledge/log.md | tail -20`

## Project registry

`~/knowledge/registry.md` is the single source of truth about **which projects exist and where they live**. The fields of each entry:

- slug (kebab-case, used in symlinks)
- absolute path
- wiki status: `live` / `seeded` / `no-wiki` / `archived`
- category: `lab` / `pet` / `order` / `personal`
- a one-line description
- tags

The registry is updated for every new project and every status change.

## Cross-project search

Two levels:

1. **Obsidian vault** in `~/knowledge/`. Thanks to the symlinks in `projects/`, search and graph view work across all projects. Ideal for visual navigation and for `[[wiki-links]]` across project boundaries.

2. **CLI**: `~/knowledge/bin/kb-search "<query>"` — ripgrep over markdown in all symlinked projects + hub-level files. Fast, with no need to start Obsidian.

   Examples:
   ```
   kb-search "cold email"            # find every mention
   kb-search "reply rate" --project <slug>   # only in one project
   ```

## Language convention

- **Page content** — the user's language (`language` in `~/knowledge/personal/profile.yaml`).
- **Paths, file names, identifiers, tags, frontmatter keys** — English; kebab-case for files, snake_case for tags.
- **Terms without a good equivalent in the user's language** — keep them in English (ICP, funnel, cold outreach, CTR, MCP, …).
- **Code and technical snippets** — English comments.

## What not to do

- **Never modify `raw/`.** Sources are immutable. If a source is bad, note that on the matching wiki page, but do not touch the original.
- **No claims without a source.** Every fact must link either to `raw/` or to another wiki page with a chain back to raw.
- **Do not write speculation into the wiki without marking it.** If it is a hypothesis, mark it explicitly with `> [!hypothesis]` or put it under "Open questions".
- **Do not duplicate knowledge between the local wiki and the hub.** Rule: applies to ≥2 projects → the hub (`concepts/`, `people/`, `companies/`, `solutions/`). Only to one → local.
- **Do not mix code and wiki.** Project code sits next to `knowledge/` as siblings, not inside it.
- **Do not create pages "just in case".** Only when there is something to say right now.

## New project

```
~/knowledge/bin/new-wiki <path-to-project> [slug] [category] [description]
```

What it does:
1. Creates `AGENTS.md` (from `_template/`) and `knowledge/` with the full structure (`README.md`, `index.md`, `log.md`, `state.md`, `backlog.md`, `escalations.md`, `incidents.md`, `strategies.md`, `reports/`, `agents/_example.md`, `.orchestration.yaml`, `raw/assets/`, `sources/`, `daily/`) in the project. It creates no `CLAUDE.md`: Claude Code reads the project `AGENTS.md` directly (see the adapter contract above).
2. Adds `knowledge/` and `.kb-ignore` to the project's `.gitignore`.
3. Adds the symlink `~/knowledge/projects/<slug>` → `<project>/knowledge`.
4. Writes a line to the hub log.
5. Registers the project as `seeded` in `~/knowledge/registry.md`: a hand-written registry gets one row in its projects table (re-running adds no second row). When the registry does not exist yet, or is generated by `kb-rebuild-registry`, it changes nothing and prints how to register the project instead. Set the status to `live` once the wiki is in use.

## Agent specs vs agent code

An important convention for AI projects (such as `<slug>`): agent specs (markdown) live in `knowledge/agent-specs/`, while the real agent code (Python/TS) lives in the project root, for example `<project>/agents/`. The names differ so they do not collide. Reason: specs are knowledge (who does what, which prompts, quality metrics), while code is a tool. They evolve at different speeds and by different rules (knowledge is ingestible, code is testable).

## Obsidian

The vault is opened **at the `~/knowledge/` level**. Thanks to the symlinks in `projects/`, the graph view and `[[wiki-links]]` work across all projects at once. Project code (`node_modules`, `.git`, sources) is physically out of reach through the symlink: we point at `knowledge/`, not at the project root.

The file `~/knowledge/.obsidian/app.json` contains `userIgnoreFilters` as extra hygiene.

## Session auto-capture (claude-memory-compiler)

In projects that already have `<project>/knowledge/log.md`, Codex and Claude Code sessions are **captured automatically** through [coleam00/claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler). Antigravity CLI (`agy`) has no hook yet — once its ecosystem stabilizes (curl-installed v1.0.0 from 2026-05-19), add a similar adapter:

**SessionStart** — the `~/knowledge/bin/kb-session-start` hook builds a manifest-aware startup bundle: agent card, `state.md`, recent `log.md`, active work/open escalations, compact prevention/ongoing incident slice, and the CLI roster/recent `daily/` when the budget allows. `index.md` and the full `incidents.md` are not loaded at startup; they remain on-demand navigation/diagnostics.

**SessionEnd / PreCompact** — the `kb-session-end` / `kb-pre-compact` hooks export:
- `CLAUDE_KB_DAILY_DIR=<project>/knowledge/daily`
- `CLAUDE_KB_LOG_FILE=<project>/knowledge/log.md`
- `CLAUDE_KB_NO_COMPILE=1`

They delegate to `~/claude-memory-compiler/hooks/session-end.py` (upstream), which parses the transcript and spawns `flush.py` (patched) as a background process. Flush calls the Claude Agent SDK (`~$0.02-0.05`), extracts Context / Decisions / Lessons / Action Items from the session, and writes:

1. **The full extract** → `<project>/knowledge/daily/YYYY-MM-DD.md` (append, one `### Session (HH:MM)` per session)
2. **One line** → `<project>/knowledge/log.md` in the format `## [YYYY-MM-DD HH:MM] session | <summary>` + `Details: [[daily/YYYY-MM-DD]]`

**What is not touched:** `state.md`, `index.md`, `raw/`, categories (icp/, offers/, channels/, ...) — all of these are curated by the human. `daily/` is raw material: the user reads it and lifts what matters into the categories.

**Opt-in:** `<project>/knowledge/log.md` exists (= the wiki is set up).
**Opt-out:** `touch <project>/.kb-ignore` — the hooks will skip it silently.

**Patch checklist** (on `git pull` in `~/claude-memory-compiler/`):
1. `scripts/flush.py::maybe_trigger_compilation()` — the first line is `if os.environ.get("CLAUDE_KB_NO_COMPILE"): return`.
2. `scripts/flush.py::append_to_daily_log()` — a branch for `CLAUDE_KB_DAILY_DIR` + a cross-ref into `CLAUDE_KB_LOG_FILE`.
3. `scripts/flush.py::main()` — does not call `append_to_daily_log` for FLUSH_OK/FLUSH_ERROR when `CLAUDE_KB_DAILY_DIR` is set.

**Monitoring and debugging:**
- Hook log: `~/claude-memory-compiler/scripts/flush.log`
- It contains: `SessionEnd fired`, `Spawned flush.py`, `Result: saved (N chars)`

## Git and the wiki

**Rule: `knowledge/` must NOT be tracked by git in any project.**

Reasons:
- Dailies may contain sensitive session transcripts
- The wiki changes independently of the code (log.md is updated every session)
- Noise in PRs / diffs
- Obsidian is a "second brain", not part of the codebase

**Convention:** in every project that has `knowledge/`, `.gitignore` contains:
```
knowledge/
.kb-ignore
```

The `bin/new-wiki` script adds these lines to `.gitignore` **automatically** when it creates a new wiki. For projects whose wiki was set up before this rule, add them by hand.

If you need versioning for the wiki, do it separately (for example, `~/knowledge/` can be its own git repo, separate from the projects).

## Extension points

- `~/knowledge/bin/` — you can add CLI utilities here.
- Hub-level `raw/` — for sources that belong to no project (general books, foundational articles).
- Once there are >100 sources — plug in [qmd](https://github.com/tobi/qmd) (BM25+vector over markdown).
- **Phase 2 for the compiler:** plug in `compile.py` to generate `concepts/`, `connections/`, `qa/` once daily captures pile up and it becomes clear what exactly is worth compiling. This will need prompt customization so that it does not rewrite the user's `index.md`.

## Important research quorum

For important research, use the quorum pipeline: independent passes by four local orchestrators — **Claude Code + Codex + Antigravity CLI (`agy`) + Grok CLI**. The Grok pass runs through `$HOME/.grok/bin/grok`, not through OpenCode, and the prompt must explicitly ask it to check current X/Twitter and Reddit discussion/signals. If this hub also keeps a written procedure at `~/knowledge/concepts/important-research-quorum-pipeline.md` (optional; the installer does not ship one), follow it; otherwise this section is the procedure.

Each pass writes a durable note to `knowledge/sources/<topic>-<agent>-<date>.md` (4 files); the final synthesis goes to `knowledge/reports/<topic>-<date>.md` with explicit agreement/disagreement/confidence. NotebookLM is the final production step: a recap in the user's language (structure: "What we found", "What this changes", "How to apply it in Vepol", "What not to take", "Next steps"). If Grok CLI is unavailable, important research is degraded; chrome-devtools-mcp or OpenCode are allowed only as an emergency fallback, with an explicit note about the degradation.

**When to call it:**
- "what are people saying about X", "what is the community saying", "what are the reactions to Y"
- any research task that mentions X/Twitter/Reddit
- when freshness matters (the last days/weeks)
- when you need an independent 4th voice (Grok CLI) for hard decisions

**When NOT to call it:**
- the answer is in the code / documentation / git history
- a technical question with no community-sentiment component
- a quick fact that a normal web search covers
