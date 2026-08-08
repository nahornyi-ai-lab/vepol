# Changelog

All notable changes to Vepol will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **MAJOR** — incompatible API changes (after 1.0)
- **MINOR** — backwards-compatible feature additions; **may be breaking in 0.x series**
- **PATCH** — backwards-compatible bug fixes

While in `0.x`, expect that any minor version bump may include breaking changes
to scripts, manifest format, or directory layout. Read this changelog before
upgrading.

## [Unreleased]

## [0.8.0] — 2026-08-09

### Added
- **Whole-block morning audio.** The morning digest now assembles the whole
  finalized same-day morning brief, an eligible rich arXiv report, and the
  Money Radar digest — in that order, with no second synthesis or compression
  pass. Local Qwen narrates the frozen source literally; NotebookLM receives
  the same source for its own non-literal Audio Overview. New `kb-brief-preflight`
  freshness gate and dedicated delivery helpers (`_kb_brief_delivery.py`,
  `kb-channel-send-text`) ship with the digest, plus their test suites
  (`test-brief-v2-preflight.sh`, `test-morning-whole-block-audio.sh`,
  `test-morning-brief-fidelity.sh`, `test-channel-send-text.sh`,
  `test-seed-sync-morning-scope.sh`).
- Secrets hygiene in the brief pipeline: `export`-prefixed lines in env files
  are parsed correctly, so they can never leak into a generated brief.

### Fixed
- **The test suite now tests the package it ships with.** Cycle and wave-rollup
  fixtures used to copy binaries from the machine's installed hub; they now
  default to the repository's own tree (override with `KB_CYCLE_SRC_BIN`).
  `tests/run-all.sh` runs green end to end from a clean checkout — previously
  it aborted mid-chain on any machine whose hub had evolved past the release.
- A fresh install without the optional Codex CLI no longer fails
  `kb-doctor install-health --strict`: absence of a never-configured Codex is
  informational; a configured Codex whose binary went missing stays P1.
- The whole-block audio test no longer demands rewriting shipped release
  notes: its doc-check asserts that *current* docs (README, getting-started,
  the mutable CHANGELOG `[Unreleased]` section) describe current behavior, and
  two latent defects (an errexit leak and a date-pinned assertion path) that
  silently aborted the suite are repaired.

### Removed
- Obsolete `test-morning-digest-rebalance.sh` (superseded by the whole-block
  behavior and its suites).

## [0.7.2] — 2026-08-07

### Fixed
- **Idea-to-task promotion works end to end.** `kb-idea promote` crashed with
  `TypeError` on every invocation: the `--create-task` flag shipped in the
  CLI, docs, and acceptance test at v0.6.0, but the library behind it never
  learned the keyword. `promote(create_task=True)` now creates a `Ready`
  kb-board task (idea title, triaged priority, expected evidence as
  acceptance, `idea_id` backlink, optional `--context` body) atomically under
  the board lock, idempotently, and mirrors the `plan_item_id` back to the
  card. The v0.6.0 acceptance test now passes as written.
  ([v0.7.2](releases/v0.7.2.md))

## [0.7.1] — 2026-08-07

### Fixed
- **Startup on stock macOS Python.** Seven files (`kb-planner`,
  `kb-session-start`, `kb-task`, and the four contact-notebook modules) used
  `str | None` annotations that Python 3.9 — the interpreter macOS ships as
  `/usr/bin/python3` — evaluates at load time, crashing with `TypeError`
  before any code ran. Scheduled jobs run with a reduced `PATH` and hit
  exactly that interpreter: the daily planner could not start from its
  LaunchAgent, the session hook lost the whole startup context bundle, and
  the People Notebook pipeline could not be imported. Each file gains one
  `from __future__ import annotations` line; an AST sweep of all 106 Python
  files, 39 Python executables and 124 embedded Python heredocs under `bin/`
  confirms no other file has the same problem. ([v0.7.1](releases/v0.7.1.md))

## [0.7.0] — 2026-07-14

