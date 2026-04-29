---
name: orchestrator-setup
description: Bootstrap the personal Karpathy-wiki + active orchestrator on a clean macOS — clones the orchestrator-seed repo, runs install.sh, verifies prereqs (Claude CLI / Codex CLI / Node / Bun), wires LaunchAgents (planner / tick / channel-telegram / orchestrator-cycle), creates the first project wiki, and verifies via kb-doctor. Use this skill when the user says "set up orchestrator", "установи orchestrator", "разверни базу знаний", "/orchestrator-setup", "set up the wiki system", "deploy orchestrator-seed", or otherwise indicates they want to install the full system on this machine. The skill is idempotent — safe to re-run.
---

# orchestrator-setup — turnkey deploy of the Karpathy-wiki + active orchestrator

Bootstraps the entire system from `aladin2907/orchestrator-seed` on this machine. After running, the user has:

- `~/knowledge/` hub with bin/, _template/, CLAUDE.md
- `~/.claude/CLAUDE.md` master schema
- 4 LaunchAgents loaded (planner 00:05, tick every 5 min, channel-telegram KeepAlive, orchestrator-cycle 07:30+20:45)
- One bootstrapped project with `cycle_enabled: false` (safety toggle)
- All `kb-*` CLIs available in `$PATH` via `~/knowledge/bin/`

Reference: `~/knowledge/orchestrator-seed/docs/setup.md` is the canonical setup walkthrough.

## When to run

- User says: «set up orchestrator», «установи orchestrator», «разверни базу знаний», «/orchestrator-setup», «deploy seed», «установи personal KB system»
- User clones the seed manually and asks how to finish setup
- Fresh macOS without `~/knowledge/` directory

## When NOT to run

- `~/knowledge/bin/kb-doctor` already exists AND `launchctl list | grep com.knowledge` shows ≥3 agents → system already deployed; redirect user to `kb-doctor --strict` for health check or `~/knowledge/orchestrator-seed/docs/troubleshooting.md` for debug
- User is on Linux/Windows (the seed is macOS-specific via LaunchAgents) — explain limitation, suggest manual port using `bin/` scripts only
- User's `$HOME` is unusual (e.g. `/var/root`, `/tmp`) — refuse, ask for corrected env

## Pre-flight checks

Before doing ANY mutation, verify these one-by-one and **stop with explicit message** if any fail:

| Check | Command | Failure response |
|---|---|---|
| macOS | `uname` returns `Darwin` | "This skill is macOS-only — see seed docs/setup.md for manual port" |
| Homebrew | `brew --version` | "Install via https://brew.sh first, then re-run" |
| Node ≥ 18 | `node --version` shows v18+ | "Run `brew install node@20` then re-run" |
| Bun | `bun --version` | "Run `brew install oven-sh/bun/bun` then re-run" |
| Python ≥ 3.11 | `python3 --version` | "Run `brew install python@3.13` then re-run" |
| Claude CLI ≥ 2.1.113 | `claude --version` | "Run `npm install -g @anthropic-ai/claude-code` then `claude login`, then re-run" |
| Codex CLI | `codex --version` | "Run `npm install -g @openai/codex` then `codex login`, then re-run" |
| ripgrep | `rg --version` | "Run `brew install ripgrep` then re-run" |
| Logged into Claude | `claude config get` doesn't error | "Run `claude login` and complete browser auth, then re-run" |
| Logged into Codex | `codex config get` or check token file | "Run `codex login`, then re-run" |

The skill should run all checks first, list the missing items, give the user copy-paste commands to fix, and exit. Only proceed when ALL preflight checks pass.

## Step-by-step procedure

### Step 1. Confirm intent

Read this back to the user verbatim and ask `OK to proceed?`:

> I'll deploy the full Karpathy-wiki + active orchestrator system on this Mac.
> What I'll do:
> 1. Clone `git@github.com:aladin2907/orchestrator-seed.git` into `~/knowledge/orchestrator-seed/`
> 2. Run `./install.sh` which:
>    - Creates `~/knowledge/` with bin/, _template/, CLAUDE.md
>    - Installs `~/.claude/CLAUDE.md` master schema (if absent)
>    - Loads 4 LaunchAgents (planner, tick, channel-telegram, orchestrator-cycle)
>    - Patches claude-memory-compiler (if you have it)
> 3. Run `kb-doctor --strict` to verify a clean install
> 4. Optional: bootstrap your first project wiki via `new-wiki <path>`
>
> The system runs cron-like jobs daily (07:30 morning plan, 20:45 evening retro) but every project ships with `cycle_enabled: false` — you opt-in per project.
>
> Approve with «yes» / «давай», cancel with «no».

