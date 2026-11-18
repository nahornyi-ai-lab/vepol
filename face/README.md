# Vepol Desktop

Vepol Desktop puts all of Vepol in one Mac window. You see where every project
stands and what today's plan is. You run your agents in real terminals right
next to that memory. You keep an eye on every task and every scheduled routine.

The app reads the same Markdown files your agents and routines write in
`~/knowledge`. It never edits your notes itself: closing a task goes through
`kb-board`, and adding a project goes through `new-wiki`. The app runs on your
Mac and listens on `127.0.0.1` only.

Vepol Desktop is optional, and `install.sh` does not build it. You build it
once from this folder on an Apple Silicon Mac. See [Build and open](#build-and-open).

## What you get

### Memory: where every project stands

The app opens on **Memory**.

The **Today** card at the top shows today's plan: the goal, two or three
outcomes, the time blocks (fixed events, such as meetings, are marked
**fixed**), the plan's status (for example **Draft**, **Confirmed** or **In
calendar**) and its latest change. Before you plan the day, it says there is
no plan yet.

**Plan my day** turns the morning brief into a plan you agree with:

1. Click **Plan my day** and pick an agent.
2. A planning session opens in a terminal in your hub. Its opening line
   waits above the terminal with **Type into terminal**. When the agent is
   ready, click it and press Enter.
3. The agent reads today's brief (if you have one), your goals and today's
   calendar. It proposes one plan and saves every version with `kb-dayplan`.
   You correct it in plain words until it fits.
4. When you say yes to the whole plan, the agent records your confirmation.
   The blocks go to Google Calendar only if you then ask for that in a separate
   message, and only through `kb-dayplan calendar`.

The plan is saved in `~/knowledge/personal/day-plans/<date>.json`. Clicking
**Plan my day** again on the same day reopens that day's planning session.
Reading and writing the calendar needs Google Calendar connected in Claude
Code. Without it, the agent asks you for the day's fixed times. When you plan
with Claude Code, its Google Calendar connector is switched off for that
session, so the calendar changes only through `kb-dayplan`.

Below the Today card there is one card per knowledge base: your hub first,
then every project, the most recently active first. Each card shows:

- **Now**: the first paragraph of the project's `state.md`.
- **Next**: the task in progress, or else the first ready one, with counts of
  tasks in progress, ready and blocked.
- **Last decision** from `decisions/` and **Last activity** from `log.md`.
- A status chip: **Up to date**, **Needs review** (the log is more than three
  days newer than `state.md`) or **No state file**.

### A project on one screen

Click a card, or a project in the sidebar, to open the project screen:

- **State**: the snapshot from `state.md`, the next task and when `state.md`
  last changed. **Show full state** unfolds the whole file.
- **Sessions**: every session in this project. The ones waiting for you or
  with an agent running come first. Click one to open it in a tab.
- **Board**: the project's tasks in columns: In Progress, Review, Blocked
  (only when it has tasks), Ready and Backlog, with Done folded below. **Open
  in Tasks** opens the Tasks table filtered to this project.
- **Decisions**, **History** (the log), **Lessons** (the prevention rules in
  `incidents.md`) and **Files** (the whole `knowledge/` folder).

Everything here is rendered Markdown and read-only. **New session here** asks
which agent to start in this project.

The sidebar lists your projects. A green dot marks a project where an agent is
running.

### Your agents in real terminals

**+ New session** asks where to work: your hub or any project linked into it,
the most recently active first, with a search field. Pick the agent at the
top: Claude Code, Codex, Antigravity (`agy`), Hermes, OpenCode or Grok. The
dialog offers every one of them that is installed and listed in your hub's
agent list, `~/knowledge/.orchestrator/cli-tools.tsv`. A colored dot shows what
Vepol last saw of each agent, such as a recent quota limit. It never stops you:
the agent's own terminal tells you about logins and quotas.

The **+** in the tab strip opens the same dialog. The **+** at the top of a
board column does too, and puts the new session in that stage.

Every new session gets its own terminal. You can run several agents side by
side in one project, even two copies of the same agent.

**Add project…** at the bottom of the dialog turns any folder into a Vepol
project. Choose a folder in the macOS panel, or create a new one there. The
hub's `new-wiki` then:

- adds an `AGENTS.md` and a `knowledge/` folder (state, log, backlog and the
  rest) where they are missing, and never overwrites a file;
