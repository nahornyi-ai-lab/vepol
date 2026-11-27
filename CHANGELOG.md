# Changelog

All notable changes to Vepol will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **MAJOR** — an incompatible change to the stable core (below)
- **MINOR** — backwards-compatible additions to the core; other `kb-*`
  commands and `processes.yaml` may change (see below)
- **PATCH** — backwards-compatible fixes

The stable core, from 1.0.0 on:

- the knowledge folder layout (`~/knowledge/` and each project's `knowledge/`)
- the task-board file format (`backlog.md`) and the `kb-board` commands
- installing and upgrading (`install.sh`, `upgrade.sh`)

Other `kb-*` commands and the background-process settings in `processes.yaml`
may still change in a minor release within 1.x; every such change is called out
in that release's entry below.

Releases before 1.0.0 were in the `0.x` series, where a minor bump could include
breaking changes to scripts, manifest format, or directory layout. If you are
upgrading from an older `0.x` install, read the entries between your version and
this one.

## [Unreleased]

## [1.2.0] — 2026-11-27

Vepol now talks to you in your language, and its repository is English-first.
A fresh install runs its daily routine without hand fixes, and a new install
grants Claude Code only what Vepol needs. Some `kb-*` commands change an exit
code or a default; each such change is called out below.
([v1.2.0](docs/releases/v1.2.0.md))

### Added
- **Plan my day, in Vepol Desktop.** The Memory view opens with a Today card:
  goal, outcomes, time blocks and the plan's status (Draft, Confirmed, In
  calendar, Conflict, Partial). "Plan my day" opens an agent in the app's
  terminal that reads the day's brief, goals and calendar, proposes a plan and
  saves every correction as a new version with the new `kb-dayplan` command
  (`personal/day-plans/<date>.json`). Your Google Calendar, reached through
  Claude Code, is written only when you ask for it, and then only Vepol's own
  marked events of that day: nothing is written if a busy event overlaps an
  agreed block, and the calendar is read back to report exactly what is there.
  The evening retro compares the day with the confirmed plan.
- **A nightly knowledge refresh.** `kb-consolidate` (06:30 in the default
  `processes.yaml`) reads what each project in `~/knowledge/hierarchy.yaml`
  logged since the last pass and applies point edits to its `state.md`, keeping
  only edits that match the page exactly and cite a log or daily note. If the
  model fails, the page gets a list of the newer log headlines instead. Each
  run leaves a report with the diff and a backup of the page under
  `~/knowledge/.orchestrator/consolidate/`. Until `hierarchy.yaml` exists it
  has nothing to do: run `kb-rebuild-registry bootstrap`, then
  `kb-rebuild-registry apply`, once. `kb-child-rollup` ships with it (a daily
  child-to-parent summary at 07:00, idle until `hierarchy.yaml` names parents).
  Both are in the default `processes.yaml` only. Install writes that file only
  when it is missing and upgrades never rewrite it, so after an upgrade
  neither runs until you add both blocks to
  `~/knowledge/personal/processes.yaml`, for example above the `mail-morning`
  block:

  ```yaml
  - id: consolidate
    enabled: true
    when: "06:30"
    run: kb-consolidate
    outputs: [file]

  - id: child-rollup
    enabled: true
    when: "07:00"
    run: kb-child-rollup
    outputs: [file]
  ```
- **Close a task from Vepol Desktop.** Every Backlog, Ready or Blocked task in
  the Tasks view has a Close button with an optional reason and an Undo.
  `kb-board` gains `cancel` and `reopen`, and `list --json` rows carry each
  task's `content_hash`.
- **Sessions that remember their task.** A Desktop session started from a task
  shows the task and its status and moves to Done when the task closes; you can
  run several sessions of one agent in one project; every terminal agent
  (Claude Code, Codex, Grok, Antigravity, Hermes, OpenCode) gets a real title and
  last message on its card.
- **Add Vepol's session hooks to the settings you already have.** When
  `~/.claude/settings.json` already existed, install left it without Vepol's
  hooks, so agents started without your knowledge base and sessions were not
  captured. `~/knowledge/bin/kb-claude-hooks --check` names the missing
  SessionStart, SessionEnd and PreCompact hooks. `--apply` writes a
  timestamped backup next to the file, then adds only those hooks and keeps
  every other setting; a second run changes nothing. An interactive install
  offers this, and `install.sh --apply` does it when `VEPOL_MERGE_HOOKS=1` is
  set.
- **A guide to your daily routine.**
  [docs/daily-routine.md](docs/daily-routine.md) covers everything Vepol runs
  on a schedule: turning on scheduled tasks, setting up Telegram step by step,
  what each step in `~/knowledge/personal/processes.yaml` does and how to
  switch it off, the brief, the retro, mail, the arXiv digest, audio, research,
  Money Radar, the nightly refresh, people reminders, time zone, and what to
  check when something does not arrive.
- **`new-wiki` registers the project.** With a hand-written
  `~/knowledge/registry.md`, `new-wiki` adds one `seeded` row for the project
  to the table under its category, and never a second one. A one-line
  description is an optional fourth argument:
  `new-wiki <path-to-project> [slug] [category] [description]`. A registry
  that `kb-rebuild-registry` generated is left untouched, and `new-wiki`
  prints the project's entry to append, unchanged, to the end of
  `~/knowledge/migration-2026-04-25.yaml`; then run
  `kb-rebuild-registry apply`. The categories are `lab`, `order`, `pet`, `job`
  and `personal` (the default).
- **`kb-brief --help`, and a status line after every run.** `kb-brief --help`
  explains `KB_BRIEF_DRY=1`, `KB_BRIEF_PROMPT_ONLY=1`, `BRIEF_TIMEOUT` and the
  06:00 preview rule. A run now ends with one line: where the brief was saved
  and whether it reached Telegram, and why not when it did not.