If user says yes → proceed. Otherwise → stop, ask what they want instead.

### Step 2. Clone the seed

```bash
SEED_DIR="$HOME/knowledge/orchestrator-seed"
mkdir -p "$HOME/knowledge"
if [[ -d "$SEED_DIR/.git" ]]; then
  echo "Seed already cloned — running git pull"
  cd "$SEED_DIR" && git pull --ff-only
else
  git clone https://github.com/aladin2907/orchestrator-seed.git "$SEED_DIR"
fi
```

If clone fails (network / auth) → report the error verbatim, stop. Don't fabricate a fix.

### Step 3. Run install.sh

```bash
cd "$SEED_DIR"
./install.sh 2>&1 | tee /tmp/orchestrator-install.log
```

The script is idempotent. If something fails midway, the log shows where. Parse the tail of the log for any error markers:
- `error:` / `failed` / `permission denied` → report exact line, stop
- `loaded com.knowledge.*` × 4 → success

### Step 4. Verify

Run these in order, report each result:

```bash
# 4.1 — kb-doctor strict
~/knowledge/bin/kb-doctor --strict
# Expected: P0=0 (info-only findings OK)

# 4.2 — LaunchAgents loaded
launchctl list | grep com.knowledge
# Expected 4 lines: planner, tick, channel-telegram, orchestrator-cycle

# 4.3 — broker reachable
~/knowledge/bin/kb-orchestrator-run "echo hello world" --cwd /tmp \
    --timeout 30 --json-status --run-id "$(uuidgen)"
# Expected: outputs "hello world", JSON file written to ~/knowledge/.orchestrator/runs/

# 4.4 — atomic backlog mutation works
~/knowledge/bin/kb-backlog append hub "verify install" --by self --json
~/knowledge/bin/kb-backlog list
# Expected: shows "verify install" under Open

# 4.5 — security guard installed (seed git hooks)
test -L ~/knowledge/orchestrator-seed/.git/hooks/pre-commit && echo "✓ pre-commit"
test -L ~/knowledge/orchestrator-seed/.git/hooks/pre-push && echo "✓ pre-push"
~/knowledge/bin/kb-doctor seed-content-audit
# Expected: both hooks symlinked, audit returns P0=0 P1=0 (P2 advisory OK)
```

If 4.5 fails (hooks missing): re-run `cd ~/knowledge/orchestrator-seed && ./install.sh`
— hook installation is idempotent and will fix it.

If 4.3 returns `category: auth` → user not logged into providers; remind them to run `claude login` and `codex login`.

If 4.4 fails with permission/lock errors → report and stop, point to docs/troubleshooting.md.

### Step 5. (Optional) Bootstrap first project

Ask the user:

> Want to set up your first project wiki right now?
> Give me an absolute path to an existing project (e.g. `~/projects/myapp`) and I'll create `<project>/CLAUDE.md` + `<project>/knowledge/` with full coordination triad.
> Skip with «later» / «потом».

If they give a path:
```bash
~/knowledge/bin/new-wiki <path-to-project> [slug] [category]
```

Show them the resulting structure:
```bash
ls "<project>/knowledge/"
cat "<project>/knowledge/README.md"
```

Remind them: project ships with `cycle_enabled: false`. To opt-in:
1. Edit `<project>/knowledge/.orchestration.yaml` → `cycle_enabled: true`
2. Run `~/knowledge/bin/kb-rebuild-registry apply`
3. Verify with `kb-doctor migration-readiness <slug>` (P0=0 means ready)

### Step 6. Tell the user what just happened + next steps

Use this template (fill in actual values):

