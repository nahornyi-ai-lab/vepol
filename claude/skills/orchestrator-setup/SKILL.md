---
name: orchestrator-setup
description: Install, finish or check Vepol (https://github.com/nahornyi-ai-lab/vepol) on this Mac by driving its own installer — install.sh agent modes --capabilities, --probe, --dry-run, --apply, --verify — then verify with kb-doctor and, if the user wants, turn on scheduled routines (LaunchAgents). Use this skill when the user says "set up Vepol", "install Vepol", "set up orchestrator", "/orchestrator-setup", "set up the wiki system", or otherwise wants the full system installed on this machine. Users may ask in their own language, for example Russian user phrasing such as "установи Vepol" or "разверни базу знаний". Safe to re-run (install.sh is idempotent).
---

# orchestrator-setup — install Vepol by driving its installer

You drive Vepol's installer; you never re-implement it. `install.sh`, `upgrade.sh` and
`uninstall.sh` make every file change. If a mode, tool or script you need is missing or
behaves oddly, stop and tell the user — do not improvise.

Read these in the Vepol repo before you install (step 1 gets the repo):

- `SETUP.prompt.md` — the canonical agent install flow. This skill follows it.
- `AGENTS.md` — the agent install and evolution contract: conflict checks for an existing
  `~/knowledge/` and `~/.claude/`, prerequisites, personalization, and what you must not do.
- `docs/dependency-matrix.md` — prerequisites and the exact command to install each one.

## When to run

- The user wants Vepol on this Mac, or an earlier install stopped halfway.
- `~/knowledge/` does not exist yet, or `./install.sh --verify --json` reports problems.

## When NOT to run

- Vepol is already installed and healthy (`./install.sh --verify --json` exits 0). Point the
  user to `~/knowledge/bin/kb-doctor install-health` for a full health check instead.
- The machine is not macOS 13 or later. Vepol supports macOS only; `install.sh` refuses to
  install anywhere else. Explain and stop.
- `~/knowledge/` exists but has no Vepol markers (`bin/kb-tick`, `_template/`): it belongs to
  another system. Stop and follow `AGENTS.md` § 1.1 — never install into it without the
  user's explicit OK, and offer a backup first.

## Rules

- Ask before anything that installs software, changes files outside the repo, loads a
  background service, or touches an account. Never use `sudo`, and never install Homebrew or
  another package manager: show the exact command and let the user run it.
- Never send secrets, tokens, private paths or knowledge-base contents off this machine.
  Never ask the user to paste a token into the chat.
- Treat empty or error output as failure, never as "nothing to do".
- Set only the `VEPOL_ENABLE_*` variables the user approved. Never set `VEPOL_APPLY_C01=1`
  on your own.
- Fix one thing at a time and re-run the same check. After three failed tries, stop and hand
  it back to the user. Never weaken a security or privacy check to make an error go away.
- If a step fails, leave the partial state as it is and report which step failed, with its
  output. `install.sh` is idempotent, so the user can fix the cause and re-run.

## Steps

### 1. Get the repo

If you are not already inside a Vepol clone and `~/vepol` does not exist, ask, then:

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
```

Read `VERSION` and `README.md`.

### 2. Check the installer is new enough

```bash
./install.sh --capabilities --json
```

The output must list `--probe`, `--apply` and `--verify`. If the command errors, prints
nothing, or lacks them, stop and tell the user to update the clone (or fall back to the
interactive `./install.sh`). Never run a bare `./install.sh` hoping it only looks — it
installs.

### 3. Look at the machine (changes nothing)

```bash
./install.sh --probe --json
```

Report `prereqs_missing_required`, `prereqs_missing_optional` and
`needs_security_migration`. Exit code 10 means a required prerequisite is missing; 11 means
a partial install (the hub exists but `bin/` is not linked).

For each missing tool, show the command from `docs/dependency-matrix.md`, let the user run
it, then probe again. Codex CLI is optional (cross-agent review) and uses the official
standalone installer:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 CODEX_INSTALL_DIR="$HOME/.local/bin" sh
```

Python packages are checked, not installed. If the install warns about them, show
`python3 -m pip install --user -r requirements.txt`; if pip answers
`externally-managed-environment` (Homebrew's Python), show
`python3 -m pip install --break-system-packages -r requirements.txt` instead.

### 4. Preview, then install

```bash
./install.sh --dry-run --json
```

Show the plan and ask which extras the user wants. All are off unless set:

- `VEPOL_ENABLE_LAUNCHD=1` — scheduled routines (see step 6)
- `VEPOL_ENABLE_TELEGRAM=1` — scaffold for Claude Code's own Telegram plugin (chatting with Claude from Telegram; it needs a second bot). The brief and the retro do not need it: they read `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `~/knowledge/personal/.secrets`
- `VEPOL_MERGE_HOOKS=1` — add Vepol's session hooks to an existing `~/.claude/settings.json` (a backup is kept)
- `VEPOL_ENABLE_MEMORY_COMPILER=1` — automatic session capture (claude-memory-compiler)

Then install with only the approved ones, for example:

```bash
VEPOL_ENABLE_LAUNCHD=1 VEPOL_ENABLE_MEMORY_COMPILER=1 ./install.sh --apply
```

If the probe reported `"needs_security_migration": true`, explain why it matters: legacy
bypass-permission keys in `~/.claude/settings.json` let an injected prompt run tools without
the user's approval. Get the user's explicit OK, then re-run the same apply command with
`VEPOL_APPLY_C01=1` added (keep the approved `VEPOL_ENABLE_*`; an extra left out is recorded
as declined).

### 5. Verify

```bash
./install.sh --verify --json              # core substrate; exit 13 lists verify_problems
~/knowledge/bin/kb-doctor install-health  # manifest, skills, hooks, LaunchAgents
```

Expect no P0 or P1 findings; P2 findings are advisory. Then run the quick proof and tell
the user what each command shows (the `kb-*` commands live in `~/knowledge/bin/`; run them
from there if they are not on the PATH yet):

```bash
kb-doctor
kb-demo brief
kb-task "My first Vepol task"
kb-search "first Vepol"
```

Finally, read the user the newest receipt under `~/knowledge/install/receipts/` and
summarize: version, what is installed, which extras are on, and anything left to do.

### 6. Scheduled routines (opt-in)

With `VEPOL_ENABLE_LAUNCHD=1`, `install.sh` renders the plists from `launchd/` into
`~/Library/LaunchAgents/` and loads them:

- `com.knowledge.tick` — every 15 minutes runs the routines declared in
  `~/knowledge/personal/processes.yaml` (morning brief, evening retro, learning digest, …)
- `com.knowledge.planner` — at 00:05 works out the day's timing (sunrise/sunset, brief and
  retro times) for `kb-tick`
- `com.knowledge.orchestrator-cycle` — the project cycle: morning plan at 07:30, evening
  retro at 20:45
- `com.knowledge.people-review-bot` — Telegram buttons for staged contacts; idle until a bot
  token is set

If the user declined at install time, turn them on later by re-running `./install.sh --apply`
with `VEPOL_ENABLE_LAUNCHD=1` plus any other extras the user already has on (plists that
already exist are kept). Check with `launchctl list | grep com.knowledge` and
`~/knowledge/bin/kb-doctor install-health`; logs are in `~/knowledge/logs/`. Which routines run, and when, is set in `processes.yaml`
(see `docs/daily-routine.md`).

Delivery to Telegram needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in
`~/knowledge/personal/.secrets` (mode 600). The user fills these in themselves.

Each project starts with `cycle_enabled: false` in `<project>/knowledge/.orchestration.yaml`,
so the project cycle skips it. Only the user turns it on; check readiness first with
`~/knowledge/bin/kb-doctor migration-readiness <slug>`.

### 7. First project (optional)

Offer to set up the first project wiki: in that project's folder, run the `init-kb` skill
(open Claude Code there and type `/init-kb`; print mode cannot hold the skill's
confirmation dialog). Do not scan `~/` recursively to find projects —
follow `AGENTS.md` § 2.1.

## Undo and upgrade

- Undo a fresh install: `./uninstall.sh`. It removes only Vepol's managed files and never
  deletes user data. If it is missing, stop — do not delete anything by hand.
- Move to the newest release later: `./upgrade.sh` (`./upgrade.sh --check` only reports).

## What this skill is not

- Not a replacement for `init-kb`, which sets up one project's wiki and runs after this.
- Not a secrets wizard: the user fills in `.secrets` and `.env` values themselves.
- Not for Linux or Windows: the scheduled routines rely on macOS LaunchAgents.
