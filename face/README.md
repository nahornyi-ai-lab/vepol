# Vepol Desktop

A native macOS window for Vepol conversations. The session board keeps manual
work stages separate from the agent's current activity. Search, project
filters, stage selection and drag/drop help return to the original conversation.

## Build and open

The local development build uses the installed Command Line Tools directly:

```sh
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

## Sessions

- **Persistent session** is the app default: Claude stream-json or Codex
  app-server. Consecutive turns reuse the process and provider conversation.
  Tool activity, streamed text and requests for human input appear in the app.
  Permission decisions use the runtime's existing policy and explicit UI
  answers; Vepol does not grant persistent permission rules.
- **Terminal** uses the canonical tmux session for a project/runtime pair.
  Open its displayed attach command, complete CLI startup/login/trust, then
  click the readiness button to send the retained first prompt. Completion is
  marked by the human, never inferred from terminal output or silence. Closing
  Vepol leaves that terminal session alive.
- Existing cards and history are preserved. An old card without a verified
  provider identity cannot silently become a new session. Failed exact resume
  is shown as unavailable continuation.

A structured session currently has no same-process terminal takeover. The UI
states this explicitly; the complete Desktop v2.1 S5 criterion remains open.
A live session also does not fire SessionEnd after each turn. Use the visible
save-to-wiki action to request a checkpoint from that same agent.

## Legacy browser entry

`./run.sh` keeps the earlier browser/one-shot entry for existing automation.
It uses tokenized launch URLs and has the historical browser reload/history
limitations. Use the native entry for the session board experience above.

## Verification

Reuse the critical board-persistence journey and the complete browser board
journey; native acceptance additionally exercises the actual `.app`, live
Claude/Codex conversations, input requests, reload, manual stage persistence
and shutdown. Run the suites from this directory with `.venv/bin/python -m
pytest tests/`.