### Added
- **People Notebook — review-gated relationship memory.** Vepol proposes contact
  cards from four sources it already sees — project logs, the mail people-
  envelope, private Telegram dialogs (read-only, on your own account), and
  calendar attendees. Every genuinely new person waits in a Telegram review
  queue for one-tap keep/skip; nothing about a new person is written without
  your approval. A known contact gets only a content-free sighting, never new
  prose. The Telegram collector never sends, edits, or joins, and carries no
  message text into the notebook by schema; API keys and session state stay in
  local secrets, not the repository. Optional enrichment runs through your
  configured Codex CLI. Company/asset roll-up from sightings is scoped and stays
  disabled until the orchestration cycle is re-enabled.

### Changed
- **Local Qwen TTS moves to the BF16 model snapshot.** The on-demand renderer
  re-pins from the 8-bit build to the BF16 Qwen3-TTS VoiceDesign snapshot for
  cleaner speech. The installer gains a non-blocking install lock, verified
  immutable release directories, atomic `install.json` promotion, and byte-exact
  preservation of any prior install marker. No weights or credentials ship in
  the repository; the model loads for one render and exits.
- **Daily and retro audio now use local Qwen TTS and Telegram MP3 files.**
  `kb-morning-digest` keeps its existing morning synthesis and trusted evening
  Retro source, converts only the finalized body to speech text, renders it
  through the pinned on-demand Qwen3-TTS 1.7B runtime, and sends the MP3 through
  Telegram `sendAudio`. NotebookLM is no longer called by these scheduled
  paths. The model is not a daemon and leaves memory after each render. Run
  `kb-tts-install` once to opt in; missing runtimes remain report/speech-only.
- **Learning digest reads full arXiv papers by default.** `kb-learning-arxiv`
  now fetches/caches selected arXiv PDFs, extracts text with `pdftotext`, and
  sends the extracted paper text to Codex through a prompt file. The manifest
  contract moves to v4 with per-paper `analysis_source`, `analysis_chars`,
  `analysis_truncated`, and `analysis_error` provenance; old abstract-only
  caches no longer satisfy the current delivery contract.
- **Grok/X/Reddit social checks are opt-in.** The scheduled learning digest no
  longer calls Grok by default or renders empty X/Reddit boilerplate when no
  social subscription is available. Set `social_check: grok` in
  `personal/daily-research.yaml` to re-enable the social lane explicitly.

## [0.6.0] — 2026-07-11

### Added
- **On-demand local Qwen TTS runtime.** `kb-tts-install` installs the pinned
  Qwen3-TTS 1.7B VoiceDesign runtime and model; `kb-tts-render` loads it only
  for a render and exits afterward. No daemon, container, LaunchAgent, model
  weights, or credentials ship in the repository.
- **Telegram MP3 transport.** `kb-channel-send-audio` uploads the generated
  file through Bot API `sendAudio`, with bounded known-rejection versus
  ambiguous-delivery states and secret-safe structured results.
- **Selectable digest audio route.** The finished morning/evening text can be
  sent either to the existing NotebookLM Audio Overview adapter or to local
  Qwen followed by Telegram. Configure it with
  `kb-digest-migrate --audio-backend notebooklm|local_qwen` or the matching
  installer option.

### Changed
- **Digest text generation is unchanged; delivery is selected afterward.**
  `[file, notebooklm_audio]` keeps the Audio Overview in NotebookLM without
  Telegram or download. `[file, telegram_audio]` sends the same finalized text
  through the existing on-demand Qwen3-TTS 1.7B runtime and Telegram
  `sendAudio`. There is no automatic fallback between the two adapters.

### Fixed
- **Same-day manual audio can no longer suppress a fresher scheduled digest.**
  Morning manifests now carry a versioned semantic snapshot of the complete
  captured input. An unchanged snapshot remains an external-call no-op; newer
  learning, Money Radar, brief, mail, idea, project, board, log, or escalation
  content triggers one serialized rebuild. Malformed snapshots and ambiguous
  Telegram uploads remain fail-closed.

