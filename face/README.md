# Vepol Desktop

A native macOS window for Vepol. The agent runs as an ordinary interactive
session in a real terminal inside the window, and the views around it show your
work: a session board with manual stages, every project's tasks, and every
scheduled Vepol process.

## Build and open

Create the app's Python environment once, then build with the installed
Command Line Tools:

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

## Terminal sessions

- «+ New session» (or «+» in a board column, which also places the session in
  that stage) opens the project's terminal for the chosen runtime (Claude or
  Codex). There is one terminal per project and runtime; asking for a second one
  opens the existing terminal and says so.
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
- **Session view** — a project → sessions tree on the left with the same state
  dots, and on the right the tabs «Session» and «Knowledge». Knowledge is a
  read-only explorer of the project's `knowledge/` folder (folders collapse, a
  name filter searches all of them, files open as plain text up to 512 KB).
- **Usage bar** along the bottom: `Claude 5h · 7d` and `Codex 7d` used
  percentages with «as of» times, grey when older than 6 hours, «no data» when
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
and Node with Playwright for the browser journeys. The Tasks and Automations
journeys read `bin/kb-board`, `bin/_kb_processes.py` and
`_template/knowledge/backlog.md` from `VEPOL_FIXTURE_KB_ROOT` if set, else from
the Vepol repository this folder sits in, else from `~/knowledge` (read-only;
fixtures run on temporary copies). Nothing touches your real conversations,
your tmux server or a real agent: each run uses its own state directory, its own
tmux server and `/bin/cat` in place of the agent.

From this directory, outside tmux:

```sh
.venv/bin/python -m pytest tests/
for s in board tasks automations orca-extras; do
  NODE_PATH=/path/to/node_modules VEPOL_FACE_PYTHON=$PWD/.venv/bin/python \
    node tests/browser/$s-e2e.cjs
done
```

`NODE_PATH` points at a `node_modules` that contains `playwright`.
