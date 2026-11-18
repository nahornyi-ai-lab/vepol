# Vepol — repository instructions

If you are an AI agent (Claude Code, Codex, Antigravity CLI `agy`, or another
CLI agent with terminal access) and the user asked you to install Vepol on
their Mac or to keep improving it with them, **your operating manual is
[AGENTS.md](AGENTS.md)** in this folder. The step-by-step install flow is
[SETUP.prompt.md](SETUP.prompt.md). Read AGENTS.md end to end before you act.

If `AGENTS.md` is missing or unreadable in the repo you are working from,
**stop and ask the user.** Do not guess the install steps. Being told to
install Vepol with no manual present means the repo is broken or partial; it
is not permission to improvise.

AGENTS.md covers:

- Phase 1: installing Vepol by driving `install.sh` (agent modes, optional
  extras, verification and the first-five-minutes proof)
- Phase 2: making it the user's own (projects, Telegram, mail, calendar,
  health data)
- Phase 3: growing it with the user across sessions
- Troubleshooting, what you must not do, and how to report problems upstream

Claude Code loads a project's `AGENTS.md` on its own only when there is no
`CLAUDE.md` or `CLAUDE.local.md` in the working folder or above it. This folder
has this `CLAUDE.md`, so Claude Code would skip `AGENTS.md` here; the line below
imports the manual instead:

@AGENTS.md

Codex reads `AGENTS.md` natively, and so does Antigravity CLI when started from
this folder with `agy --add-dir "$PWD"`. Every agent ends up with the same
manual.

## For human readers

This file points AI agents to their manual. The product documentation is here:

- [README.md](README.md): what Vepol is and how to install it
- [docs/getting-started.md](docs/getting-started.md): install and first steps
  in detail
- [docs/features.md](docs/features.md): every module and what it needs
- [docs/what-is-vepol.md](docs/what-is-vepol.md): the long-form explanation of
  what Vepol is and is not
- [docs/methodology/](docs/methodology/): how agents work with the knowledge
  base
- [docs/visuals/](docs/visuals/): diagrams
