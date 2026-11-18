"""kb-multibot — multi-bot Telegram agent runtime supervisor.


Package layout:
  config.py     — supervisor config from env / ~/.orchestrator/multibot.env
  events.py     — dataclasses: TelegramEvent, QueueEntry, RunState
  mention.py    — mention parsing (incoming + outbound) and /stop detection
  registry.py   — load per-project .orchestration.yaml into AgentRegistry
  state.py      — file-based service state IO (queues/, runs/, observer/, watchdog/);
                  the per-agent FIFO queue (max 20) lives in queues/<slug>.json
  cache.py      — in-memory rolling cache per chat_id (~15 last messages)
  flock.py      — per-agent global file lock
  loops.py      — loop guards (cooldown, depth, fan-out, hourly quota)
  watchdog.py   — stdout silence detection
  spawner.py    — subprocess wrappers (ClaudeAdapter runs `claude -p`,
                  CodexAdapter runs `codex exec`)
  listener.py   — Telethon group events listener
  sender.py     — Bot API sendMessage with retry/backoff
  prompts.py    — context block formatting for agent prompts
  supervisor.py — main asyncio event loop, wires everything

CLI entrypoints (in bin/):
  kb-multibot-supervisor   — main supervisor binary (LaunchAgent target)
  kb-multibot-setup        — first-time Telethon auth + shared group chat_id
  kb-multibot-add          — register a project's bot: kb-multibot-add <token> [--slug <slug>]
  kb-multibot-list         — show all agents, token present/missing and last runs
  kb-multibot-remove       — disable an agent (--kick, --archive)

Design notes: docs/methodology/multibot-agent-runtime.md
Service state directory: ~/.orchestrator/multibot/
"""

from __future__ import annotations

# Version for debug + LaunchAgent log header.
__version__ = "0.1.0-dev"
