"""Event schema dataclasses — concept §7.11.

All Telegram-side data flowing through supervisor is normalized into these structs
before reaching mention parser, queue, spawner, or loop guards. Implementation
detail of how Telethon Message objects map to TelegramEvent is in listener.py.

JSON serialization here is for persistent run/queue state files.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Any


def _now_utc() -> str:
    """ISO-8601 with Z suffix, second precision — matches concept §7.11 examples."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass(frozen=True)
class EventFrom:
    """Origin of an incoming or outbound Telegram message.

    For human messages: user_id + username + is_bot=False.
    For bot-originated messages (outbound from our supervisor): is_bot=True + bot_slug.
    """

    user_id: int
    username: str | None
    is_bot: bool
    bot_slug: str | None = None  # set when is_bot=True and bot is one of ours

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class TelegramEvent:
    """Normalized incoming or outbound Telegram message — single shape for both.

    Listener fills this from Telethon Message objects; mention parser consumes it
    without needing to know about Telethon internals. Frozen so events can be
    dedup-keyed by (chat_id, message_id) without worrying about mutation.

    Fields mirror concept §7.11 schema. ts is wall-clock UTC ISO-8601.
    """

    ts: str
    chat_id: int
    chat_type: str  # "group" or "private"
    message_id: int
    from_: EventFrom
    text: str
    reply_to_message_id: int | None
    message_thread_id: int | None  # for forum topics
    mentions: tuple[str, ...]  # bot usernames extracted (no @ prefix)
    raw_event_offset_id: int | None = None  # Telethon offset for catchup

    @property
    def dedup_key(self) -> tuple[int, int]:
        """Concept §7.11: dedup by (chat_id, message_id)."""
        return (self.chat_id, self.message_id)

    @property
    def is_private(self) -> bool:
        return self.chat_type == "private"

    @property
    def is_group(self) -> bool:
        return self.chat_type == "group"

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["from"] = d.pop("from_")
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TelegramEvent:
        from_ = EventFrom(**d["from"])
        return cls(
            ts=d["ts"],
            chat_id=d["chat_id"],
            chat_type=d["chat_type"],
            message_id=d["message_id"],
            from_=from_,
            text=d["text"],
            reply_to_message_id=d.get("reply_to_message_id"),
            message_thread_id=d.get("message_thread_id"),
            mentions=tuple(d.get("mentions", [])),
            raw_event_offset_id=d.get("raw_event_offset_id"),
        )


@dataclasses.dataclass
class QueueEntry:
    """One pending task in an agent's FIFO queue. Concept §7.11 + §7.4.

    Persisted as JSON line in ~/.orchestrator/multibot/queues/<agent_slug>.json
    (single file holding a list — supervisor rewrites atomically on each enqueue/
    dequeue). Mutable so supervisor can mark `picked_at` and rewrite.
    """

    queued_at: str
    trigger_msg_id: int
    trigger_chat_id: int
    trigger_user_id: int
    trigger_text: str  # original message text for prompt reconstruction
    parent_run_id: str | None = None
    delegation_trigger_msg_id: int | None = None
    picked_at: str | None = None  # set when dequeued for spawn

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QueueEntry:
        return cls(**d)

    @classmethod
    def from_event(
        cls,
        event: TelegramEvent,
        parent_run_id: str | None = None,
        delegation_trigger_msg_id: int | None = None,
    ) -> QueueEntry:
        return cls(
            queued_at=_now_utc(),
            trigger_msg_id=event.message_id,
            trigger_chat_id=event.chat_id,
            trigger_user_id=event.from_.user_id,
            trigger_text=event.text,
            parent_run_id=parent_run_id,
            delegation_trigger_msg_id=delegation_trigger_msg_id,
        )


# Run status state machine — strict enum-like set of strings.
# Concept §7.11 lists these values; spawner.py + watchdog.py transition between them.
RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_KILLED = "killed"
RUN_STATUS_TIMEOUT = "timeout"
RUN_STATUS_STALE = "failed_stale"  # >24h pending child, 
RUN_STATUSES = frozenset(
    {
        RUN_STATUS_QUEUED,
        RUN_STATUS_RUNNING,
        RUN_STATUS_SUCCESS,
        RUN_STATUS_FAILED,
        RUN_STATUS_KILLED,
        RUN_STATUS_TIMEOUT,
        RUN_STATUS_STALE,
    }
)


@dataclasses.dataclass
class RunState:
    """One agent run lifecycle, persisted in ~/.orchestrator/multibot/runs/<run_id>.json.

    Schema mirrors concept §7.11. Mutable so supervisor can update last_stdout_ts,
    status, ended_at, reply_msg_id as the run progresses. Atomic file replacement
    on each update (tmp+rename) to avoid torn writes.
    """

    run_id: str
    agent_slug: str
    status: str
    source_chat_id: int
    trigger_msg_id: int
    trigger_user_id: int
    started_at: str
    parent_run_id: str | None = None
    delegation_trigger_msg_id: int | None = None
    ended_at: str | None = None
    last_stdout_ts: str | None = None
    pid: int | None = None
    depth: int = 0  # mention-graph depth, see loops.py
    claude_session_id: str | None = None  # for warm-resume
    reply_msg_id: int | None = None  # the sendMessage that supervisor posted
    kill_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in RUN_STATUSES:
            raise ValueError(
                f"invalid run status {self.status!r}; expected one of {sorted(RUN_STATUSES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunState:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> RunState:
        return cls.from_dict(json.loads(s))


__all__ = [
    "EventFrom",
    "TelegramEvent",
    "QueueEntry",
    "RunState",
    "RUN_STATUS_QUEUED",
    "RUN_STATUS_RUNNING",
    "RUN_STATUS_SUCCESS",
    "RUN_STATUS_FAILED",
    "RUN_STATUS_KILLED",
    "RUN_STATUS_TIMEOUT",
    "RUN_STATUS_STALE",
    "RUN_STATUSES",
]
