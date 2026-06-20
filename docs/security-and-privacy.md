# Security & privacy

Vepol is local-first. Your knowledge never leaves your machine unless you wire up an
optional channel yourself. This page covers what install touches, what stays yours, and how
the agent-driven install stays safe.

## What the installer changes (managed) vs. what's yours (user data)

**Managed** (created/refreshed by `install.sh`, removed by `uninstall.sh`):
- `~/knowledge/bin/*` symlinks into the repo, `~/knowledge/orchestrator-seed` pointer
- `~/.claude/.vepol/CLAUDE.managed.md` + a small include block in `~/.claude/CLAUDE.md`
- installed Claude skills, `_template/`, and (opt-in) `com.knowledge.*` LaunchAgents

**Yours, never deleted** by upgrade or uninstall:
- everything you author in `~/knowledge/`: `raw/`, `daily/`, `projects/`, `personal/`,
  `concepts/`, `sources/`, `log.md`, `state.md`, `registry.md`, …
- `install/receipts/`, your `~/.claude/settings.json`, and your own content in `~/.claude/CLAUDE.md`

`uninstall.sh` removes only managed files and leaves your hub in place. `./uninstall.sh --dry-run`
shows exactly what it would remove first.

## Secrets

- Secrets live in mode-`600` files (`~/knowledge/personal/.secrets`, channel `.env` files) and
  are never read or transmitted by Vepol's core.
- The agent-driven install prompt is explicitly told: **never send secrets, tokens, private
  paths, or knowledge-base contents off the machine.**
- The installer never asks a model whether a token is safe — secret handling is deterministic.

## The C-01 settings migration

If you have a legacy `~/.claude/settings.json` with `permissions.defaultMode = bypassPermissions`
(or `skipDangerousModePermissionPrompt: true`), an injected prompt could trigger tool calls
without your approval. The installer detects this and:

- in interactive install, asks before migrating;
- in agent-driven `--apply`, it does **not** silently change your settings and does **not**
  abort — it completes the core install and reports `needs_security_migration` so the agent can
  explain it and get your explicit OK. Only then (`VEPOL_APPLY_C01=1`) is the migration applied,
  always after snapshotting `settings.json` and preserving its original file mode.

## Safe agent-driven install

The setup prompt requires the agent to:

- run read-only checks (`--probe`, `--capabilities`) before anything that mutates;
- **stop instead of improvising** if a tool/mode/script is missing (no hand-rolled installs or
  deletions);
- ask before installing software, loading services, or touching accounts; never `sudo` or
  install a package manager;
- treat empty/error output as failure.

If the installer is too old to support these modes, unknown flags exit non-zero with empty
output, so the agent detects it and stops rather than running a blind full install.

## Reporting issues

Security reports: see [`SECURITY.md`](../SECURITY.md).
