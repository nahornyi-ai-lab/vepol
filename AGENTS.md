# Vepol — setup and evolution manual for AI agents

> **You are reading this because the user asked you (Claude Code, Codex,
> Antigravity CLI `agy`, or another CLI agent with terminal access) to install
> Vepol or to keep improving it with them.** This is your operating manual.
> Read it end to end before you act.

The user does not need to learn any commands. **You** install Vepol, **you**
fix what breaks, and **you** keep growing the system with them, session after
session.
You do all of it by driving Vepol's own scripts (`install.sh`, `upgrade.sh`,
`uninstall.sh` and the `kb-*` commands), never by re-implementing them.

The step-by-step install flow is [`SETUP.prompt.md`](SETUP.prompt.md). This
manual adds the judgment around it: conflicts, prerequisites, errors,
personalization and the work after install.

## Startup context and the agent card

At the start of every session in a project that has a `knowledge/` wiki, load
the startup context before your first substantive answer or action: the
applicable agent card, `knowledge/state.md`, a recent slice of
`knowledge/log.md`, active work and open escalations, and a short incident
slice.

- In Claude Code, the SessionStart hook injects this as a `Startup Context
  Manifest`. When the manifest is present, treat the slices it lists as already
  read. Do not reread `knowledge/index.md`, the full `knowledge/incidents.md` or
  the whole backlog just to satisfy this rule.
- Without the manifest (an agent with no hooks), run
  `~/knowledge/bin/kb-session-start --print --cwd "$PWD"`. Or read by hand: the
  agent card (`knowledge/agents/agent-card.md`, else
  `~/knowledge/agents/agent-card.md`, else say that none exists),
  `knowledge/state.md`, `tail -n 80 knowledge/log.md` (160 lines when that
  shows fewer than 3 dated entries), active work via `kb-board`, open
  escalations, and the `## Prevention rules` and `## Ongoing` sections of
  `knowledge/incidents.md` when present.
- `knowledge/index.md` and the full `knowledge/incidents.md` are for
  navigation and diagnosis on demand, not for startup.
- Load the card at session start. Do not wait for a "who are you" question;
  that question only uses the card's `## Self-introduction`, which you already
  read.

Before Vepol is installed there is nothing to load. A fresh clone of this repo
has none either: its `knowledge/` folder holds only the hub contract's source
files (`AGENTS.md`, `CLAUDE.md`), which the installer copies to `~/knowledge`.
Go straight to Phase 1.

## Agent card and state contract

`agent-card.md` is the project role's full passport, loaded at startup. Do not
clip it on purpose. It holds the project's identity, scope, boundaries, skills,
subagents and runtime notes. General workflow rules belong in `AGENTS.md`, not
copied into every card.

`knowledge/state.md` is the current-state dashboard, not a log or an archive.
Keep it in the present tense and overwrite it: when reality changes, write the
event to `knowledge/log.md` and replace the stale line in `state.md`. Dates of
past events, finished work, test and review proof, resolved blockers and old
snapshots belong in `log.md`, `reports/`, `decisions/`, `sources/` or a
thematic page. Current deadlines, active offers, metric timestamps, source
freshness and the `Last Updated` date may stay.

## Your role in three sentences

1. **Set up Vepol cleanly on the user's Mac**: read this file, check the
   prerequisites, run the installer's agent modes, handle errors as they
   appear and verify that the result works.
2. **Personalize it during setup**: ask the fewest useful questions, look at
   what is on disk (with care, see § 2.1) and connect Vepol to the user's real
   projects and routine.
3. **Keep evolving it with the user after install**: in every session, look
   for a skill worth adding, a project worth giving memory, a recurring pattern
   worth writing down, or drift worth cleaning up.

## What Vepol is (so you can explain it plainly)

Vepol is a personal AI assistant that lives on the user's Mac. It remembers
every project, plans the day and runs the daily routine through the agents the
user already has, and it writes everything down in plain Markdown that stays
theirs.

It is not a model. It is a layer of files and scripts around ready-made
agents. Claude Code, Codex, Antigravity, Hermes, OpenCode and Grok do the
reasoning. Vepol gives them one shared memory, a scheduler, logs and a task
board, so they work as one assistant instead of starting every chat from zero.

Use these framings when you explain what the user gets:

- **Works right after install:** the hub `~/knowledge` and one `knowledge/`
  folder per project; startup context in Claude Code (session hooks);
  `kb-search`; the task board (`kb-task`, `kb-board`); ideas (`kb-idea`);
  people cards (`kb-contact`); the demo (`kb-demo`); the health check
  (`kb-doctor`); `upgrade.sh` and `uninstall.sh`. `kb-idea` and `kb-contact`
  need the Python packages from `requirements.txt` (§ 1.2).
- **On once the user answers yes to "Install scheduled tasks?":** the morning
  brief, the evening retro, mail summaries, the daily arXiv learning digest,
  the morning and evening audio digests, and the nightly `state.md` refresh.
- **Needs the user's own account or source:** a Telegram bot (delivery), Gmail
  through Codex, Google Calendar through Claude Code, a NotebookLM sign-in or
  the local Qwen voice (audio), a daily health JSON from their own sync
  (Garmin, Apple Health, …), and Codex for second opinions and failover.
- **Switched on later, when the user wants it:** Money Radar, people
  proposals, follow-up reminders, daily research on a schedule.
- **Experimental:** the multi-project nightly cycle and plan dispatch, the
  auto-executor (`kb-execute-next`), the evolution loop (`kb-evolution`) and
  the multi-bot Telegram runtime.
- **Direction, not shipped (never promise it):** autonomy that grows as the
  user's corrections drop, a strategy file that updates itself, health data
  that sets the day's intensity beyond the brief's one suggestion, and Pro
  modules.

Where things live after install:

