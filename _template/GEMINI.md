# {{PROJECT_NAME}} — Gemini CLI adapter

This file exists for Gemini CLI's `GEMINI.md` convention.
It is not the canonical project contract.

Read the canonical project contract first:

@./AGENTS.md

Runtime notes for Gemini CLI:

- Treat `knowledge/` plus the hub at `~/knowledge/` as durable state.
- If Gemini hooks or memory loading are unavailable, manually read the relevant KB files before work and write durable outcomes back before stopping.
- Durable write-back targets include `log.md`, `state.md`, `incidents.md`, `backlog.md`, `escalations.md`, `index.md`, and relevant topic pages as described in `AGENTS.md`.
- Keep Gemini-specific behavior here only when it cannot live in `AGENTS.md`.
