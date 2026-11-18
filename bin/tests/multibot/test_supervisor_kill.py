"""Supervisor kill paths: the watchdog and /stop signal only the run's own child.

Regression for the pid=-1 bug: the supervisor used to register every run
with pid=-1, so a watchdog trip (15 min of stdout silence, i.e. any long
`claude -p --output-format json` run) or /stop called os.kill(-1, SIGTERM),
which signals every process the user owns.

Every test here runs with os.kill replaced by a guard that raises instead of
signalling pid <= 1, so a regression fails the test rather than the machine.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

try:  # the listener needs Telethon; these tests never connect to Telegram
    import telethon  # noqa: F401
except ImportError:
    _stub = types.ModuleType("_kb_multibot.listener")
    _stub.GroupListener = object
    sys.modules.setdefault("_kb_multibot.listener", _stub)

from _kb_multibot import supervisor as sv  # noqa: E402
from _kb_multibot.config import SupervisorConfig  # noqa: E402
from _kb_multibot.events import EventFrom, TelegramEvent  # noqa: E402
from _kb_multibot.registry import AgentSpec  # noqa: E402
from _kb_multibot.spawner import BaseAdapter  # noqa: E402


_REAL_KILL = os.kill
_signalled: list[tuple[int, int]] = []


def _guarded_kill(pid, sig):
    if pid <= 1 or pid in (os.getpid(), os.getppid()):
        raise AssertionError(f"supervisor tried to signal pid={pid}")
    _signalled.append((pid, sig))
    return _REAL_KILL(pid, sig)


class _SilentAdapter(BaseAdapter):
    """Fake agent: a child that prints nothing until it is stopped."""

    name = "silent"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/sleep", "60"]


class _QuickAdapter(BaseAdapter):
    name = "quick"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return ["/bin/sh", "-c", 'echo \'{"result": "done"}\'']


class _MissingAdapter(BaseAdapter):
    name = "missing"

    def _argv_with_prompt(self, prompt, workdir, agent_slug, run_id):
        return None


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def set_reaction(self, **kw):
        return None

    async def send_message(self, **kw):
        self.sent.append(kw.get("text", ""))
        return types.SimpleNamespace(message_id=99)

    async def close(self):
        return None


def _event() -> TelegramEvent:
    return TelegramEvent(
        ts="2026-01-01T00:00:00Z",
        chat_id=-100123,
        chat_type="group",
        message_id=5,
        from_=EventFrom(user_id=7, username="demo", is_bot=False, bot_slug=None),
        text="@demo_bot status?",
        reply_to_message_id=None,
        message_thread_id=None,
        mentions=("demo_bot",),
    )


class SupervisorKillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        root = Path(self.td.name)
        self.config = SupervisorConfig(
            tg_api_id=1,
            tg_api_hash="hash",
            group_chat_id=-100123,
            session_file=root / "session",
            projects_dir=root / "projects",
            state_root=root / "state",
            bot_tokens_dir=root / "bots",
            log_file=root / "log",
        )
        self.spec = AgentSpec(
            slug="demo",
            bot_id=1,
            bot_username="demo_bot",
            bot_token_ref=str(root / "bots" / "demo.env"),
            workdir=str(root),
            runtime="claude",
            parent_slug=None,
        )
        self.bystander = subprocess.Popen(["/bin/sleep", "60"])
        self.addCleanup(self._reap_bystander)
        _signalled.clear()
        for p in (
            mock.patch("os.kill", _guarded_kill),
            mock.patch("os.killpg", side_effect=AssertionError("killpg called")),
            mock.patch.object(sv, "read_bot_token", lambda ref: "TEST_TOKEN"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _reap_bystander(self) -> None:
        if self.bystander.poll() is None:
            self.bystander.kill()
        self.bystander.wait()

    async def _supervisor(self) -> sv.Supervisor:
        sup = sv.Supervisor(self.config)
        await sup.sender.close()
        sup.sender = _FakeSender()
        return sup

    async def _start_run(self, sup, adapter):
        with mock.patch.object(sv, "make_adapter", lambda *a, **k: adapter):
            task = asyncio.create_task(sup._spawn_for_agent(self.spec, _event()))
            for _ in range(500):
                if sup.watchdog.all_runs():
                    break
                await asyncio.sleep(0.01)
        runs = sup.watchdog.all_runs()
        self.assertEqual(len(runs), 1, "run was never registered with the watchdog")
        return task, runs[0]

    def test_real_child_pid_recorded(self) -> None:
        async def scenario():
            sup = await self._supervisor()
            adapter = _SilentAdapter()
            task, wr = await self._start_run(sup, adapter)
            self.assertGreater(wr.pid, 1)
            self.assertEqual(wr.pid, adapter._proc.pid)
            self.assertEqual(sup.state.read_run(wr.run_id).pid, wr.pid)
            await sup._kill_expired_run(wr.run_id, wr.pid, "explicit_stop")
            await asyncio.wait_for(task, timeout=10)

        asyncio.run(scenario())

    def test_watchdog_trip_kills_only_that_child(self) -> None:
        async def scenario():
            sup = await self._supervisor()
            adapter = _SilentAdapter()
            task, wr = await self._start_run(sup, adapter)
            child = adapter._proc
            # Far in the future: 15 min of silence has passed.
            expired = sup.watchdog.expired_runs(now=wr.started_at + 10_000)
            self.assertEqual([(r.run_id, reason) for r, reason in expired],
                             [(wr.run_id, "silence")])
            for r, reason in expired:
                await sup._kill_expired_run(r.run_id, r.pid, reason)
            await asyncio.wait_for(task, timeout=10)
            return wr, child, sup

        wr, child, sup = asyncio.run(scenario())
        self.assertIsNotNone(child.returncode, "the agent's child is still running")
        self.assertEqual({pid for pid, _sig in _signalled}, {wr.pid})
        self.assertIsNone(self.bystander.poll(), "an unrelated process was signalled")
        run = sup.state.read_run(wr.run_id)
        self.assertEqual(run.status, "killed")
        self.assertEqual(run.kill_reason, "silence")
        self.assertEqual(len(sup.watchdog), 0)
        self.assertEqual(sup._run_adapters, {})

    def test_hard_timeout_recorded_as_timeout(self) -> None:
        async def scenario():
            sup = await self._supervisor()
            task, wr = await self._start_run(sup, _SilentAdapter())
            await sup._kill_expired_run(wr.run_id, wr.pid, "timeout")
            await asyncio.wait_for(task, timeout=10)
            return sup, wr

        sup, wr = asyncio.run(scenario())
        run = sup.state.read_run(wr.run_id)
        self.assertEqual(run.status, "timeout")
        self.assertEqual(run.kill_reason, "timeout")
        self.assertIsNone(self.bystander.poll())

    def test_stop_command_kills_only_that_child(self) -> None:
        async def scenario():
            sup = await self._supervisor()
            adapter = _SilentAdapter()
            task, wr = await self._start_run(sup, adapter)
            sup.registry = sv.AgentRegistry({"demo": self.spec})
            stop = dataclasses.replace(_event(), text="/stop @demo_bot", message_id=6)
            await sup._handle_stop_command(stop)
            await asyncio.wait_for(task, timeout=10)
            return sup, wr

        sup, wr = asyncio.run(scenario())
        self.assertEqual({pid for pid, _sig in _signalled}, {wr.pid})
        self.assertIsNone(self.bystander.poll())
        self.assertEqual(sup.state.read_run(wr.run_id).kill_reason, "explicit_stop")

    def test_kill_after_run_finished_sends_no_signal(self) -> None:
        # A late watchdog poll or /stop for a finished run must not signal
        # its old pid, which the OS may have handed to another process.
        async def scenario():
            sup = await self._supervisor()
            with mock.patch.object(sv, "make_adapter", lambda *a, **k: _QuickAdapter()):
                await sup._spawn_for_agent(self.spec, _event())
            (run,) = sup.state.list_runs()
            self.assertGreater(run.pid, 1)
            await sup._kill_expired_run(run.run_id, run.pid, "silence")
            return sup, run

        sup, run = asyncio.run(scenario())
        self.assertEqual(_signalled, [])
        self.assertEqual(sup.state.read_run(run.run_id).status, "success")

    def test_placeholder_pid_never_signalled(self) -> None:
        # Even with a live adapter, a bogus pid is refused, not broadcast.
        async def scenario():
            sup = await self._supervisor()
            adapter = _SilentAdapter()
            task, wr = await self._start_run(sup, adapter)
            with self.assertLogs("kb-multibot", level="ERROR"):
                for bogus in (-1, 0):
                    await sup._kill_expired_run(wr.run_id, bogus, "silence")
                    sup.watchdog.add(wr.run_id, "demo", pid=wr.pid)
            self.assertIsNone(adapter._proc.returncode)
            await sup._kill_expired_run(wr.run_id, wr.pid, "explicit_stop")
            await asyncio.wait_for(task, timeout=10)

        asyncio.run(scenario())
        self.assertNotIn(-1, {pid for pid, _sig in _signalled})
        self.assertIsNone(self.bystander.poll())

    def test_spawn_failure_leaves_no_watchdog_entry(self) -> None:
        # A missing claude binary used to leave a pid=-1 entry that tripped
        # 15 minutes later.
        async def scenario():
            sup = await self._supervisor()
            with mock.patch.object(sv, "make_adapter", lambda *a, **k: _MissingAdapter()):
                await sup._spawn_for_agent(self.spec, _event())
            return sup

        sup = asyncio.run(scenario())
        self.assertEqual(len(sup.watchdog), 0)
        self.assertEqual(sup._run_adapters, {})
        self.assertEqual(sup.watchdog.expired_runs(now=10**12), [])
        self.assertEqual(_signalled, [])
        runs = sup.state.list_runs()
        self.assertEqual([r.status for r in runs], ["failed"])


if __name__ == "__main__":
    unittest.main()