- keeps your own `AGENTS.md`, if the folder has one, and appends one short
  block, marked `BEGIN VEPOL` and `END VEPOL`, that tells agents where the
  project's memory is and how to load it (a linked or read-only `AGENTS.md`
  is left as it is);
- adds `knowledge/` and `.kb-ignore` to the folder's `.gitignore`;
- links the project into your hub and notes it in the hub's log;
- adds a row for it to the hub's `registry.md` when you keep that file by hand.
  When `kb-rebuild-registry` generates that file, the project is not added to
  it, and the app does not show the migration-table entry `new-wiki` prints
  for that case. On such a hub, add projects with `new-wiki` in a terminal,
  append the entry it prints to `~/knowledge/migration-2026-04-25.yaml`, then
  run `kb-rebuild-registry apply`.

It does not ask first: choosing the folder sets it up, and your new session
starts there. A folder that is already a project just opens.

#### The terminal

The terminal is a real terminal (xterm.js) on a `tmux` session that stays out
of sight: no status bar, the mouse wheel scrolls back, and `Ctrl-B` goes to the
agent, not to tmux. You type straight into it, and it follows the window size.
It opens your login shell in the project folder and types the agent's command
for you.

- The agent starts only when you ask: when you create the session, or when you
  click **Start**. Opening a session only attaches to it.
- The header shows the agent's state, read from the process itself: **Agent
  running · PID 12345**, **Agent not running** with **Start**, or **State
  unknown** with the reason. The board card shows the same state.
- Exit the agent and you are back at your shell in the project folder. **Start**
  types the agent's command again. Nothing restarts on its own.
- Quit Vepol and the terminal and the agent keep running. On the next launch
  the same session comes back with the same PID.

Vepol starts Claude Code with `--permission-mode manual` and Codex with
`--sandbox workspace-write --ask-for-approval on-request`, so a permissive
default in your own config does not apply here. Antigravity gets
`--add-dir <project folder>`. Antigravity and Grok ask once per folder whether
you trust that folder; you answer in the terminal. Hermes works in the folder set by
`terminal.cwd` in `~/.hermes/config.yaml`, not in the project folder.

#### Take a session over in Terminal.app

Open a session and look at the **Session** tab in the right panel. Under
**Open the same terminal** it shows the exact command, for example:

```sh
tmux attach -t kb-acme-web-1a2b3c4d5e6f-claude
```

Run it in Terminal.app, or any terminal, and you continue the same session
with the same agent and the same history.

#### Tabs and the Memory panel

Every session you open becomes a tab along the top. Closing a tab leaves the
agent running. Your tabs come back after you quit and reopen the app, and the
tab you had selected opens again. Reopening only attaches; it never restarts
an agent.

The **Memory** tab in the right panel is a read-only explorer of the project's
`knowledge/` folder, next to the terminal. Folders fold, a filter searches
every file name, Markdown opens rendered and other files open as plain text
(up to 512 KB). **Open project memory** jumps to the project screen.

### Sessions board

**Sessions** shows every session as a card in five stages: Queue, Research,
Working, Review and Done. You choose the stage: drag a card, or use the stage
menu on it. Search and a project filter narrow the board.

Each card shows the agent's own title for that session and, for most agents,
its last message, read from the agent's local files. It also shows the
project, its folder and the agent's state. A session you started from a task shows the task's status, and
it moves to Done by itself when the task is done or closed.

### Tasks

**Tasks** puts every project's `knowledge/backlog.md`, and the hub's
`backlog.md`, in one table. It reads them through `kb-board`. Status chips
(Active, Backlog, Closed, All), a project filter and search narrow the list.

- **Start session** asks which agent to use and starts it in that project. The
  task line then waits above the terminal with **Type into terminal**, which
  types it for you without pressing Enter. If the task already has an open
  session, that session opens instead.
- **Close** on a Backlog, Ready or Blocked task asks once, with an optional
  reason, and moves the task to **Cancelled** through `kb-board cancel`.
  **Undo** in the banner puts it back through `kb-board reopen`. A task that
  was Blocked comes back as Ready.

The app never edits a board itself. Claiming tasks, every other status change
and new tasks stay with your agents.

### Automations

**Automations** lists every routine in `~/knowledge/personal/processes.yaml`:
the morning brief, the evening retro, mail summaries, the arXiv review, Money
Radar, the audio digests and the rest. For each one you see its schedule, what
it waits for, today's state and the reason, the last and next run, and a
14-day history. Click a routine to see its last run's output and log lines.