- **A contributor guide, community files and CI.**
  [CONTRIBUTING.md](CONTRIBUTING.md) covers the development setup, the tests
  and the language rule, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) sets how
  we treat each other. Bug and idea forms help you open an issue (security
  problems go to a private advisory), and pull requests start from a short
  template. A GitHub Actions workflow runs `tests/run-all.sh` and the Vepol
  Desktop tests on macOS for every pull request and every push to `main`.
  `tests/run-all.sh` now also runs the twelve daily-routine suites (brief,
  retro, audio digests, mail, calendar, people, research, Money Radar and user
  language), the `kb-codex-cleanup` scope suite, and the `kb-doctor` and
  multi-bot pytest suites, so it needs `pytest` for the `python3` on your
  `PATH` (`python3 -m pip install --user pytest`).

### Changed
- **Morning brief v3: readable in a minute, with optional sleep and health.**
  `kb-brief` now writes a short phone-first brief (date · focus, day plan, main
  actions; decisions, mail and ideas only when there are any; one-line
  changed / risks / quiet tails). Point `KB_HEALTH_METRICS` at a folder of daily
  `health-morning/v1` files to get a 🫀 Body section; without it the brief never
  mentions health and never waits. See
  [docs/health-in-the-brief.md](docs/health-in-the-brief.md).
- **The brief's time no longer depends on sunrise.** `kb-planner` records a
  fixed brief time, `KB_BRIEF_HM` (07:00 by default), instead of one tied to
  sunrise. The brief itself runs when `processes.yaml` says: by default after
  the 07:15 mail read.
- **A manual brief at night is a preview.** A manual `kb-brief` run before
  `KB_BRIEF_PREVIEW_BEFORE` (06:00) writes `briefs/<date>-preview-HHMM.md`, so
  the scheduled morning brief is still written and delivered.
- **The Automations view shows the real reason a routine failed** (quota,
  model, auth, network or timeout) instead of the first line of its output.
- **Failed end-of-session summaries are kept, not lost.** With session capture
  on, a summary that fails (most often after an expired login) waits in
  `pending/` with the real reason and is retried at the next successful session
  end; `kb-session-start` mentions stuck summaries for the current project.
- **An English-first repository, and Vepol talks to you in your language.**
  Code, comments, prompts, templates, skills and docs in the repository are
  in English; other languages appear only in per-language tables, in patterns
  that must match text in that language, and in tests (see
  [CONTRIBUTING.md](CONTRIBUTING.md)). What Vepol writes for you follows
  `language:` in `~/knowledge/personal/profile.yaml`: prompts tell the agent
  which language to answer in, and fixed labels come from per-language tables
  with English as the default. This now also covers parts that were Russian
  for everyone: the audio digest (see Fixed), the arXiv digest's translation
  warnings, the daily-research digest labels, the NotebookLM packet from
  `kb-arxiv-notebooklm`, the ideas dashboard (`personal/ideas.md`), the
  headings of a generated `registry.md`, and the hub's rule for which
  language wiki pages are written in. With a Russian profile, your briefs,
  retros and digests and their fixed labels stay in Russian; new project
  templates, a few labels in report source lists and `log.md`, and most
  terminal messages (for example from `kb-search` and `kb-doctor`) are now
  English.
- **Install needs fewer tools and checks their versions.** You need git,
  Claude Code (`claude`), ripgrep, Python 3.10+ and bash 5+. Node and Bun are
  optional: no `kb-*` script runs them; Node helps install npm-based CLIs such
  as Codex, and Bun runs only Claude Code's own Telegram plugin. The Homebrew
  hint is `brew install bash ripgrep git python@3`. `install.sh --probe` now
  reports the Python and bash versions and exits 10 when one is too old.
  `kb-doctor install-health` requires the same tools and reports a missing
  optional one as info.
- **Install explains Telegram and the scheduled tasks.** It says that the
  brief, retro, digests and review buttons read `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` from `~/knowledge/personal/.secrets`, how to find your
  chat id (message your bot, then open
  `https://api.telegram.org/bot<token>/getUpdates` and read `chat.id`), and
  that briefs are saved but not sent until both are set. The optional Claude
  Code Telegram plugin, for chatting with Claude, needs Bun and a second bot.
  Each LaunchAgent is described by what it really does. The next steps say to
  open Claude Code in a project and type `/init-kb`, and the Gemini CLI step
  and the empty `~/.gemini` folder are gone. When Python packages are
  missing, the hint names the Python in use and gives the
  `--break-system-packages` form that Homebrew Python needs.
- **A failed local voice install no longer stops the install.** The local Qwen
  question now comes after the Telegram question, so scripts that pipe
  answers by position need updating. If `kb-tts-install` fails, install warns
  with the reason and the retry command, leaves `processes.yaml` as it was and
  carries on. `install.sh --apply --audio-backend local_qwen` then finishes
  and exits 11 (partial install) instead of stopping halfway with exit 1. The
  install receipt records the audio route.
- **Claude Code loads Vepol's global instructions.** New installs write the
  Vepol block in `~/.claude/CLAUDE.md` as a real import,
  `@~/.claude/.vepol/CLAUDE.managed.md`. The old line was an HTML comment that
  Claude Code ignored. An existing block is left as it is, and install prints
  the line to put in its place.
- **Re-running install keeps your setup current.** It adds agents missing
  from `~/knowledge/.orchestrator/cli-tools.tsv` and never edits your rows; a
  commented-out row keeps that agent off. LaunchAgents installed from now on
  have `~/.local/bin` at the end of their `PATH`, so agent CLIs from native
  installers are found. Session capture clones `claude-memory-compiler` at a
  pinned commit and says when `uv` is missing. `requirements.txt` lists the
  optional Telethon and python-dotenv packages for the Telegram people
  collector and the multi-bot runtime.
- **Scheduled Claude runs use your account's default model.**
  `kb-orchestrator-run` no longer passes `--model claude-opus-4-7`. Set
  `CLAUDE_MODEL` (or `CODEX_MODEL` for Codex) to choose a model; for scheduled
  runs, put it in the LaunchAgent's `EnvironmentVariables`.
- **Your Mac's time zone, everywhere.** Mail day windows, calendar reads and
  writes, follow-up reminders, task dates, idea calendar blocks and the day
  plan use `KB_TZ`, then `TZ`, then your Mac's own zone. Before, several of
  them assumed Europe/Madrid.
