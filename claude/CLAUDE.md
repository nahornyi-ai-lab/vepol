# Claude Code Global Adapter

This file is loaded by Claude Code on this machine.
It is not the canonical orchestrator contract.

Read the canonical machine-wide contract first:

@__HOME__/knowledge/AGENTS.md

Runtime notes for Claude Code:

- Treat `__HOME__/knowledge/` as the global source of truth.
- Treat each project `knowledge/` directory as durable project state.
- Runtime-native files such as `CLAUDE.md` are adapters only; `AGENTS.md` wins on conflict unless the user says otherwise. Antigravity CLI (`agy`) reads `AGENTS.md` natively via `agy --add-dir <path>`.
- Keep Claude-specific behavior here only when it cannot live in `AGENTS.md`.
