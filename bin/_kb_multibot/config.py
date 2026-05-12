"""Supervisor config — single source of truth for paths + env.

Reads TG_API_ID/TG_API_HASH from environment (LaunchAgent EnvironmentVariables)
or from `~/.orchestrator/multibot.env`. The supervisor refuses to start if
required values are missing — see `kb-multibot-setup` for first-time
interactive authentication that populates this file.

Group chat_id (the shared Telegram supergroup where agents live) is
config-driven so tests and dev can override.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:  # pragma: no cover — fallback parser
    def dotenv_values(path: str | Path) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
        return out


# Supervisor's own dotenv file — preferred location, populated by
# kb-multibot-setup. Holds TG_API_ID, TG_API_HASH, KB_MULTIBOT_GROUP_CHAT_ID
# and other tunables.
MULTIBOT_ENV = Path.home() / ".orchestrator" / "multibot.env"


@dataclasses.dataclass(frozen=True)
class SupervisorConfig:
    """Resolved config — built once at supervisor startup."""

    tg_api_id: int
    tg_api_hash: str
    group_chat_id: int  # Telegram chat_id of the shared group (negative for groups)
    session_file: Path
    projects_dir: Path
    state_root: Path
    bot_tokens_dir: Path
    log_file: Path

    @property
    def is_complete(self) -> bool:
        return bool(self.tg_api_id and self.tg_api_hash and self.group_chat_id)


def _read_env_chain() -> dict[str, str]:
    """Layer env sources: os.environ wins over multibot.env."""
    chain: dict[str, str] = {}
    chain.update(dotenv_values(MULTIBOT_ENV))
    chain.update({k: v for k, v in os.environ.items() if v is not None})
    return chain


def load_config() -> SupervisorConfig:
    """Build SupervisorConfig from layered env sources.

    Raises ValueError if required vars (TG_API_ID, TG_API_HASH,
    KB_MULTIBOT_GROUP_CHAT_ID) are missing — caller (supervisor or
    kb-multibot-setup) is expected to surface an actionable error.
    """
    env = _read_env_chain()

    raw_api_id = env.get("TG_API_ID", "").strip()
    raw_api_hash = env.get("TG_API_HASH", "").strip()
    raw_chat_id = env.get("KB_MULTIBOT_GROUP_CHAT_ID", "").strip()

    if not raw_api_id or not raw_api_hash:
        raise ValueError(
            f"TG_API_ID and TG_API_HASH not set. Looked in env and {MULTIBOT_ENV}. "
            f"Run `kb-multibot-setup` first."
        )

    try:
        api_id = int(raw_api_id)
    except ValueError:
        raise ValueError(f"TG_API_ID must be int, got {raw_api_id!r}")

    if not raw_chat_id:
        raise ValueError(
            f"KB_MULTIBOT_GROUP_CHAT_ID not set. "
            f"Set in {MULTIBOT_ENV} or LaunchAgent plist EnvironmentVariables. "
            f"Find chat_id via Telethon: get_entity('@your_group_username').id"
        )
    try:
        group_chat_id = int(raw_chat_id)
    except ValueError:
        raise ValueError(f"KB_MULTIBOT_GROUP_CHAT_ID must be int, got {raw_chat_id!r}")

    hub = Path(env.get("KB_HUB", str(Path.home() / "knowledge")))
    state_root = Path(env.get("KB_MULTIBOT_STATE_ROOT", str(Path.home() / ".orchestrator" / "multibot")))
    session_file = Path(env.get("KB_MULTIBOT_SESSION_FILE", str(Path.home() / ".orchestrator" / "multibot-supervisor.session")))
    bot_tokens_dir = Path(env.get("KB_MULTIBOT_TOKENS_DIR", str(Path.home() / ".claude" / "channels" / "bots")))
    log_file = Path(env.get("KB_MULTIBOT_LOG_FILE", str(hub / "logs" / "multibot-supervisor.log")))

    return SupervisorConfig(
        tg_api_id=api_id,
        tg_api_hash=raw_api_hash,
        group_chat_id=group_chat_id,
        session_file=session_file,
        projects_dir=hub / "projects",
        state_root=state_root,
        bot_tokens_dir=bot_tokens_dir,
        log_file=log_file,
    )


def read_bot_token(bot_token_ref: str) -> str | None:
    """Read BOT_TOKEN from a bots/<slug>.env file.

    `bot_token_ref` may be `~/.claude/channels/bots/<slug>.env` or an
    absolute path. Returns None if the file is missing or BOT_TOKEN is
    not set.
    """
    path = Path(os.path.expanduser(bot_token_ref))
    if not path.is_file():
        return None
    vals = dotenv_values(path)
    return vals.get("BOT_TOKEN") or vals.get("TOKEN")


__all__ = [
    "SupervisorConfig",
    "load_config",
    "read_bot_token",
    "MULTIBOT_ENV",
]
