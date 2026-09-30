# Vepol Desktop

A native macOS window for Vepol. The agent runs as an ordinary interactive
session in a real terminal inside the window, and the views around it show your
work: a session board with manual stages, every project's tasks, and every
scheduled Vepol process.

## Build and open

Vepol Desktop runs on Apple Silicon Macs. It needs Python 3.11 or later (for
example from `brew install python`) and the Command Line Tools. Create the
app's Python environment once with that Python, then build (the build uses the
Command Line Tools' macOS SDK; pass `SDK=<path>` to `./desktop/build.sh` to use
another):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./desktop/build.sh
open desktop/build/VepolDesktop.app
```

The bundle points to this checkout and its `.venv/bin/python`; keep both in
place. It is a local development bundle, not a standalone distribution.
The backend binds `127.0.0.1:8781` and refuses an existing listener before
opening the conversation store at `~/.vepol/face/`.

The native shell passes its in-memory token through an inherited pipe and
injects it at document start into a nonpersistent WKWebView. The page uses a
bare URL; reload does not discard authentication. Cmd-W closes the window
while preserving work. Reopen from the Dock or Cmd-0. Cmd-Q checks for active
work and, when idle, closes the owned protocol clients and backend naturally.

## Memory

The app opens on **Memory**: one card per knowledge base, the hub first, then
every project with the newest activity first. A card shows the project's
**Now** (the first paragraph of `state.md`), **Next** (the first task in
progress, else the first ready one, with counts from `kb-board`), the **Last
decision** in `decisions/` and the **Last activity** in `log.md`, plus a status
chip: «Up to date», «Needs review» (the log is more than 3 days newer than
`state.md`) or «No state file». Clicking a card opens the project's memory page:
State, Plans, Decisions, History, Lessons (the prevention rules in
`incidents.md`) and Files, all rendered as Markdown and read-only; «New session
here» opens a terminal in that project.

### Sample workspace

`demo/workspace/` is an invented company with a hub and three developer projects
(`acme-web`, `design-system`, `billing-api`). After building the app, open it
with:

```sh
./demo.sh
```

The script copies the sample to a fresh `~/.vepol/demo-workspace/` (replacing
the previous copy) and runs the app on port 8782 with its own state directory,
its own tmux server and `KB_HUB` set to the copy. Your own conversations, your
tmux sessions and `~/knowledge` are not touched.

## Terminal sessions

- «+ New session» (or «+» in a board column, which also places the session in
  that stage) asks which project to work in: the hub and every project linked
  in `~/knowledge/projects/`, most recent activity first (the project's own
  sessions in the app and the last change to its `knowledge/log.md`), with a
  search field and the agent. In the native app the agent can be any installed
  agent CLI from the hub roster (`~/knowledge/.orchestrator/cli-tools.tsv`):
  Claude, Codex, Antigravity (`agy`), Hermes, OpenCode or Grok; its availability
  is shown but never blocks the terminal, where the CLI itself reports login or
  quota problems. First-run screens (agy and Grok ask once per folder whether to
  trust it) are answered by you in the terminal. Hermes follows its own
  `terminal.cwd` setting in `~/.hermes/config.yaml`, not the project folder.
  It then opens that project's terminal. There is one terminal per project and
  runtime; asking for a second one opens the existing terminal and says so.
- «Add project…» in the same dialog opens the macOS folder panel (it can create
  a new folder). The chosen folder becomes a Vepol project through the hub's own
  `new-wiki` — it adds `AGENTS.md`, `CLAUDE.md` and `knowledge/` where they are
  missing, never overwrites a file, and links the project into the hub — and the
  session starts there. A folder that is already a project just opens.
- The agent starts only when you click: creating the session or clicking
  «Start». Opening a session attaches to it and never starts anything.
- The terminal is xterm.js connected to a tmux session that tmux keeps alive
  invisibly (no status bar, mouse scrolling on, Ctrl-B goes to the agent). You
  type into it directly, and it follows the window size.
- The header shows the agent's state from process evidence only: «Agent running
  · PID n», «Agent not running» with «Start», or «State unknown» with the
  reason. The same state is on the board card.
- The composer pastes a prompt into the terminal. After each app start, confirm
  once with «Terminal ready — send» that login/trust in the terminal is done.
  Completion is yours to judge; pasted prompts never mark the app busy.
- Quitting Vepol leaves the terminal and the agent running; the next launch
  shows the same PID and re-attaches. If the agent exits, the header says so and
  «Start» opens a new one — never automatically.

Conversations created earlier as persistent (structured) sessions or one-shot
runs keep their history and still open in the app.

## Views

- **Sessions** — the board: Queue / Research / Working / Review / Done, drag or
  the stage selector, search, project filter. Every card and the headings show
  folder · project · path on disk; clicking anywhere on a card opens it.
- **Tasks** — every project's `knowledge/backlog.md`, read through `kb-board`,
  as a table with status chips and search. «Start session» opens that project's
  terminal with the task text typed into the composer; nothing is sent. The view
  never writes a board.
- **Automations** — every process in `personal/processes.yaml` with its
  schedule, dependency, state and reason, last and next run, 14-day history and
  output tails, plus Hermes cron jobs and, when it is loaded or installed in
  `~/Library/LaunchAgents`, the `com.knowledge.backup` launchd job. Read-only;
  states come from the files the scheduler already writes, and «Unknown» means
  there is no evidence.
- **Session view** — a project → sessions tree on the left (every project,
  most recent activity first) with the same state dots, and on the right the tabs «Session» and «Memory». Memory is a
  read-only explorer of the project's `knowledge/` folder (folders collapse, a
  name filter searches all of them, Markdown files open rendered and other
  files as plain text, up to 512 KB) with a link «Open project memory».
- **Usage bar** along the bottom: `Claude 5h · 7d` and Codex's current
  windows as used percentages with «as of» times, grey when older than 6 hours, «no data» when
  there is none. Codex numbers come from its own rollout files under
  `$CODEX_HOME/sessions` (default `~/.codex`). Claude numbers come from a small
  file your Claude Code status line writes; add this line to your statusLine
  script, where `$input` holds the JSON Claude Code passes on stdin:

  ```sh
  printf '%s' "$input" | jq -e '.rate_limits' >/dev/null && printf '%s' "$input" | jq -c '{rate_limits, at: now}' > ~/.vepol/face/.crl.tmp && mv ~/.vepol/face/.crl.tmp ~/.vepol/face/claude-rate-limits.json
  ```

  The bar makes no network call and reads no credentials.

## Legacy browser entry

`./run.sh` keeps the earlier browser/one-shot entry for existing automation.
It uses tokenized launch URLs and has the historical browser reload/history
limitations. Use the native entry for the experience above.

## Verification

Tests need `pytest` and `httpx` in the app's `.venv` on top of
`requirements.txt` (`.venv/bin/pip install -r requirements.txt pytest httpx`),
and Node with Playwright for the browser journeys. The Tasks, Automations and
Projects journeys (and the add-project test) read `bin/kb-board`,
`bin/new-wiki`, `bin/_kb_processes.py` and `_template/` from `VEPOL_FIXTURE_KB_ROOT` if set, else from
the Vepol repository this folder sits in, else from `~/knowledge` (read-only;
fixtures run on temporary copies). Nothing touches your real conversations,
your tmux server or a real agent: each run uses its own state directory, its own
tmux server and `/bin/cat` in place of the agent.

From this directory, outside tmux:

```sh
.venv/bin/python -m pytest tests/
for s in memory board tasks automations orca-extras projects; do
  NODE_PATH=/path/to/node_modules VEPOL_FACE_PYTHON=$PWD/.venv/bin/python \
    node tests/browser/$s-e2e.cjs
done
```

`NODE_PATH` points at a `node_modules` that contains `playwright`.
