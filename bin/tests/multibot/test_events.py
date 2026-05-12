"""Tests for events.py — dataclass round-trip + invariants.

Run: python3 -m unittest bin.tests.multibot.test_events
  or via tests/test-multibot.sh
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Add bin/ to sys.path for direct test execution.
BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.events import (  # noqa: E402
    EventFrom,
    QueueEntry,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCESS,
    RunState,
    TelegramEvent,
)


class TelegramEventTests(unittest.TestCase):
    def _sample(self) -> TelegramEvent:
        return TelegramEvent(
            ts="2026-05-11T14:23:01Z",
            chat_id=-1001234567,
            chat_type="group",
            message_id=12891,
            from_=EventFrom(
                user_id=1234567890, username="demo", is_bot=False, bot_slug=None
            ),
            text="@vepol_bot статус релиза?",
            reply_to_message_id=None,
            message_thread_id=None,
            mentions=("vepol_bot",),
            raw_event_offset_id=42,
        )

    def test_dedup_key_is_chat_and_message_id(self) -> None:
        e = self._sample()
        self.assertEqual(e.dedup_key, (-1001234567, 12891))

    def test_chat_type_helpers(self) -> None:
        group_event = self._sample()
        self.assertTrue(group_event.is_group)
        self.assertFalse(group_event.is_private)

        private_event = TelegramEvent(
            ts=group_event.ts,
            chat_id=1234567890,
            chat_type="private",
            message_id=1,
            from_=group_event.from_,
            text="hi",
            reply_to_message_id=None,
            message_thread_id=None,
            mentions=(),
        )
        self.assertTrue(private_event.is_private)
        self.assertFalse(private_event.is_group)

    def test_to_dict_renames_from_underscore(self) -> None:
        d = self._sample().to_dict()
        self.assertIn("from", d)
        self.assertNotIn("from_", d)
        self.assertEqual(d["from"]["user_id"], 1234567890)

    def test_roundtrip_via_json(self) -> None:
        original = self._sample()
        s = json.dumps(original.to_dict(), ensure_ascii=False)
        loaded = TelegramEvent.from_dict(json.loads(s))
        self.assertEqual(loaded, original)
        self.assertEqual(loaded.dedup_key, original.dedup_key)

    def test_frozen_dataclass_immutable(self) -> None:
        e = self._sample()
        with self.assertRaises(dataclasses_error := Exception):
            # frozen=True raises FrozenInstanceError on attr set
            e.text = "modified"  # type: ignore[misc]


class QueueEntryTests(unittest.TestCase):
    def test_from_event_copies_trigger_fields(self) -> None:
        e = TelegramEvent(
            ts="2026-05-11T14:23:01Z",
            chat_id=-100,
            chat_type="group",
            message_id=42,
            from_=EventFrom(user_id=7, username="demo", is_bot=False),
            text="@vepol_bot do X",
            reply_to_message_id=None,
            message_thread_id=None,
            mentions=("vepol_bot",),
        )
        q = QueueEntry.from_event(e)
        self.assertEqual(q.trigger_msg_id, 42)
        self.assertEqual(q.trigger_chat_id, -100)
        self.assertEqual(q.trigger_user_id, 7)
        self.assertEqual(q.trigger_text, "@vepol_bot do X")
        self.assertIsNone(q.parent_run_id)
        self.assertIsNone(q.picked_at)

    def test_from_event_with_delegation(self) -> None:
        e = TelegramEvent(
            ts="2026-05-11T14:30:00Z",
            chat_id=-100,
            chat_type="group",
            message_id=200,
            from_=EventFrom(user_id=8847291834, username="vepol_bot", is_bot=True, bot_slug="vepol"),
            text="@vepol_marketing_bot prepare release-note",
            reply_to_message_id=42,
            message_thread_id=None,
            mentions=("vepol_marketing_bot",),
        )
        q = QueueEntry.from_event(
            e, parent_run_id="abc-123", delegation_trigger_msg_id=200
        )
        self.assertEqual(q.parent_run_id, "abc-123")
        self.assertEqual(q.delegation_trigger_msg_id, 200)

    def test_roundtrip(self) -> None:
        original = QueueEntry(
            queued_at="2026-05-11T14:23:01Z",
            trigger_msg_id=42,
            trigger_chat_id=-100,
            trigger_user_id=7,
            trigger_text="hi",
        )
        loaded = QueueEntry.from_dict(original.to_dict())
        self.assertEqual(loaded, original)


class RunStateTests(unittest.TestCase):
    def _sample(self) -> RunState:
        return RunState(
            run_id="abc-123",
            agent_slug="vepol",
            status=RUN_STATUS_QUEUED,
            source_chat_id=-100,
            trigger_msg_id=42,
            trigger_user_id=7,
            started_at="2026-05-11T14:23:01Z",
        )

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RunState(
                run_id="x",
                agent_slug="vepol",
                status="totally-bogus",
                source_chat_id=-100,
                trigger_msg_id=1,
                trigger_user_id=1,
                started_at="2026-05-11T14:23:01Z",
            )

    def test_status_transitions_valid(self) -> None:
        r = self._sample()
        # mutate (not frozen) — supervisor does this
        r.status = RUN_STATUS_RUNNING
        self.assertEqual(r.status, RUN_STATUS_RUNNING)
        r.status = RUN_STATUS_SUCCESS
        self.assertEqual(r.status, RUN_STATUS_SUCCESS)
        # __post_init__ doesn't re-run on assignment — that's expected; supervisor
        # validates via status set explicitly when transitioning. This test
        # documents the limitation.

    def test_json_roundtrip(self) -> None:
        original = self._sample()
        s = original.to_json()
        # JSON is stable and human-readable for diff/audit
        self.assertIn("abc-123", s)
        self.assertIn("vepol", s)
        loaded = RunState.from_json(s)
        self.assertEqual(loaded, original)


if __name__ == "__main__":
    unittest.main()
