# LLM Wiki Hub — Gemini CLI adapter

This file exists for Gemini CLI's `GEMINI.md` convention.
It is not the canonical hub contract.

Read the canonical hub contract first:

@./AGENTS.md

Runtime notes for Gemini CLI:

- Treat `/Users/macbook/knowledge/` and project `knowledge/` directories as durable state.
- If Gemini hooks or memory loading are unavailable, manually read the relevant KB files before work and write durable outcomes back before stopping.
- Durable write-back targets include `log.md`, `state.md`, `incidents.md`, `backlog.md`, `escalations.md`, `index.md`, and relevant topic pages as described in `AGENTS.md`.
- Keep Gemini-specific behavior here only when it cannot live in `AGENTS.md`.
