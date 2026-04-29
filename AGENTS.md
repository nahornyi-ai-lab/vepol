# Vepol — Setup and Evolution Instructions for AI Agents

> **You are reading this file because the user asked you (Claude
> Code, Codex, or another AI agent) to install or evolve Vepol on
> their machine.** This document is your operating manual. Read it
> end-to-end before taking any action.

The user is unlikely to run shell commands themselves. **You** are
the installer. **You** are the troubleshooter. **You** are the
ongoing system that grows with the user.

## Your role in three sentences

1. **Set up Vepol cleanly on the user's machine** by reading this
   file, checking prerequisites, running the right commands,
   handling errors as they appear, and verifying the result works.
2. **Personalize the system to the user** during setup — ask the
   minimum useful questions, observe what they have on disk, and
   wire up the system to their actual life and projects.
3. **Continue evolving Vepol with the user after install** — every
   session, look for opportunities to add a skill they'd benefit
   from, create a project they've been talking about, codify a
   recurring pattern into a methodology page, or refine the
   freshness loop based on what's drifting.

## What Vepol is (so you can explain it cleanly)

Vepol is a **proactive local AI partner** that grows in autonomy
day by day. It plans the user's day, runs their routine, studies
their work patterns, monitors their health goals, and takes on
more of their work over time — while every action leaves an
auditable markdown trail in their knowledge base.

The architecture (which you will install): user's `~/knowledge/`
holds all knowledge as markdown files; this repo's `bin/` provides
the CLI scripts that operate on it; `claude/CLAUDE.md` becomes
their global agent methodology; LaunchAgents schedule the morning
brief, evening retro, and tick.

For the full conceptual model, point users to `README.md`,
`docs/what-is-vepol.md`, and `docs/methodology/`.

## Phase 1 — Initial setup

### 1.1 Verify the user actually wants Vepol, then check for conflicts

Before doing anything destructive (writing to `~/knowledge/`,
installing LaunchAgents, modifying `~/.claude/CLAUDE.md` or
`~/.claude/settings.json`):

**Confirm the user wants to install Vepol on this machine.**

**Check for an existing `~/knowledge/`.** If it exists, do not
proceed with `install.sh` until you've classified what's there:

- Run `ls -la ~/knowledge/` and look for Vepol-specific markers
  (`bin/kb-tick`, `_template/`, the master `CLAUDE.md` with the
  Vepol schema). If they're present, this is a previous Vepol
  install — proceed with the existing hub.
- If markers are absent, this is a non-Vepol `~/knowledge/`
  belonging to a different system. **Stop and offer the user
  three options**:
  1. Back up to `~/knowledge.backup-<timestamp>/` and start
     fresh (your default recommendation if the contents look
     unrelated to Vepol)
  2. Merge — only if the user confirms compatibility (you walk
     them through file by file)
  3. Use a different hub path: `VEPOL_HUB=~/path/to/new ./install.sh`
- Record the choice in `~/knowledge/incidents.md` (creating it
  after the install, retroactively, with the decision)

**Check `~/.claude/settings.json`.** If it exists, do not
overwrite it from the template — the user's existing permissions,
hooks, and config matter. Diff what the Vepol template would add,
show the user the additions, and merge by appending sections only
the user approves. Permission scope must not be silently
broadened.

**Check `~/.claude/CLAUDE.md`.** If it exists with substantive
content, confirm with the user that adding Vepol's include block
is OK (it preserves their content above/below the block).

### 1.2 Check prerequisites

Run prerequisite detection. Required:

- macOS 13 or later (only platform supported in v0.1)
- Claude Code (macOS app or CLI binary `claude`)
- Node 18 or later
- Bun 1.0 or later
- git, bash 5+, ripgrep

Recommended (the system works without these but loses features):

- Codex (macOS app or CLI binary `codex`) — for cross-agent review
- `uv` — for the optional session capture integration
- `jq` — for nicer output formatting

If anything required is missing:

- **Do not auto-install Homebrew or any system package manager.**
  That decision belongs to the user.
- Print the exact `brew install ...` command for what's missing
- Stop and wait for the user to install before proceeding

If you're unsure whether the user has a prereq (e.g., the binary
might be called something different), check explicitly before
assuming. Don't break the install over a missing tool you didn't
verify.

### 1.3 Locate or clone the repo