## [0.5.0] — 2026-07-02

### Added
- **Daily audio digests (`kb-morning-digest`)** — the digest engine ships
  publicly. Every morning it gathers the freshest output of your scheduled
  processes into one digest file; a new `--period evening` mode produces a
  short (~1–2 minute) recap right after the evening retro (what got done, what
  is hanging, what mail still waits). If the `notebooklm` CLI is connected,
  each digest also becomes an audio overview in a monthly NotebookLM notebook;
  without it (or on quota/rate-limit/auth failure) every run keeps the file,
  skips the audio, and exits cleanly. Morning and evening keep separate files,
  manifests, and locks and share only the monthly notebook. The evening recap
  is built from the composed day file only — raw mail bodies, addresses, and
  envelopes are never read by the evening path, and untrusted-data fencing is
  stripped before text reaches NotebookLM.
- **Schedule migration (`kb-digest-migrate`)** — idempotent, reversible
  `processes.yaml` migration: inserts the evening digest after your retro,
  anchors the morning digest behind your last enabled morning process,
  re-anchors only its own managed block when a better anchor appears, and
  leaves customized blocks untouched. Fresh installs get both digests
  automatically.

### Changed
- **`kb-retro` persists the retro.** The retro text is appended to
  `briefs/<today>.md` as a `## Retro (HH:MM)` section, so the day file carries
  the whole day (brief + retro + reflection) and feeds the evening recap.
- **Scheduler audio policy: narrow allowlist replaces the blanket ban.**
  Scheduled `notebooklm_audio` is now allowed ONLY for the two digest
  processes, each bound to its exact run command; anything else still fails
  closed. The digest binary additionally enforces a background runtime guard
  (allowlisted process id + matching command + declared audio output, else
  file-only with zero NotebookLM calls).

## [0.4.0] — 2026-07-02

### Added
- **Mail briefing (`kb-mail-brief`, `kb-mail-block`)** — read-only Gmail
  intelligence for the daily loops. A background reader runs before the morning
  brief and the evening retro, minimizes new inbox threads into a bounded,
  privacy-safe summary (no raw bodies, addresses, or recipients ever persisted;
  private `personal/mail/` storage), and `kb-brief` / `kb-retro` / the
  orchestrator cycle surface what needs attention. Email content is treated as
  untrusted input: minimized, strictly validated, and fenced before it reaches
  the brief, so email text gets no instruction authority; the reading step
  itself is read-only with no action tools (see the release notes for the
  exact boundary). Enabled by
  default but reads nothing until Gmail is connected; real reads require the
  Codex CLI with Gmail access, otherwise mail quietly reports unavailable and
  never blocks the brief. Vepol ships no draft/send/label/delete code path and
  never requests a write; reader isolation is instruction- and policy-level in
  this release (see the release notes for the exact boundary).
- **Schedule migration (`kb-mail-migrate`)** — idempotent, reversible
  `processes.yaml` migration that schedules the mail reader one tick before
  your existing brief/retro times, preserving every other process and chain.
  Fresh installs are scheduled automatically.
- **Cycle postcondition check (`_kb_orchestrator/`)** — the orchestrator cycle
  now re-reads its claimed side effects from disk and refuses to report success
  it cannot prove.

### Changed
- `kb-brief`, `kb-retro`, and `kb-orchestrator-cycle` gained the mail
  integration hooks and the cycle's accumulated local hardening.

## [0.3.1] — 2026-06-22

### Added
- **Prompt-first agent self-install** — `install.sh` can now guide Codex,
  Claude Code, and other agents through probe, dry-run, verify, apply,
  uninstall, and upgrade flows without asking them to guess install state.
- **Money Radar (`kb-money-radar`)** — an opt-in scheduled opportunity radar
  is shipped disabled by default in `processes.yaml`, with safety guards,
  source/link filtering, idempotency, and a dedicated acceptance suite.
