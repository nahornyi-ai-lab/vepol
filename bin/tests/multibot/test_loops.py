"""Tests for loops.py — 4 loop guards (cooldown, depth, fan-out, quota)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.loops import (  # noqa: E402
    DEFAULT_DEPTH_CAP,
    DEFAULT_FAN_OUT_CAP,
    DEFAULT_HOURLY_QUOTA_PER_USER,
    LoopGuard,
    MAX_DEPTH_CAP,
    get_depth_cap,
)


class DepthCapTests(unittest.TestCase):
    def test_default(self) -> None:
        self.assertEqual(DEFAULT_DEPTH_CAP, 4)

    def test_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"KB_MULTIBOT_DEPTH_CAP": "6"}):
            self.assertEqual(get_depth_cap(), 6)

    def test_env_clamped_to_max(self) -> None:
        with mock.patch.dict(os.environ, {"KB_MULTIBOT_DEPTH_CAP": "100"}):
            self.assertEqual(get_depth_cap(), MAX_DEPTH_CAP)

    def test_env_minimum_one(self) -> None:
        with mock.patch.dict(os.environ, {"KB_MULTIBOT_DEPTH_CAP": "0"}):
            self.assertEqual(get_depth_cap(), 1)

    def test_env_invalid_falls_back(self) -> None:
        with mock.patch.dict(os.environ, {"KB_MULTIBOT_DEPTH_CAP": "not-a-number"}):
            self.assertEqual(get_depth_cap(), DEFAULT_DEPTH_CAP)


class CooldownTests(unittest.TestCase):
    def test_no_cooldown_initially(self) -> None:
        g = LoopGuard()
        self.assertFalse(g.in_cooldown(-100, "vepol"))

    def test_cooldown_after_mark(self) -> None:
        g = LoopGuard(cooldown_sec=30)
        g.mark_outbound(-100, "vepol", now=1000.0)
        self.assertTrue(g.in_cooldown(-100, "vepol", now=1010.0))
        self.assertTrue(g.in_cooldown(-100, "vepol", now=1029.9))
        self.assertFalse(g.in_cooldown(-100, "vepol", now=1031.0))

    def test_cooldown_per_chat_agent(self) -> None:
        # Different chat or different agent — independent cooldowns
        g = LoopGuard(cooldown_sec=30)
        g.mark_outbound(-100, "vepol", now=1000.0)
        self.assertFalse(g.in_cooldown(999, "vepol", now=1010.0))
        self.assertFalse(g.in_cooldown(-100, "kb-mail", now=1010.0))


class DepthTests(unittest.TestCase):
    def test_depth_below_cap(self) -> None:
        g = LoopGuard(depth_cap=4)
        self.assertFalse(g.depth_exceeded(0))
        self.assertFalse(g.depth_exceeded(3))

    def test_depth_at_cap_blocks(self) -> None:
        g = LoopGuard(depth_cap=4)
        self.assertTrue(g.depth_exceeded(4))
        self.assertTrue(g.depth_exceeded(5))


class FanOutTests(unittest.TestCase):
    def test_within_cap_all_pass(self) -> None:
        g = LoopGuard(fan_out_cap=10)
        spawn, queue = g.truncate_fan_out(["a", "b", "c"])
        self.assertEqual(spawn, ["a", "b", "c"])
        self.assertEqual(queue, [])

    def test_exact_cap(self) -> None:
        g = LoopGuard(fan_out_cap=3)
        mentions = ["a", "b", "c"]
        spawn, queue = g.truncate_fan_out(mentions)
        self.assertEqual(spawn, ["a", "b", "c"])
        self.assertEqual(queue, [])

    def test_over_cap_queues_rest(self) -> None:
        g = LoopGuard(fan_out_cap=3)
        mentions = ["a", "b", "c", "d", "e"]
        spawn, queue = g.truncate_fan_out(mentions)
        self.assertEqual(spawn, ["a", "b", "c"])
        self.assertEqual(queue, ["d", "e"])

    def test_default_cap_is_10(self) -> None:
        self.assertEqual(DEFAULT_FAN_OUT_CAP, 10)
        g = LoopGuard()
        # 12 mentions → 10 spawn, 2 queue
        mentions = [f"bot_{i}" for i in range(12)]
        spawn, queue = g.truncate_fan_out(mentions)
        self.assertEqual(len(spawn), 10)
        self.assertEqual(len(queue), 2)


class HourlyQuotaTests(unittest.TestCase):
    def test_default_quota_60(self) -> None:
        self.assertEqual(DEFAULT_HOURLY_QUOTA_PER_USER, 60)

    def test_no_quota_initially(self) -> None:
        g = LoopGuard()
        self.assertFalse(g.quota_exceeded(user_id=7))
        self.assertEqual(g.current_quota_usage(7), 0)

    def test_record_and_check(self) -> None:
        g = LoopGuard(hourly_quota=3)
        g.record_spawn(7, now=1000.0)
        g.record_spawn(7, now=1100.0)
        self.assertFalse(g.quota_exceeded(7, now=1200.0))
        g.record_spawn(7, now=1200.0)
        # 3 spawns at quota=3 → exceeded
        self.assertTrue(g.quota_exceeded(7, now=1300.0))

    def test_quota_window_slides(self) -> None:
        # Spawns older than 1h are pruned
        g = LoopGuard(hourly_quota=2)
        g.record_spawn(7, now=1000.0)
        g.record_spawn(7, now=1100.0)
        self.assertTrue(g.quota_exceeded(7, now=1200.0))
        # >1h later: old spawns dropped
        self.assertFalse(g.quota_exceeded(7, now=1000.0 + 3601.0))

    def test_per_user_isolation(self) -> None:
        g = LoopGuard(hourly_quota=1)
        g.record_spawn(7, now=1000.0)
        # user 7 over quota, user 8 untouched
        self.assertTrue(g.quota_exceeded(7, now=1100.0))
        self.assertFalse(g.quota_exceeded(8, now=1100.0))


if __name__ == "__main__":
    unittest.main()