- `~/knowledge/` is the hub. It holds `AGENTS.md` (the hub contract every
  agent follows), `CLAUDE.md`, `state.md`, `log.md`, `backlog.md`,
  `registry.md` (the project list), `strategies.md`, `personal/` (private
  settings: `.secrets`, `profile.yaml`, `processes.yaml`), `projects/` (a link
  to each project's `knowledge/`), `briefs/`, `logs/` and `install/receipts/`.
- `~/knowledge/bin/` holds every `kb-*` command as a link into this repo, so
  the repo must stay where it is.
- `~/.claude/CLAUDE.md` gets a short managed block that imports
  `~/.claude/.vepol/CLAUDE.managed.md`, a small adapter that loads the hub
  contract into every Claude Code session. The user's own text in that file
  stays. Project context reaches Claude Code through the SessionStart hook in
  `~/.claude/settings.json`.
- `~/.claude/skills/` gets three skills: `init-kb`, `development-loop` and
  `orchestrator-setup`.
- `~/Library/LaunchAgents/com.knowledge.*.plist` holds the four scheduled
  tasks, only if the user said yes to them.

The morning brief, the evening retro and the project cycle run their model
call through `kb-orchestrator-run`, which tries Codex first and falls back to
Claude Code when Codex is missing, signed out, rate-limited or returns
nothing. `KB_ORCHESTRATOR_BACKENDS` changes the order. A few routines pick
their agent themselves: the arXiv digest asks Claude first and Codex second,
and mail is read only through Codex.

### The task board

The task board is plain Markdown. `knowledge/backlog.md` is the single source
of truth, and you change it through `kb-board`, never through a database or an
old one-line writer. The statuses are `Backlog`, `Ready`, `In Progress`,
`Blocked`, `Review`, `Done` and `Cancelled`; `Review` is where work waits for
verification.

```bash
~/knowledge/bin/kb-board check ~/knowledge/projects/<slug>/backlog.md
~/knowledge/bin/kb-board append ~/knowledge/projects/<slug>/backlog.md "<title>" --status Ready --plan-item-id <id> --actor <agent>
~/knowledge/bin/kb-board claim ~/knowledge/projects/<slug>/backlog.md --plan-item-id <id> --actor <agent>
~/knowledge/bin/kb-board heartbeat ~/knowledge/projects/<slug>/backlog.md --plan-item-id <id> --claim-id <claim_id> --actor <agent>
~/knowledge/bin/kb-board request-review ~/knowledge/projects/<slug>/backlog.md --plan-item-id <id> --claim-id <claim_id> --actor <agent>
~/knowledge/bin/kb-board close ~/knowledge/projects/<slug>/backlog.md --plan-item-id <id> --claim-id <claim_id> --outcome closed --actor <agent>
```

For a quick task, `~/knowledge/bin/kb-task "text" [--project <slug>]` appends
one to the Backlog of the hub board, or of that project's board, and prints
`✓ Added to … board (id: <plan_item_id>)`; `--json` prints only kb-board's JSON
result. The next session's startup bundle lists open Backlog items after the
Ready, In Progress, Blocked and Review ones (the first 10).

### The spec gate for non-trivial work

Non-trivial work follows one path: research -> one lightweight independent
spec review -> owner-approved spec -> `knowledge/spec-approvals.md` with the
exact `spec-contract` hash (a SHA-256 fingerprint of the approved spec) ->
build plan -> RED tests with mandatory E2E path (tests written first, which
fail until the code exists) -> implementation. The owner can approve in chat;
you write the approval down for them. A changed hash alone
does not restart review. Material drift in the scenario after approval goes
back to one lightweight review and the owner's approval.

## Phase 1 — Initial setup

Follow [`SETUP.prompt.md`](SETUP.prompt.md) step by step. The sections below
explain each check and what to do when it fails.

### 1.1 Verify the user actually wants Vepol, then check for conflicts

Before anything that writes to `~/knowledge/`, installs LaunchAgents or
changes `~/.claude/`, **confirm the user wants Vepol on this Mac.**

**Check for an existing `~/knowledge/`.** If it exists, classify it before you
run `install.sh --apply`:

- Run `ls -la ~/knowledge/` and look for Vepol markers: `bin/kb-tick`,
  `_template/`, `AGENTS.md` (the hub contract) and the `orchestrator-seed`
  link back to the repo. If they are there, this is an earlier Vepol install.
  Re-running the installer is safe: it keeps every file the user owns,
  refreshes the managed links, templates, skills and Claude adapter, and adds
  only what is missing.
- `./install.sh --probe --json` exits 11 when `~/knowledge` exists but has no
  Vepol commands linked. That means an earlier install stopped halfway, or the
  folder belongs to another tool.
- If the markers are absent, this `~/knowledge/` belongs to a different
  system. **Stop and offer the user three options:**
  1. Move it aside to a dated backup, then install fresh (your default when the
     contents look unrelated to Vepol):
     `mv ~/knowledge ~/knowledge.backup-$(date +%Y%m%d-%H%M%S)`
  2. Install into it, only after the user confirms. Walk them through what the
     installer does there: it creates missing folders and files, links the
     `kb-*` commands into `bin/` (replacing files of the same name), refreshes
     `_template/` and `security/scanner-signatures/`, and moves any real folder
     that stands where a managed link goes aside with a `.pre-vepol.<time>`
     suffix. It leaves an existing `AGENTS.md`, `CLAUDE.md`, `log.md`,
     `state.md`, `index.md`, `backlog.md`, `registry.md` and the files in
     `personal/` as they are. In `personal/` it only tightens file modes, and
     it rewrites the audio digest blocks of `processes.yaml` only when you
     pass `--audio-backend`.
  3. Stop and install later. A different hub folder is not an option yet:
     `install.sh --apply` refuses a custom `VEPOL_HUB` (only `--probe`,
     `--dry-run` and `--verify` accept it).
- After the install, record the choice as one line in `~/knowledge/log.md`.

**Check `~/.claude/settings.json`.** The installer never replaces an existing
file with its template. On an existing file it does two things:

- It looks for legacy bypass-permission keys
  (`permissions.defaultMode: "bypassPermissions"`,
  `skipDangerousModePermissionPrompt: true`). The probe reports them as
  `needs_security_migration`. The fix needs the user's explicit OK (step 6 of
  `SETUP.prompt.md`).
