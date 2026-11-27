# Getting started with Vepol

This guide gets Vepol working on your Mac in about an hour. By the end, Vepol is installed
and checked, and your first task and idea are saved and easy to find.
One of your projects has its own memory, and your daily routine is ready to arrive in
Telegram.

Each step says what you get, then shows the commands. Run them in order.

1. [Before you start](#before-you-start)
2. [Install](#install)
3. [Put Vepol's commands on your PATH](#put-vepols-commands-on-your-path)
4. [Install the Python packages](#install-the-python-packages)
5. [Check the install](#check-the-install)
6. [Your first five minutes](#your-first-five-minutes)
7. [Give a project its memory](#give-a-project-its-memory)
8. [If you already had Claude Code settings](#if-you-already-had-claude-code-settings)
9. [Turn on your daily routine](#turn-on-your-daily-routine)
10. [Open Vepol Desktop](#open-vepol-desktop)
11. [Upgrade](#upgrade)
12. [Uninstall](#uninstall)

## Before you start

You need a Mac with macOS 13 (Ventura) or later and these tools:

| Tool | What Vepol uses it for |
|---|---|
| Claude Code, the `claude` command-line tool (not the Claude desktop app) | Your agent sessions, the start-of-session hook, `/init-kb` and the model calls in your routines |
| `git` | Getting and upgrading Vepol |
| `rg` (ripgrep) | `kb-search` |
| `python3` 3.10 or later | The start-of-session hook and most `kb-*` commands |
| `bash` 5 or later | Hooks and scripts (macOS ships bash 3.2) |

With Homebrew:

```bash
brew install bash ripgrep git python@3
curl -fsSL https://claude.ai/install.sh | bash   # Claude Code; or: brew install --cask claude-code
```

Then open a new terminal and run `claude` once to sign in.

Other tools are optional, and each one switches on an extra. The one most worth adding is
the Codex CLI. With it, the brief and the retro run on Codex first and switch to Claude Code
when Codex is unavailable. Codex's Gmail plugin is also how Vepol reads your mail for the
brief and the retro. Any standard Codex install works, for example `npm i -g @openai/codex`;
then run `codex login`.
The full list, with versions and install commands, is in
[the dependency matrix](dependency-matrix.md).

Vepol always installs into `~/knowledge`; another location is not supported yet. If you
already have a folder there, back it up first. The installer keeps your files, but it adds
its own folders and files next to them.

## Install

There are two routes. Both run the same installer, `install.sh`, and end in the same place.

### Let an agent install it (recommended)

Open [`SETUP.prompt.md`](../SETUP.prompt.md), copy the prompt in the box and paste it into
Claude Code or Codex. The agent:

1. Clones Vepol to `~/vepol`, after asking you, and checks that the installer is new enough
   (`./install.sh --capabilities --json`).
2. Looks at your Mac without changing anything (`./install.sh --probe --json`) and tells you
   what is missing. It shows you the install command; you run it yourself.
3. Shows you the plan (`./install.sh --dry-run --json`) and asks which extras you want.
4. Installs with only the extras you approved (`./install.sh --apply`), then checks the result
   (`./install.sh --verify --json`).
5. Reads you the install receipt from `~/knowledge/install/receipts/`.

The prompt tells the agent to ask before it installs software, changes files outside the
clone or loads a background service. It never uses `sudo`, and it stops instead of
improvising when something is missing. The installer makes every file change; the agent only
drives it.

### Install by hand

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
./install.sh
```

The installer checks your tools first. If something is missing, it prints the exact install
command and stops; install it and run `./install.sh` again. It never installs a package
manager and never uses `sudo`.

Then it sets up the hub: `~/knowledge`, the one central folder that links every project. It
links Vepol's commands (`kb-*` and `new-wiki`) into `~/knowledge/bin` and installs three
Claude Code skills: `init-kb`, `development-loop` and `orchestrator-setup`. It adds a short
Vepol block to `~/.claude/CLAUDE.md` (your own text stays) and creates
`~/.claude/settings.json` only if you have none.

Next it asks about the extras. Every question defaults to no. You can run `./install.sh`
again later to say yes.

| The installer asks | What yes does |
|---|---|
| Apply this migration now? | Asked only if your `~/.claude/settings.json` lets Claude Code skip permission prompts. It turns that off and keeps a backup. |
| Add Vepol's session hooks to your existing settings.json? A backup is kept. | Asked only if you already had a `settings.json`. See [If you already had Claude Code settings](#if-you-already-had-claude-code-settings). |
| Install scheduled tasks? | Starts your daily routine in the background. See [Turn on your daily routine](#turn-on-your-daily-routine). |
| Create the Claude Code Telegram plugin scaffold (a second bot; token filled later)? | Prepares `~/.claude/channels/telegram/.env` for Claude Code's own Telegram plugin, which lets you chat with Claude in Telegram. The morning brief does not need it. |
| Use local Qwen for digest audio and send MP3 to Telegram? (No keeps NotebookLM) | Asked on a new install only. Downloads a voice model so your morning and evening digests arrive as MP3s in Telegram. Needs Apple Silicon, `uv`, `ffmpeg` and about 10 GiB free. If it fails, the install carries on with NotebookLM. |
| Install claude-memory-compiler for automatic session capture? | Clones a small open-source tool to `~/claude-memory-compiler`. After each Claude Code session in a project with its own memory, it writes what was decided and learned to that project's `knowledge/daily/` and adds a line to `log.md`. Needs `uv`. |

At the end, the installer runs a health check (`kb-doctor install-health --strict`). It
writes a receipt to `~/knowledge/install/receipts/` and prints what to try next.

Vepol writes to you in your Mac's language. The installer reads it from your terminal's
locale and falls back to English. To change it, edit `language:` in
`~/knowledge/personal/profile.yaml`, for example `language: en`.

## Put Vepol's commands on your PATH

The installer does not change your `PATH`. Add `~/knowledge/bin` once, so you can type
`kb-task` instead of `~/knowledge/bin/kb-task`:

```bash
echo 'export PATH="$HOME/knowledge/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

zsh is the default shell on macOS. If you use bash, write the line to `~/.bash_profile`
instead. The rest of this guide assumes the `PATH` is set. If you skip this step, put
`~/knowledge/bin/` in front of each Vepol command.

## Install the Python packages

`kb-idea` and the people commands need a few Python packages. The installer checks for them
but does not install them. Install them now:

```bash
cd ~/vepol
python3 -m pip install --user -r requirements.txt
```

If pip stops with `externally-managed-environment` (Homebrew's Python does this), run this
instead:

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
```

Vepol's commands run the first `python3` on your `PATH`, and scheduled tasks look in
`/opt/homebrew/bin` first. Install the packages into that Python, not into a virtual
environment, which scheduled tasks never see. With Homebrew's Python, one install serves both
your terminal and the daily routine. If a package is missing, `kb-idea` and `kb-contact` stop
with one line that names it and the command to install it.

The NotebookLM audio, the default route for the audio digests, needs the `notebooklm`
command. Install it with pipx and sign in:

```bash
brew install pipx
pipx ensurepath          # once, so your terminal finds ~/.local/bin; open a new terminal after it
pipx install notebooklm-py && notebooklm login
```

pipx puts `notebooklm` in `~/.local/bin`, where scheduled routines look for it. They also
check your `PATH` and `KB_NOTEBOOKLM_BIN`. `requirements.txt` installs the same package, but
a `--user` install can put the command in a folder such as `~/Library/Python/3.X/bin`, which
scheduled routines never search.

## Check the install

```bash
kb-doctor install-health
```

It checks the installed files, the Claude Code hooks, the scheduled tasks you turned on,
session capture, the tools Vepol needs and the Python packages above (for the `python3` on your
`PATH`). The first line is the summary:

```text
kb-doctor 2026-11-18: P0=0 P1=0 P2=0 info=12
```

`P0=0 P1=0` means the install is healthy. P0 marks a broken part and P1 a problem to fix;
each line names what is wrong and where. A missing Python package is a P1 that names the
package and the `pip` command to install it. P2 and info lines are notes, mostly about optional
extras you have not turned on. Add `--verbose` to see them all. With `--strict`, the command
exits 2 on any P0 and 1 on any P1. The installer runs it that way.

## Your first five minutes

Four steps show the core of Vepol: write something down, find it again, catch an idea, and
see what a morning brief looks like.

1. **Write your first task.** It goes on the hub's task board, `~/knowledge/backlog.md`.

   ```bash
   kb-task "My first Vepol task"
   ```

   It prints one line: `✓ Added to hub board (id: …)`.

2. **Find it again.** `kb-search` looks through the hub and every project's notes. It never
   reads `.secrets` or other secret files.

   ```bash
   kb-search "first Vepol"
   ```

   It shows the task in `~/knowledge/backlog.md`.

3. **Catch an idea.** Each idea becomes its own card in `~/knowledge/personal/ideas/`, ready
   to triage, park or turn into a task later. `kb-search` finds it too.

   ```bash
   kb-idea capture "My first Vepol idea"
   kb-search "first Vepol idea"
   ```

4. **See a morning brief.** `kb-demo` runs any `kb-*` command against a private copy of an
   invented demo hub (in `~/.vepol/demo-knowledge`), so your own notes and your clone stay
   untouched.

   ```bash
   kb-demo brief
   ```

   A model writes the brief, so this step needs Claude Code or Codex signed in, and it can
   take a few minutes. It prints the brief and sends nothing.

More on ideas, from capture to calendar block: [Idea intake](modules/idea-intake.md).

## Give a project its memory

A project with its own memory keeps where it stands, what happened, what was decided and what
comes next. It lives in a `knowledge/` folder inside the project. Every Claude Code session
you open there starts from it. There are three ways to set it up, and all three use the same
tool, `new-wiki`.

**In Claude Code (recommended).** Open Claude Code in the project folder:

```bash
cd ~/code/my-app
claude
```

Then type `/init-kb` at the Claude Code prompt. Claude reads the project and proposes a short
name (the slug), a category and a one-line description. It waits for your OK before it writes
anything. Because of this back-and-forth, `/init-kb` does not work with `claude -p`.

**From the terminal.**

```bash
new-wiki ~/code/my-app
```

The slug comes from the folder name. The full form is
`new-wiki <path-to-project> [slug] [category] [description]`, where the category is `lab`
(research and experiments), `order` (client work), `pet` (side projects), `job` (employment)
or `personal` (everything else, the default).

**In Vepol Desktop.** Once you have [built the app](#open-vepol-desktop), choose
**Add project…** in the New session dialog and pick the folder.

Each way creates `AGENTS.md` and a `knowledge/` folder (`state.md`, `log.md`, `backlog.md` and
more), and never overwrites a file that already exists. If the project already has its own
`AGENTS.md`, your text stays and one short block, marked `BEGIN VEPOL` and `END VEPOL`, is
added at the end; it tells Codex and other agents to load Vepol's startup context. It links the
folder into `~/knowledge/projects/` and adds the project to `~/knowledge/registry.md`. Once
that file is generated by `kb-rebuild-registry`, `new-wiki` leaves it alone and prints the
entry to append to `~/knowledge/migration-2026-04-25.yaml` instead; then run
`kb-rebuild-registry apply`. Vepol Desktop does not show that entry, so on such a hub add
projects from the terminal or with `/init-kb`. Each way also adds `knowledge/` to the
project's `.gitignore`, so your notes stay out of the project's repository.

From then on, every Claude Code session in that folder starts with the project's state,
recent log and open tasks. Codex and other agents read the project's `AGENTS.md`, which tells
them to load the same context. To add a task to the project's board:

```bash
kb-task "Ship the landing page" --project my-app
```

## If you already had Claude Code settings

Vepol adds three hooks to `~/.claude/settings.json`. SessionStart loads the project's memory
when a session begins. SessionEnd and PreCompact hand the session to session capture; without
it, they do nothing.

If the installer created `settings.json` for you, the hooks are already there. That file holds
only the hooks, the status line, and permission to read `~/knowledge` and run its commands.

If you already had a `settings.json`, the interactive installer asked before adding the hooks.
`./install.sh --apply`, the route the agent uses, adds them only when you set
`VEPOL_MERGE_HOOKS=1`. To check and add them yourself:

```bash
kb-claude-hooks --check
kb-claude-hooks --apply
```

`--check` exits 0 when all three hooks are present. It exits 1 when any is missing and names
the missing ones. `--apply` first saves a backup next to the file
(`settings.json.bak-YYYY-MM-DD-HHMMSS`). Then it adds only the missing hooks and keeps every
other setting. Running it again changes nothing. The file is rewritten as JSON with two-space
indents, so its spacing may change. If the file is not valid JSON, nothing is written and the
command exits 2. `kb-doctor install-health` also reports a missing hook as P0 and names this
command.

## Turn on your daily routine

Once scheduled tasks are on and Telegram is connected, Vepol runs your day on its own:

- **Every morning**, after the 07:15 mail check, a one-minute brief arrives in Telegram. It
  holds your focus, a timed plan around today's meetings, the actions that matter, every new
  email with whether you need to act on it, ready ideas, risks and decisions. Then comes a
  review of up to three new arXiv papers on AI agents, explained in your language, one
  message per paper.
- **Every evening**, after the 20:30 mail check, a short retro lists what closed, what is
  waiting and what still needs a reply.
- **Audio digests** of the morning and evening messages are made in NotebookLM by default, or
  sent to Telegram as MP3s with the local Qwen voice.

Each brief is saved to `~/knowledge/briefs/` before it is sent, and every run writes to
`~/knowledge/logs/`. A model writes the brief and the retro, so Codex or Claude Code must be
signed in. Mail and meetings appear once you connect them in step 3.

**1. Turn on scheduled tasks.** If you said no at install, run the installer again and answer
yes to "Install scheduled tasks?":

```bash
cd ~/vepol
./install.sh
```

To skip the questions, run `VEPOL_ENABLE_LAUNCHD=1 ./install.sh --apply` instead. Running the
installer again is safe: it keeps your notes and settings.

This loads four macOS background jobs (LaunchAgents):

- `tick` runs every 15 minutes. It starts each routine in `~/knowledge/personal/processes.yaml`
  when that routine is due.
- `planner` writes the day's schedule at 00:05.
- `people-review-bot` stays on and handles your taps on people proposals in Telegram. It is
  idle until Telegram is connected.
- `orchestrator-cycle` runs at 07:30 and 20:45. It is an experimental cycle that dispatches
  an approved plan across your projects in the morning and reviews them in the evening. It
  does nothing until you set it up for a project.

**2. Connect Telegram.**

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. Send your bot any message. Then open `https://api.telegram.org/bot<token>/getUpdates` in a
   browser, with your token in place of `<token>`, and copy the number at `"chat":{"id": ...}`.
3. Put both values in `~/knowledge/personal/.secrets`. The installer created this file with
   both lines empty and made it readable only by you. Open it in TextEdit:

   ```bash
   open -e ~/knowledge/personal/.secrets
   ```

   Then fill in the two lines:

   ```text
   TELEGRAM_BOT_TOKEN=<token from BotFather>
   TELEGRAM_CHAT_ID=<your chat id>
   ```

4. Send yourself a test message:

   ```bash
   kb-channel-send test "Hello from Vepol"
   ```

   Exit code 0 means Telegram accepted it. Exit code 3 means the token or the chat id is still
   empty, and 4 means the send failed.

Until both values are set, briefs and digests are saved in `~/knowledge` but not sent. If you
also use Claude Code's Telegram plugin, give it a different bot: two programs reading one bot
take each other's messages.

**3. Connect your sources (optional).** Each one adds to the brief:

- **Mail.** Install Codex and connect its Gmail plugin. Vepol only reads; it never sends,
  labels or deletes mail.
- **Calendar.** Connect Google Calendar in Claude Code.
- **Health.** Point the brief at a daily JSON file from your own sync, such as Garmin or Apple
  Health. The brief then opens with how you slept and one suggestion for the day. See
  [Health in the brief](health-in-the-brief.md).
- **Audio.** The default NotebookLM route needs `notebooklm login`; the audio stays in
  NotebookLM. To get MP3s in Telegram instead, switch to the local Qwen voice. It needs Apple
  Silicon, `uv`, `ffmpeg` and about 10 GiB free:

  ```bash
  brew install uv ffmpeg
  kb-tts-install
  kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend local_qwen
  ```

What runs when, how to switch each routine on or off, and the extras you can add later, such
as Money Radar and people proposals, are in [Your daily routine](daily-routine.md).

## Open Vepol Desktop

Vepol Desktop puts everything in one window: every project's memory, today's plan with
**Plan my day**, your agents in real terminals, every task, and every routine with its health.
The installer does not build it. You build it once from the clone.

You need an Apple Silicon Mac, Python 3.11 or later, Apple's standalone Command Line Tools
(run `xcode-select --install` if `/Library/Developer/CommandLineTools` is missing) and
`tmux`. Every agent terminal runs in tmux, so your agents keep running when you quit the app.

```bash
brew install python tmux
cd ~/vepol/face
"$(brew --prefix)/bin/python3" -m venv .venv
.venv/bin/python --version        # must print 3.11 or later
.venv/bin/pip install -r requirements.txt
./desktop/build.sh
open desktop/build/VepolDesktop.app
```

Name the Python explicitly, as above: a plain `python3` may be Apple's 3.9, which does not
work here.

To look around before you point the app at your own work, run `./demo.sh` from `face/` after
the build. It opens the app on an invented company with three projects, in a fresh copy at
`~/.vepol/demo-workspace`. The demo has its own port and its own tmux server, so `~/knowledge`
and your own sessions stay untouched.

The app runs from this clone and its `face/.venv`, so keep both where they are. Details are
in the [Vepol Desktop guide](../face/README.md).

## Upgrade

```bash
cd ~/vepol
./upgrade.sh --check   # shows your release and the newest one; changes nothing
./upgrade.sh
```

`./upgrade.sh` moves the clone to the newest release, re-runs the installer
(`./install.sh --apply`) and checks the result. It refreshes what Vepol manages: the command
links in `~/knowledge/bin`, the Vepol instructions Claude Code loads (`~/.claude/.vepol/CLAUDE.managed.md`),
the skills and the project template in `~/knowledge/_template/`. It leaves your notes,
`.secrets`, `processes.yaml`, `settings.json` and scheduled tasks as they are. When you are
already on the newest release, it still re-runs the installer, which repairs missing links.

To turn on an extra while you upgrade, set its variable, for example
`VEPOL_ENABLE_LAUNCHD=1 ./upgrade.sh`.

Upgrades follow releases, not `main`. If you cloned `main` and it is ahead of the newest
release, `./upgrade.sh` moves you back to that release. To stay on `main`, run `git pull` in
`~/vepol` and then `./install.sh --apply`. If local changes in the clone block the switch,
the upgrade stops before it changes anything else.

If you use Vepol Desktop, run the `.venv/bin/pip install` and `./desktop/build.sh` lines
again in `~/vepol/face` after an upgrade, then reopen the app.

## Uninstall

```bash
cd ~/vepol
./uninstall.sh --dry-run   # lists what would go; changes nothing
./uninstall.sh
```

It asks once, then removes only what Vepol manages:

- the command links in `~/knowledge/bin` and the `~/knowledge/orchestrator-seed` link;
- `~/.claude/.vepol/` and the Vepol block in `~/.claude/CLAUDE.md` (your own text stays);
- the `init-kb`, `development-loop` and `orchestrator-setup` skills it installed;
- Vepol's scheduled tasks, each stopped before its file is removed.

It keeps `~/knowledge` and every note in it, and the clone in `~/vepol`. Add
`--backup-user-data` to save the hub to `~/vepol-knowledge-backup-<timestamp>.tgz` first, and
`--yes` to skip the question.

At the end, it lists anything it left in place on purpose, with how to remove it:

- Vepol's hooks and status line in `~/.claude/settings.json`. Remove the hook entries,
  because they run `~/knowledge/bin` commands the uninstall removed. Remove the `statusLine`
  entry before you delete its script.
- `~/.claude/statusline-command.sh`.
- `~/claude-memory-compiler`, if you installed session capture.
- The local Qwen voice in `~/.local/share/vepol-qwen-tts`.
- `~/.claude/channels/telegram/`.

Vepol Desktop keeps its sessions in `~/.vepol/`. Delete that folder too if you built the app.

## Where to go next

- [Your daily routine](daily-routine.md): every routine, when it runs and how to change it.
- [Features](features.md): everything Vepol does, module by module.
- [People](modules/people.md): a card per person, with follow-up reminders.
- [Security and privacy](security-and-privacy.md): what Vepol touches and what stays private.
- `~/knowledge/AGENTS.md`: the rules every agent follows in your knowledge base.
- [Methodology](methodology/): how agents work with the knowledge base.