- **Startup Context Manifest** — `kb-session-start` now injects the agent card,
  project state, recent log, active work, open escalations, and compact
  incident prevention rules without loading full indexes by default. It also
  supports `--print --cwd` for hook-less agents.

### Changed
- **Learning digest LLM split** — `kb-learning-arxiv` now uses Codex for
  offline translation/method summaries and Grok only for X/Twitter + Reddit
  social context. The manifest contract moves to v3 and stale v2 caches no
  longer satisfy delivery.
- **Evening retro board source** — `kb-retro` now reads canonical markdown
  `kb-board` files instead of the old Plane board snapshot path.
- **Owner-approved spec gate docs** — the public methodology now documents the
  owner approval queue/hash gate and the post-approval build-plan step.
- **Agent card/state templates** — generated project templates are more
  explicit about startup-loaded cards, boundaries, state hygiene, and durable
  KB write-back.

### Fixed
- Installer verification now catches missing or replaced `orchestrator-seed`
  pointers and `install.sh --apply` self-heals a non-symlink seed pointer
  instead of leaving verify/apply behavior inconsistent.
- Startup context injection no longer starves critical sections when `index.md`,
  incident history, backlog bodies, or card/state files are large.

## [0.3.0] — 2026-06-20

### Added
- **Idea Intake (`kb-idea`)** — a Software 3.0 event-driven process
  for ideas you write or dictate: atomic canonical cards under
  `personal/ideas/`, rendered `personal/ideas.md` dashboard, triage/priority,
  ready/promoted digest for `kb-brief`, markdown `kb-board` promotion through
  `--create-task`, explicit calendar proposal / approval, and terminal outcome
  write-back.
- **User language setting** — set your language once in
  `personal/profile.yaml` (`language: en|ru|es|uk|de|...`; the installer
  derives a default from your system locale) and every user-facing process
  — morning brief, evening retro, learning digest, people reminders —
  delivers in it. Invalid or missing values fall back to English and never
  block delivery. Deterministic labels currently ship in English and
  Russian; other languages get English labels with native LLM content.
- **arXiv learning runner (`kb-learning-arxiv`)** — the scheduled `learning`
  process now reads arXiv directly: deterministic regex ranking selects up
  to three papers per day, one Grok CLI call checks prior X/Twitter and
  Reddit discussion and produces Russian summaries bounded by each paper's
  title+abstract, and a short Russian digest is delivered through the
  configured channel. Grok failures degrade gracefully (statuses marked
  `degraded`, digest still ships, summary falls back to marked abstract
  extracts). The old broad-radar `kb-daily-research` stays available for
  manual runs only.
- **Background processes runtime** — the routine processes
  (daily brief, evening retro, learning digest, people extraction,
  follow-up reminders, calendar pull) are now declared in a single
  `personal/processes.yaml` and gated through `kb-tick`. Five fields per
  process (`id`, `enabled`, `when`, `run`, `outputs`); a missing config
  self-heals with safe defaults; each process has its own independent
  `enabled` switch.
- **Development Loop methodology** — one vendor-neutral process any agent
  follows for new work (scope → research-first → design → spec →
  cross-agent review → tests → implementation review → write-back →
  verify), with v2 quality gates.
  [`docs/methodology/development-loop.md`](docs/methodology/development-loop.md)
- **Agent CLI roster** — every agent session now starts knowing which
  CLI tools are installed on the machine and when to reach for each:
  `kb-cli-roster` generates a per-machine `.active-roster.md` from a
  declarative registry and injects it at session start.

### Changed
- **Daily research / learning is text-first.** Background runs deliver a
  text digest through the configured channel and make zero NotebookLM
  calls; the NotebookLM notebook + Russian audio recap is an explicit
  on-demand mode. Daily research sources are curated and audio artifacts
  are no longer downloaded locally.
- **`daily` runs only its declared command.** The hidden arXiv prefetch
  that `kb-tick` used to run before the morning brief is removed; arXiv
  ownership lives entirely in the `learning` process.