- **The brief and retro leave mail out until mail works.** Until a mail read
  has succeeded once, they say nothing about mail: no section and no daily
  "mail could not be checked" line. After that, a failure comes with its
  reason, including a new one for a missing Codex: install Codex and connect
  its Gmail plugin, or set `KB_CODEX_BIN`.
- **`kb-channel-send` has new exit codes and sends long messages whole.** Exit
  3 now means Telegram is not configured (it was 2) and exit 4 a failed send
  (it was 3). `kb-channel-send-audio` exits 3 instead of 20 when Telegram is
  not configured. A message longer than Telegram's limit (4096 UTF-16 units)
  is split at line breaks into as many parts as it needs, instead of two parts
  ending in "[truncated]". If your own scripts call these commands, update
  their exit-code checks.
- **`kb-search` searches more of your hub.** Besides concepts, people,
  companies, solutions and raw notes, it searches `reports/`, `sources/`,
  `briefs/`, `daily/` and `personal/`, so `kb-idea` cards are found, plus the
  `.txt` digests in the hub's and each project's `reports/`.
- **"Why it matters" in the arXiv digest is about your work.** When
  `personal/daily-research.yaml` sets neither `focus_project` nor
  `focus_context`, each paper is explained for your own work with AI agents,
  naming your live projects from `registry.md`, not for Vepol. A file that
  sets either key keeps the old wording.
- **Docs rewritten against the code.** The [README](README.md), the
  [feature reference](docs/features.md), [What is Vepol](docs/what-is-vepol.md),
  [Getting started](docs/getting-started.md), the
  [dependency matrix](docs/dependency-matrix.md),
  [Security and privacy](docs/security-and-privacy.md),
  [Health in the brief](docs/health-in-the-brief.md), the
  [People](docs/modules/people.md) and
  [Idea Intake](docs/modules/idea-intake.md) guides, the
  [Vepol Desktop](face/README.md) and [demo](demo/README.md) READMEs, and the
  guides agents follow to install Vepol ([SETUP.prompt.md](SETUP.prompt.md),
  [AGENTS.md](AGENTS.md)) describe what ships today and label what is
  experimental. The multi-bot docs are in English, and every command they tell
  you to run exists.
- **The startup bundle lists your Backlog.** Active work in the bundle now
  also lists open Backlog items, where `kb-task` and `kb-board append` put new
  tasks, after the Ready, In Progress, Blocked and Review ones: the first 10,
  then one line with the count and the `kb-board list … --status Backlog`
  command for the rest. A task added with `kb-task "…" --project my-app` now
  shows up in the next session in that project. `kb-session-start --print`
  without `--cwd` now uses the current folder when `$CLAUDE_PROJECT_DIR` is not
  set; before, it printed nothing.
- **`kb-task` prints one line, and `--json` for scripts.** A task added now
  prints `✓ Added to hub board (id: <id>)` or
  `✓ Added to project '<slug>' board (id: <id>)`; the `(via kb-board append)`
  suffix and the `{'ok': True, …}` line are gone. `kb-task "…" --json` prints
  only kb-board's JSON result; with `--calendar`, the follow-up proposal then
  goes to stderr. If your scripts read kb-task's output, update them.
- **`new-wiki` keeps your own `AGENTS.md` and adds the startup step.** On a
  project that already has an `AGENTS.md` (also through **Add project…** in
  Vepol Desktop), it keeps your text and appends one block, once, between
  `<!-- BEGIN VEPOL … -->` and `<!-- END VEPOL -->`: the project's wiki is
  `knowledge/`, and an agent with no startup context runs
  `~/knowledge/bin/kb-session-start --print --cwd "$PWD"`. A linked or
  read-only `AGENTS.md` is not changed; `new-wiki` prints the line to add.
- **`kb-rebuild-registry bootstrap` no longer overwrites your migration
  table.** When `~/knowledge/migration-2026-04-25.yaml` (or the `--out` path)
  exists, it exits 2 and says how to add a project instead. `bootstrap
  --force` rebuilds the table and keeps the old one as
  `migration-2026-04-25.yaml.bak-<date>-<time>`, but it cannot read back a
  `registry.md` that `apply` generated, so check every category, status and
  description afterwards.
- **English registry categories say what they hold.** A fresh English
  `registry.md` has the sections `lab — research and experiments`,
  `order — client work`, `pet — side projects`, `job — employment` and
  `personal / other`, and the header of a generated one names the same
  meanings. `kb-rebuild-registry check` still accepts the older header line,
  and the next `apply` writes the new one. Russian registries are unchanged.
- **Re-running install says whether the hub's `AGENTS.md` and `CLAUDE.md` are
  current.** It prints "up to date", or "differs from this version's — not
  overwritten" with a `diff` command, instead of the same warning on every
  run. It never overwrites either file.
