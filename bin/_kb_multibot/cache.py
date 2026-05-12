"""In-memory rolling cache — last N messages per chat_id.

Concept §5/§7.3: supervisor injects recent group context (~15 messages) into
spawn prompt. This module is the cache; listener.py populates it, prompts.py
formats output blocks from it. No persistence — rebuilt on supervisor startup
via `iter_messages` catchup (rare event).

Thread-safety: supervisor is single-process asyncio; cache mutations happen
on the event loop thread. No locks needed.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from .events import TelegramEvent


# Concept §7.4 default — recent group context window for cold-start spawn prompt.
DEFAULT_CACHE_SIZE = 15


class MessageCache:
    """Per-chat ring buffer of TelegramEvent, oldest-first iteration.

    Capacity per chat is a hard cap — older events are evicted as new ones
    arrive (FIFO). Different chats are independent — group `<your_group>` and
    each DM bot↔user channel each get their own deque.
    """

    def __init__(self, capacity: int = DEFAULT_CACHE_SIZE):
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self._capacity = capacity
        self._buffers: dict[int, deque[TelegramEvent]] = {}
        # Track last seen message_id per chat for dedup at the cache layer too —
        # supervisor de-dupes at intake but this is belt-and-suspenders for
        # catchup that might replay slightly past last_seen.
        self._last_seen: dict[int, int] = {}

    @property
    def capacity(self) -> int:
        return self._capacity

    def append(self, event: TelegramEvent) -> bool:
        """Add an event to its chat's cache. Returns True if added, False if dup.

        Dedup is by message_id within chat — replays of already-seen messages
        are dropped silently.
        """
        chat_id = event.chat_id
        buf = self._buffers.get(chat_id)
        if buf is None:
            buf = deque(maxlen=self._capacity)
            self._buffers[chat_id] = buf
        # Dedup by message_id within chat
        if any(existing.message_id == event.message_id for existing in buf):
            return False
        # Update last_seen even if event is older than last (out-of-order arrival
        # is possible during catchup); supervisor's last_seen for catchup-window
        # purposes is tracked separately in state.observer.
        last = self._last_seen.get(chat_id, 0)
        if event.message_id > last:
            self._last_seen[chat_id] = event.message_id
        buf.append(event)
        return True

    def recent(self, chat_id: int, limit: int | None = None) -> list[TelegramEvent]:
        """Return up to `limit` most recent events for chat_id, oldest-first.

        If limit is None, returns full cache content (up to capacity). Oldest-
        first is the natural prompt order — agent reads context chronologically.
        """
        buf = self._buffers.get(chat_id)
        if not buf:
            return []
        if limit is None or limit >= len(buf):
            return list(buf)
        # deque doesn't support negative indexing slicing directly — convert
        return list(buf)[-limit:]

    def last_seen_message_id(self, chat_id: int) -> int | None:
        """Highest message_id observed in this chat — for catchup resume."""
        return self._last_seen.get(chat_id)

    def clear(self, chat_id: int | None = None) -> None:
        """Drop cached events for one chat, or all chats if chat_id is None.

        Used in tests and on explicit supervisor reset. Not part of normal
        operation.
        """
        if chat_id is None:
            self._buffers.clear()
            self._last_seen.clear()
        else:
            self._buffers.pop(chat_id, None)
            self._last_seen.pop(chat_id, None)

    def bulk_load(self, events: Iterable[TelegramEvent]) -> int:
        """Load many events at once (e.g. from startup catchup iter_messages).

        Returns count of events actually added (post-dedup). Order should be
        oldest-first to fill the buffer correctly; capacity eviction will
        keep the newest.
        """
        added = 0
        for e in events:
            if self.append(e):
                added += 1
        return added

    def chat_ids(self) -> list[int]:
        """All chat_ids currently in cache — for diagnostics."""
        return list(self._buffers.keys())


__all__ = ["MessageCache", "DEFAULT_CACHE_SIZE"]