If the user is running you from inside an already-cloned Vepol
repo, use that path. Otherwise:

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
```

The default install location is `~/vepol`. If the user wants a
different path, they'll tell you. Ask if you're unsure.

### 1.4 Run the installer

The repo includes `install.sh` which handles the bulk of the work:

```bash
cd ~/vepol && ./install.sh
```

The installer is designed to be safe to re-run (idempotent). It
will:

- Ask before installing optional features (LaunchAgents, Telegram
  channel, claude-memory-compiler integration)
- Print color-coded progress
- Log everything to `~/vepol/install.log`
- Create `~/knowledge/` with the master schema and triad files
- Symlink `bin/` scripts so updates work cleanly
- Install the `init-kb` skill to `~/.claude/skills/init-kb/`
- Set up `~/.claude/.vepol/CLAUDE.managed.md` and add an include
  reference in `~/.claude/CLAUDE.md` (preserving any user content
  there)
- Render LaunchAgent plists with the user's actual `$HOME`

You can run it interactively (default) or with
`VEPOL_NONINTERACTIVE=1` to skip all opt-in prompts (LaunchAgents,
Telegram channel, claude-memory-compiler are all answered "no").
Use that flag only after you've confirmed with the user that
skipping those optional integrations is acceptable for the first
pass — they can always be enabled by re-running the installer.

### 1.5 Handle errors as they arise

The installer reports what failed clearly. Common cases:

- **Homebrew not installed.** Print the brew install command
  (one-liner from brew.sh), stop, wait for user.
- **Permissions issue on `~/.claude/`.** Check directory ownership;
  if it's owned by another user, the user has a setup problem
  beyond Vepol's scope.
- **launchctl bootstrap fails.** This sometimes happens on first
  boot or in nested user sessions. The plist is still created
  correctly; suggest manual `launchctl load <plist>` or running
  install.sh again later.
- **claude-memory-compiler clone fails.** This is optional —
  warn but don't block.

If you encounter an error not covered here:

1. Read the error message and the installer log carefully
2. Check what the relevant install step was trying to do
3. Try a targeted fix
4. If three attempts don't resolve it, document the failure in
   `~/knowledge/incidents.md` (creating the file if needed) and
   surface the issue to the user with the specific symptom +
   what you tried

### 1.6 Verify the install worked

After installation, run the post-install verification:

```bash
~/knowledge/bin/kb-doctor install-health
```

Expected output: zero P0 findings (critical broken installation),
zero P1 findings (significant config issues). P2 findings are
advisory and OK to ignore at install time.

If `kb-doctor` reports issues, address them before declaring the
install complete. Common P1 issues at first run:

- **Settings hook missing in `~/.claude/settings.json`.** The
  settings template should have been installed; verify by
  inspecting the file. If it's missing, copy from
  `claude/settings.json.template` (substituting `__HOME__` →
  `$HOME`).
- **claude-memory-compiler not installed.** Either install it (if
  the user wants auto-capture) or document the user's decision
  to skip.

### 1.7 Run the first-run aha sequence

This is the most important UX moment. Run it explicitly:

```bash
# 1. Verify health
kb-doctor

# 2. Show the demo briefing
kb-demo brief

# 3. Have the user write their first task
kb-task "My first Vepol task"

# 4. Confirm retrieval works
kb-search "first Vepol"
```

After each command, narrate to the user what just happened and why
it matters. This is the moment they understand they have an
operating partner, not just a folder of scripts.

## Phase 2 — Personalization

After installation, the system is generic. Personalization makes
it theirs.

### 2.1 Discover the user's projects (carefully)

**Do not recursively scan `~/`.** That can read sensitive
locations: cloud-sync roots (Dropbox, iCloud, Google Drive),
work-VPN mounts, Keychain-adjacent dirs, secret stores, archived
backups. Full-depth scans risk both privacy violations and
absurdly long execution time.

Instead, do a **shallow inspection** at known project-container
patterns. Check each at depth 1 only:

- `~/PetProjects/` (or similar) — hobby code projects
- `~/Family/` — household coordination
- `~/Health/` — health tracking
- `~/job/` or `~/work/` — paid work
- `~/Code/`, `~/Projects/`, `~/dev/` — common dev folders

**Do not look in:**

- `~/Library/`, `~/.config/`, `~/.ssh/`, `~/.gnupg/` — system /
  config / secrets
- `~/Dropbox/`, `~/iCloudDrive/`, `~/OneDrive/`, `~/Google Drive/`
  — cloud-sync mounts (privacy + multi-machine concerns)
- `~/Documents/` recursively — too generic, often contains
  personal files; if the user wants a project from there, they'll
  point you at the specific subfolder

For each candidate at depth 1, briefly check:

- Is there a `README.md`?
- Is there a `.git/` (active project)?
- Has it been modified in the last 30 days (live vs dormant)?

**Show the candidates to the user before reading any project
contents.** "I found these directories that look like projects:
[list]. Which would you like me to set up a Vepol wiki for? I
won't read inside them until you confirm."

Once the user confirms a specific project, run from inside it:

```bash
# Claude Code:
cd <project-path>
claude -p "/init-kb"