- **Install's "Try these next" list.** It now suggests `kb-doctor
  install-health`, `kb-task`, `kb-search`, `kb-idea capture` (with the Python
  packages) and `kb-demo brief`, and no longer a plain `kb-brief`.
- **`kb-doctor install-health` checks the Python packages.** It checks that
  the `python3` on your `PATH` can import python-frontmatter, click, PyYAML
  and jellyfish. A missing one is a P1 (`install-health:python-packages-missing`)
  that names the `pip` command for your checkout's `requirements.txt`, so
  `install-health --strict` exits 1 and the installer's last step says
  "kb-doctor reported issues" until they are installed. A missing
  CoreLocationCLI is now an info line instead of a P2.
- **A brief without Telegram says `delivery: not_configured`.** The brief's
  day file (and the preview and error files) used `telegram_failed` when
  Telegram was not set up. It now says `not_configured`: nothing was sent and
  nothing was tried. As before, a run after you set up Telegram sends the
  saved brief without a new model call. If your own scripts read the
  `delivery:` line, update them.
- **Claude Code in the Vepol folder loads the agent manual.** The
  repository's `CLAUDE.md` now imports `AGENTS.md` (`@AGENTS.md`). Claude Code
  loads a project's `AGENTS.md` itself only when there is no `CLAUDE.md` or
  `CLAUDE.local.md` in the folder or above it, so an agent asked to install
  Vepol from the clone saw only a pointer to the manual.
- **When no AI agent answers, the brief says why in plain words.** `kb-brief`
  exits 1, saves no brief and sends (at most once a day, when Telegram is set
  up) "The brief was not made: no AI agent answered", one line per agent tried
  with the reason (for example "Claude Code: not signed in — run `claude`
  once to sign in."), and the log to check. A manual run, or a scheduled one
  without Telegram, prints the same text. It no longer shows `rc=75` or
  "exhausted"; `brief.log` keeps the raw error.

### Fixed
- **No Codex warning for a desktop app alone.** `kb-doctor install-health`
  raised the P1 `codex-missing` on a Mac where `~/.codex` existed but no
  Codex CLI was installed. The ChatGPT and Codex desktop apps create that
  folder, so a fresh install ended with "kb-doctor reported issues". Now the
  P1 needs `KB_CODEX_BIN` to be set, or a successful Codex run recorded by
  `kb-orchestrator-run` on this hub (`providers.codex.last_success_at` in
  `~/knowledge/.orchestrator/state.json`). Otherwise a missing Codex CLI is
  the info line `codex-optional-absent`.
- **The installer's health report starts at the top.** `install.sh` showed only
  the last 15 lines of `kb-doctor install-health`, so with a few findings the
  summary line (`P0=… P1=…`), the `## P0` heading and the first finding were cut
  off. It now shows the report from its first line; one longer than 40 lines is
  cut at the bottom, with the number of lines left out and the command that
  prints all of it. `install.log` keeps the whole report.
- **Clearer first-run lines, and the receipt records the session hooks.** A new
  `--apply` install no longer says "existing digest audio backend preserved";
  it names NotebookLM as the default for a new install. When session capture is
  not installed, the installer says it was skipped, as it does for scheduled
  tasks. The receipt's `opt_ins` line gains `session_hooks=on`, `off` or
  `unknown`: whether all three session hooks were in `~/.claude/settings.json`
  when the run finished.
- **`new-wiki` leaves a `.gitignore` that already covers the wiki alone.** In a
  git repo it now asks git (`git check-ignore`) whether `knowledge/` and
  `.kb-ignore` are already ignored, so a repo that ignores the wiki another
  way, for example with `knowledge/*` and exceptions, gets no extra line.
  Outside git it still looks for the exact lines.
- **Hub sessions start in the hub folder.** A Desktop session for the hub now
  runs inside `~/knowledge`, so the hub agent gets its own startup context, and
  **Add project…** on the hub folder opens the hub.
