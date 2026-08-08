# Getting started with Vepol

Vepol is a local AI operating environment: a durable markdown knowledge field where you and
your agents (Claude Code, Codex, …) work over one shared source of truth. **Two agents, one field.**

There are two ways to install. Both end in the same place.

## Option A — let an agent install it (recommended)

Open the [README](../README.md) (or [`SETUP.prompt.md`](../SETUP.prompt.md)), copy the setup
prompt, and paste it to a coding agent with terminal access. The agent will:

1. Check the installer is new enough (`./install.sh --capabilities --json`).
2. Look at your machine without changing anything (`./install.sh --probe --json`).
3. Show you a plan and ask which extras you want.
4. Install (`./install.sh --apply`), verify (`--verify`), and run a quick proof.
5. Read you back the receipt under `~/knowledge/install/receipts/`.

The agent asks before every change. The installer does all the file work; the agent only drives.

## Option B — do it by hand

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
./install.sh
```

`./install.sh` walks you through the same steps interactively.

## First five minutes (the "aha")

After install, prove it works without reading any methodology first:

```bash
kb-doctor                       # system health — should be green
kb-demo brief                   # a synthesized brief from the demo project
kb-task "My first Vepol task"   # write your first task
kb-idea capture "My first Vepol idea" --source chat
kb-search "first Vepol"         # confirm retrieval finds it
```

Morning audio is built from whole finalized same-day blocks: the morning brief,
an eligible rich arXiv report, and the Money Radar digest. Vepol does not run a
second synthesis or shortening pass over them. Local Qwen narrates the frozen
source literally; NotebookLM receives the same source and may produce its own
non-literal Audio Overview. When arXiv has no new papers, the learning process
sends a short text notice and contributes no arXiv audio block.

## What's next

- `~/knowledge/AGENTS.md` — the canonical hub contract (how the field is organized).
- `docs/modules/idea-intake.md` — how event-driven idea capture works.
- `docs/methodology/` — the principles (TRIZ, spec-driven, cross-agent review) — read when curious.
- Start a wiki in a real project: `cd <project> && claude -p "/init-kb"`.

## Prerequisites & safety

- What you need installed: [`docs/dependency-matrix.md`](dependency-matrix.md).
- What Vepol touches, what stays private, and how uninstall protects your data:
  [`docs/security-and-privacy.md`](security-and-privacy.md).

## Updating / removing

```bash
./upgrade.sh      # pull latest and re-apply; never touches your data
./uninstall.sh    # remove only Vepol-managed files; your hub stays
```
