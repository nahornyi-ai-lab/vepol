# Dependency matrix

Vepol checks what you have and tells you what is missing. It never installs the tools on this
page for you, never installs a package manager and never uses `sudo`. You decide what goes on
your Mac; Vepol uses whatever is there.

To see where your Mac stands, run this from the Vepol folder. It changes nothing:

```bash
./install.sh --probe --json
```

It lists missing required tools (`prereqs_missing_required`), missing optional tools
(`prereqs_missing_optional`), version problems (`prereqs_version_problems`) and what each
optional tool enables (`optional_tools`). It exits 10 when a required tool is missing or too
old. `./install.sh --help` prints the required and optional tools as plain text.

## Required

The install stops until all of these are present.

| Tool | Minimum | What Vepol uses it for | Install |
|---|---|---|---|
| macOS | 13 (Ventura) | LaunchAgents, file layout. Vepol runs on macOS only. | — |
| git | any | Getting and upgrading Vepol | `brew install git` |
| Claude Code (`claude`) | current | Start-of-session hooks, the `/init-kb` skill, the calendar, and scheduled routines (on its own or when Codex is unavailable) | see below |
| ripgrep (`rg`) | any | `kb-search` | `brew install ripgrep` |
| python3 | 3.10 | The start-of-session hook and most `kb-*` commands | `brew install python@3` |
| bash | 5 | Hooks and scripts (macOS ships bash 3.2) | `brew install bash` |

Claude Code here means the command-line tool. The Claude desktop app does not provide the
`claude` command.