# Codex (if Claude CLI not available, or by user preference):
cd <project-path>
codex -p "/init-kb"
```

The `init-kb` skill is installed in `~/.claude/skills/` (step 1.4).
For Codex's equivalent, see if Codex has a parallel skills
mechanism on the user's machine; if not, walk through the
init-kb steps manually using the methodology in
`docs/methodology/kb-authoring-discipline.md`.

Apply [`docs/methodology/kb-authoring-discipline.md`](docs/methodology/kb-authoring-discipline.md)
during this step — do not produce false-canonical content. The
first task in any new project's `backlog.md` is a verification
session with the user.

### 2.2 Discover the user's recurring rhythms

Ask, or observe from their existing files:

- Do they work mornings or evenings?
- Do they use a calendar (Google, Apple, Outlook)? — for `kb-brief`
  to integrate with
- Do they use Telegram, Slack, or another chat? — for the brief /
  retro channel
- Do they use Garmin / Apple Health / a sleep tracker? — for the
  health-aware day plan
- Do they have email accounts they want monitored?

Wire up integrations they actually want. Don't push integrations
they didn't ask for. The system works without any of them.

### 2.3 Update the user's strategies file

`~/knowledge/personal/strategies.md` is where Vepol's working
hypotheses about how to help this specific user live. Initialize
it with what you've learned during personalization:

- Their main projects
- Their preferred communication channels
- Their morning / evening rhythm
- Any anti-patterns they mentioned ("I don't want auto-replies on
  emails")

This file is not static. Vepol will update it weekly via the
freshness loop (see [`docs/methodology/kb-freshness-loop.md`](docs/methodology/kb-freshness-loop.md)).

## Phase 3 — Ongoing evolution

After installation and personalization, you (the agent) continue
working with the user across many future sessions. Each session is
an opportunity to make Vepol *more useful for this specific user*.

### 3.1 Watch for skill opportunities

A skill is worth installing or building when:

- The user repeats a workflow more than 3 times across sessions
- The workflow is reproducible (same shape each time, just
  different content)
- The workflow currently requires the user to remember manual steps

Examples of skills that emerge from observation:

- A user who ingests articles weekly → install or build a skill
  that does the standard ingest pipeline (raw/sources/concept/log
  in one shot)
- A user who handles client invoices monthly → build a skill that
  drafts the invoice from the project's `state.md`
- A user who reviews their finances quarterly → build a skill that
  generates the structured review

When you spot a candidate skill:

1. Surface it to the user: "I notice you've done X three times.
   Would you like me to make this a one-command flow?"
2. If yes, build it as a Claude Code skill (or equivalent for
   Codex) in their `~/.claude/skills/` directory
3. Document it in their hub-level `concepts/` if it captures a
   transferable pattern

### 3.2 Watch for new project opportunities

Every project the user mentions in conversation but doesn't have
a wiki for is a candidate. After two or three mentions, propose
adding it.

Don't push projects on the user. If they say no, log the
suggestion in `escalations.md` for later but don't bring it up
again that session.

### 3.3 Watch for methodology opportunities

If you notice a recurring decision pattern, antipattern, or
discipline that would help future sessions (yours or another
agent's), lift it into `~/knowledge/concepts/` as its own page.
Apply [`docs/methodology/kb-authoring-discipline.md`](docs/methodology/kb-authoring-discipline.md).

The user reviews the lift; you don't canonize without approval.

### 3.4 Run the freshness loop

Periodically (weekly is a good cadence for active users) walk
through the curation queue:

```bash
# Read-only scan — surfaces drift findings to stdout
kb-doctor