- It checks results, not only exit codes. For the arXiv review, Money Radar,
  the audio digests and the mail summaries it reads the result file. A run
  that exited 0 without a good result shows **Failed in result**.
- A strip at the top says whether the scheduler itself is loaded.
- Every state comes from records the scheduler and launchd already keep. No
  evidence shows as **Unknown**, never as OK.
- **Other schedules** adds your Hermes cron jobs and a `com.knowledge.backup`
  launchd job, if you have them.

The routines run only if you answered yes to **Install scheduled tasks?** in
the installer. They run whether the app is open or not.

### Usage bar

The bar along the bottom shows how much of your Claude limits (5-hour and
7-day) and your Codex limits you have used, in percent, with the time of each
reading. A reading older than six hours turns gray. A missing one says
**no data**. The bar reads local files only: no network call, no credentials.

- **Codex** works on its own. The numbers come from Codex's session files in
  `~/.codex/sessions` (or `$CODEX_HOME/sessions`).
- **Claude** needs `jq` (`brew install jq`) and one line in the script that
  your Claude Code status line runs. Vepol's installer puts one at
  `~/.claude/statusline-command.sh` if you have none. Add the line after the
  line that reads Claude Code's JSON into `$input` (`input=$(cat)` in Vepol's
  script):

  ```sh
  mkdir -p ~/.vepol/face && printf '%s' "$input" | jq -e '.rate_limits' >/dev/null && printf '%s' "$input" | jq -c '{rate_limits, at: now}' > ~/.vepol/face/.crl.tmp && mv ~/.vepol/face/.crl.tmp ~/.vepol/face/claude-rate-limits.json
  ```

  It writes the file only when Claude Code's JSON includes `rate_limits`.

## Build and open

[Install Vepol](../README.md#install) first. The app reads your hub at
`~/knowledge` and uses the tools in it: `kb-board`, `kb-dayplan`, `new-wiki`
and the agent list.

You need:

- An Apple Silicon Mac with macOS 13 or later.
- The standalone Command Line Tools in `/Library/Developer/CommandLineTools`.
  The build uses them even when Xcode is installed, and it leaves your selected
  Xcode alone. If that folder is missing, run `xcode-select --install`.
- Python 3.11 or later, for example from Homebrew.
- `tmux`, which keeps every agent's terminal alive. Without it the app opens,
  but it cannot start an agent.

From your Vepol checkout:

```sh
brew install python tmux
cd face
"$(brew --prefix)/bin/python3" -m venv .venv
.venv/bin/python --version        # must print 3.11 or later
.venv/bin/pip install -r requirements.txt
./desktop/build.sh
open desktop/build/VepolDesktop.app
```

Name the Python explicitly when you create `.venv`. A plain `python3` is often
the 3.9 that comes with the Command Line Tools, and the app needs 3.11 or
later. Any Python 3.11 or later works, wherever it comes from.

`./desktop/build.sh` compiles the app into `desktop/build/VepolDesktop.app`
and signs it ad hoc for this Mac. It stamps the app with the version in the
repository's `VERSION` file, so **About Vepol** shows the release you built.
To build against another macOS SDK, pass `SDK=<path>` to `./desktop/build.sh`.

This is a local build, not a packaged release. It is not notarized, and Python
is not bundled. The app runs its backend straight from this checkout with
`.venv/bin/python`:

- When you update the checkout, quit and reopen the app to use the new
  backend.
- Rebuild when `desktop/` changes, or after you move the checkout.
- Run the `pip install` line again when `requirements.txt` changes.

## Try it on the sample workspace

Want to look around before you point the app at your own work? After the
build, run this from `face/`:

```sh
./demo.sh
```

It opens the app on an invented software company: a hub and three projects,
`acme-web`, `design-system` and `billing-api`. Each project has its state,
tasks, decisions, lessons, history and a little code.

What the demo keeps apart from your own setup:

- It works on a fresh copy in `~/.vepol/demo-workspace/`. Each run replaces
  the previous copy.
- It uses its own port (8782), its own app state and its own `tmux` server, so
  demo terminals never reach your sessions.
- Agents you start there get the copy as their hub (`KB_HUB`).
- Your `~/knowledge`, your Vepol conversations and your tmux sessions are not
  touched.

What still comes from your Mac:

- The agents are your real agent CLIs, with your own logins, settings and
  quotas. The agent list comes from `~/knowledge/.orchestrator/cli-tools.tsv`.
- **Plan my day** reads your real calendar, and writes to it only if you ask.
- **Add project…** writes into the folder you choose, so choose a scratch
  folder.
- **Automations** shows an error for the demo's own routines (the sample has
  no `processes.yaml`), next to your real scheduler status, Hermes jobs and
  backup job.
