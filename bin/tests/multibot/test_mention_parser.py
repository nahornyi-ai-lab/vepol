"""Tests for mention.py — text-based parser invariants."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.mention import (  # noqa: E402
    extract_mentions,
    extract_stop_targets,
    filter_bot_mentions,
    has_stop_command,
)


class ExtractMentionsTests(unittest.TestCase):
    def test_single_mention(self) -> None:
        self.assertEqual(extract_mentions("@vepol_bot статус?"), ["vepol_bot"])

    def test_multiple_in_order(self) -> None:
        self.assertEqual(
            extract_mentions("@vepol_bot и @kb_mail_bot проверьте"),
            ["vepol_bot", "kb_mail_bot"],
        )

    def test_duplicates_collapsed_preserving_first(self) -> None:
        self.assertEqual(
            extract_mentions("@a_bot @b_bot @a_bot"), ["a_bot", "b_bot"]
        )

    def test_case_insensitive_lowercased(self) -> None:
        self.assertEqual(extract_mentions("@Vepol_Bot @VEPOL_BOT"), ["vepol_bot"])

    def test_no_mentions_returns_empty(self) -> None:
        self.assertEqual(extract_mentions("plain text without mentions"), [])

    def test_email_addresses_extract_local_part(self) -> None:
        # `me@example.com` — regex matches `example` (5 chars, starts with letter).
        # Filter step in filter_bot_mentions weeds this out via known_bots set.
        result = extract_mentions("email me at me@example.com and tag @real_bot")
        self.assertIn("real_bot", result)
        # `example` is allowed by regex but won't be in registry.
        # We don't assert exact membership of `example` here — just demonstrate
        # that filter is required.

    def test_too_short_mentions_skipped(self) -> None:
        # min 5 chars after @, so @abc and @4u are not matches.
        self.assertEqual(extract_mentions("@abc @4u @longer_bot"), ["longer_bot"])

    def test_empty_string(self) -> None:
        self.assertEqual(extract_mentions(""), [])

    def test_none_safe(self) -> None:
        # Defensive: callers may pass None for caption-less messages
        self.assertEqual(extract_mentions(None), [])  # type: ignore[arg-type]


class FilterBotMentionsTests(unittest.TestCase):
    def test_keeps_known_drops_unknown(self) -> None:
        known = {"vepol_bot", "kb_mail_bot"}
        self.assertEqual(
            filter_bot_mentions(
                ["vepol_bot", "example", "kb_mail_bot", "stranger_bot"], known
            ),
            ["vepol_bot", "kb_mail_bot"],
        )

    def test_order_preserved(self) -> None:
        known = {"a_bot", "b_bot", "c_bot"}
        self.assertEqual(
            filter_bot_mentions(["c_bot", "a_bot", "b_bot"], known),
            ["c_bot", "a_bot", "b_bot"],
        )

    def test_empty_input(self) -> None:
        self.assertEqual(filter_bot_mentions([], {"any_bot"}), [])


class StopCommandTests(unittest.TestCase):
    def test_simple(self) -> None:
        self.assertTrue(has_stop_command("/stop @vepol_bot"))

    def test_case_insensitive(self) -> None:
        self.assertTrue(has_stop_command("please /STOP @bot"))

    def test_word_boundary_required(self) -> None:
        self.assertFalse(has_stop_command("/stoplight"))
        self.assertFalse(has_stop_command("don't/stop"))

    def test_bare_stop(self) -> None:
        self.assertTrue(has_stop_command("/stop"))

    def test_no_stop(self) -> None:
        self.assertFalse(has_stop_command("just talking"))


class ExtractStopTargetsTests(unittest.TestCase):
    def test_with_mentions(self) -> None:
        self.assertEqual(
            extract_stop_targets("/stop @vepol_bot @kb_mail_bot"),
            ["vepol_bot", "kb_mail_bot"],
        )

    def test_bare_stop_no_targets(self) -> None:
        # Bare /stop returns empty; caller resolves target from reply_to.
        self.assertEqual(extract_stop_targets("/stop"), [])

    def test_non_stop_message_returns_empty(self) -> None:
        self.assertEqual(extract_stop_targets("@bot do X"), [])


if __name__ == "__main__":
    unittest.main()
