"""Tests for spawner.py — adapters use simple echo binaries for subprocess test."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot import spawner  # noqa: E402
from _kb_multibot.spawner import (  # noqa: E402
    BaseAdapter,
    ClaudeAdapter,
    CodexAdapter,
    SpawnFailed,
    make_adapter,
)


_REAL_KILL = os.kill


def _guarded_kill(pid, sig):
    """os.kill stand-in for tests: never lets a group/broadcast signal through."""
    if pid <= 1 or pid in (os.getpid(), os.getppid()):
        raise AssertionError(f"test tried to signal pid={pid}")
    return _REAL_KILL(pid, sig)


class _EchoAdapter(BaseAdapter):
    """Test adapter: writes prompt content back to stdout via /bin/cat.

    Useful for verifying spawn lifecycle without depending on claude/codex.
    """

    name = "echo"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/cat", "{PROMPT_FILE}"]


class _JsonAdapter(BaseAdapter):
    """Test adapter: writes a JSON envelope so parsing logic exercises."""

    name = "json"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return [
            "/bin/sh",
            "-c",
            'echo \'{"result": "ok", "session_id": "test-sid", "total_cost_usd": 0.01}\'',
        ]


class _MixedAdapter(BaseAdapter):
    """Test adapter: writes some plain log lines then a JSON envelope at end."""

    name = "mixed"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return [
            "/bin/sh",
            "-c",
            ('echo "progress 1"; echo "progress 2"; '
             'echo \'{"result": "done", "session_id": "sid-9"}\''),
        ]


class _FailAdapter(BaseAdapter):
    """Test adapter: exits non-zero with stderr."""

    name = "fail"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/sh", "-c", "echo 'err msg' >&2; exit 7"]


class _MissingAdapter(BaseAdapter):
    """Test adapter: _argv returns None (binary not found)."""

    name = "missing"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return None


class _PidAdapter(BaseAdapter):
    """Test adapter: the child prints its own pid."""

    name = "pid"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/sh", "-c", "echo $$"]


class _SleepAdapter(BaseAdapter):
    """Test adapter: a silent child that runs until it is signalled."""

    name = "sleep"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/sleep", "30"]


class _StubbornAdapter(BaseAdapter):
    """Test adapter: a child that ignores SIGTERM (needs SIGKILL).

    It prints "ready" once the trap is in place so the test signals it only
    after that point.
    """

    name = "stubborn"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/sh", "-c", 'trap "" TERM; echo ready; exec /bin/sleep 30']


def _run_async(coro):
    return asyncio.run(coro)


class SpawnLifecycleTests(unittest.TestCase):
    def test_echo_passes_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            adapter = _EchoAdapter()
            result = _run_async(
                adapter.spawn(
                    run_id="r1",
                    agent_slug="test",
                    workdir=td,
                    prompt="hello world",
                )
            )
            self.assertEqual(result.exit_code, 0)
            self.assertIn("hello world", result.stdout)
            self.assertEqual(result.run_id, "r1")
            self.assertEqual(result.agent_slug, "test")
            self.assertGreaterEqual(result.duration_sec, 0)

    def test_json_envelope_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            adapter = _JsonAdapter()
            result = _run_async(
                adapter.spawn(
                    run_id="r2",
                    agent_slug="t",
                    workdir=td,
                    prompt="x",
                )
            )
            self.assertEqual(result.exit_code, 0)
            self.assertIsNotNone(result.parsed)
            self.assertEqual(result.parsed["result"], "ok")
            self.assertEqual(result.parsed["session_id"], "test-sid")

    def test_mixed_output_parses_trailing_json(self) -> None:
        # claude -p sometimes emits log lines before the JSON envelope
        with tempfile.TemporaryDirectory() as td:
            adapter = _MixedAdapter()
            result = _run_async(
                adapter.spawn(
                    run_id="r3",
                    agent_slug="t",
                    workdir=td,
                    prompt="x",
                )
            )
            self.assertEqual(result.exit_code, 0)
            self.assertIsNotNone(result.parsed)
            self.assertEqual(result.parsed["session_id"], "sid-9")

    def test_failed_exit_captured(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            adapter = _FailAdapter()
            result = _run_async(
                adapter.spawn(
                    run_id="r4",
                    agent_slug="t",
                    workdir=td,
                    prompt="x",
                )
            )
            self.assertEqual(result.exit_code, 7)
            self.assertIn("err msg", result.stderr)

    def test_missing_binary_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            adapter = _MissingAdapter()
            with self.assertRaises(SpawnFailed):
                _run_async(
                    adapter.spawn(
                        run_id="r5",
                        agent_slug="t",
                        workdir=td,
                        prompt="x",
                    )
                )

    def test_stdout_callback_invoked(self) -> None:
        chunks: list[str] = []

        with tempfile.TemporaryDirectory() as td:
            adapter = _MixedAdapter()
            _run_async(
                adapter.spawn(
                    run_id="r6",
                    agent_slug="t",
                    workdir=td,
                    prompt="x",
                    on_stdout_chunk=chunks.append,
                )
            )
            # 2 progress lines + 1 JSON envelope = 3 chunks (one per readline)
            self.assertGreaterEqual(len(chunks), 3)
            self.assertTrue(any("progress" in c for c in chunks))

    def test_stdout_callback_exception_swallowed(self) -> None:
        # If watchdog.touch raises, process must still complete
        def boom(_chunk: str) -> None:
            raise RuntimeError("watchdog broke")

        with tempfile.TemporaryDirectory() as td:
            adapter = _EchoAdapter()
            result = _run_async(
                adapter.spawn(
                    run_id="r7",
                    agent_slug="t",
                    workdir=td,
                    prompt="x",
                    on_stdout_chunk=boom,
                )
            )
            self.assertEqual(result.exit_code, 0)


class PidRecordingTests(unittest.TestCase):
    def test_on_started_reports_real_child_pid(self) -> None:
        started: list[int] = []
        with tempfile.TemporaryDirectory() as td:
            result = _run_async(
                _PidAdapter().spawn(
                    run_id="p1",
                    agent_slug="t",
                    workdir=td,
                    prompt="x",
                    on_started=started.append,
                )
            )
        self.assertEqual(len(started), 1)
        self.assertGreater(started[0], 1)
        # The pid the callback got is the pid the child itself reports.
        self.assertEqual(started[0], int(result.stdout.strip()))

    def test_on_started_failure_stops_the_child(self) -> None:
        def boom(_pid: int) -> None:
            raise RuntimeError("watchdog registration failed")

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory() as td, \
                mock.patch("os.kill", _guarded_kill):
            with self.assertRaises(RuntimeError):
                _run_async(
                    _SleepAdapter().spawn(
                        run_id="p2", agent_slug="t", workdir=td, prompt="x",
                        on_started=boom,
                    )
                )
        # The 30 s child was killed instead of being left unwatched.
        self.assertLess(time.monotonic() - t0, 10)


class KillGuardTests(unittest.TestCase):
    """kill() must never signal -1 (every user process), 0 (own group),
    negative ids (groups), 1 (launchd), itself or its parent."""

    def test_dangerous_pids_are_refused_without_signal(self) -> None:
        for pid in (-1, 0, -12345, 1, os.getpid(), os.getppid()):
            with self.subTest(pid=pid), \
                    mock.patch("os.kill") as kill, \
                    mock.patch("os.killpg") as killpg, \
                    self.assertLogs("kb-multibot", level="ERROR") as logs:
                sent = _run_async(BaseAdapter().kill(pid, escalate_after=0))
                self.assertFalse(sent)
                kill.assert_not_called()
                killpg.assert_not_called()
                self.assertIn("refusing to signal", logs.output[0])

    def test_non_int_pid_refused(self) -> None:
        with mock.patch("os.kill") as kill, \
                self.assertLogs("kb-multibot", level="ERROR"):
            for pid in (None, "123", True, 1.5):
                self.assertFalse(_run_async(BaseAdapter().kill(pid, escalate_after=0)))
            kill.assert_not_called()


class KillChildTests(unittest.TestCase):
    """A kill reaches exactly one child; an unrelated process survives."""

    def setUp(self) -> None:
        self.bystander = subprocess.Popen(["/bin/sleep", "60"])
        self.addCleanup(self._reap_bystander)

    def _reap_bystander(self) -> None:
        if self.bystander.poll() is None:
            self.bystander.kill()
        self.bystander.wait()

    def _spawn_then_kill(self, adapter: BaseAdapter, escalate_after: float,
                         wait_for_ready: bool = False):
        async def scenario():
            started: list[int] = []
            chunks: list[str] = []
            with tempfile.TemporaryDirectory() as td:
                task = asyncio.create_task(adapter.spawn(
                    run_id="k1", agent_slug="t", workdir=td, prompt="x",
                    on_started=started.append, on_stdout_chunk=chunks.append,
                ))
                for _ in range(500):
                    if started and (chunks or not wait_for_ready):
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(started, "child never started")
                sent = await adapter.kill(started[0], escalate_after=escalate_after)
                result = await asyncio.wait_for(task, timeout=10)
                return started[0], sent, result

        with mock.patch("os.kill", _guarded_kill), \
                mock.patch("os.killpg", side_effect=AssertionError("killpg")):
            return _run_async(scenario())

    def test_sigterm_stops_only_the_spawned_child(self) -> None:
        pid, sent, result = self._spawn_then_kill(_SleepAdapter(), escalate_after=5)
        self.assertTrue(sent)
        self.assertEqual(result.exit_code, -signal.SIGTERM)
        self.assertNotEqual(pid, self.bystander.pid)
        self.assertIsNone(self.bystander.poll(), "unrelated process was signalled")

    def test_escalates_to_sigkill_when_term_ignored(self) -> None:
        pid, sent, result = self._spawn_then_kill(
            _StubbornAdapter(), escalate_after=0.5, wait_for_ready=True
        )
        self.assertTrue(sent)
        self.assertEqual(result.exit_code, -signal.SIGKILL)
        self.assertIsNone(self.bystander.poll(), "unrelated process was signalled")

    def test_bare_pid_kill_targets_only_that_pid(self) -> None:
        target = subprocess.Popen(["/bin/sleep", "60"])
        try:
            with mock.patch("os.kill", _guarded_kill):
                sent = _run_async(BaseAdapter().kill(target.pid, escalate_after=0.2))
            self.assertTrue(sent)
            self.assertEqual(target.wait(timeout=5), -signal.SIGTERM)
            self.assertIsNone(self.bystander.poll(), "unrelated process was signalled")
        finally:
            if target.poll() is None:
                target.kill()
                target.wait()

    def test_handle_released_after_exit(self) -> None:
        adapter = _EchoAdapter()
        started: list[int] = []
        with tempfile.TemporaryDirectory() as td:
            _run_async(adapter.spawn(run_id="k2", agent_slug="t", workdir=td,
                                     prompt="x", on_started=started.append))
        # No handle is kept for a finished child, so nothing can signal it.
        self.assertIsNone(adapter._proc)
        self.assertEqual(len(started), 1)


class ClaudePathTests(unittest.TestCase):
    """Shared lookup order: $KB_CLAUDE_BIN, PATH, ~/.local/bin, Homebrew."""

    def _exe(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_kb_claude_bin_wins(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            custom = self._exe(Path(td) / "custom" / "claude")
            on_path = self._exe(Path(td) / "path" / "claude")
            env = {"KB_CLAUDE_BIN": str(custom), "PATH": str(on_path.parent)}
            with mock.patch.dict(os.environ, env):
                self.assertEqual(spawner._claude_path(), str(custom))

    def test_path_before_local_bin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            self._exe(home / ".local" / "bin" / "claude")
            on_path = self._exe(Path(td) / "path" / "claude")
            env = {"PATH": str(on_path.parent), "KB_CLAUDE_BIN": ""}
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(spawner.Path, "home", return_value=home):
                self.assertEqual(spawner._claude_path(), str(on_path))

    def test_local_bin_found_without_path(self) -> None:
        # launchd's PATH has no ~/.local/bin, where the native installer puts claude.
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            local = self._exe(home / ".local" / "bin" / "claude")
            empty = Path(td) / "empty"
            empty.mkdir()
            with mock.patch.dict(os.environ, {"PATH": str(empty), "KB_CLAUDE_BIN": ""}), \
                    mock.patch.object(spawner.Path, "home", return_value=home):
                self.assertEqual(spawner._claude_path(), str(local))

    def test_non_executable_override_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "claude"
            bad.write_text("x", encoding="utf-8")
            bad.chmod(0o644)
            on_path = self._exe(Path(td) / "path" / "claude")
            env = {"KB_CLAUDE_BIN": str(bad), "PATH": str(on_path.parent)}
            with mock.patch.dict(os.environ, env):
                self.assertEqual(spawner._claude_path(), str(on_path))


class FactoryTests(unittest.TestCase):
    def test_claude_factory(self) -> None:
        a = make_adapter("claude")
        self.assertIsInstance(a, ClaudeAdapter)

    def test_codex_factory(self) -> None:
        a = make_adapter("codex")
        self.assertIsInstance(a, CodexAdapter)

    def test_codex_factory_accepts_supervisor_kwargs(self) -> None:
        # The supervisor always passes resume_session_id (None unless
        # warm_session); a codex agent used to crash with a TypeError here.
        for resume in (None, "sid-1"):
            a = make_adapter("codex", resume_session_id=resume)
            self.assertIsInstance(a, CodexAdapter)

    def test_claude_factory_keeps_resume_id(self) -> None:
        a = make_adapter("claude", resume_session_id="sid-1")
        self.assertEqual(a.resume_session_id, "sid-1")

    def test_unknown_runtime_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_adapter("gemini")


class JsonParsingTests(unittest.TestCase):
    def test_full_stdout_is_json(self) -> None:
        s = '{"result": "ok"}'
        self.assertEqual(BaseAdapter._try_parse_json(s), {"result": "ok"})

    def test_trailing_json_after_logs(self) -> None:
        s = "log line one\nlog line two\n{\"result\": \"ok\"}\n"
        self.assertEqual(BaseAdapter._try_parse_json(s), {"result": "ok"})

    def test_no_json_returns_none(self) -> None:
        self.assertIsNone(BaseAdapter._try_parse_json("just text\nno json"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(BaseAdapter._try_parse_json(""))


if __name__ == "__main__":
    unittest.main()