- It checks Vepol's three session hooks (SessionStart, SessionEnd,
  PreCompact) and adds the missing ones only with consent: the interactive
  question, or `VEPOL_MERGE_HOOKS=1` with `--apply`. That runs
  `~/knowledge/bin/kb-claude-hooks --apply`, which writes a timestamped backup
  (`settings.json.bak-YYYY-MM-DD-HHMMSS`), appends only the missing hook
  entries and leaves permissions and every other key alone. Before you ask,
  show the user what gets added: three commands,
  `bash ~/knowledge/bin/kb-session-start`, `kb-session-end` and
  `kb-pre-compact`.

The installer stops if the file contains `//` or `/*` comments (strict JSON
only). It skips both checks, with a warning, if the file does not parse. When
there is no `settings.json`, the installer creates a minimal one: read access
to `~/knowledge`, permission to run `~/knowledge/bin` commands, the three
hooks and a status line.

**Check `~/.claude/CLAUDE.md`.** If it has real content, confirm with the user
that Vepol may add its managed block at the top; everything else in the file
stays. A block written by an older installer carries an HTML-comment line that
Claude Code does not load. The installer leaves it and prints the replacement
line, `@~/.claude/.vepol/CLAUDE.managed.md`. Offer to make that one-line edit.

### 1.2 Check prerequisites

`./install.sh --probe --json` reports the macOS version, the required tools,
their versions and most optional tools without changing anything. It does not
look for `notebooklm`, `tmux` or the Python packages.
`prereqs_missing_required` and `prereqs_version_problems` block the install
(exit 10); `prereqs_missing_optional` does not.

Required:

- macOS 13 or later (the only supported platform)
- Claude Code, the command-line tool `claude` (the Claude desktop app does not
  provide it). Vepol finds it through `$KB_CLAUDE_BIN`, your `PATH`,
  `~/.local/bin`, `/opt/homebrew/bin` or `/usr/local/bin`.
- `git` and ripgrep (`rg`)
- Python 3.10 or later as `python3` (the session hooks need it)
- bash 5 or later (macOS ships 3.2; a Homebrew bash counts)

Optional (each one adds a feature; the install never needs them):

- `codex`: cross-agent review, second opinions, mail reading, and the first
  choice for the morning brief and evening retro (they fall back to Claude
  Code). Vepol finds it through `$KB_CODEX_BIN`, `~/.local/bin/codex`, your
  `PATH`, `/opt/homebrew/bin/codex` or `/usr/local/bin/codex`.
- `uv`: automatic session capture and the local Qwen voice install
- `jq`: the Claude Code status line
- `gh`: GitHub work from agent sessions (PRs, issues, releases)
- `node`: installing agent CLIs with npm; no `kb-*` script runs it
- `bun`: only Claude Code's own Telegram plugin
- `agy` (Antigravity CLI): an independent third opinion
- `grok` (Grok CLI): current social and news research
- `notebooklm` (`pipx install notebooklm-py && notebooklm login`): the default
  route for the audio digests, and research notebooks, in the user's language
- `tmux`: the terminals in Vepol Desktop (§ 1.8)

`~/knowledge/bin/kb-cli-offer --list` prints every agent CLI Vepol can use
and how to install it.

Python packages are checked, not installed. Without them `kb-idea`,
`kb-contact` and the people tools fail. Check with
`python3 -c "import frontmatter, click, yaml, jellyfish"`.

If something is missing:

- **Do not install Homebrew or any other package manager.** That decision is
  the user's.
- Show the exact command and wait for the user to run it. The installer prints
  the same ones:

  ```bash
  # Required tools (Homebrew):
  brew install bash ripgrep git python@3

  # Claude Code, the command-line tool:
  curl -fsSL https://claude.ai/install.sh | bash
  # or: brew install --cask claude-code

  # Python packages (kb-* scripts use the python3 on PATH; a separate venv is not picked up):
  python3 -m pip install --user -r ~/vepol/requirements.txt
  # if pip reports "externally-managed-environment":
  python3 -m pip install --break-system-packages -r ~/vepol/requirements.txt

  # Codex CLI (optional): any one of
  npm i -g @openai/codex
  brew install --cask codex
  ```

- Re-run `./install.sh --probe --json` after each fix.

If you are unsure whether a tool is there (it may sit outside `PATH`), check
explicitly before you call it missing.

### 1.3 Locate or clone the repo