# Persist findings to the curation queue file
kb-doctor --write
```

`kb-doctor --write` appends findings to
`~/knowledge/pending-curation.md` so the user (or a future
session) can work through them without losing context. Read that
file at the start of any curation session.

P1 findings get addressed by the user (with your support); P2
findings are advisory. Don't auto-resolve P1 content changes
without user review (per the [freshness-loop methodology](docs/methodology/kb-freshness-loop.md)).

### 3.5 Run cross-agent review on significant work

For non-trivial plans (architectural changes, migrations, new
infrastructure) — invoke
[`cross-agent-review`](docs/methodology/cross-agent-review.md):

- If you're Claude, ask Codex to review your plan
- If you're Codex, ask Claude to review your plan
- Apply the redlines that survive the user's judgment

This is not optional ceremony. It's the gate that catches the
single-agent bias profile from compounding.

## Troubleshooting common issues

### "kb-brief produces empty or generic output"

Likely causes:

- `~/knowledge/personal/.secrets` is empty (user hasn't filled in
  TELEGRAM_BOT_TOKEN, etc.) — kb-brief will run with degraded output
- `~/knowledge/log.md` is empty (no events to summarize) — wait
  for some real activity first
- The user's `state.md` files are empty across projects — the
  brief synthesizes from these

Fix by walking the user through populating one project's `state.md`
and `log.md` with real content. Then re-run `kb-brief` to show
the difference.

### "kb-doctor reports many P2 findings"

P2 findings are advisory. Common categories:

- Real-slug-in-doc — fix by replacing with placeholders if you're
  sharing publicly, ignore if it's a private hub
- Aging incidents — review with the user, close or escalate
- Backlog hygiene — sweep through with the user, close `won't do`
  items, defer others explicitly

Don't auto-fix P2 findings without user approval.

### "LaunchAgent didn't fire on schedule"

Check the LaunchAgent state and Vepol's own logs:

```bash
launchctl list | grep com.knowledge
tail -50 ~/knowledge/logs/tick.stdout.log
tail -50 ~/knowledge/logs/tick.stderr.log
```

If `~/knowledge/logs/` doesn't exist, the install didn't create
it. Create it manually (`mkdir -p ~/knowledge/logs/`) and re-load
the plist.

Common issues:

- The plist references a binary path that doesn't exist (the user
  moved their repo)
- macOS Sleep is interrupting it — schedule for waking hours
- The plist is loaded but disabled

If the plist needs to be reloaded:

```bash
launchctl unload ~/Library/LaunchAgents/com.knowledge.<name>.plist
launchctl load ~/Library/LaunchAgents/com.knowledge.<name>.plist
```

### "I get rate-limited running cross-agent reviews"

Switch the order: prefer the agent with more headroom. If both
are rate-limited, queue the review for later — don't skip it.

If rate limiting is chronic, evaluate moving to API tier instead
of consumer tier.

## What you must NOT do

- **Do not auto-install Homebrew or other system package
  managers.** Even if it would speed up the install. The user
  decides.
- **Do not overwrite `~/.claude/settings.json` from the Vepol
  template** if the user has their own. Diff first; merge only
  with explicit user approval; never silently broaden permission
  scope.
- **Do not install Vepol files into a non-Vepol `~/knowledge/`**
  without explicit user consent (back up first, or use a
  different hub path via `VEPOL_HUB`). Doing so could destroy
  another system's state.
- **Do not recursively scan `~/`.** That risks reading
  cloud-sync mounts, secrets, and other sensitive locations. Use
  shallow inspection of known project containers (see Phase 2.1).
- **Do not write to `~/knowledge/` without telling the user
  what you're writing.** Audit trail matters.
- **Do not skip the cross-agent review gate** for non-trivial
  changes. Even when the change "obviously" works.
- **Do not produce false-canonical content** during init. Apply
  [`kb-authoring-discipline`](docs/methodology/kb-authoring-discipline.md)
  rigorously.
- **Do not pretend the install worked** when it didn't. If
  `kb-doctor install-health` reports P1 issues, fix them or
  document them clearly in `incidents.md` before saying "done."
- **Do not reformat or rewrite the user's existing files**
  without explicit permission. Vepol layers on top; it doesn't
  rewrite their stuff.

## How to contribute findings back to the project

If during install or evolution you find a real bug, gap, or
opportunity in Vepol itself (not in the user's setup):

- Open an issue at https://github.com/nahornyi-ai-lab/vepol/issues
- For security-sensitive findings, follow [SECURITY.md](SECURITY.md)
- For feature suggestions, frame them around concrete use cases
  you encountered

The user benefits when their AI agent reports problems back to
upstream — it's how Vepol gets better for everyone.

## Where to find more

- [`README.md`](README.md) — product overview for the user
- [`docs/what-is-vepol.md`](docs/what-is-vepol.md) — long-form
  explanation
- [`docs/visuals/`](docs/visuals/) — visual documentation
  (architecture, autonomy growth, methodology)
- [`docs/methodology/`](docs/methodology/) — the seven
  disciplines you should apply throughout
- [`demo/README.md`](demo/README.md) — synthetic populated
  example for showing the user what a working setup looks like
