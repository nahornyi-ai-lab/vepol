# Security and privacy

Vepol runs on your Mac. It has no cloud service of its own and collects no usage data. Your
memory is plain Markdown in `~/knowledge` and in each project's `knowledge/` folder. It
leaves your Mac only when an AI agent or a service you connect needs it, and the table below
shows where it goes.

In short:

- The installer changes only the files listed on this page and asks before each optional part.
- Your existing Claude Code `settings.json` is never changed without your yes.
- Secrets live in private files that only you can read. Vepol reads them as data and sends
  each secret only to the service it unlocks.
- Vepol never saves email bodies. After Codex reads your mail, email text reaches a model only
  as fenced, untrusted data.
- Session capture removes token-shaped secrets before anything is saved.
- Vepol Desktop listens only on your own Mac, behind a fresh key for every launch.
- `./uninstall.sh` removes what Vepol manages and keeps your knowledge.

## What leaves your Mac

| When | What is sent | To whom |
|---|---|---|
| You work with an agent (Claude Code, Codex or any other) | The files it reads, including the project memory loaded at session start | That agent's provider |
| Scheduled routines: nightly `state.md` refresh, morning brief, evening retro | Project state, logs and tasks. The brief also gets today's mail summary, your calendar and your health numbers, and the retro the evening mail summary, when you set them up. | Codex, or Claude when Codex is unavailable. The nightly refresh uses Claude. |
| Mail summaries | Codex reads up to 25 new threads per run through its Gmail plugin. Vepol then passes at most 600 characters of each latest message back to Codex for sorting. | Codex |
| Calendar | Reads the coming days' events. Writes only the plan blocks and follow-up reminders you approve. | Claude Code, through its Google Calendar connector. When Claude cannot answer, Codex stands in with its own Calendar plugin, except for day-plan blocks. |
| arXiv learning digest | The text of up to three selected papers, plus your project names or the focus you set, so it can say why each paper matters | Claude, with Codex as the fallback. If you turn on `social_check: grok`, Grok also gets each paper's title, authors, link and abstract. |
| Audio digests, NotebookLM route | The finished brief (with its body section, if set up), the arXiv report, the Money Radar digest when it is on, and the evening retro | Google NotebookLM, once you sign in with `notebooklm login` |
| Audio digests, local Qwen route | The finished MP3, rendered on your Mac | Your Telegram bot |
| Delivery | The brief, retro, digests and people-review buttons | `api.telegram.org`, to your own bot and chat |
| Money Radar (off until you turn it on) | The location and edge you write in `personal/money-radar.yaml` | Codex, Claude, Grok and Antigravity, which search the web |
| `kb-daily-research` (when you run it) | A research topic and the links it collected | Google NotebookLM, in its NotebookLM mode |
| `kb-contact enrich` (when you run it) | A person's name plus the email domain, company, role, location or Telegram handle on their card | A Codex web search |
| Session capture (if you turn it on) | A redacted excerpt of the session | Claude, which summarizes it |
| The midnight planner (with scheduled tasks) | Your approximate latitude and longitude | `api.sunrise-sunset.org`. When no other location is known, `ip-api.com` over plain HTTP. |
| Multi-bot runtime (experimental, set up by hand) | Messages in the Telegram groups you connect | The agent (Claude or Codex) behind each bot |

The planner takes your location from `CoreLocationCLI` when it is installed, else from
`KB_FALLBACK_LAT` and `KB_FALLBACK_LON` in `.secrets`, else from `ip-api.com`. With none of
them it skips the lookup.

Install and upgrade send none of your data. They only download software: new Vepol releases
(`./upgrade.sh`) and, when you choose them, the session-capture tool with its packages and the
Qwen voice's runtime and model.

## What the installer changes

`./install.sh` never uses `sudo`, never installs a package manager and never edits your shell
profile or `PATH`.

### Your hub, `~/knowledge`