If the user runs you from inside a Vepol clone, use that path. Otherwise ask,
then:

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
```

The default location is `~/vepol`. If the user wants another path, use it.
Wherever it is, it stays there: every command in `~/knowledge/bin/` is a link
into it.

### 1.4 Run the installer

Drive the installer's agent modes in the order `SETUP.prompt.md` gives. The
read-only modes print JSON and change nothing.

| Command | What it does | Exit codes |
|---|---|---|
| `./install.sh --capabilities --json` | Lists the modes, opt-in variables, required tools, minimum versions and optional tools | 0 |
| `./install.sh --probe --json` | Reports prerequisites, versions, hub state and `needs_security_migration` | 0 ready; 10 a required tool is missing or too old; 11 `~/knowledge` exists without linked commands |
| `./install.sh --dry-run --json` | Shows the plan | 0 |
| `./install.sh --apply` | Installs without asking; extras come from environment variables | 0 done; 11 everything installed except the local Qwen voice; any other non-zero code: stopped, with the reason on screen |
| `./install.sh --verify --json` | Checks the core: the hub, the command links, the `orchestrator-seed` link back to the repo, the managed Claude block | 0 ok; 13 problems listed in `verify_problems` |

An unknown flag or two conflicting modes exit 2 with nothing on stdout.
`./install.sh --help` prints the usage.

Extras for `--apply` are off unless set. Set only the ones the user approved:

- `VEPOL_ENABLE_LAUNCHD=1`: scheduled tasks. Four LaunchAgents:
  - `com.knowledge.tick` (every 15 minutes) runs the routines in
    `~/knowledge/personal/processes.yaml` when they are due: mail summaries,
    the morning brief, the arXiv digest, the audio digests, the evening retro,
    and so on.
  - `com.knowledge.planner` (00:05) starts each day's record,
    `~/knowledge/logs/today-plan.json`, which tick uses to run every routine
    once a day. The routines' times come from `processes.yaml`.
  - `com.knowledge.orchestrator-cycle` (07:30 and 20:45, experimental) runs the
    multi-project cycle, only for projects with `cycle_enabled: true`.
  - `com.knowledge.people-review-bot` (always on) handles Telegram review
    buttons and stays idle until Telegram is set up.
- `VEPOL_ENABLE_MEMORY_COMPILER=1`: automatic capture of each Claude Code
  session into the project's `knowledge/daily/` notes, with one line in
  `log.md`. It clones claude-memory-compiler into `~/claude-memory-compiler`
  at a pinned commit and needs `uv`. Only Claude Code sessions are captured,
  and only in projects that have a wiki.
- `VEPOL_MERGE_HOOKS=1`: adds the three session hooks to an existing
  `~/.claude/settings.json`, with a backup (§ 1.1).
- `VEPOL_ENABLE_TELEGRAM=1`: only a scaffold for Claude Code's own Telegram
  plugin (`~/.claude/channels/telegram/.env`), which lets the user chat with
  Claude from Telegram. It needs `bun` and a second bot. The brief does not
  use it; see § 2.2 for Telegram delivery.
- `VEPOL_APPLY_C01=1`: the settings security migration. Only with the user's
  explicit OK, never on your own.

The digest audio route is a flag: `--audio-backend notebooklm` or
`--audio-backend local_qwen`. A new install starts on NotebookLM, where the
audio stays in NotebookLM. Local Qwen renders an MP3 on this Mac and sends it
to Telegram. It needs Apple Silicon, `uv`, `ffmpeg` and about 10 GiB of free
disk, and it downloads the voice model during the install. An existing install
keeps its route unless the flag is given.

What `--apply` does:

- Checks the prerequisites and stops, printing the install commands, if a
  required one is missing.
- Creates the hub `~/knowledge/` and links every `kb-*` command into
  `~/knowledge/bin/`. Installs the agent roster
  (`~/knowledge/.orchestrator/cli-tools.tsv`), appending agents the user's copy
  does not list yet and never changing existing rows.
- Creates, only when missing: the hub `AGENTS.md` and `CLAUDE.md`, the hub's
  `log.md`, `state.md`, `index.md`, `backlog.md`, `escalations.md`,
  `incidents.md` and `strategies.md`, `registry.md`,
  `personal/.secrets` (mode 600), `personal/profile.yaml` (language from the
  system locale) and `personal/processes.yaml` (the routine schedule).
- Writes `~/.claude/.vepol/CLAUDE.managed.md` and its block in
  `~/.claude/CLAUDE.md`; creates `~/.claude/settings.json` only if there is
  none; handles an existing one as § 1.1 describes.
- Installs the three skills into `~/.claude/skills/`. A `SKILL.md` that Vepol
  did not install is backed up first, never overwritten.
- Adds the extras the user approved and sets mode 600/700 on secret files.
- Writes the install manifest, runs `kb-doctor install-health --strict`,
  writes a receipt to `~/knowledge/install/receipts/<date-time>.md` and prints
  the next steps.

Its progress lines and warnings also go to `install.log` in the repo folder,
rewritten on each install run.

The interactive `./install.sh` asks instead of reading variables, defaulting
to No, in this order: the security migration (only when bypass keys are
found), the hooks merge (only for an existing `settings.json` without them),
scheduled tasks, the Claude Code Telegram plugin scaffold, the audio route
(new installs only) and session capture. `VEPOL_NONINTERACTIVE=1 ./install.sh`
answers No to all of them. As an agent, prefer `--apply` with the variables
the user approved.

The installer is safe to re-run. It keeps every file the user owns and never
removes a LaunchAgent. When you re-run `--apply`, pass the same extras again:
one you leave out is recorded as declined in the receipt.

To move to a newer release later: `./upgrade.sh` checks out the newest release
tag (not the tip of `main`, which can be ahead of it), re-runs
`install.sh --apply` and `--verify`, and passes `VEPOL_ENABLE_*`,
`VEPOL_APPLY_C01` and `VEPOL_MERGE_HOOKS` through, so give it the same extras
as the install. `./upgrade.sh --check` only reports.

To undo an install: `./uninstall.sh --dry-run` lists what it would remove, and
`./uninstall.sh --yes` removes it without a prompt (run it only with the
user's OK; `--backup-user-data` first packs the hub into a dated `.tgz` in the
home folder). It removes only Vepol's managed files: the command links, the
managed Claude block and file, the skills and the LaunchAgents. It never
deletes the hub. At the end it lists what it left in place on purpose (the
hooks in `settings.json`, the status line script, `~/claude-memory-compiler`,
the local Qwen voice, the Telegram plugin folder) and how to remove each. If
`uninstall.sh` is missing, stop: never delete anything by hand.

### 1.5 Handle errors as they arise

The installer says what failed. Common cases:

- **A required tool is missing or too old.** The installer prints the install
  commands and stops. Show them to the user, wait, probe again. If Homebrew
  itself is missing, the installer prints its official one-line installer;
  the user runs it, not you.
- **`~/.claude/settings.json` has comments.** The install stops: "Strict JSON
  only". The user removes the comments (or approves your edit after a backup),
  then re-runs.
- **`~/.claude/settings.json` does not parse.** The install continues but
  skips the security check and the hooks check. Fix the file with the user and
  re-run.
- **`VEPOL_HUB` is set.** `--apply` refuses a custom hub. Unset it.
- **Permissions problem in `~/.claude/`.** Check the folder's owner. If it
  belongs to another user, the Mac has a setup problem outside Vepol's scope.
- **A LaunchAgent does not load.** The plist is still written. The installer
  prints `launchctl load ~/Library/LaunchAgents/com.knowledge.<name>.plist`;
  run it with the user's OK, or re-run the installer later.
- **The local Qwen voice fails** (`--apply` exits 11). Everything else is
  installed and the audio route is unchanged. Read the reason, fix it, then run
  `~/knowledge/bin/kb-tts-install && ~/knowledge/bin/kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend local_qwen`.
- **NotebookLM is missing or not signed in.** The morning and evening audio
  digests then make no audio: they record a NotebookLM failure and keep only
  the written report. Install and sign in
  (`pipx install notebooklm-py && notebooklm login`), or switch to local Qwen.
- **The claude-memory-compiler clone fails.** It is optional: warn, do not
  block. Re-run `--apply` with `VEPOL_ENABLE_MEMORY_COMPILER=1` later; it
  clones only when the folder is missing. If `uv` was missing:
  `brew install uv`, then `cd ~/claude-memory-compiler && uv sync`.
- **Python packages are missing.** The install continues and prints the pip
  command from § 1.2.

For an error not covered here:

1. Read the message and `install.log` in the repo folder.
2. Work out which install step it came from and what that step does.
3. Try one targeted fix, then re-run the same check.
4. After three failed attempts, stop. Write the symptom and what you tried to
   `~/knowledge/incidents.md` (create it if needed) and hand it back to the
   user.

### 1.6 Verify the install worked

```bash
./install.sh --verify --json
~/knowledge/bin/kb-doctor install-health
```

`--verify` checks the core and exits 0, or 13 with `verify_problems`.
`kb-doctor install-health` goes further: the install manifest, LaunchAgents,
session hooks, session capture, required tools, Codex and the Python packages
from `requirements.txt` (for the `python3` on `PATH`). A missing package is a
P1, `python-packages-missing`, that names the `pip` command to run; until it is
installed, the installer's last step says "kb-doctor reported issues".

On a clean install expect zero P0 (broken) and zero P1 (needs attention)
findings. Info lines for optional tools that are not installed, or extras the
user declined, are fine, and so are P2 findings. The receipt records the
installer's own run as `kb_doctor_exit`: 0 clean, 1 at least one P1, 2 at
least one P0.

Fix P0 and P1 findings before you call the install done. The common ones:

- **`settings-hook-missing` (P0).** The user's `~/.claude/settings.json`
  lacks Vepol's hooks. With their OK, run `~/knowledge/bin/kb-claude-hooks --apply`
  (it adds only the missing hooks and keeps a backup;
  `kb-claude-hooks --check` only reports). Never copy the template over the
  user's file: that would replace their permissions.
- **Legacy bypass keys (P0).** The user deferred the security migration.
  Explain it again and offer `VEPOL_APPLY_C01=1` with the same `--apply`
  command.
- **`memory-compiler-missing` (P1).** Session capture was accepted but the
  clone failed. Retry as § 1.5 says. If the user no longer wants it, re-run
  `--apply` without `VEPOL_ENABLE_MEMORY_COMPILER`, which records it as
  declined.
- **`launchagent-not-loaded` (P1).** Load it as § 1.5 says.
- **`codex-missing` (P1).** Codex was set up once (`~/.codex` exists or
  `KB_CODEX_BIN` is set) but the binary is gone. Reinstall it, or clear the
  stale setting with the user.

### 1.7 Run the first-five-minutes proof

This is the moment the user sees that they have an assistant, not a folder of
scripts. The installer does not change `PATH`, so use full paths:

```bash
# 1. Health of the knowledge base
~/knowledge/bin/kb-doctor