- Installer and hub setup hardened for existing/partial/upgraded
  installs: prerequisite version enforcement, never deleting hub
  directories (moved aside instead), custom-hub (`KB_HUB`/`VEPOL_HUB`)
  handling in hooks and roster scripts.
- Seed release hygiene extended: shipped files are routed through the
  seed sanitizer and scrubbed of maintainer-workspace references.

### Fixed
- Manifest state for daily research is namespaced per mode: text-only
  failures no longer consume the NotebookLM audio retry budget, a
  delivered digest is required for text-only idempotency, and legacy
  mixed-state manifests migrate conservatively without erasing real
  audio attempts.
- Tilde (`~`) in `processes.yaml` run-command arguments is expanded, so
  processes run correctly under launchd with `cwd=/`.

## [0.2.1] — 2026-05-29

Patch release after the public `v0.2.0` smoke.

### Fixed
- Removed the mandatory `jsonschema` runtime import from the Evolution Loop
  proposal validator. The validator now uses a small stdlib checker, so
  `./tests/run-all.sh` passes from a fresh public clone without first running
  `pip install -r requirements.txt`.

## [0.2.0] — 2026-05-29

Second public release candidate. This release moves Vepol's task workflow to
the markdown-native `kb-board` protocol and hardens the install/security
baseline after the May rollout audit.

### Added
- **Markdown-native task board (`kb-board`)** — `knowledge/backlog.md`
  is now the single source of truth for tasks, with exact status sections
  (`Backlog`, `Ready`, `In Progress`, `Blocked`, `Review`, `Done`,
  `Cancelled`), multiline task blocks, ID-first mutations, claim leases,
  heartbeat/sweep support, and a full parser/formatter/checker test suite.
- **Board-first agent workflow** — `AGENTS.md`, templates, and the
  project seed now instruct agents to create, claim, review, and close tasks
  through `kb-board`. Legacy `kb-backlog` mutation commands fail fast on
  migrated boards; list/read compatibility remains for old one-line boards.
- **Release install-health gates** — `kb-doctor install-health` now checks
  unsafe Claude settings bypass keys, managed install hash drift, expected
  LaunchAgent state, binary availability, and seed/git version drift. The
  reviewed disabled state for `com.knowledge.orchestrator-cycle` is reported
  as informational while scanner-v2 promotion evidence is pending.
- **Seed release hygiene** — `kb-seed-sync` now blocks personal/dev leakage
  through leak-scan and structural seed-content audit before commit/push.
- **Daily NotebookLM research loop** — `kb-daily-research` selects one
  useful topic per day from the active project, creates a NotebookLM notebook,
  imports web research, and generates a Russian audio recap focused on
  "what we found", "how this applies to Vepol", "what not to take", and
  next actions. Topic can be pinned with `--set-topic` or returned to
  automatic selection with `--auto-topic`; `kb-tick` runs this as the default
  one-audio-per-day morning research path.
- **Antigravity CLI native AGENTS.md loading** — `agy --add-dir <path>`
  pre-loads project `AGENTS.md` (and `GEMINI.md` if present) into the
  system prompt via `cascadeManager`. Standard launcher — `agy-here`
  shell function appended to `~/.zshrc` by `install.sh`. Project-level
  `GEMINI.md` adapter removed 2026-05-22 (Gemini CLI free/Pro/Ultra
  deprecation 2026-06-18; `agy` reads `AGENTS.md` directly). Global
  `~/.gemini/GEMINI.md` written by `install.sh` Step 4 imports the
  canonical hub `AGENTS.md` and acts as fallback when `agy` runs
  without `--add-dir`.
- **Multi-bot agent runtime** — `kb-multibot-supervisor`, plus
  `kb-multibot-setup` / `kb-init-agent` / `kb-deactivate-agent`
  CLIs, a LaunchAgent template, a Telethon group listener, a Bot
  API sender with retry/backoff, per-agent queues, file-lock
  serialization, stdout-silence watchdog, four loop guards
  (cooldown / depth / fan-out / hourly quota), and 154 unit
  tests. Concept and spec at
  [`docs/methodology/multibot-agent-runtime.md`](docs/methodology/multibot-agent-runtime.md).
