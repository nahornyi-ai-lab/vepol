# Vepol Face

One screen for talking to Vepol, instead of jumping between Claude, Codex,
Antigravity, Grok, Telegram and terminal windows.

Local-first: the backend binds `127.0.0.1` only, mints a fresh token in memory
on every launch, and never persists it.

## Run it

```bash
./run.sh
```

It prints one URL with the token embedded and opens your browser. Stop with
Ctrl-C.

Options:

```bash
./run.sh --no-open           # don't open a browser
./run.sh --port 8790         # different port
./run.sh --hub ~/knowledge   # different hub
```

The launcher refuses to start if the port is taken (it names the process that
holds it) and refuses any non-loopback bind outright.

## What the screen shows

- **Target** — the hub orchestrator plus every project registered in
  `~/knowledge/projects/`, with a filter box.
- **Runtime** — each CLI with a live status dot. A runtime is green only after
  a **successful observation**. An expired cooldown is not availability; an
  unobserved runtime shows `unknown`, not `available`.
- **Conversation** — multi-turn, continued through the broker's stable resume
  key `vepol-face:<conversation>:<target>:<runtime>`.
- **Run** — live status, and the failure reason when there is one.
- **KB write-back** — the files the run actually changed in that target's
  `knowledge/`, or a plain statement that nothing durable changed.
- **Interactive** — the canonical `tmux attach` command for full takeover.

## The rule that shapes the whole thing

**A runtime failure is never shown as an answer.** Exit code 0 with empty
output is a failure. An unclassified error is a failure. A quota-dead runtime
is visibly dead. This is the one behaviour that separates a trustworthy agent
surface from one that quietly hands you silence.

## Nested-session containment

A live agent session exports `CLAUDECODE`, ~20 `CLAUDE_CODE_*` variables and
`ANTHROPIC_BASE_URL`. Any child process inherits them and then behaves as a
nested session — verified 2026-08-15: an inherited `claude -p` hung
indefinitely, while the same call with those variables stripped returned in
seconds.

`vepol_face.broker.clean_env()` strips them from every runtime Vepol Face
spawns, so it works whether you launch it from your own terminal or from
inside an agent session.

## Layout

```
vepol_face/
  config.py     bind policy — loopback or refuse
  auth.py       per-launch in-memory token, default-deny origins
  targets.py    target discovery from the hub's projects/ symlinks
  runtimes.py   capability read-model over the broker's own state
  broker.py     kb-orchestrator-run adapter + the "0 is not an answer" rule
  sessions.py   canonical tmux names, file-backed prompt paste
  runs.py       conversation/run persistence under ~/.vepol/face/
  evidence/     KB write-back diffing
  app.py        FastAPI + WebSocket
  server.py     launcher
  static/       the whole UI, one file, no build step
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Every test names the spec acceptance criterion it enforces. Written before the
implementation.

## Spec

`../knowledge/decisions/vepol-face-macos-app-2026-06-24.md`
(contract `sha256:3c09461b…`).

**Known deviation:** the spec pins TypeScript/React/Vite for the frontend. This
build ships a single dependency-free HTML file instead, because Node on this
machine is v17 and modern Vite needs 18+. The backend boundary, the event
shape and every acceptance criterion are unchanged; only the rendering vehicle
differs. Flagged for the spec review.
