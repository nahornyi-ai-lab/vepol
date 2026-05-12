"""Tests for watchdog.py — stdout-silence detection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.watchdog import Watchdog  # noqa: E402


class WatchdogTests(unittest.TestCase):
    def test_add_and_get(self) -> None:
        wd = Watchdog()
        wd.add(run_id="abc", agent_slug="vepol", pid=42, silence_sec=900, now=1000.0)
        wr = wd.get("abc")
        self.assertIsNotNone(wr)
        self.assertEqual(wr.pid, 42)
        self.assertEqual(wr.last_stdout_ts, 1000.0)
        self.assertEqual(wr.started_at, 1000.0)

    def test_contains_and_len(self) -> None:
        wd = Watchdog()
        self.assertNotIn("abc", wd)
        self.assertEqual(len(wd), 0)
        wd.add("abc", "vepol", pid=1, now=0.0)
        self.assertIn("abc", wd)
        self.assertEqual(len(wd), 1)

    def test_touch_updates_last_stdout(self) -> None:
        wd = Watchdog()
        wd.add("abc", "vepol", pid=1, now=1000.0)
        wd.touch("abc", now=1500.0)
        wr = wd.get("abc")
        self.assertEqual(wr.last_stdout_ts, 1500.0)

    def test_touch_unknown_silent(self) -> None:
        wd = Watchdog()
        wd.touch("never-added")  # no-op, no error

    def test_remove(self) -> None:
        wd = Watchdog()
        wd.add("abc", "vepol", pid=1, now=0.0)
        wd.remove("abc")
        self.assertNotIn("abc", wd)
        # Remove of unknown is silent
        wd.remove("never-added")

    def test_silence_expiry(self) -> None:
        wd = Watchdog()
        wd.add("abc", "vepol", pid=1, silence_sec=900, now=1000.0)
        # Just before threshold — not expired
        expired = wd.expired_runs(now=1899.0)
        self.assertEqual(expired, [])
        # At threshold — expired
        expired = wd.expired_runs(now=1900.0)
        self.assertEqual(len(expired), 1)
        wr, reason = expired[0]
        self.assertEqual(wr.run_id, "abc")
        self.assertEqual(reason, "silence")

    def test_silence_reset_by_touch(self) -> None:
        wd = Watchdog()
        wd.add("abc", "vepol", pid=1, silence_sec=900, now=1000.0)
        # Touch close to threshold — silence timer resets
        wd.touch("abc", now=1800.0)
        # Now 1899 — only 99s since last touch, well under 900s threshold
        self.assertEqual(wd.expired_runs(now=1899.0), [])

    def test_hard_timeout(self) -> None:
        wd = Watchdog()
        wd.add(
            "abc",
            "vepol",
            pid=1,
            silence_sec=99999,  # silence disabled effectively
            hard_timeout_sec=3600,
            now=1000.0,
        )
        # 1 hour — at threshold
        expired = wd.expired_runs(now=4600.0)
        self.assertEqual(len(expired), 1)
        wr, reason = expired[0]
        self.assertEqual(reason, "timeout")

    def test_no_hard_timeout_when_off(self) -> None:
        # Default: hard_timeout_sec=None, only silence checked
        wd = Watchdog()
        wd.add("abc", "vepol", pid=1, silence_sec=900, now=1000.0)
        # Touch every 100s for 10 hours — runs forever without silence trigger
        for t in range(1000, 36000, 100):
            wd.touch("abc", now=float(t))
        self.assertEqual(wd.expired_runs(now=36050.0), [])

    def test_silence_wins_over_timeout(self) -> None:
        # Both expired at same check — silence first in result
        wd = Watchdog()
        wd.add(
            "abc",
            "vepol",
            pid=1,
            silence_sec=100,
            hard_timeout_sec=200,
            now=1000.0,
        )
        # 300s later: silent for 300s, run for 300s — silence is first reason
        expired = wd.expired_runs(now=1300.0)
        self.assertEqual(len(expired), 1)
        wr, reason = expired[0]
        self.assertEqual(reason, "silence")

    def test_all_runs_snapshot(self) -> None:
        wd = Watchdog()
        wd.add("a", "vepol", pid=1, now=0.0)
        wd.add("b", "kb-mail", pid=2, now=1.0)
        snapshot = wd.all_runs()
        self.assertEqual(len(snapshot), 2)


if __name__ == "__main__":
    unittest.main()