- **Vendor-neutral agent positioning in docs** — public docs now
  state that Vepol coordinates ready-made CLI agents such as Claude
  Code, Codex, Antigravity CLI, and future agents over one shared KB.

### Changed
- Project-level `GEMINI.md` adapters are removed from the distribution;
  `AGENTS.md` is the canonical instruction file and Antigravity CLI reads it
  natively via `agy --add-dir`.
- `kb-execute-next` now refuses migrated multiline `kb-board` files instead
  of attempting legacy `kb-backlog` claim/close operations. Use explicit
  `kb-board` claims until executor v2 is ported.

### Security
- Removed legacy `skipDangerousModePermissionPrompt` from the Claude settings
  template and added regression coverage so unsafe bypass keys cannot silently
  re-enter release builds.
- Hardened seed publication against local-path, personal-name, and private
  hub-page leakage; `knowledge/solutions/` stays home-only and is not tracked
  in the public seed.

## [0.1.0] — 2026-05-02

First tagged public release. The repository was opened on 2026-04-29
with the scaffolding listed under "Initial scaffolding" below; the
feature sections that follow (daily-plan generator, Stripe Payment
Links, People, MCP-first sources) landed between 2026-04-30 and
2026-05-02 and are all part of this release.

### Initial scaffolding (2026-04-29)

- **Public repository structure** — `bin/`, `_template/`, `claude/`,
  `launchd/`, `patches/`, `policy/`, `tests/`, `demo/`, `docs/`.
- **Global methodology** — Claude Code conventions and orchestrator
  rules in `claude/CLAUDE.md`; per-project schema in
  `_template/CLAUDE.md`.
- **Demo wiki** — synthetic populated knowledge base demonstrating the
  five archetype projects (family / work / health / finance / learning).
- **Methodology pages** — seven concept pages on the substrate and
  practice (`docs/methodology/`):
  orchestrated-knowledge-base, kb-authoring-discipline, kb-freshness-loop,
  triz-for-design, spec-driven-workflow, cross-agent-review,
  parallel-orchestrators.
- **Visual documentation** — eight infographics + a Mermaid mind map
  + a briefing doc explaining Vepol on one page (`docs/visuals/`).
- **Privacy-aware install lifecycle** — `install.sh` with detect-only
  prereq checks, include-pattern CLAUDE.md merge, opt-in invasive
  features, first-run aha sequence.
- **3-layer leak prevention** for maintainers
  (regex blocklist / whitelist of allowed concepts / structural audit
  via `kb-doctor seed-content-audit`). A fourth semantic-LLM scan is
  designed but is maintainer-only tooling and is not part of this
  public release.
- **Agent-driven onboarding** — `AGENTS.md` (operating manual for AI
  agents installing Vepol) + runtime adapters such as `CLAUDE.md`
  for Claude Code. Antigravity CLI (`agy`) reads `AGENTS.md`
  natively via `agy --add-dir <path>`; no project-level adapter needed.

### Daily-plan generator v0.1 (2026-04-30)

- **`kb-orchestrator-cycle gen-plan`** — generates
  `daily-plan/<tomorrow>.md` from open backlog at retro time
  (deterministic; no LLM in v0.1). Hooked into `cmd_retro`.
- **`kb-backlog stamp`** — atomic operation to attach a `plan_item_id`
  to an existing open backlog row, with drift detection via expected
  body hash and same-/cross-slug duplicate guards.
- **`kb-cycle-launch` parser fix** — `approved_at` extraction now
  correctly handles ISO datetimes, quoted values, comments, and the
  `null` / `~` / empty sentinels.
- **Acceptance coverage** for the generator, the stamp op, end-to-end
  dispatch loop, idempotency, and edge cases.

### Stripe Payment Links (2026-04-30)