> ✅ Orchestrator deployed
>
> System state:
> - Hub: `~/knowledge/`
> - Seed: `~/knowledge/orchestrator-seed/` (git tracked, push your fork later)
> - LaunchAgents: 4 loaded
> - Bootstrapped project: <path> (slug=<slug>, status=seeded, cycle_enabled=false)
>
> What runs automatically:
> - 00:05 daily — `kb-planner` drafts tomorrow's brief draft
> - every 5 min — `kb-tick` (channel guard, brief/retro firing)
> - 07:00 — `kb-brief` posts brief to Telegram (after you wire `~/knowledge/personal/.secrets`)
> - 07:30 — `kb-orchestrator-cycle plan` (no-op until you `approved_at:`)
> - 20:45 — `kb-orchestrator-cycle retro` (only fires for `cycle_enabled: true` projects)
> - long-lived — `com.knowledge.channel-telegram` (incoming TG messages)
>
> Next steps:
> 1. Configure secrets (Telegram, Anthropic, OpenAI keys) — see `~/knowledge/orchestrator-seed/docs/setup.md` § Telegram bridge
> 2. Decide which projects opt into the daily cycle. Start with one — flip `cycle_enabled: true` in its `.orchestration.yaml`, run `kb-rebuild-registry apply`, watch the next evening retro.
> 3. Read `~/knowledge/orchestrator-seed/docs/README.md` — entrypoint for everything else.
>
> Health check anytime: `kb-doctor --strict`
> Troubleshooting: `~/knowledge/orchestrator-seed/docs/troubleshooting.md`

## Common failure modes (preempt these)

### `claude login` works but broker returns `auth`
The CLI is logged in but the session token isn't where the broker looks. Run:
```bash
ls ~/.claude/auth.json && head -c 50 ~/.claude/auth.json
```
If empty/absent → re-run `claude login` and watch for the success message.

### LaunchAgent loads but exits 78 / 1
Path issue in plist — usually `__HOME__` substitution failed. Check the rendered plist:
```bash
grep -E "Program|Path" ~/Library/LaunchAgents/com.knowledge.tick.plist | head
```
If you see literal `__HOME__` → re-run `install.sh`.

### `bun: command not found` after install
Bun was installed but PATH not refreshed. Open a new terminal OR run:
```bash
export PATH="$HOME/.bun/bin:$PATH"
hash -r
```

### kb-doctor reports P1 "reports/ directory missing" for a project
Expected — `reports/` is created on first cycle invocation OR can be pre-created:
```bash
mkdir -p <project>/knowledge/reports
```

## Security guard (built-in to every install)

The seed ships with a 3-layer guard against accidentally publishing
personal data to GitHub. Every install gets this for free; nothing
to configure.

**Layer 1 — `kb-seed-sync` leak-scan.** Runs on every commit. Greps the
seed for known identifier patterns (maintainer name variants, real
project slugs, local paths like `/Users/<name>`, API token shapes,
etc.). Refuses to commit on hit.

**Layer 2 — `kb-seed-sync` structural audit.** Runs immediately after
leak-scan. Invokes `kb-doctor seed-content-audit` which verifies:
- live `registry.md` / `hierarchy.yaml` / `migration-*.yaml` NOT tracked
- `personal/`, `concepts/`, `people/`, `companies/`, `solutions/`,
  `raw/`, `sources/` directories NOT tracked
- `.orchestrator/`, `logs/` NOT tracked
- Hub-level `log.md` / `state.md` / `backlog.md` / `escalations.md` /
  `incidents.md` / `strategies.md` NOT tracked (only `_template/`
  versions allowed)
- No dated `reports/<YYYY-MM-DD>.md` in templates (only `_template.md`)
- No real personal slugs (read at runtime from live migration table)
  appearing in docs as examples instead of placeholders

**Layer 3 — git pre-push hook.** Last line of defense before bytes
hit the remote. Runs `kb-doctor seed-content-audit`. If P1 findings,
push is blocked. Force-bypass with `git push --no-verify` (NOT
recommended).

If a user reports «moy push не проходит» — first check what the audit
says; explain the finding; help fix the leak; never advise --no-verify.

The structure is documented in `docs/security-and-privacy.md`.

## Important constraints

- **Never** modify a user's existing project files outside `<project>/CLAUDE.md` and `<project>/knowledge/`. Code stays code.
- **Never** push to GitHub on behalf of the user. The seed at `~/knowledge/orchestrator-seed/` has the upstream `aladin2907/orchestrator-seed` remote — explicit user action required to push.
- **Never** flip `cycle_enabled: true` automatically. Default is opt-in for safety; user must do it deliberately.
- If anything goes wrong mid-install, leave the partial state intact and report exactly which step failed. Don't try to "clean up" — the install.sh is idempotent so the user can fix-and-retry.

## What this skill is NOT

- Not a replacement for `init-kb` skill (which is per-project wiki bootstrap; runs AFTER orchestrator-setup).
- Not a config wizard for secrets (.secrets / .env contents) — that's manual per setup.md.
- Not Linux/Windows compatible — LaunchAgents are macOS-specific.