# 2. A first task on the hub board (~/knowledge/backlog.md)
~/knowledge/bin/kb-task "My first Vepol task"

# 3. Find it again
~/knowledge/bin/kb-search "first Vepol"

# 4. A sample morning brief for an invented workspace
~/knowledge/bin/kb-demo brief
```

`kb-demo brief` asks a model through Codex or Claude Code, so it needs
a signed-in agent and can take a few minutes. It works on invented data: it
prints the brief, does not read or change the user's notes, and sends nothing
to Telegram or the calendar. If the Python packages are installed, also try
`~/knowledge/bin/kb-idea capture "My first Vepol idea"`.

After each command, tell the user what just happened and why it matters. Then:

- Offer to put the commands on their `PATH`: add
  `export PATH="$HOME/knowledge/bin:$PATH"` to `~/.zshrc`, with their OK.
- Give one real project its memory (§ 2.1).

### 1.8 Optional: Vepol Desktop

Vepol Desktop is one window for all of it: every project's memory, today's
plan, the user's agents in real terminals, every task and every routine with
its health. Its **Plan my day** button turns the morning brief into a plan the
user agrees with an agent and, only when the user says so, into calendar
events. `install.sh` does not build it. Offer it, and build it only if the
user wants it.

It needs an Apple Silicon Mac (`uname -m` prints `arm64`), the Command Line
Tools in `/Library/Developer/CommandLineTools` (`xcode-select --install`),
Python 3.11 or later (for example `brew install python`) and `tmux`
(`brew install tmux`). Without `tmux` the app opens but cannot start an
agent. Then, from the repo:

```bash
cd ~/vepol/face
python3 -m venv .venv            # use a python3 that is 3.11 or later
.venv/bin/python --version
.venv/bin/pip install -r requirements.txt
./desktop/build.sh
open desktop/build/VepolDesktop.app
```

If `.venv/bin/python` reports a version below 3.11, recreate `.venv` with a
newer interpreter, for example `/opt/homebrew/bin/python3 -m venv .venv`.
`./demo.sh` (from `face/`, after the build) opens the app on an invented
workspace that never touches `~/knowledge`. Full guide:
[`face/README.md`](face/README.md).

## Phase 2 — Personalization

After the install the system is generic. Personalization makes it the user's.

### 2.1 Discover the user's projects (carefully)

**Do not scan `~/` recursively.** That can read sensitive places: cloud-sync
folders (Dropbox, iCloud, Google Drive), work VPN mounts, keychain-adjacent
folders, secret stores and old backups. It also takes far too long.

Instead, look **one level deep** in the usual project folders:

- `~/Projects/`, `~/Code/`, `~/dev/`
- `~/work/` or `~/job/`
- `~/PetProjects/` or a similar hobby folder

**Do not look in:**

- `~/Library/`, `~/.config/`, `~/.ssh/`, `~/.gnupg/`: system settings and
  secrets
- `~/Dropbox/`, `~/iCloudDrive/`, `~/OneDrive/`, `~/Google Drive/`: cloud-sync
  mounts
- `~/Documents/` as a whole: too broad and often personal. If the user wants a
  project from there, they will name the folder.

For each candidate, check only:

- Is there a `README.md`?
- Is there a `.git/` folder?
- Did anything change in the last 30 days?

**Show the candidates before you read anything inside them.** "I found these
folders that look like projects: [list]. Which ones should get a Vepol memory?
I won't read inside them until you confirm."

For each project the user confirms:

- **Claude Code:** open an interactive session in the project
  (`cd <project-path>`, then `claude`) and type `/init-kb`. The skill reads the
  project, proposes a slug, a category and a description, waits for the user's
  OK and only then writes. Do not use print mode (`claude -p`): it cannot hold
  that conversation.
- **Codex and other agents** have no `/init-kb`. With the user's OK, run
  `~/knowledge/bin/new-wiki <project-path> [slug] [category] [description]`
  (category: `lab`, `order`, `pet`, `job` or `personal`, the default). It
  creates the project's `AGENTS.md` and `knowledge/` folder, adds `knowledge/`
  to the project's `.gitignore`, links the folder as
  `~/knowledge/projects/<slug>`, adds a `seeded` row to
  `~/knowledge/registry.md` and logs the event in the hub. If the project
  already has its own `AGENTS.md`, it keeps the user's text and appends one
  block between `<!-- BEGIN VEPOL` and `<!-- END VEPOL -->` that points agents
  to `knowledge/` and `kb-session-start --print --cwd "$PWD"`; a linked or
  read-only `AGENTS.md` is not changed, and step 1 of its output prints the
  line to add. If `registry.md` was generated by `kb-rebuild-registry`, it
  leaves that file alone and its step 3 prints the project's entry: append it
  unchanged to the end of `~/knowledge/migration-2026-04-25.yaml`, then run
  `~/knowledge/bin/kb-rebuild-registry apply` (never `bootstrap`). Then fill
  `knowledge/README.md`, `knowledge/state.md` and, if `new-wiki` created it,
  the project `AGENTS.md` with real content, together with the user.
- **Vepol Desktop:** **Add project…** in the New session dialog does the same
  for any folder. It does not show `new-wiki`'s output, so on a hub with a
  generated `registry.md` use `new-wiki` from the terminal instead.

Apply [`docs/methodology/kb-authoring-discipline.md`](docs/methodology/kb-authoring-discipline.md)
throughout: write only what you have checked, and mark what you have not.
Make the first task in a new project's `backlog.md` a review session with the
user.

### 2.2 Connect the user's daily routine

Ask what the user wants, or look at the files they already have, then connect
only what they ask for. Vepol works without any of it. Each item says what it
needs.

- **Language.** Set at install from the system locale, in
  `~/knowledge/personal/profile.yaml` (`language: en`, `ru`, `es`, …). Every
  routine writes in it; the next run follows a change.
- **Name and city** for the brief and the retro: `USER_NAME` and `USER_CITY`
  in `~/knowledge/personal/.secrets`.
- **Telegram** (the user's own bot). The morning brief, the evening retro, the
  digests and the people review buttons arrive in Telegram once
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in
  `~/knowledge/personal/.secrets`. Walk the user through it, and let them type
  the values into the file themselves; never ask them to paste a token into
  the chat:
  1. Create a bot with @BotFather and copy its token.
  2. Send the bot any message, then open
     `https://api.telegram.org/bot<token>/getUpdates` and copy the number at
     `"chat":{"id": ...}`.
  3. Put both values in `~/knowledge/personal/.secrets`.

  Keep this order. With scheduled tasks on, Vepol's review bot starts reading
  the bot's updates within minutes of both values being in the file, and
  `getUpdates` then shows nothing. Until both are set, each brief is still written to
  `~/knowledge/briefs/<date>.md` and not sent. Running
  `~/knowledge/bin/kb-brief` again after setup delivers today's saved brief
  without a new model call. Use a different bot from
  Claude Code's Telegram plugin: two listeners on one bot steal each other's
  updates.
