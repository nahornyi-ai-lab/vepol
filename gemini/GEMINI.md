# Gemini CLI Global Adapter

This file is loaded by Gemini CLI on this machine.
It is not the canonical orchestrator contract.

Read the canonical machine-wide contract first:

@__HOME__/knowledge/AGENTS.md

Runtime notes for Gemini CLI:

- Answer in Russian by default unless the user asks otherwise.
- Treat `__HOME__/knowledge/` as the global source of truth.
- Treat each project `knowledge/` directory as durable project state.
- Runtime-native files such as `CLAUDE.md` and `GEMINI.md` are adapters only; `AGENTS.md` wins on conflict unless the user says otherwise.
- If hooks or memory loading are unavailable, manually read the relevant KB files before work and write durable outcomes back before stopping.
