# {{PROJECT_NAME}} — Claude Code adapter

This file exists for Claude Code's `CLAUDE.md` convention.
It is not the canonical project contract.

Read the canonical project contract first:

@./AGENTS.md

Runtime notes for Claude Code:

- Treat `knowledge/` plus the hub at `~/knowledge/` as durable state.
- Keep Claude-specific behavior here only when it cannot live in `AGENTS.md`.
- If this adapter and `AGENTS.md` conflict, `AGENTS.md` wins unless the user says otherwise.