- Creates the hub and its folders if they are missing, and keeps an existing hub.
- `bin/` holds links to the commands and helper modules in the Vepol folder, and
  `orchestrator-seed` links to the Vepol folder itself. A real folder in `bin/` where Vepol
  needs a link, or a real file or folder at `orchestrator-seed`, is moved aside with a
  `.pre-vepol.<timestamp>` suffix, never deleted. A file in `bin/` with the same name as a
  Vepol command is replaced by the link.
- `_template/` (the project template) is refreshed on every run.
- `security/scanner-signatures/` (patterns for spotting instructions hidden in content) is
  copied from the repo.
- `.orchestrator/` holds the agent list `cli-tools.tsv`, `install-manifest.json` and a note of
  the options you declined. A re-run only adds rows for agents the list does not know yet; it
  never edits or re-enables yours. The hub's `.active-roster.md` tells agents which CLIs are
  installed.
- Starter files are written only when they are missing: `AGENTS.md`, `CLAUDE.md`, `index.md`,
  `log.md`, `state.md`, `backlog.md`, `escalations.md`, `incidents.md`, `strategies.md`,
  `registry.md`, `personal/.secrets`, `personal/profile.yaml` and `personal/processes.yaml`.
  On a re-run, install says whether the hub's `AGENTS.md` and `CLAUDE.md` are up to date; when
  one differs from what this version would write, it prints a `diff` command and still leaves
  the file as it is.
- Each run writes a receipt to `~/knowledge/install/receipts/`. Its log, `install.log`, goes in
  the Vepol folder.

### Claude Code, `~/.claude`

**The managed block.** Vepol keeps its global instructions in
`~/.claude/.vepol/CLAUDE.managed.md` and rewrites that file on every install and upgrade. It
imports `~/knowledge/AGENTS.md`, so every Claude Code session on your Mac starts with the hub's
rules. Your `~/.claude/CLAUDE.md` gets this block at the top (the file is created if you have
none):

```text
<!-- BEGIN VEPOL MANAGED — do not edit. Source: ~/.claude/.vepol/CLAUDE.managed.md -->
@~/.claude/.vepol/CLAUDE.managed.md
<!-- END VEPOL MANAGED -->
```

Your own text below it is never touched. A block written by an older installer has the line
`<!-- @include ~/.claude/.vepol/CLAUDE.managed.md -->` instead, which Claude Code does not
load. The installer leaves that line as it is and prints the replacement.

**`settings.json`, only when you have none.** The installer then creates
`~/.claude/settings.json` from a minimal template. It contains:

- `permissions.allow`: `Read(~/knowledge/**)`, and running commands from `~/knowledge/bin/`
  (written once with `~` and once with your full home path);
- `permissions.defaultMode`: `"default"`, Claude Code's standard mode, which asks before edits
  and commands you have not allowed;
- three hooks: `SessionStart` runs `kb-session-start`, `SessionEnd` runs `kb-session-end`,
  `PreCompact` runs `kb-pre-compact`;
- `statusLine`, which runs `~/.claude/statusline-command.sh`.

Nothing else: no broad Bash, Edit or Write grants, no web hosts, no plugins.

**An existing `settings.json`** is never changed without your yes. Without Vepol's hooks,
Claude Code sessions start without the project's memory and are not captured. To add them:

```bash
~/knowledge/bin/kb-claude-hooks --check   # exit 0: all present; 1: some missing; 2: not valid JSON
~/knowledge/bin/kb-claude-hooks --apply   # adds only the missing hooks
```

`--apply` first saves a backup next to the file (`settings.json.bak-YYYY-MM-DD-HHMMSS`), then
adds only the missing hook entries and keeps every other key. A second run changes nothing.
The interactive install asks the same question; the agent install does it with
`VEPOL_MERGE_HOOKS=1 ./install.sh --apply`.

