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

(no changes since 0.1.0)

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
  agents installing Vepol) + `CLAUDE.md` pointer for Claude Code's
  convention.

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
resale). Each release auto-converts to MIT on its second anniversary;
v0.1.0 converts on **2028-05-02**. See `LICENSE` and `COMMERCIAL.md`
for the authoritative wording and common scenarios.

[Unreleased]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nahornyi-ai-lab/vepol/releases/tag/v0.1.0
