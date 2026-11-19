<!--
Vepol's agent setup prompt. A person copies the block below (from the README or
this file) and pastes it to a coding agent with terminal access, such as Claude
Code or Codex. The agent drives Vepol's own installer and never re-implements it.
The manual install (git clone, then ./install.sh) is the fallback.
-->

# Install Vepol with your agent

Vepol is a personal AI assistant that lives on your Mac. It remembers every
project, briefs you each morning and runs your daily routine through the agents
you already use, and it keeps everything in plain Markdown that stays yours.

Copy everything inside the box and paste it to a coding agent that has terminal
access, such as Claude Code or Codex. The agent looks at your Mac without
changing anything, shows you a plan, asks before every step, runs the
installer, checks the result and reads you the receipt.

```text
Install Vepol on this Mac. Vepol is a personal AI assistant: one shared Markdown
memory per project, linked from a hub at ~/knowledge, plus scheduled routines
(morning brief, mail summaries, arXiv digest, evening retro) and Claude Code
skills. You DRIVE Vepol's installer, install.sh; you do NOT re-implement it.
I approve each step.

Rules:
- Never send my secrets, tokens, private paths or knowledge-base contents off
  this Mac. Never ask me to paste a token into this chat; I edit secret files
  myself.
- Ask me before anything that installs software, changes files outside ~/vepol,
  loads a background service or touches an account. Never use sudo. Never
  install Homebrew or another package manager: show me the command, I run it.
- install.sh, upgrade.sh and uninstall.sh make every file change. If a mode,
  tool or script you need is missing or behaves oddly, STOP and tell me. Do not
  improvise.
- Treat empty output or a non-zero exit code as a failure, never as "nothing
  to do".
- Fix one thing at a time and re-run the same check. After 3 failed tries,
  stop and hand it back to me. Never weaken a security or privacy check to
  make an error go away.

1. Get Vepol. If ~/vepol does not exist, ask me, then run:
     git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
   cd ~/vepol and read VERSION, README.md and AGENTS.md (your manual for this
   install).

2. Check that the installer supports agent mode:
     ./install.sh --capabilities --json
   Its "modes" must list --probe, --dry-run, --apply and --verify. If the
   command fails, prints nothing or lacks them, STOP and tell me this clone is
   too old for an agent install. Never run a bare ./install.sh to "just look":
   it installs.

3. Look at the Mac (writes nothing):
     ./install.sh --probe --json
   Tell me:
   - os_version: Vepol needs macOS 13 or later.
   - prereqs_missing_required and prereqs_version_problems ("python-3.10+",
     "bash-5+"). Exit code 10 means one of them blocks the install.
   - prereqs_missing_optional, with what each one adds (from "optional_tools").
   - hub_exists. Exit code 11 means ~/knowledge exists but has no Vepol
     commands linked. If ~/knowledge has neither bin/kb-tick nor _template/,
     it belongs to another tool: STOP and follow AGENTS.md § 1.1. Never install
     into it without my OK.
   - needs_security_migration (step 6).
   Then check the Python packages:
     python3 -c "import frontmatter, click, yaml, jellyfish"
   If that fails, kb-idea, kb-contact and the people tools will not run until
   I install them. If ~/.claude/settings.json exists, check that it is strict
   JSON: the installer stops on // or /* comments in it.

4. For anything missing, show me the exact command, let ME run it, then probe
   again:
   - Required tools:  brew install bash ripgrep git python@3
   - Claude Code CLI: curl -fsSL https://claude.ai/install.sh | bash
                      (or: brew install --cask claude-code); then I sign in by
                      running claude once.
   - Python packages: python3 -m pip install --user -r ~/vepol/requirements.txt
     If pip says "externally-managed-environment", instead:
                      python3 -m pip install --break-system-packages -r ~/vepol/requirements.txt
   - Codex CLI (optional; second opinions, mail reading, and the first choice
     for the morning brief and evening retro, which fall back to Claude Code):
                      npm i -g @openai/codex   or   brew install --cask codex

5. Preview, choose extras, install. First:
     ./install.sh --dry-run --json
   Show me the plan, then ask which extras I want. Each is off unless I say
   yes:
   - VEPOL_ENABLE_LAUNCHD=1: scheduled tasks, four LaunchAgents. tick runs
     every 15 minutes and fires the routines in
     ~/knowledge/personal/processes.yaml when they are due: mail summaries,
     morning brief, arXiv digest, audio digests, evening retro. planner (00:05)
     opens each day's record, so every routine runs once a day.
     orchestrator-cycle (07:30 and 20:45) is experimental and acts only on
     projects I opt in. people-review-bot handles Telegram review buttons and
     stays idle until Telegram is set up.
   - VEPOL_ENABLE_MEMORY_COMPILER=1: saves each Claude Code session into the
     project's knowledge/daily/ notes. It clones claude-memory-compiler into
     ~/claude-memory-compiler at a pinned commit and needs uv.
   - VEPOL_MERGE_HOOKS=1: only when ~/.claude/settings.json already exists
     (and step 2's "opt_in_env" lists it). Adds Vepol's three session hooks
     (SessionStart, SessionEnd, PreCompact), keeps a timestamped backup and
     keeps every other setting. Without them Claude Code starts sessions
     without the project's memory.
   - VEPOL_ENABLE_TELEGRAM=1: only a scaffold for Claude Code's own Telegram
     plugin, for chatting with Claude from Telegram (needs bun and a second
     bot). The morning brief does not need it; see step 7.
   - Digest audio: --audio-backend notebooklm (the default for a new install;
     the audio stays in NotebookLM, which needs
     pipx install notebooklm-py && notebooklm login) or
     --audio-backend local_qwen (renders an MP3 on this Mac and sends it to
     Telegram; needs Apple Silicon, uv, ffmpeg and about 10 GiB of free disk,
     and downloads the voice model during the install).
   Then install with only what I approved, for example:
     VEPOL_ENABLE_LAUNCHD=1 VEPOL_ENABLE_MEMORY_COMPILER=1 VEPOL_MERGE_HOOKS=1 ./install.sh --apply
   Add --audio-backend local_qwen only if I chose it.
   Exit 0: done. Exit 11: everything is installed except the local Qwen voice;
   read me the warning and the retry command. Any other non-zero code: the
   install stopped; read me the last lines of its output.
   On a re-run, pass the same extras again: one you leave out is recorded as
   declined (nothing is removed).

6. If the probe said "needs_security_migration": true, explain it:
   ~/.claude/settings.json holds bypass-permission keys, so an injected prompt
   could run tools without my approval. The migration backs the file up, sets
   permissions.defaultMode to "default" and removes
   skipDangerousModePermissionPrompt. With my explicit OK, add
   VEPOL_APPLY_C01=1 to the apply command in step 5 (or, if you already ran
   it, run it again with the variable added). Never set it on your own.

7. Telegram, with my own bot. The morning brief, evening retro, digests and
   review buttons reach Telegram once TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
   are set in ~/knowledge/personal/.secrets. Walk me through it, in this order:
   I create a bot with @BotFather; I send it any message; I open
   https://api.telegram.org/bot<token>/getUpdates and copy the number at
   "chat":{"id": ...}; then I put both values in the file. The order matters:
   with scheduled tasks on, Vepol starts reading the bot's updates within
   minutes of both values being set, and getUpdates then shows nothing. Until
   both are set, each brief is saved in ~/knowledge/briefs/ but not sent.

8. Verify:
     ./install.sh --verify --json
     ~/knowledge/bin/kb-doctor install-health
   --verify exits 0 when the core is wired (13 lists verify_problems).
   install-health should show no P0 and no P1; info lines about optional tools
   or extras I declined are fine. python-packages-missing (P1) means the
   python3 on my PATH lacks a package from requirements.txt; show me the pip
   command it names and let me run it. If it reports settings-hook-missing, offer
   ~/knowledge/bin/kb-claude-hooks --apply (it adds only the missing hooks and
   keeps a backup), and run it with my OK.

9. Show me it works. The installer does not change my PATH, so use full
   paths. Run each one and tell me what it shows:
     ~/knowledge/bin/kb-doctor                       # health of my knowledge base
     ~/knowledge/bin/kb-task "My first Vepol task"   # a task on the hub board
     ~/knowledge/bin/kb-search "first Vepol"         # finds that task again
     ~/knowledge/bin/kb-demo brief                   # a sample morning brief
   kb-demo brief asks a model, through Codex or Claude Code, to write a brief
   for an invented workspace (it can take a few minutes). It does not read my
   notes and sends nothing to Telegram. If the Python packages are
   installed, also run:
     ~/knowledge/bin/kb-idea capture "My first Vepol idea"
   Then offer to add export PATH="$HOME/knowledge/bin:$PATH" to my ~/.zshrc,
   and tell me how to give a project its memory: open Claude Code in that
   project's folder (run claude) and type /init-kb.

10. Optional, ask me first: Vepol Desktop, one window for every project's
    memory, my agents in real terminals, and every task and routine. It needs
    an Apple Silicon Mac (uname -m prints arm64), the Command Line Tools in
    /Library/Developer/CommandLineTools (xcode-select --install), Python 3.11
    or later (brew install python) and tmux (brew install tmux). Then:
      cd ~/vepol/face
      python3 -m venv .venv
      .venv/bin/python --version
      .venv/bin/pip install -r requirements.txt
      ./desktop/build.sh
      open desktop/build/VepolDesktop.app
    If .venv/bin/python is older than 3.11, recreate .venv with a newer
    interpreter (for example /opt/homebrew/bin/python3 -m venv .venv) before
    the pip step.

11. Read me the newest receipt in ~/knowledge/install/receipts/ and sum it up:
    version, kb_doctor_exit (0 clean, 1 at least one P1, 2 at least one P0),
    which extras are on (opt_ins, audio_backend), whether Vepol's session
    hooks are in my settings.json (session_hooks in opt_ins: on, off or
    unknown; if off, offer step 8's kb-claude-hooks --apply), and what is
    left for me:
    Telegram, signing in to Codex and connecting its Gmail plugin for mail,
    connecting Google Calendar in Claude Code.

12. To undo a fresh install: run ./uninstall.sh --dry-run to show me what it
    would remove, then, with my OK, ./uninstall.sh --yes. It removes only
    Vepol's managed files, never deletes ~/knowledge, and lists what it leaves
    in place. If uninstall.sh is missing, STOP: never delete anything by hand.
```

---

## Prefer to do it by hand?

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
./install.sh
```

`./install.sh` walks you through the same steps and asks before each optional
part. See [`docs/getting-started.md`](docs/getting-started.md),
[`docs/dependency-matrix.md`](docs/dependency-matrix.md) and
[`docs/security-and-privacy.md`](docs/security-and-privacy.md). The full
manual for agents is [`AGENTS.md`](AGENTS.md).