**Also in `~/.claude`:** `statusline-command.sh` (only if missing) and three skills in
`~/.claude/skills/`: `init-kb`, `development-loop` and `orchestrator-setup`. Each carries a
`.vepol-managed` marker. A `SKILL.md` of your own with the same name is first moved aside to
`SKILL.md.pre-vepol.<timestamp>`.

### Bypass-mode check

If your `settings.json` sets `permissions.defaultMode` to `"bypassPermissions"`, Claude Code
runs tools without asking. `skipDangerousModePermissionPrompt: true` turns off its warning
about that mode. Then a prompt hidden in a web page, an email or a file could make it act on
your behalf. The installer checks for both keys:

- The interactive install explains the risk and asks before changing anything.
- `./install.sh --apply` never changes them on its own. It reports
  `needs_security_migration` in `--probe` and in the install receipt. You apply the fix with
  `VEPOL_APPLY_C01=1 ./install.sh --apply`.
- The fix saves `settings.json.bak-<timestamp>` with the same file mode, sets `defaultMode` to
  `"default"`, removes `skipDangerousModePermissionPrompt` and writes the file atomically,
  keeping its original mode.

The check needs strict JSON. A `settings.json` with `//` or `/*` comments stops the install
until you remove them. A file that does not parse is skipped with a warning.
`kb-doctor install-health` repeats the check for your global settings, the hub and every linked
project's `.claude/settings.json`.

### Optional parts

Each one is off until you say yes. The agent install turns them on with
`VEPOL_ENABLE_LAUNCHD=1`, `VEPOL_ENABLE_TELEGRAM=1`, `VEPOL_ENABLE_MEMORY_COMPILER=1` and
`--audio-backend local_qwen`.