All of it with Homebrew ([brew.sh](https://brew.sh)):

```bash
brew install bash ripgrep git python@3
curl -fsSL https://claude.ai/install.sh | bash   # Claude Code; or: brew install --cask claude-code
```

Then open a new terminal and run `claude` once to sign in.

### Python packages

`requirements.txt` holds `python-frontmatter`, `click`, `PyYAML` and `jellyfish` (people
cards, ideas, `kb-contact`), plus `notebooklm-py`, the NotebookLM package. For the scheduled
audio digests, install its `notebooklm` command with pipx (see [Optional tools](#optional-tools)).
The installer checks for the first four and warns when one is missing, and
`kb-doctor install-health` reports a missing one as a P1 with the command that installs it.
Neither installs them. Run this from the Vepol folder:

```bash
python3 -m pip install --user -r requirements.txt
```

If pip answers `externally-managed-environment` (Homebrew's Python does), use:

```bash
python3 -m pip install --break-system-packages -r requirements.txt
```

Install them into the `python3` on your `PATH`: the `kb-*` commands run that Python, so a
separate virtual environment is not picked up.

Two extra packages serve only the Telegram people collector (`kb-telegram-people`) and the
experimental multi-bot runtime (`kb-multibot-*`). With Homebrew's Python, use
`--break-system-packages` in place of `--user`:

```bash
python3 -m pip install --user 'telethon>=1.36,<2.0' 'python-dotenv>=1.0,<2.0'
```

## Where Vepol finds Claude Code and Codex

Any standard install works: the official installers, Homebrew or npm. Vepol takes the first
match in this order.

| Agent | Lookup order |
|---|---|
| `claude` | `$KB_CLAUDE_BIN` (when it points at a program), `claude` on your `PATH`, `~/.local/bin/claude`, `/opt/homebrew/bin/claude`, `/usr/local/bin/claude` |
| `codex` | `$KB_CODEX_BIN`, `~/.local/bin/codex`, `codex` on your `PATH`, `/opt/homebrew/bin/codex`, `/usr/local/bin/codex` |

- Vepol skips a Codex copy it finds inside a macOS app bundle (`/Applications/Codex.app/…`),
  because the app replaces it when it updates.
- `KB_CODEX_BIN` is final: when it is set, Vepol tries no other path. Point it at a path that
  does not exist to switch Codex off. The brief and the retro then run on Claude, and the mail
  summaries stop, because only Codex reads Gmail.
- The brief, the retro and the project cycle pass no model flag, so each agent uses your
  account's default model. Set `CLAUDE_MODEL` or `CODEX_MODEL` to choose one. For scheduled
  routines, add them to the `EnvironmentVariables` of the LaunchAgent in
  `~/Library/LaunchAgents/`. The nightly `state.md` refresh and calendar reads ask Claude for
  `sonnet`; `KB_CONSOLIDATE_MODEL` and `KB_MCP_MODEL` change that.
- Scheduled routines run with a short `PATH`: `/opt/homebrew/bin`, `/usr/local/bin`, the
  system folders and `~/.local/bin`. The installer keeps a LaunchAgent that is already
  installed, so one written by an older version has no `~/.local/bin`. Most routines also try
  the fixed locations above, so they find `claude` and `codex` either way. Calendar reads and
  `kb-doctor mcp-check` use the `claude` lookup order above too.

## Optional tools

Each one switches on an extra. A missing optional tool never stops the install.

| Tool | What it gives you | Install |
|---|---|---|
| Codex CLI (`codex`) | The first choice for the scheduled brief and retro; Claude takes over when Codex is unavailable. Reads Gmail for the mail summaries through its Gmail plugin. Second opinions, and the web lookup in `kb-contact enrich`. | `npm i -g @openai/codex`, `brew install --cask codex`, or the standalone installer at https://chatgpt.com/codex/install.sh. Then `codex login`. |
| `uv` | Automatic session capture (it does not run without `uv`) and the local Qwen voice install | `brew install uv` |
| `jq` | The Claude Code status line | `brew install jq` |
| `gh` | GitHub work from agent sessions: pull requests, issues, releases | `brew install gh` |
| `node` | Installing agent CLIs with npm, for example Codex. No `kb-*` command runs it. | `brew install node` |
| `bun` | Claude Code's Telegram plugin, for chatting with Claude in Telegram | `brew install bun` |
| NotebookLM CLI (`notebooklm`) | The default audio route for the morning and evening digests, and the NotebookLM mode of `kb-daily-research` | `pipx install notebooklm-py`, then `notebooklm login` |
| `pdftotext` | Lets the arXiv digest read the full paper. Without it the digest works from the abstract. | `brew install poppler` |
| Antigravity (`agy`) | An independent third opinion; one of the Money Radar scouts; an agent in Vepol Desktop | the vendor's installer, see https://antigravity.google |
| Grok CLI (`grok`) | Current social and news research; the optional social check in the arXiv digest; a Money Radar scout | the vendor's installer, see https://x.ai |
| OpenCode (`opencode`) | A backup for Grok, with any model; an agent in Vepol Desktop | the vendor's installer, see https://opencode.ai |
| Hermes (`hermes`) | A general-purpose agent you can start in Vepol Desktop | the vendor's installer |
| CoreLocationCLI | Your location for the planner's sunrise and sunset times, which are informational only. Without it, the planner uses `KB_FALLBACK_LAT` and `KB_FALLBACK_LON` from `~/knowledge/personal/.secrets`, or else a guess from your IP address (ip-api.com). | `brew install --cask corelocationcli` |

`pipx` itself comes from `brew install pipx`. It puts `notebooklm` in `~/.local/bin`, where
scheduled routines look for it. They also check your `PATH` and `$KB_NOTEBOOKLM_BIN`. The
`notebooklm-py` line in `requirements.txt` installs the same package, but a `--user` install
can put the command in a folder such as `~/Library/Python/3.X/bin`, which scheduled routines
never search.

## Audio digests

The morning and evening audio digests take one of two routes. A new interactive install asks
which one you want; `./install.sh --apply` takes `--audio-backend notebooklm` or
`--audio-backend local_qwen`.

**NotebookLM** (the default). Needs the `notebooklm` command, signed in with
`notebooklm login`. The digest goes to NotebookLM as a source and NotebookLM makes the Audio
Overview there. No audio is sent to Telegram.

**Local Qwen voice.** Narrates on your Mac and sends an MP3 to your Telegram bot. It needs:

- an Apple Silicon Mac;
- `uv`, `ffmpeg` (which includes `ffprobe`) and `lsof` (part of macOS);
- at least 10 GiB of free disk. The install sets up a pinned Python runtime with `uv`,
  downloads the pinned Qwen3-TTS model into `~/.local/share/vepol-qwen-tts` (or
  `$KB_TTS_HOME`) and checks the packages and the model files against pinned SHA-256 hashes;
- a Telegram bot for delivery (see
  [Turn on your daily routine](getting-started.md#turn-on-your-daily-routine)).

To switch to it after install:

```bash
brew install uv ffmpeg
~/knowledge/bin/kb-tts-install
~/knowledge/bin/kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend local_qwen
~/knowledge/bin/kb-tts-render --check
```

The last command prints `{"ready": true, …}` and exits 0 when the voice can render. If the
local Qwen install fails during `./install.sh`, everything else still installs and the audio
route stays as it was. With `--apply`, the installer then exits 11 (partial install).

## Vepol Desktop

The native app is built from source on your Mac. It needs:

| Requirement | Why | Install |
|---|---|---|
| Apple Silicon Mac, macOS 13 or later | The app is built for arm64 | — |
| Command Line Tools | The build uses their Swift compiler and macOS SDK | `xcode-select --install` |
| Python 3.11 or later | The app's own Python environment (FastAPI, Uvicorn and websockets, from `face/requirements.txt`) | `brew install python@3` |
| `tmux` | Every agent terminal in the app runs in a tmux session | `brew install tmux` |

It starts whichever agents you have installed: Claude Code, Codex, Antigravity, Hermes,
OpenCode or Grok. Build steps are in [`face/README.md`](../face/README.md#build-and-open).

## Accounts and sources

These are not programs to install, but some routines need them.

| What | Used for | How to connect it |
|---|---|---|
| A Telegram bot and your chat id | Delivering the brief, retro, digests and people-review buttons | Put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `~/knowledge/personal/.secrets` |
| Gmail | Mail summaries in the brief and retro | Connect Gmail in Codex (its Gmail plugin) |
| Google Calendar | Today's meetings in the brief; calendar blocks from **Plan my day** in Vepol Desktop | Connect Google Calendar in Claude Code. Codex's Google Calendar plugin can stand in for reads. |
| NotebookLM | The default audio route | `notebooklm login` |
| A daily health JSON from your own sync | The body section of the morning brief | See [Health in the brief](health-in-the-brief.md) |

Without any of them the brief and retro still run and are saved under `~/knowledge`. They
just cover less.