- **Install points to Claude Code, not the Claude desktop app** (#34). When
  `claude` is missing, `install.sh` now prints the exact install command for
  Claude Code, the command-line tool
  (`curl -fsSL https://claude.ai/install.sh | bash` or
  `brew install --cask claude-code`), and `kb-cli-offer` gives the Homebrew
  command and the setup page; the dependency docs and `AGENTS.md` say the
  same. Login hints use `claude auth login`.
- **A fresh install runs its daily routine.** `kb-planner` crashed on the
  empty `KB_FALLBACK_LAT=` line that install writes to
  `~/knowledge/personal/.secrets`, so no day plan was written and `kb-tick`
  ran no routine at all. Empty coordinates now count as not set, and a plan
  for today is always written, with default times when a lookup fails. The
  location comes from CoreLocationCLI, then `KB_FALLBACK_LAT` and
  `KB_FALLBACK_LON`, and only then from ip-api.com.
- **Routines keep going without Telegram.** Until `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` are set, the brief, the retro, the arXiv digest, Money
  Radar, daily research and the local audio digest save their output, log one
  "telegram not configured" line and exit 0, so the routines after them still
  run. Before, the brief failed on every tick and nothing after it started.
  Once Telegram is set up, running `kb-brief` again sends the saved brief
  without a new model call, and the arXiv digest keeps its messages for a
  later run.
- **The evening retro reaches Telegram.** It read only the older
  `TELEGRAM_TOKEN` key, so a retro set up with `TELEGRAM_BOT_TOKEN`, the key
  install writes, was never sent. It now uses `TELEGRAM_BOT_TOKEN` first (the
  old key still works) and sends through the same checked sender as the
  brief.
- **Morning audio in your language.** The morning digest told the model to
  write Russian for every user, and its titles, captions, weekday names,
  sources heading, failure alert, NotebookLM notebook name and NotebookLM
  prompts were Russian for everyone. All of it now follows your profile
  language, English by default; a Russian profile keeps the same titles,
  captions and narration rules. This month's NotebookLM notebook is still
  found after the rename.
- **The local Qwen voice works.** The audio digest asks
  `kb-tts-render --check` whether the voice is ready, but that option did not
  exist, so every local audio digest was marked unavailable. `--check` now
  checks what `kb-tts-install` set up without downloading or loading the
  model, and `--language` defaults to your profile language instead of
  Russian. The failure alert names commands that exist (`kb-tts-install`,
  `kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend notebooklm`
  and `kb-morning-digest --force`) instead of a `kb-tts-engine` that never
  shipped. The spoken text skips the arXiv report's scores, source lists,
  authors, categories and bare links, and each NotebookLM call times out after
  120 seconds (`KB_MORNING_NOTEBOOKLM_TIMEOUT`) instead of holding up the
  schedule.
- **Switching an optional input off no longer stops the routines that wait
  for it.** A process with `when: after:<id>` whose parent is `mail-morning`,
  `mail-evening`, `learning` or `money-radar` and has `enabled: false` now
  runs at the parent's own trigger, following the chain up. With
  `mail-morning` and `mail-evening` off, the brief runs at 07:15 and the
  retro at 20:30; before, they never ran. Switching off any other step, such
  as `daily` or `retro`, still holds the steps after it for the day.
- **A long health wait no longer gets the brief killed.** `kb-tick` now tells
  each routine its time limit (`KB_PROCESS_TIMEOUT`). When the brief is still
  waiting for your health data and that limit is near, it stops before the
  model call, sends nothing, and `kb-tick` runs it again on the next tick. At
  your deadline it goes out without the health section, as before.
- **Money Radar runs on schedule once you switch it on.** Started by
  `kb-tick` without `MONEY_RADAR_PROJECT`, it ran from a folder with no
  `knowledge/` and exited with code 2. It now writes into the hub
  (`~/knowledge/sources/money-radar/` and `~/knowledge/reports/money-radar/`)
  and logs that it did. Its Claude lane finds Claude Code the standard way
  instead of only at `/opt/homebrew/bin/claude`.
- **Vepol finds Codex and Claude Code wherever a standard installer puts
  them.** Codex: `$KB_CODEX_BIN`, `~/.local/bin/codex`, your `PATH`,
  `/opt/homebrew/bin/codex`, `/usr/local/bin/codex`, so a Homebrew, npm or
  standalone install works; a copy inside an app bundle is skipped. Before,
  Codex counted only at `~/.local/bin/codex`. Claude Code: `$KB_CLAUDE_BIN`,
  your `PATH`, `~/.local/bin/claude`, `/opt/homebrew/bin/claude`,
  `/usr/local/bin/claude`, so scheduled jobs find a native install that is
  missing from launchd's `PATH`. Vepol Desktop's agent list checks the same
  places, and `kb-cli-offer` now lists Hermes.
- **The arXiv tools share one snapshot, and your research settings stay.**
  `kb-arxiv-notebooklm` and the paper lane of `kb-daily-research` read
  `sources/arxiv-learning-snapshot-<date>.md`, which `kb-learning-arxiv`
  writes; before, they looked for a file nothing wrote. The `--set-topic`,
  `--auto-topic` and `--legacy-auto-topic` options of `kb-daily-research`
  change only their own keys in `personal/daily-research.yaml` and keep the
  rest, and a run no longer creates that file.
- **A fresh hub is complete.** Install creates `~/knowledge/logs/`, fills in
  the hub's index, log, state, backlog, escalations, incidents and strategies
  pages (they kept a literal `{{PROJECT_NAME}}` and `{{DATE}}`), and writes a
  `registry.md` with an empty table per category, in English or, for a
  Russian profile, in Russian. `kb-rebuild-registry bootstrap` works on it;
  without a `registry.md` it explains what to create and exits 2 instead of
  crashing. `kb-spawn-project` finds the path column by its header, so the
  tables `kb-rebuild-registry apply` writes work too, and without a
  `registry.md` it says so and exits 3 instead of crashing.
- **`kb-doctor` is accurate on a fresh install.** Accepting scheduled tasks no
  longer gives two P0 findings for the optional `channel-telegram` and
  `multibot-supervisor` LaunchAgents; they are info now (refresh an older
  manifest with `~/knowledge/bin/kb-bootstrap-manifest --force`). Missing Node
  or Bun, `kb-seed-sync`, `GEMINI.md` or `_template/CLAUDE.md`, and a new
  project's empty task board no longer count as problems. A missing session
  hook now tells you to run `~/knowledge/bin/kb-claude-hooks --apply`, and
  `kb-doctor agent-entrypoint --strict` exits 1 on a P1, as the hub contract
  says.
- **`uninstall.sh` removes everything it should and lists what it leaves.** It
  unloads and removes six LaunchAgents: `tick`, `planner`,
  `orchestrator-cycle`, `people-review-bot`, `channel-telegram` and
  `multibot-supervisor`; the last three used to stay loaded. It recognizes
  both forms of the Vepol block in `~/.claude/CLAUDE.md` and warns, instead of
  reporting success, when it cannot. At the end it lists what it leaves on
  purpose and how to remove each: the hooks and status line in
  `~/.claude/settings.json`, `~/.claude/statusline-command.sh`,
  `~/claude-memory-compiler`, the local Qwen voice and
  `~/.claude/channels/telegram/`.
- **`kb-codex-cleanup` stops only Vepol's own processes.** It stops leftover
  Codex helper processes (the `codex-companion` brokers an interrupted Codex
  review can leave holding a folder) only when they serve the hub or a linked
  project's `knowledge/` folder, and it finds duplicate Claude Code Telegram
  plugins by the plugin's path. Before, it stopped them for any folder and ran
  `pkill -9 -f 'bun server\.ts'`, which killed any Bun `server.ts` process on
  your Mac. Each stop is TERM first, then KILL after about 3 seconds. A
  broker serving a folder whose name only starts like the hub's (for example
  `~/knowledge copy`) is left alone; when a broker's folder name contains a
  space, it is stopped only if its real working folder is the hub, a folder
  under it or a linked project's `knowledge/`.
- **Multi-bot runtime (experimental): stopping a run stops only that run.**
  When a run went silent for too long or got `/stop`, the supervisor sent its
  stop signals to pid -1, which reaches every process you own. It now signals
  only the agent's own child process (SIGTERM, then SIGKILL after up to 5
  seconds) and refuses pid 1 or below, itself and its parent. Agents with
  `runtime: codex` now start (they crashed at spawn), the supervisor finds
  Claude Code in `~/.local/bin`, and `kb-multibot-setup` ends by pointing to
  `kb-multibot-add <token>` instead of a `kb-init-agent` that never shipped.
- **The multi-project cycle (experimental) waits until you set it up.**
  `kb-orchestrator-cycle` runs a morning plan and an evening retro for the
  projects you opt in. On a hub where it was never set up, its 07:30 and 20:45
  runs log one line on how to enable it and exit 0 instead of failing twice a
  day. With `KB_AUTONOMY_GATE_INPUT` or `KB_AUTONOMY_GATE_DEEP=1` set and no
  `_kb_autonomy` safety scanner (Vepol does not ship one), `retro` and `plan`
  refuse at the start with exit 75 instead of stopping halfway. Project retros
  read the day's plan from `~/knowledge/daily-plan/<date>.md`, where it is
  written.