- **Two annual auto-renewing subscriptions** for the commercial
  license, processed by Stripe in EUR:
  Small (€1500/year) and Mid-size (€5000/year).
- **`COMMERCIAL.md` rewrite** with the buy links, term/renewal
  semantics, and tax routing (EU B2B reverse charge per Art. 196,
  non-EU export, Spain/EU B2C → email path).

### People (Vepol's memory of people, in markdown) — 2026-04-30

- **`docs/modules/people.md`** — the public concept: People is
  not a CRM; it is one markdown card per person, sitting next to
  your project knowledge so every Vepol agent can read it natively.
- **`bin/_kb_people/`** — Python package: card model with
  `<!-- MANUAL-NOTES -->` (human-only) + `<!-- DERIVED-SIGHTINGS -->`
  (auto-managed) regions; index for fast email/name lookup; three-tier
  dedup (UUID / email-deterministic / fuzzy name match); sources
  protocol.
- **`bin/kb-contact`** CLI — add / log / remind / search / due /
  show / **review-drafts** (interactive walk through draft cards
  with confirm / merge / delete / skip).
- **`bin/kb-calendar-sync`** — ingest Google Calendar attendees
  through the MCP path (see "MCP-first sources" below).
- **`bin/kb-people-remind`** — daily 9:00 LaunchAgent surfaces
  contacts whose `next_touch_due` is today (or overdue) via Telegram.
- **`bin/kb-channel-send`** — canonical Telegram delivery wrapper.
  Per-variable credential resolution; env always wins, `.secrets`
  fills gaps; long messages split safely.
- **Markdown-injection mitigation** centralized in
  `card._escape_markdown_table_cell()`: pipes escaped, comment
  markers defanged, newlines flattened. Applies to every source.
- **Bot/system local-part filter** drops common role mailboxes
  (`meet`, `schedule`, `noreply`, `alerts`, `billing`, etc.) before
  they become contact cards.

### MCP-first sources (2026-05-02)

- **`docs/methodology/mcp-first-sources.md`** — the principle:
  Vepol modules that read external data (calendar, mail, chat, …)
  route through an MCP host (`claude -p` + MCP server) rather than
  vendor SDKs. Strict envelope contract, permissive item validation,
  two-layer preflight (host + per-tool canaries), single canonical
  exception process with a dated registry.
- **`bin/_kb_mcp/runner.py`** — `McpHostRunner` abstraction.
  Single point of contact with the host. Strict JSON envelope
  parser rejects preamble, trailing content, malformed JSON, missing
  fields, non-bool `ok`. Three exception types: host / response /
  tool.
- **Calendar source migrated** from `google-api-python-client` +
  OAuth client (and `~/.vepol/tokens/`) to the MCP path. No vendor
  SDK; no per-source credentials file; auth is the MCP host's
  responsibility.
- **`kb-doctor mcp-check`** preflight — basic-echo probe + Calendar
  canary (`mcp__claude_ai_Google_Calendar__list_calendars` attempted
  with attempt-and-observe-failure-mode; never trust a model's
  self-report of "yes, this tool exists").
- **Integration test harness** — `bin/tests/test-people-integration.sh`
  with six fixtures exercising the full pipeline including injection
  mitigation and the bot filter.

### License

FSL-1.1-MIT — source-available; free for personal use, internal
commercial use, professional services to clients, modifications, and
non-competing forks. Restricted for competing products or services
made available to others (hosted SaaS substituting for Vepol, branded
resale). Each release auto-converts to MIT on its second anniversary:
v0.1.0 converts on **2028-05-02**, v0.2.x converts on **2028-05-29**,
v0.3.0 converts on **2028-06-20**, v0.3.1 converts on
**2028-06-22**, and v0.4.0 converts on **2028-07-02**. See `LICENSE` and
`COMMERCIAL.md` for the authoritative wording and common scenarios.

[Unreleased]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nahornyi-ai-lab/vepol/releases/tag/v0.1.0
