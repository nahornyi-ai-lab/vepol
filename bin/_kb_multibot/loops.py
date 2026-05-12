"""Loop guards — deterministic spawn-throttling layer.

Active guards:
  - cooldown:         per (chat_id, agent_slug), default 30s
  - mention-graph:    D=4 default (override via KB_MULTIBOT_DEPTH_CAP env)
  - fan-out cap:      F=10 parallel spawns per incoming event
  - hourly quota:     Q=60 spawns/hour per user

All decisions deterministic — same input always produces same allow/deny.
This module is pure logic, no IO. State is in-memory dicts owned by caller
(LoopGuard instance owned by supervisor); supervisor decides whether to
persist these dicts (currently not, since they're advisory and rebuilt
naturally from runs/ on restart).
"""

from __future__ import annotations

import datetime as dt
import os
from collections import deque
from typing import Dict, Tuple


DEFAULT_COOLDOWN_SEC = 30
DEFAULT_DEPTH_CAP = 4  # override via env KB_MULTIBOT_DEPTH_CAP
MAX_DEPTH_CAP = 8  # absolute ceiling regardless of env (paranoia)
DEFAULT_FAN_OUT_CAP = 10
DEFAULT_HOURLY_QUOTA_PER_USER = 60


def get_depth_cap() -> int:
    """Read depth cap from env, clamp to [1, MAX_DEPTH_CAP], default D=4."""
    raw = os.environ.get("KB_MULTIBOT_DEPTH_CAP")
    if raw is None:
        return DEFAULT_DEPTH_CAP
    try:
        v = int(raw)
    except ValueError:
        return DEFAULT_DEPTH_CAP
    return max(1, min(v, MAX_DEPTH_CAP))


class LoopGuard:
    """In-memory loop-prevention state.

    One instance per supervisor process. All state is volatile — rebuilt on
    restart from `runs/` directory if needed (most guards are short-window
    so cold start is fine).
    """

    def __init__(
        self,
        cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
        depth_cap: int | None = None,
        fan_out_cap: int = DEFAULT_FAN_OUT_CAP,
        hourly_quota: int = DEFAULT_HOURLY_QUOTA_PER_USER,
    ):
        self.cooldown_sec = cooldown_sec
        self.depth_cap = depth_cap if depth_cap is not None else get_depth_cap()
        self.fan_out_cap = fan_out_cap
        self.hourly_quota = hourly_quota

        # cooldown: (chat_id, agent_slug) → last_outbound_ts (epoch seconds)
        self._last_outbound: Dict[Tuple[int, str], float] = {}

        # hourly quota: user_id → deque of spawn timestamps (epoch seconds)
        # within the last 3600s window; older entries pruned on each check
        self._user_spawn_log: Dict[int, deque[float]] = {}

    # ----- Cooldown -----

    def in_cooldown(self, chat_id: int, agent_slug: str, now: float | None = None) -> bool:
        """True if agent recently posted to chat — block further spawn for now."""
        key = (chat_id, agent_slug)
        last = self._last_outbound.get(key)
        if last is None:
            return False
        n = now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        return (n - last) < self.cooldown_sec

    def mark_outbound(
        self, chat_id: int, agent_slug: str, now: float | None = None
    ) -> None:
        """Record bot's outbound message for cooldown tracking."""
        key = (chat_id, agent_slug)
        n = now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        self._last_outbound[key] = n

    # ----- Mention-graph depth -----

    def depth_exceeded(self, depth: int) -> bool:
        """True if delegation chain has reached cap and must terminate."""
        return depth >= self.depth_cap

    # ----- Fan-out cap -----

    def truncate_fan_out(self, mentions: list[str]) -> Tuple[list[str], list[str]]:
        """Split mentions into (spawn_now, queue_later) based on fan_out_cap.

        Concept §7.4: F=10 parallel spawns per event, остальные в очередь.
        Returns (parallel_targets, queued_targets).
        """
        if len(mentions) <= self.fan_out_cap:
            return list(mentions), []
        return list(mentions[: self.fan_out_cap]), list(mentions[self.fan_out_cap :])

    # ----- Hourly quota -----

    def _prune_user_log(self, user_id: int, now: float) -> deque[float]:
        log = self._user_spawn_log.get(user_id)
        if log is None:
            log = deque()
            self._user_spawn_log[user_id] = log
        cutoff = now - 3600.0
        while log and log[0] < cutoff:
            log.popleft()
        return log

    def quota_exceeded(self, user_id: int, now: float | None = None) -> bool:
        """True if user has already triggered Q spawns in the past hour."""
        n = now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        log = self._prune_user_log(user_id, n)
        return len(log) >= self.hourly_quota

    def record_spawn(self, user_id: int, now: float | None = None) -> None:
        """Mark one spawn against user's hourly quota."""
        n = now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        log = self._prune_user_log(user_id, n)
        log.append(n)

    def current_quota_usage(self, user_id: int, now: float | None = None) -> int:
        """Return user's spawn count in past hour — for diagnostics/reply text."""
        n = now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        log = self._prune_user_log(user_id, n)
        return len(log)


__all__ = [
    "LoopGuard",
    "DEFAULT_COOLDOWN_SEC",
    "DEFAULT_DEPTH_CAP",
    "MAX_DEPTH_CAP",
    "DEFAULT_FAN_OUT_CAP",
    "DEFAULT_HOURLY_QUOTA_PER_USER",
    "get_depth_cap",
]