- **`kb-idea` really checks for duplicates.** Triage compares the card's title
  with every other idea card and writes down what it found, instead of
  claiming a check it never ran. New cards no longer mention a
  `personal/priority-profile.md` that does not exist.
- **Session capture stays quiet when you declined it.** `kb-session-end` and
  `kb-pre-compact` exit silently when `~/claude-memory-compiler` is not
  installed.
- **The setup skills match the installer.** The `orchestrator-setup` skill
  drives `install.sh`'s agent modes and follows `SETUP.prompt.md`; it used to
  clone another repository and cite files that do not ship. The `init-kb`
  skill no longer expects a project `CLAUDE.md`.
- **Vepol Desktop: the demo adds projects, and About shows the right
  version.** **Add project…** works in `face/demo.sh`, and
  `face/desktop/build.sh` stamps the built app with the version in `VERSION`;
  the About box said 1.1.0.
- **Upgrading keeps the extras you already have.** `upgrade.sh` re-runs
  `install.sh --apply` without answers for the extras, and the installer took
  that as "declined": it recorded installed scheduled tasks and session capture
  as switched off, so `kb-doctor` and the install receipt reported them off.
  Extras that are already installed are now kept as they are; an explicit
  `VEPOL_ENABLE_LAUNCHD=0` still declines.
- **`kb-demo` works on a private copy, and `kb-demo task` works.** The demo
  commands now run against a copy of `demo/knowledge` in
  `~/.vepol/demo-knowledge` (`kb-demo reset` starts it over), so trying the
  demo never changes files in your clone, which `upgrade.sh` would then refuse
  to update. `kb-demo task` failed because the demo hub has no `bin/`; it now
  adds the task to the copy's board. `kb-demo retro` prints the retro instead
  of sending it, as `kb-demo brief` already did.
- **`kb-rebuild-registry apply` handles a project with no description.** A
  project added without one (`new-wiki <path>` with no fourth argument, or
  **Add project…**) made `apply` stop with `KeyError: 'description'`. It now
  keeps the description line already in the project's README.
- **`kb-execute-next` sends the task to Claude Code again.** Its direct
  Claude lane, used for a project path that is not registered in the hub,
  put the prompt after `--add-dir` and `--allowedTools`, which read it as one
  more value, so Claude ran with no task. It now runs
  `claude -p <prompt> --add-dir <project> --permission-mode acceptEdits --allowedTools Bash`
  and finds Claude Code the standard way, including under launchd's `PATH`.
- **`kb-doctor mcp-check` finds Claude Code where calendar reads do.** It
  looked only on your `PATH` and reported a P0 "MCP-first sources cannot run"
  while calendar reads worked. It now checks `$KB_CLAUDE_BIN`, your `PATH`,
  `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`.
- **`kb-idea` and `kb-contact` name a missing Python package.** Instead of a
  traceback, they print one line with the package, the Python that lacks it
  and the `pip` command, and exit 1.

### Security
- **A minimal Claude Code settings file for new installs.** When
  `~/.claude/settings.json` does not exist, install writes only what Vepol
  needs: reading `~/knowledge`, running `~/knowledge/bin` commands, the three
  session hooks and the status line. It no longer grants blanket `Bash`,
  `Read`, `Edit` and `Write` or a list of web hosts, and no longer adds
  plugins, a theme, a sound on stop or a Bash hook that pointed at a script
  Vepol does not ship. Background Claude runs that must write (the project
  cycle's report for each project, `kb-execute-next`, `kb-spawn-project` and
  chat turns in Vepol Desktop)
  pass `--permission-mode acceptEdits --allowedTools Bash` themselves, so
  they keep working; the brief and the retro run Claude read-only (see
  below). This applies only when install creates the file; an existing one is
  not replaced.
- **Your Telegram bot token stays out of agents and process lists.**
  `kb-brief` exported the `TELEGRAM_*` values into the environment of the
  agent that writes the brief; now only the sender gets them. `kb-retro` no
  longer runs `.secrets` as shell code: it reads the five keys it needs as
  data, as `kb-brief` does. The retro and `kb-channel-send` no longer put the
  token on a `curl` command line, where any process list could show it.
- **`kb-search` never searches secrets.** Now that it searches `personal/`, it
  skips files named `.secrets`, `.env`, `*.token`, `token.json` and similar,
  in every folder.
- **The opt-in Grok check in the arXiv digest is read-only.** With
  `social_check: grok`, Grok runs with `--deny write --deny edit --deny bash`,
  as in Money Radar.
- **Only background Claude runs that must write can edit files and run
  commands.** `kb-orchestrator-run` has a new `--allow-edits` flag. Without
  it, its Claude lane runs with `--disallowedTools Bash,Edit,Write,NotebookEdit`,
  which wins over your settings, so the brief's and the retro's Claude
  fallback cannot edit files or run commands; everything else still follows
  your Claude Code settings. With it (the project cycle's report for each
  project, `kb-execute-next` and `kb-spawn-project` in text mode), Claude runs
  with `--permission-mode acceptEdits --allowedTools Bash`: edits are accepted
  in the job's folders, and Bash may run any command, in any folder. In 1.1.1
  these runs passed no permission flags and used only your own Claude Code
  settings. The Codex lane is unchanged and runs with approvals and the
  sandbox off for every job. Vepol Desktop passes the flag on every one-shot
  run (a session from an earlier version, or the legacy `./run.sh` page), so
  Claude there can still edit files and run commands. When the runner fails
  without an answer and Desktop retries Claude directly, that retry passes no
  permission flags and follows your own Claude Code settings.

## [1.1.1] — 2026-10-05

A fix release for the first five minutes after install and for honest failure
reasons. The stable core keeps its contracts; `upgrade.sh` now follows release
tags (below). ([v1.1.1](docs/releases/v1.1.1.md))

### Fixed
- **`kb-doctor` is green on a correct fresh install.** A hub with no projects
  yet reports one info line («no projects registered yet — create one with
  new-wiki») instead of a P0. A registry whose rows are present but unparseable
  still reports the P0.