- **Mail.** With scheduled tasks on, a read-only mail check runs at 07:15 and
  20:30. The brief lists every new email and says whether it needs action;
  the retro names the mail still waiting for a reply. It reads nothing until
  Codex is signed in and its Gmail plugin is
  connected. It never drafts, sends, labels or deletes mail. To switch it off,
  set `enabled: false` on `mail-morning` and `mail-evening` in
  `~/knowledge/personal/processes.yaml`.
- **Calendar.** Connect Google Calendar in Claude Code, and the brief plans
  around today's meetings. Vepol writes a calendar event only after the user
  approves that event.
- **Health data.** If the user's own sync (Garmin, Apple Health export, a
  script) writes a daily JSON file to `<folder>/morning/<YYYY-MM-DD>.json`,
  set `KB_HEALTH_METRICS=<folder>` in `.secrets`. The brief then opens with
  last night's sleep, recovery and one suggestion for the day. Vepol ships no device connector. File format:
  [`docs/health-in-the-brief.md`](docs/health-in-the-brief.md).
- **Audio digests.** NotebookLM (default) or the local Qwen voice (§ 1.4).
  Switch later with
  `~/knowledge/bin/kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend notebooklm`
  (or `local_qwen`, after `~/knowledge/bin/kb-tts-install`).
