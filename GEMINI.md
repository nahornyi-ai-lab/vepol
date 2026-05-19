# Vepol — Gemini CLI Adapter

This file exists for Gemini CLI's `GEMINI.md` project-context convention.
It is not a separate operating manual.

Read the shared Vepol installer/evolution contract first:

@./AGENTS.md

Runtime note for Gemini CLI:

- Use the repository `AGENTS.md` as the source of operational instructions.
- Treat the markdown knowledge base as the durable source of truth, not Gemini chat memory.
- If Gemini CLI hooks or memory loading are unavailable, compensate manually: read the relevant KB files before work and write durable outcomes back before stopping.
- Keep Gemini-specific details here only when they are truly about Gemini CLI behavior. Shared rules belong in `AGENTS.md`, `CLAUDE.md`, or the KB schema.
