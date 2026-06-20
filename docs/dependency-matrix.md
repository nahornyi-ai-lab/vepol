# Dependency matrix

Vepol is **detect-only**: the installer checks for prerequisites and tells you the exact
command to install anything missing, but it never auto-installs a package manager or uses
`sudo`. You install what you want; Vepol uses whatever is present.

`./install.sh --probe --json` reports exactly which of these are missing on your machine.

## Required

| Tool | Minimum | Why | Install |
|---|---|---|---|
| macOS | 13 (Ventura) | launchd, paths | — (Linux on roadmap) |
| git | any recent | clone/upgrade, repo ops | `brew install git` |
| Claude CLI | current | core orchestrator | https://claude.ai/download |
| node | 18+ | skills / MCP runtime | `brew install node` |
| bun | 1+ | fast scripts | `brew install bun` |
| ripgrep (`rg`) | any | search across the field | `brew install ripgrep` |
| python3 | 3.10+ | SessionStart hook, People module | `brew install python@3` |
| bash | 5+ | scripts/hooks (macOS ships 3.2) | `brew install bash` |

One-liner for the Homebrew route:

```bash
brew install bash node bun ripgrep git python@3
# Claude CLI: https://claude.ai/download
```

Python libraries (checked, not auto-installed):

```bash
pip3 install -r requirements.txt
```

## Optional (enable extras)

| Tool | Enables | Install |
|---|---|---|
| Codex CLI | cross-agent review (second opinion) | https://chatgpt.com/codex |
| Antigravity (`agy`) | third-opinion reviews | per vendor |
| Grok CLI | current/social research pass | per vendor |
| `uv` | faster Python deps for memory-compiler | `brew install uv` |
| `jq`, `gh` | JSON/GitHub helpers | `brew install jq gh` |

Missing optional tools never block install — Vepol degrades gracefully and uses whatever you have.