- **`kb-demo brief` is built from the demo wiki.** `kb-brief` now finds its
  helpers (agenda, mail, ideas, preflight, sender) next to itself when the hub
  has no `bin/`, so the demo prompt carries the demo projects instead of empty
  fallbacks. `kb-demo` keeps the demo synthetic: the calendar reader is disabled
  and `brief` runs dry (prints the brief, delivers nowhere).
- **Portable Python.** `kb-orchestrator-cycle` and the
  `kb-multibot-*` scripts use `#!/usr/bin/env python3` instead of Apple's
  `/usr/bin/python3`, which exits 69 until the Xcode licence is accepted.
- **`new-wiki` speaks English and fails clearly.** A missing folder gives
  `new-wiki: folder not found: <path>` and exit 1 with nothing created. It no
  longer writes a project `CLAUDE.md`: Claude Code 2.1.277+ reads `AGENTS.md`
  directly, and a `CLAUDE.md` anywhere above a project disables that.
- **Failure reasons are the real cause.** A shared rule (`_kb_failure_reason.py`)
  picks the quota / unsupported-model / auth / network / timeout line out of a
  provider's output instead of the first or last line. The orchestrator broker
  records it as `reason_code`, treats Codex's «you've hit your usage limit» as a
  rate limit with the real «try again at …» reset time (and Gemini «retry in …»
  hints), and records an empty Codex answer as a failure, not a success. The
  mail reader reports `gmail_unavailable:quota` / `:model`, the calendar reader
  prefixes its error with `quota:` / `model:`, and the brief says why mail is
  unavailable and for how many days in a row.

### Changed
- **`upgrade.sh` upgrades to the newest release tag** (`vX.Y.Z`, pre-release
  tags skipped) instead of pulling the tip of `main`; `--check` compares the
  current release with the newest tag. A clone with local edits still stops with
  the manual-resolve message.

Not in this release (live on the maintainers' hub, ships with the next full
sync): bounded quota-aware retries in `kb-tick`, the local-Qwen voice fallback
in the morning digest.

## [1.1.0] — 2026-10-01

Vepol Desktop only. The stable core, the other `kb-*` commands and
`processes.yaml` are unchanged.

### Added
- **Memory.** Vepol Desktop opens on Memory: one card per knowledge base, the
  hub first, then each project by latest activity, with a status (Up to date,
  Needs review, No state file), what is happening now (`state.md`), what is
  next (`kb-board`), the last decision and the last activity. Read at request
  time from files that already exist; nothing new is required in the knowledge
  layout. ([v1.1.0](docs/releases/v1.1.0.md))
- **Project screen.** A click on a project in the sidebar or on its Memory card
  opens one screen for it: a State box (the snapshot from `state.md`, the next
  task, when `state.md` changed, and «Show full state»), the project's sessions
  with their states in colour (waiting for you or running first; a click opens
  the session in a tab), its tasks as a read-only board (In Progress, Review,
  Blocked, Ready, Backlog; Done folded), then decisions, history, lessons and
  files. It refreshes every 30 seconds while shown.
- **Any project, or a new one.** «+ New session» asks for the project: the hub
  and every project linked into it, most recent activity first, with search.
  «Add project…» opens the macOS folder panel and turns the chosen folder into a
  Vepol project through the hub's `new-wiki`, which adds what is missing and
  never overwrites a file; the session starts there.
- **More agents in the terminal.** Besides Claude Code and Codex, the in-app
  terminal starts agy (Antigravity), Hermes, OpenCode and Grok, chosen from the
  installed agents in the hub roster; their availability is shown but never
  blocks. Every agent is shown as its icon (sources and licences in
  `face/vepol_face/static/vendor/agent-icons/LICENSE.md`).
- **Tabs.** Every opened session is a tab. Closing a tab stops nothing, and the
  same tabs come back after you quit and reopen the app.
- Knowledge is rendered as Markdown (vendored marked 16.4.2 and DOMPurify
  3.4.10, served locally; raw HTML and images are dropped).
- A sample workspace in `demo/workspace/` and `face/demo.sh`, which opens it on
  port 8782 with its own state and tmux server, apart from your own data.

### Changed
- The sidebar holds the app's sections and lists projects only; a green dot
  marks a project where an agent is running.
- The in-app terminal runs your login shell and types the agent command into
  it, so leaving the agent drops back to a working prompt. When the agent
  exits, the terminal says so and Start opens a new one for the session on
  screen; nothing restarts on its own.