- The usage bar shows your real Codex usage.

To take a demo session over in Terminal.app, point tmux at the demo's own
server and use the session name from **Open the same terminal**:

```sh
TMUX_TMPDIR="$(cat ~/.vepol/demo-workspace/.tmux-dir)" tmux attach -t <session name>
```

Quit the demo app with `Cmd-Q`. The next `./demo.sh` ends the previous demo's
terminals before it replaces the copy. If port 8782 is still in use,
`./demo.sh` stops and tells you a demo is already running.

## How it works

- **Two parts.** A small Swift app (`desktop/`) draws the window. It starts
  the backend, a local FastAPI server (`vepol_face/`), with this checkout's
  `.venv/bin/python`. The page inside the window talks only to that backend.
- **Local only.** The backend binds `127.0.0.1:8781` and refuses any other
  address. If something else holds the port, the app shows the error with
  **Retry**; it never moves to another port. It takes the port before it opens
  its conversation store in `~/.vepol/face/`, so two copies never write to it
  at once.
- **A key per launch.** Each launch makes a fresh random token in memory. The
  app hands it to the backend through an inherited pipe, never through a file,
  an argument or a URL, and injects it into the page when the page loads.
  Every API call and every WebSocket must carry it, and requests from any
  other origin are refused. The web view keeps no cookies or storage between
  launches. To bring your tabs back, the backend saves only their ids, in
  `~/.vepol/face/ui-tabs.json`. Links to other sites open in your browser.
- **Clean agent terminals.** Each agent pane starts from an empty environment
  that carries only `HOME`, `PATH`, `TERM`, `USER`, `LOGNAME`, `SHELL`,
  `LANG`, `LC_ALL`, `TMPDIR` and `KB_HUB`. No API key or token from the app's
  own environment reaches the agent. Your login shell then reads your own
  startup files, like any terminal window. Each session has its own tmux
  session, named `kb-<project>-<id>-<agent>`.
- **State from evidence.** The agent's state comes from the process: the
  pane's PID and the program in the foreground. Screen output is never used.
- **Window and quit.** `Cmd-W` closes the window and keeps everything running;
  the Dock icon or `Cmd-0` brings it back. `Cmd-R` reloads the page. `Cmd-Q`
  checks with the backend first. If an older structured session is still
  working or waits for your decision, Vepol stays open and says so. Otherwise
  the backend shuts down cleanly. Agent terminals live in tmux and keep running
  either way, so an agent at work in a terminal never holds up a quit.
- **Older sessions.** Structured sessions and one-shot runs created by earlier
  versions keep their history and still open. New sessions are always
  terminals.
- **Legacy browser entry.** `./run.sh` starts the earlier browser version on
  `127.0.0.1:8781` for existing automation. It passes the token in the URL,
  and the page drops it from the address bar, so a reload loses the session.
  Use the app for everything on this page.
- **Removing it.** `uninstall.sh` does not touch Vepol Desktop. To remove it,
  quit the app and delete `face/desktop/build/`, `face/.venv`, `~/.vepol/face/`
  (your session list and tabs) and, if you ran the demo,
  `~/.vepol/demo-workspace/`. Agent terminals you left running stay in tmux
  until you exit them.

## Run the tests

The tests need `pytest` and `httpx` in the app's `.venv`, and Node with
Playwright for the browser journeys. From `face/`:

```sh
.venv/bin/pip install -r requirements.txt pytest httpx
```

Run them outside tmux:

```sh
.venv/bin/python -m pytest tests/
for s in memory today board tasks automations orca-extras projects; do
  NODE_PATH=/path/to/node_modules VEPOL_FACE_PYTHON=$PWD/.venv/bin/python \
    node tests/browser/$s-e2e.cjs
done
```

`NODE_PATH` points at a `node_modules` folder that contains `playwright`.

The browser journeys use the hub's own tools, read-only: `bin/kb-board`,
`bin/kb-dayplan`, `bin/new-wiki`, `bin/_kb_processes.py` and `_template/`. They
take them from `VEPOL_FIXTURE_KB_ROOT` if it is set, else from the Vepol
checkout this folder sits in, else from `~/knowledge`. Fixtures run on
temporary copies. Nothing touches your real conversations, your tmux server or
a real agent: each run has its own state folder, its own tmux server and
`/bin/cat` in place of the agent.
