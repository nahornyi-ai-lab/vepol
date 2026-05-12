"""Tests for flock.py — per-agent exclusive lock."""

from __future__ import annotations

import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.flock import AgentLock, AgentLockBusy, with_agent_lock  # noqa: E402


def _hold_lock_subprocess(lock_dir: str, slug: str, duration: float) -> None:
    """Child process that holds the lock for `duration` seconds."""
    lock = AgentLock(lock_dir, slug)
    lock.try_acquire()
    time.sleep(duration)
    lock.release()


class AgentLockTests(unittest.TestCase):
    def test_invalid_slug_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                AgentLock(td, "")
            with self.assertRaises(ValueError):
                AgentLock(td, "../escape")
            with self.assertRaises(ValueError):
                AgentLock(td, "with/slash")

    def test_acquire_release_basic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock = AgentLock(td, "vepol")
            self.assertFalse(lock.is_held())
            lock.try_acquire()
            self.assertTrue(lock.is_held())
            self.assertTrue(lock.path.exists())
            lock.release()
            self.assertFalse(lock.is_held())

    def test_release_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock = AgentLock(td, "vepol")
            lock.release()  # no-op when not held
            lock.try_acquire()
            lock.release()
            lock.release()  # second release is no-op

    def test_double_acquire_same_instance_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock = AgentLock(td, "vepol")
            lock.try_acquire()
            with self.assertRaises(ValueError):
                lock.try_acquire()
            lock.release()

    def test_concurrent_acquire_from_subprocess_busy(self) -> None:
        # Child holds lock; parent tries to acquire → AgentLockBusy
        with tempfile.TemporaryDirectory() as td:
            slug = "vepol"
            proc = multiprocessing.Process(
                target=_hold_lock_subprocess, args=(td, slug, 1.0)
            )
            proc.start()
            try:
                # Wait a moment for child to acquire lock
                time.sleep(0.2)
                parent_lock = AgentLock(td, slug)
                with self.assertRaises(AgentLockBusy):
                    parent_lock.try_acquire()
                self.assertFalse(parent_lock.is_held())
            finally:
                proc.join(timeout=3)

    def test_lock_released_after_subprocess_exits(self) -> None:
        # After child releases lock and exits, parent can acquire
        with tempfile.TemporaryDirectory() as td:
            slug = "vepol"
            proc = multiprocessing.Process(
                target=_hold_lock_subprocess, args=(td, slug, 0.2)
            )
            proc.start()
            proc.join()  # wait for child to release and exit
            self.assertEqual(proc.exitcode, 0)
            parent_lock = AgentLock(td, slug)
            parent_lock.try_acquire()
            parent_lock.release()

    def test_per_agent_independence(self) -> None:
        # Locking "vepol" doesn't lock "kb-mail"
        with tempfile.TemporaryDirectory() as td:
            l1 = AgentLock(td, "vepol")
            l2 = AgentLock(td, "kb-mail")
            l1.try_acquire()
            l2.try_acquire()  # independent
            l1.release()
            l2.release()

    def test_touch_activity_updates_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock = AgentLock(td, "vepol")
            lock.try_acquire()
            try:
                initial = lock.last_activity_ts()
                time.sleep(0.05)
                lock.touch_activity()
                after = lock.last_activity_ts()
                self.assertGreater(after, initial)
            finally:
                lock.release()

    def test_last_activity_ts_none_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock = AgentLock(td, "no-such-agent-ever-acquired")
            self.assertIsNone(lock.last_activity_ts())

    def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with AgentLock(td, "vepol") as lock:
                self.assertTrue(lock.is_held())
            self.assertFalse(lock.is_held())

    def test_with_agent_lock_helper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with with_agent_lock(td, "vepol") as lock:
                self.assertTrue(lock.is_held())
            # Exiting context releases
            l2 = AgentLock(td, "vepol")
            l2.try_acquire()  # succeeds because previous released
            l2.release()


if __name__ == "__main__":
    unittest.main()
