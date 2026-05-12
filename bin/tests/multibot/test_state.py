"""Tests for state.py — atomic file IO, queue/run/observer state."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.events import (  # noqa: E402
    QueueEntry,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCESS,
    RunState,
)
from _kb_multibot.state import StateStore  # noqa: E402


class StateStoreSetupTests(unittest.TestCase):
    def test_default_root_under_home(self) -> None:
        s = StateStore()
        self.assertTrue(str(s.root).endswith(".orchestrator/multibot"))

    def test_custom_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = StateStore(td)
            self.assertEqual(s.root, Path(td))

    def test_ensure_dirs_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = StateStore(td)
            s.ensure_dirs()
            s.ensure_dirs()  # second call must not fail
            for sub in (s.queues, s.runs, s.observer, s.watchdog, s.cache):
                self.assertTrue(sub.is_dir())


class QueueTests(unittest.TestCase):
    def _store(self, td: str) -> StateStore:
        s = StateStore(td)
        s.ensure_dirs()
        return s

    def _entry(self, msg_id: int = 1) -> QueueEntry:
        return QueueEntry(
            queued_at="2026-05-11T14:23:01Z",
            trigger_msg_id=msg_id,
            trigger_chat_id=-100,
            trigger_user_id=7,
            trigger_text=f"trigger {msg_id}",
        )

    def test_read_empty_queue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            self.assertEqual(s.read_queue("vepol"), [])

    def test_write_and_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            entries = [self._entry(1), self._entry(2), self._entry(3)]
            s.write_queue("vepol", entries)
            loaded = s.read_queue("vepol")
            self.assertEqual(loaded, entries)

    def test_isolation_between_agents(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_queue("vepol", [self._entry(1)])
            s.write_queue("kb-mail", [self._entry(2), self._entry(3)])
            self.assertEqual(len(s.read_queue("vepol")), 1)
            self.assertEqual(len(s.read_queue("kb-mail")), 2)

    def test_atomic_write_no_tmp_left(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_queue("vepol", [self._entry(1)])
            # No leftover .tmp files after successful write
            leftover = list(s.queues.glob("*.tmp"))
            self.assertEqual(leftover, [])

    def test_write_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_queue("vepol", [self._entry(1), self._entry(2)])
            s.write_queue("vepol", [self._entry(3)])
            loaded = s.read_queue("vepol")
            self.assertEqual([e.trigger_msg_id for e in loaded], [3])


class RunTests(unittest.TestCase):
    def _store(self, td: str) -> StateStore:
        s = StateStore(td)
        s.ensure_dirs()
        return s

    def _run(self, run_id: str = "abc-123", parent: str | None = None) -> RunState:
        return RunState(
            run_id=run_id,
            agent_slug="vepol",
            status=RUN_STATUS_QUEUED,
            source_chat_id=-100,
            trigger_msg_id=42,
            trigger_user_id=7,
            started_at="2026-05-11T14:23:01Z",
            parent_run_id=parent,
        )

    def test_read_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            self.assertIsNone(s.read_run("never-existed"))

    def test_write_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            r = self._run()
            s.write_run(r)
            loaded = s.read_run("abc-123")
            self.assertEqual(loaded, r)

    def test_invalid_run_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            with self.assertRaises(ValueError):
                s.run_path("../escape")
            with self.assertRaises(ValueError):
                s.run_path("with/slash")
            with self.assertRaises(ValueError):
                s.run_path("")

    def test_list_runs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_run(self._run("a"))
            s.write_run(self._run("b"))
            s.write_run(self._run("c"))
            runs = s.list_runs()
            ids = sorted(r.run_id for r in runs)
            self.assertEqual(ids, ["a", "b", "c"])

    def test_children_of_parent_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_run(self._run("parent"))
            s.write_run(self._run("child1", parent="parent"))
            s.write_run(self._run("child2", parent="parent"))
            s.write_run(self._run("unrelated"))
            children = s.children_of_parent_run("parent")
            ids = sorted(r.run_id for r in children)
            self.assertEqual(ids, ["child1", "child2"])

    def test_status_update_via_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            r = self._run()
            s.write_run(r)
            r.status = RUN_STATUS_RUNNING
            s.write_run(r)
            loaded = s.read_run("abc-123")
            self.assertEqual(loaded.status, RUN_STATUS_RUNNING)


class ObserverTests(unittest.TestCase):
    def _store(self, td: str) -> StateStore:
        s = StateStore(td)
        s.ensure_dirs()
        return s

    def test_read_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            self.assertEqual(s.read_observer_offsets(), {})

    def test_write_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_observer_offset(-1001234567, 12891)
            s.write_observer_offset(1234567890, 555)
            offsets = s.read_observer_offsets()
            self.assertEqual(offsets[-1001234567], 12891)
            self.assertEqual(offsets[1234567890], 555)

    def test_update_existing_chat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.write_observer_offset(-100, 1)
            s.write_observer_offset(-100, 2)
            offsets = s.read_observer_offsets()
            self.assertEqual(offsets[-100], 2)

    def test_corrupted_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.observer_path().write_text("not json", encoding="utf-8")
            self.assertEqual(s.read_observer_offsets(), {})


if __name__ == "__main__":
    unittest.main()
