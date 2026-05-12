"""kb-multibot — multi-bot Telegram agent runtime supervisor.


Package layout:
  events.py     — dataclasses: TelegramEvent, QueueEntry, RunState
  mention.py    — mention parsing (incoming + outbound)
  registry.py   — load per-project .orchestration.yaml into AgentRegistry
  state.py      — file-based service state IO (queues/, runs/, observer/, watchdog/)
  cache.py      — in-memory rolling cache per chat_id (~15 last messages)
  queue.py      — per-agent FIFO queue (max 20)
  flock.py      — per-agent global file lock
  loops.py      — loop guards (cooldown, depth, fan-out, hourly quota)
  watchdog.py   — stdout silence detection
  spawner.py    — subprocess wrappers (ClaudeAdapter via kb-spawn-project, CodexAdapter)
  listener.py   — Telethon group events listener
  sender.py     — Bot API sendMessage with retry/backoff
  delegation.py — parent → children tracking via parent_run_id + reply correlation
  prompts.py    — context block formatting for agent prompts
  supervisor.py — main asyncio event loop, wires everything

CLI entrypoints (in bin/):
  kb-multibot-supervisor   — main supervisor binary (LaunchAgent target)
  kb-multibot-setup        — first-time Telethon auth + token validation
  kb-init-agent            — interactive new agent onboarding
  kb-deactivate-agent      — agent disable + token revoke

Service state directory: ~/.orchestrator/multibot/
"""

from __future__ import annotations

# Version for debug + LaunchAgent log header.
__version__ = "0.1.0-dev"