- **Scheduled tasks**, four LaunchAgents in `~/Library/LaunchAgents/`, logging to
  `~/knowledge/logs/`:
  - `com.knowledge.tick` every 15 minutes runs the routines that are due in
    `~/knowledge/personal/processes.yaml`;
  - `com.knowledge.planner` at 00:05 writes the day's plan, `logs/today-plan.json`;
  - `com.knowledge.orchestrator-cycle` at 07:30 and 20:45 runs the experimental project cycle.
    It starts no agent until a project sets `cycle_enabled: true`;
  - `com.knowledge.people-review-bot`, always on, handles the Telegram review buttons. It stays
    idle until `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set.

  A LaunchAgent that is already installed is kept as it is.
- **Claude Code Telegram plugin scaffold:** `~/.claude/channels/telegram/.env` (mode 600) for
  the plugin's own bot.
- **Session capture:** clones `claude-memory-compiler` into `~/claude-memory-compiler`, pinned
  to the commit Vepol's patch was tested against, applies the patch and runs `uv sync`.
- **Local Qwen voice:** a Python environment and the model in `~/.local/share/vepol-qwen-tts`.
  It runs only while it renders; no service stays running.

## What stays yours

- Everything you write in the hub and in project `knowledge/` folders.
- Starter files once they exist. Install and upgrade never overwrite `.secrets`,
  `profile.yaml`, `processes.yaml`, `registry.md` or the hub's `AGENTS.md` and `CLAUDE.md`.
  `processes.yaml` changes only when you choose an audio route.
- Your own text in `~/.claude/CLAUDE.md`, your `settings.json`, your own skills.

`./upgrade.sh` moves the Vepol folder to the newest release tag and re-runs
`./install.sh --apply`. Only managed files are refreshed. It passes `VEPOL_ENABLE_*`,
`VEPOL_APPLY_C01` and `VEPOL_MERGE_HOOKS` through to the installer.

## Secrets

- **One private file.** `~/knowledge/personal/.secrets` holds the Telegram bot token and chat
  id, plus optional settings such as your name, your city, a fallback location and the health
  data folder. The installer creates it with mode 600 inside a mode 700 folder. The
  experimental multi-bot runtime keeps its own bot tokens in `~/.claude/channels/bots/`.
- **Modes are re-applied on every install.** `personal/` gets 700; `.secrets`,
  `processes.yaml`, `profile.yaml` and `daily-research.yaml` get 600; `~/.orchestrator` and
  `~/.claude/channels/bots` get 700, with 600 on the env and session files inside. The
  installer refuses to change a symlinked path and warns instead. `kb-doctor install-health`
  re-checks the secret files and folders.
- **Read as data.** Nothing sources `.secrets` as shell code, so no line in it ever runs. Most
  scripts read only the keys they need, and the brief and the retro hand the bot token only to
  the Telegram sender, never to the model run.
- **Kept off command lines.** `kb-channel-send` hands the bot token to `curl` on standard input
  (`curl -K -`), and the Python senders keep it inside the process, so it never shows up in
  `ps`. The one exception is the experimental multi-bot setup: `kb-multibot-add` takes a bot's
  token as its argument.
- **Sent only where it belongs.** The bot token goes only to `api.telegram.org`.
- **Never searched.** `kb-search` skips `.secrets`, `.env` and token files by name.
- **Two bots, two files.** The bot that delivers your brief lives in `.secrets`. Claude Code's
  Telegram plugin uses `~/.claude/channels/telegram/.env` and needs a different bot: two
  listeners on one bot take each other's messages.
- **The agent install.** The setup prompt in [`SETUP.prompt.md`](../SETUP.prompt.md) tells the
  agent never to send secrets, tokens, private paths or knowledge-base contents off your Mac.

## Mail

- **Read-only.** Codex runs in its read-only sandbox (`--sandbox read-only`) and is told to use
  only Gmail's read tools: never draft, send, label, archive or delete. It reads at most 25
  threads per run.
- **Minimized.** The saved summary keeps a few short fields per email: the date and time,
  Gmail's message ids, the sender's display name, the subject, a type (needs reply, receipt,
  newsletter, …), the urgency, a one-line summary and suggested next steps. Vepol never saves
  bodies, attachments or recipient lists. Sender addresses go only to a separate senders file
  for the People module: name, address, domain, count and times, with no subjects or bodies.
- **Private.** Both files live under `~/knowledge/personal/mail/` with mode 600, inside the
  mode 700 `personal/` folder.
- **Fenced.** Codex reads each email with read tools only and is told to treat it as data.
  After that read, email text reaches a model only inside a block marked as untrusted data. The
  block is closed with a random marker that a message cannot fake, and the model is told to
  treat its content as data, never as instructions. The brief and the retro read mail the same
  way.
- **Quiet until set up.** Until a mail read has worked once, the brief and the retro leave mail
  out.

## Session capture

Session capture is off unless you turn it on at install. It runs when a Claude Code session
ends and before Claude Code compacts its context, only in projects that have
`knowledge/log.md` and no `.kb-ignore` file, and never in your home folder itself or under
`/tmp`. Token-shaped secrets are replaced with `[REDACTED-…]` before the excerpt is saved,
summarized by Claude and written to `daily/` and `log.md`: Anthropic and OpenAI keys, Telegram
bot tokens, Google API keys, GitHub tokens, Stripe keys, AWS access keys, Slack tokens, JWTs,
and values named like `api_key`, `secret`, `token` or `password`.

## Scheduled routines

Routines run while you are away, so they cannot stop to ask. The brief, the retro and the
project cycle run through Vepol's agent runner, `kb-orchestrator-run`. Codex always runs with
`--dangerously-bypass-approvals-and-sandbox`, so it can edit files and run commands without
asking, for every routine. Claude's permissions depend on the routine:

- **The brief and the retro** run Claude read-only, with
  `--disallowedTools Bash,Edit,Write,NotebookEdit`. Deny rules win over allow rules, so those
  four tools stay off even if your `~/.claude/settings.json` allows them. Everything else
  comes from your own Claude Code settings: which files it may read, which web hosts it may
  fetch, MCP tools and hooks.
- **The project cycle's report for each project, the task executor (`kb-execute-next`),
  `kb-spawn-project` and chat turns in Vepol Desktop** run Claude with `--permission-mode acceptEdits --allowedTools Bash`:
  they pass `--allow-edits` to `kb-orchestrator-run`, and the executor's own Claude lane sets
  the same flags. File edits in the job's folders are accepted without asking, and the `Bash`
  rule lets it run any shell command, in any folder.
  `kb-spawn-project --json` and `--stream` call Claude directly instead, with your own
  settings.

Other routines use narrower modes: the mail reader runs Codex read-only, the
nightly `state.md` refresh runs Claude with its tools switched off, and Money Radar's Claude
scout runs in plan mode with read and web tools only. These flags apply only to background
runs; your own sessions keep your settings. Every routine logs to `~/knowledge/logs/`. Keep
this in mind when the installer asks "Install scheduled tasks?".

## Vepol Desktop

- **Your Mac only.** The app's backend listens on `127.0.0.1:8781` and refuses to listen on
  any address outside your Mac. If something else already holds the port, the app shows which
  process and does not start.
- **A new key every launch.** The app makes a key from 32 random bytes each time it starts,
  hands it to the backend over a private pipe and keeps it in memory; it is never written to
  disk. Every data request and every terminal connection must carry it. The page itself and
  its bundled scripts load without it and hold no data.
- **Origin check.** Requests from any other web origin are refused.
- **Nothing kept in the web view.** The window stores no cookies or site data between launches
  and loads no code from the internet. Only the app's own address opens inside it. Other links
  open in your browser, and never a link that contains the key. Request bodies are capped at
  64 KB.
- **Agents start on your click.** Each agent terminal starts from a clean environment (your
  user name, home, `PATH`, language and hub location) and then your login shell. Keys in the
  app's own environment do not reach tmux or the agent's command line. Claude Code starts with
  `--permission-mode manual`, and Codex with
  `--sandbox workspace-write --ask-for-approval on-request`.
- **Calendar only on your word.** When you plan your day with Claude Code, that session runs
  without its Google Calendar tool. `kb-dayplan calendar` writes the agreed blocks, and only
  for a plan version you confirmed.
- **App state** (conversations, open tabs) lives in `~/.vepol/face/`.

## Uninstall

```bash
./uninstall.sh --dry-run            # list what would be removed; change nothing
./uninstall.sh                      # asks once, then removes
./uninstall.sh --backup-user-data   # also packs the hub into ~/vepol-knowledge-backup-<timestamp>.tgz first
```

It removes:

- the `bin/` links that point into the Vepol folder (links of your own stay), and the
  `orchestrator-seed` link;
- `~/.claude/.vepol/` and the managed block in `~/.claude/CLAUDE.md`, in either form. If the
  markers surround anything else, it leaves the file alone and tells you;
- the `SKILL.md` of each skill that carries the `.vepol-managed` marker (other files you added
  to those folders stay);
- six LaunchAgents, each unloaded first: `com.knowledge.tick`, `planner`, `orchestrator-cycle`,
  `people-review-bot`, `channel-telegram` and `multibot-supervisor`.

It leaves these in place and lists them at the end, so you can remove them by hand:

- Vepol's hooks and `statusLine` in `~/.claude/settings.json`;
- `~/.claude/statusline-command.sh`;
- `~/claude-memory-compiler`;
- the local Qwen voice in `~/.local/share/vepol-qwen-tts` (or `$KB_TTS_HOME`);
- `~/.claude/channels/telegram/`.

It never deletes your hub, including `_template/`, `security/`, `.orchestrator/` and
`install/receipts/`. It also leaves Vepol Desktop's state in `~/.vepol/face/` and the Vepol
folder itself. Delete those by hand if you want them gone.

## Reporting a vulnerability

Please report it privately, not in a public issue. [`SECURITY.md`](../SECURITY.md) explains
how, what to include and when to expect an answer.