- Claude terminal sessions take their title from Claude's own transcript
  (`/rename`, then Claude's generated title, then the first prompt) instead of
  «(new conversation)».
- The session header follows the agent's start and exit within a second.
- Claude is started from its native install (`~/.local/bin/claude`) before a
  Homebrew copy, so `claude update` takes effect.
- The session side tab «Knowledge» is now «Memory»; `kb-board` lock files are
  no longer listed in it.

### Fixed
- The app icon is drawn on the exact macOS icon shape, so macOS 26 no longer
  shows it as a small V inside a grey tile.

## [1.0.0] — 2026-09-26

### Added
- **Vepol Desktop** — a native macOS app under `face/`. Your agent runs as an
  ordinary interactive session in a real terminal inside the window (xterm.js
  over a local bridge to a per-project tmux session, one per project and
  runtime); the agent starts only on your click, opening a session only
  attaches, and closing the window or quitting the app leaves the agent running
  for the app to re-attach. Around the terminal: a session board with five
  manual stages (drag and drop, search, project filter, «+» per column), a
  **Tasks** view of every project's `backlog.md` read through `kb-board` with
  «Start session», an **Automations** view of every scheduled process with
  state, reason, last and next run, 14-day history and output tails (plus Hermes
  cron jobs, and the `com.knowledge.backup` launchd job when it is loaded or
  installed), a project → sessions tree with a read-only **Knowledge**
  explorer, and a status bar with Claude and Codex plan usage from local files
  only. Loopback-only backend; the per-launch token stays in memory. English UI.
  Built from source with the Command Line Tools; ad-hoc signed, not notarized.
  Python dependencies in `face/requirements.txt`.
  ([v1.0.0](docs/releases/v1.0.0.md))
- **`kb-runtime-registry`** — shows which agent CLIs can actually work right
  now. Eight tri-state fields per runtime (`installed`, `authenticated`,
  `quota_available`, `healthy`, `resumable`, `interactive`, `web_current`,
  `edit_capable`); `available` only after a successful known-answer probe or
  orchestrator run in the last 24 hours with no active cooldown; `unknown`
  renders as degraded.
  `--report` never spends quota, `--probe [<runtime>…]` records one known-token
  check and refuses to run inside an agent session (exit 3), `--json` validates
  against the shipped schema. Hermetic `runtime-registry` leg in
  `tests/run-all.sh`; live smoke in `tests/runtime-registry/live-smoke.sh`.
- `hermes` (Nous Research Hermes Agent) joins the agent roster in
  `bin/cli-tools.tsv` — seven runtimes in total.
- The durable Claude launcher `bin/kb-claude-run` ships with the package.

### Changed
- **The startup context arrives whole.** `kb-session-start` drops the
  per-section caps; the bundle budget is 250,000 characters and content is
  trimmed only above it, with the trimmed slice named. The bundle opens with a
  short recovery block and ends with
  `KB-STARTUP-BUNDLE-END v1 chars=<N> sha256=<H>`, so a complete bundle can be
  told from a cut one. Each slice reports `present`, `clipped`, `omitted`,
  `empty` or `missing`, computed after assembly; the old `included` status is
  gone. New `tests/startup-context/delivery-contract.py`.
- **`kb-doctor seed-content-audit` fails closed.** It proves the seed directory
  is its own git repository root, enumerates tracked files NUL-separated with
  inherited `GIT_*` variables removed, and turns any failure to enumerate
  (non-zero exit, timeout, launch error, undecodable output) into a blocking
  P1 `no-git` finding that names the cause. A missing seed directory and an
  empty but proven repository stay silent.
- **Specification review is now one lightweight, code-aware pass.** One
  independent reviewer reads the spec and relevant code/API, then returns
  `GO`, at most three questions, or a proven logical `BLOCK`. Repeated
  exact-hash review, Layer 1/Layer 2 passes, mandatory implementation review,
  and automatic Codex stop-time review have been removed. RED/E2E tests, owner
  approval, live smoke, evidence, and `kb-doctor` remain mandatory.
- **Specs are capped at 150 lines** and must answer four questions — what we do,
  how it works (every branch named), what is out of scope, how we check it.
  Review rounds, superseded hashes and research live in the knowledge base and
  are linked, not kept in the spec. The old mandatory section list is retired.
- `new-wiki` no longer enables the Codex stop-review gate in new projects.
- `kb-orchestrator-run` runs its Claude lane through the durable runner and
  waits for natural exit, with no wall-clock timeout.
- Versioning: from 1.0.0 on, incompatible changes to the stable core — the
  knowledge folder layout, the `kb-board` file format and commands, and
  install/upgrade — come only with a major version. Other `kb-*` commands and
  `processes.yaml` may change within 1.x with a note here (see the preamble
  above).

### Fixed
- Resumed Codex sessions no longer exit on the second turn
  (`codex exec resume` is no longer passed `-C`).
- `tests/run-all.sh` no longer sends prompts to installed agent CLIs or writes
  to the user's run history: `broker-race.py` runs `kb-orchestrator-run`
  against fake `claude`/`codex` programs, and the cycle suites keep their
  durable runs inside their sandboxes (`KB_CLAUDE_RUN_ROOT`). The install legs
  still ask the installed `codex` for its version.

### License
Vepol 1.0.0 converts to MIT on **2028-09-26**.

## [0.8.1] — 2026-08-14

### Fixed
- **Board writers can no longer erase your backlog.** Every `kb-board`
  mutation (and `kb-idea promote --create-task`) used to re-render the board
  from what its parser recognized and replace the whole file — so prose,
  hand-written notes, and legacy headings were dropped, and a board with no
  recognized task blocks could be replaced wholesale by a single new task,
  silently and with exit 0. Mutating writers now validate the *existing* file
  before publishing (`kb-board fmt --write` and `kb-board migrate --write` are
  the deliberate exceptions — they are the dry-run-first remedy commands): a
  non-empty board that fails `kb-board check` is refused with
  `EORIGINAL`, the offending codes, and the remedy commands, and the file is
  left byte-identical. Empty and title-only boards stay mutable so bootstrap
  still works, and a sweep with nothing to move stays a silent no-op.
  **Behavior change:** mutations on a non-canonical board now refuse instead
  of quietly canonicalizing it — run `kb-board fmt <path>` (dry run first) or
  `kb-board migrate <path>` to canonicalize deliberately.
  ([v0.8.1](docs/releases/v0.8.1.md))
- `kb-board` reports structured mutation failures instead of a Python
  traceback: `{"ok": false, "code", "message"}` with `--json`, or
  `kb-board: <code>: <message>` on stderr, exit 1.

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
  ([v0.7.2](docs/releases/v0.7.2.md))

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
  confirms no other file has the same problem. ([v0.7.1](docs/releases/v0.7.1.md))

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
  `kb-multibot-setup` / `kb-multibot-add` / `kb-multibot-remove` /
  `kb-multibot-list` CLIs, a LaunchAgent template, a Telethon group
  listener, a Bot API sender with retry/backoff, per-agent queues,
  file-lock serialization, stdout-silence watchdog, four loop guards
  (cooldown / depth / fan-out / hourly quota), and 154 unit
  tests. Concept and spec at
  [`docs/methodology/multibot-agent-runtime.md`](docs/methodology/multibot-agent-runtime.md).
  (Corrected later: this entry first named `kb-init-agent` and
  `kb-deactivate-agent`, design names that never shipped. The release
  shipped `kb-multibot-add`, `kb-multibot-remove` and `kb-multibot-list`.)
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

[Unreleased]: https://github.com/nahornyi-ai-lab/vepol/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.8.1...v1.0.0
[0.8.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/nahornyi-ai-lab/vepol/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nahornyi-ai-lab/vepol/releases/tag/v0.1.0
