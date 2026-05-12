"""Tests for cache.py — rolling buffer with dedup."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.cache import DEFAULT_CACHE_SIZE, MessageCache  # noqa: E402
from _kb_multibot.events import EventFrom, TelegramEvent  # noqa: E402


def _event(msg_id: int, chat_id: int = -100, text: str = "x") -> TelegramEvent:
    return TelegramEvent(
        ts=f"2026-05-11T14:23:{msg_id:02d}Z",
        chat_id=chat_id,
        chat_type="group",
        message_id=msg_id,
        from_=EventFrom(user_id=7, username="demo", is_bot=False),
        text=text,
        reply_to_message_id=None,
        message_thread_id=None,
        mentions=(),
    )


class MessageCacheTests(unittest.TestCase):
    def test_default_capacity_matches_concept(self) -> None:
        # Concept §5: ~15 messages per chat.
        self.assertEqual(DEFAULT_CACHE_SIZE, 15)
        c = MessageCache()
        self.assertEqual(c.capacity, 15)

    def test_invalid_capacity_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MessageCache(capacity=0)

    def test_append_and_recent(self) -> None:
        c = MessageCache(capacity=10)
        c.append(_event(1))
        c.append(_event(2))
        c.append(_event(3))
        recent = c.recent(-100)
        self.assertEqual([e.message_id for e in recent], [1, 2, 3])

    def test_recent_with_limit(self) -> None:
        c = MessageCache(capacity=10)
        for i in range(1, 6):
            c.append(_event(i))
        last_two = c.recent(-100, limit=2)
        self.assertEqual([e.message_id for e in last_two], [4, 5])

    def test_capacity_eviction_keeps_newest(self) -> None:
        c = MessageCache(capacity=3)
        for i in range(1, 6):  # 1, 2, 3, 4, 5
            c.append(_event(i))
        # only last 3 should remain
        recent = c.recent(-100)
        self.assertEqual([e.message_id for e in recent], [3, 4, 5])

    def test_chat_isolation(self) -> None:
        c = MessageCache(capacity=5)
        c.append(_event(1, chat_id=-100))
        c.append(_event(2, chat_id=-100))
        c.append(_event(10, chat_id=999))
        self.assertEqual([e.message_id for e in c.recent(-100)], [1, 2])
        self.assertEqual([e.message_id for e in c.recent(999)], [10])

    def test_empty_chat_recent(self) -> None:
        c = MessageCache()
        self.assertEqual(c.recent(99999), [])

    def test_dedup_drops_replay(self) -> None:
        c = MessageCache(capacity=5)
        self.assertTrue(c.append(_event(1)))
        self.assertFalse(c.append(_event(1)))  # same msg_id
        self.assertEqual(len(c.recent(-100)), 1)

    def test_last_seen_tracks_max(self) -> None:
        c = MessageCache(capacity=5)
        c.append(_event(5))
        c.append(_event(3))  # out-of-order, but last_seen stays at 5
        c.append(_event(7))
        self.assertEqual(c.last_seen_message_id(-100), 7)

    def test_last_seen_missing_chat(self) -> None:
        c = MessageCache()
        self.assertIsNone(c.last_seen_message_id(99999))

    def test_clear_one_chat(self) -> None:
        c = MessageCache(capacity=5)
        c.append(_event(1, chat_id=-100))
        c.append(_event(2, chat_id=999))
        c.clear(-100)
        self.assertEqual(c.recent(-100), [])
        self.assertEqual(len(c.recent(999)), 1)

    def test_clear_all(self) -> None:
        c = MessageCache(capacity=5)
        c.append(_event(1, chat_id=-100))
        c.append(_event(2, chat_id=999))
        c.clear()
        self.assertEqual(c.chat_ids(), [])

    def test_bulk_load(self) -> None:
        c = MessageCache(capacity=10)
        events = [_event(i) for i in range(1, 6)]
        added = c.bulk_load(events)
        self.assertEqual(added, 5)
        # bulk_load is idempotent — re-loading same events adds nothing
        again = c.bulk_load(events)
        self.assertEqual(again, 0)

    def test_chat_ids(self) -> None:
        c = MessageCache()
        c.append(_event(1, chat_id=-100))
        c.append(_event(2, chat_id=200))
        self.assertEqual(sorted(c.chat_ids()), [-100, 200])


if __name__ == "__main__":
    unittest.main()