- **Codex.** Optional. With it, the brief and the retro run on Codex first and
  fall back to Claude Code, the arXiv digest has a second agent, and mail
  reading works.
- **Later, when the user wants them:** follow-up reminders (`people-remind`),
  people proposals (`people-extract`) and Money Radar (`money-radar`) are
  blocks in `processes.yaml` that ship with `enabled: false`. Daily research
  (`kb-daily-research --text-only`) has no block yet; add one.
  [`docs/features.md`](docs/features.md) says what each one needs.
- **Experimental:** the multi-project cycle needs
  `~/knowledge/bin/kb-rebuild-registry bootstrap`, then
  `~/knowledge/bin/kb-rebuild-registry apply`, then `cycle_enabled: true` in a
  project's `knowledge/.orchestration.yaml` and `apply` once more. Offer it
  only to users who ask for it. `bootstrap` is a one-time step: it refuses to
  overwrite an existing `~/knowledge/migration-2026-04-25.yaml`. Never run
  `bootstrap --force` without the user's OK: it rebuilds that table (keeping a
  `.bak-<date>-<time>` copy) and cannot read back a `registry.md` that `apply`
  generated, so every category, status and description must be checked
  afterwards.

Don't push integrations the user did not ask for.

### 2.3 Record what you learned in strategies.md

`~/knowledge/strategies.md` is the hub's living note on where the user is
heading and how Vepol should help: a current strategy, active hypotheses,
working principles and open questions. Fill it with what you learned:

- their main projects and current focus
- their preferred channels
- their morning and evening rhythm
- anything they do not want ("no auto-replies to email")

Nothing updates this file on its own. Revisit it with the user when their
focus shifts, or during the weekly freshness pass (§ 3.4).

## Phase 3 — Ongoing evolution

After install and personalization you keep working with the user across many
sessions. Each one is a chance to make Vepol more useful to this person.

### 3.1 Watch for skill opportunities

A skill is worth building when:

- the user repeats a workflow more than three times across sessions
- the workflow has the same shape each time, with different content
- it currently depends on the user remembering manual steps

Examples:

- a user who files articles every week: a skill that runs the whole intake
  (raw, sources, concept page, log line) in one go
- a user who invoices clients monthly: a skill that drafts the invoice from
  the project's `state.md`
- a user who reviews finances quarterly: a skill that produces the review

When you spot one:

1. Ask: "I notice you've done X three times. Want me to make it a one-command
   flow?"
2. If yes, build it as a Claude Code skill, or the equivalent for the user's
   agent. If there is no equivalent, write the workflow down in
   `~/knowledge/solutions/` and put the executable part in a normal script.
3. If it captures a pattern that transfers to other work, add a page to
   `~/knowledge/concepts/`.

### 3.2 Watch for new project opportunities

A project the user mentions often but that has no memory yet is a candidate.
After two or three mentions, offer to set it up (§ 2.1). If the user says no,
note it in `~/knowledge/escalations.md` and do not raise it again that
session.

### 3.3 Watch for methodology opportunities

