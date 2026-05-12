"""Tests for spawner.py — adapters use simple echo binaries for subprocess test."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.spawner import (  # noqa: E402
    BaseAdapter,
    ClaudeAdapter,
    CodexAdapter,
    SpawnFailed,
    make_adapter,
)


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


class FactoryTests(unittest.TestCase):
    def test_claude_factory(self) -> None:
        a = make_adapter("claude")
        self.assertIsInstance(a, ClaudeAdapter)

    def test_codex_factory(self) -> None:
        a = make_adapter("codex")
        self.assertIsInstance(a, CodexAdapter)

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