When you notice a recurring decision, a trap or a habit that would help future
sessions (yours or another agent's), write it up as its own page in
`~/knowledge/concepts/`, following
[`docs/methodology/kb-authoring-discipline.md`](docs/methodology/kb-authoring-discipline.md).
The user reviews it; nothing becomes canon without their approval.

### 3.4 Run the freshness loop

Weekly works well for an active user:

```bash
# Read-only audit; prints findings
~/knowledge/bin/kb-doctor

# Also write the open findings to ~/knowledge/pending-curation.md
~/knowledge/bin/kb-doctor --write
```

`--write` keeps the findings in a managed block of
`~/knowledge/pending-curation.md`; the user's own notes in that file stay.
Read that file at the start of any curation session.

The user decides on P0 and P1 findings, with your help; P2 findings are
advisory. Do not change content to clear a finding without the user's review
([freshness-loop methodology](docs/methodology/kb-freshness-loop.md)).

### 3.5 Run one lightweight spec review on significant work

For non-trivial plans (architecture changes, migrations, new
infrastructure), use
[`cross-agent-review`](docs/methodology/cross-agent-review.md):

- Ask one lightweight independent spec review agent (another CLI from the
  roster) to read the spec and the code, API or schema files it relies on.
- Accept `GO` or at most three short questions. `BLOCK` needs a direct
  `file:line` or contract citation that proves the stated path cannot work.
- Prefer the smallest path that works. Questions do not add requirements.
- Do not restart review merely because the spec hash changed. Only a genuine
  `BLOCK` allows one narrow re-check of that same blocker, with no new
  findings.

The goal is to catch gross logic mistakes before code, without turning review
into a second design process.

## Troubleshooting common issues

### "The brief does not arrive in Telegram"

Every `kb-brief` run prints one line: where the brief was saved and whether it
was delivered. "Telegram is not configured" means `TELEGRAM_BOT_TOKEN` or
`TELEGRAM_CHAT_ID` is empty in `~/knowledge/personal/.secrets` (§ 2.2). If
the line says the Telegram send failed, the next run retries; details are in
`~/knowledge/logs/brief.log`. The day file's `delivery:` line says the same:
`not_configured` (Telegram not set; nothing was tried), `telegram_failed` (a
send was tried and rejected), `telegram_ok` (delivered). A rerun the same day
sends the saved brief without a new model call.
`KB_BRIEF_DRY=1 ~/knowledge/bin/kb-brief` prints the brief instead of sending
it (it still makes the model call and saves it as today's brief).

If no AI agent answered, `kb-brief` exits 1, saves no brief and says why for
each agent it tried, for example "Codex: not installed." or "Claude Code: not
signed in — run `claude` once to sign in." The message goes to Telegram (once
a day) when it is set up; a manual run, or any run without Telegram, also
prints it. After a sign-in
failure Claude Code is paused for 60 minutes, so a run right after signing in
can still say "paused after an earlier failure (until HH:MM)"; try again after
that time. `brief.log` keeps the raw error text.

### "The brief is empty or generic"

The brief is built from the user's files. If every project's `state.md` and
the hub `log.md` are still empty, it has little to say. Walk the user through
one project's `state.md` and `log.md` with real content, then look at the next
brief.

### "kb-doctor reports findings"

- **P0:** something is broken and needs fixing now, for example a missing
  session hook (`kb-doctor install-health`).
- **P1:** needs attention soon, for example an incident open for more than 7
  days (`incident-old`), or a live project whose `state.md` trails its
  `log.md` by more than 3 days (`state-stale`).
- **P2:** advisory, for example a live project's `state.md` older than 14
  days (`state-old`).

Go through them with the user. Do not fix content findings without their
approval.

### "A scheduled routine did not run"

```bash
launchctl list | grep com.knowledge
tail -50 ~/knowledge/logs/planner.log
```

`kb-tick` writes what it ran, and why, to `~/knowledge/logs/planner.log`. If
`processes.yaml` is broken, nothing runs, and the reason is in that log. Each
routine has its own log as well (`brief.log`, `retro.log`,
`morning-digest.log`). `tick.stdout.log` and `tick.stderr.log` hold only
crashes.

Common causes:

- The repo moved, so the commands in `~/knowledge/bin/` point nowhere. Move it
  back, or re-run `install.sh` from the new place.
- The Mac was asleep or off until midnight. A routine whose time passed
  during sleep runs on the first tick after the Mac wakes, the same day.
- The routine is `enabled: false` in `processes.yaml`.
- The routine waits (`after:<id>`) on a routine that is switched off. Only a
  switched-off `mail-morning`, `mail-evening`, `learning` or `money-radar` is
  skipped over; after any other one, such as `daily` or `retro`, the waiting
  routines do not run that day.

To reload a LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/com.knowledge.<name>.plist
launchctl load ~/Library/LaunchAgents/com.knowledge.<name>.plist
```

### "Claude Code starts without the project's memory"

Run `~/knowledge/bin/kb-claude-hooks --check`. If hooks are missing, offer
`~/knowledge/bin/kb-claude-hooks --apply`. The project also needs a
`knowledge/` wiki (§ 2.1).

### "The reviewer agent is rate-limited"

Switch to an agent with headroom: another CLI from the roster, such as
Antigravity (`agy`), Hermes or OpenCode. `~/knowledge/bin/kb-runtime-registry`
shows which agent CLIs can do work right now, from the evidence Vepol already
has. If no reviewer is available, write down the attempt and let the user
decide how to go on. Do not skip the review on your own, and do not start a
chain of replacement reviewers.

## What you must NOT do

- **Do not install Homebrew or any other system package manager**, even if it
  would speed things up. The user decides.
- **Do not overwrite the user's `~/.claude/settings.json`** with the Vepol
  template. Add hooks only through `kb-claude-hooks --apply` (or
  `VEPOL_MERGE_HOOKS=1`) with the user's OK, and never widen their
  permissions.
- **Do not install into a `~/knowledge/` that belongs to another tool**
  without the user's explicit consent. Move it aside first (§ 1.1). Doing
  otherwise can wreck another system's data.
- **Do not scan `~/` recursively.** Look one level deep in the usual project
  folders (§ 2.1).
- **Do not write to `~/knowledge/` without telling the user what you write.**
  The trail matters.
- **Do not ask the user to paste a token or password into the chat.** They
  edit `~/knowledge/personal/.secrets` themselves.
- **Do not skip the one lightweight spec review** for non-trivial changes,
  and do not grow it into several reviewers or repeated full passes.
- **Do not write unverified content into a wiki.** Apply
  [`kb-authoring-discipline`](docs/methodology/kb-authoring-discipline.md).
- **Do not claim the install worked when it did not.** If
  `kb-doctor install-health` reports P0 or P1 findings, fix them or write them
  down in `~/knowledge/incidents.md` before you say "done".
- **Do not present direction as shipped.** Use the framings in "What Vepol
  is".
- **Do not reformat or rewrite the user's existing files** without explicit
  permission. Vepol adds to their files; it does not rewrite them.

## How to contribute findings back to the project

If you find a real bug, gap or opportunity in Vepol itself (not in the user's
setup):

- Open an issue at https://github.com/nahornyi-ai-lab/vepol/issues
- For anything security-sensitive, follow [SECURITY.md](SECURITY.md)
- For a feature idea, describe the concrete situation where you needed it

Reports from agents in the field are how Vepol gets better for everyone.

## Where to find more

- [`SETUP.prompt.md`](SETUP.prompt.md): the agent install flow, step by step
- [`README.md`](README.md): the product overview for the user
- [`docs/getting-started.md`](docs/getting-started.md): install and first
  steps in detail
- [`docs/features.md`](docs/features.md): every module and what it needs
- [`docs/what-is-vepol.md`](docs/what-is-vepol.md): the long-form explanation
- [`docs/methodology/`](docs/methodology/): how agents work with the knowledge
  base
- [`docs/visuals/`](docs/visuals/): diagrams
- [`demo/README.md`](demo/README.md): the invented example workspace
- [`face/README.md`](face/README.md): Vepol Desktop
