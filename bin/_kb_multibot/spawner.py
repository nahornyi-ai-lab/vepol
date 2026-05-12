"""Subprocess spawning — ClaudeAdapter (via kb-spawn-project) and CodexAdapter.

Concept §16: ClaudeAdapter — thin async wrapper around existing `kb-spawn-project`
(не re-implement аргументной логики claude -p). CodexAdapter — direct subprocess
to `codex exec` (no existing wrapper).

Both adapters share the same async interface so supervisor doesn't care which
runtime an agent uses. They take prompt text + workdir + agent_slug + run_id,
return SpawnResult with stdout, exit code, parsed JSON.

stdout is streamed incrementally so watchdog.touch() can be called on each
chunk — keeping the silence-detector honest.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Callable


@dataclasses.dataclass
class SpawnResult:
    """Outcome of one agent invocation."""

    run_id: str
    agent_slug: str
    exit_code: int
    stdout: str
    stderr: str
    parsed: dict | None  # parsed JSON from stdout if `--output-format json`, else None
    killed: bool = False
    kill_reason: str | None = None  # "silence" | "timeout" | "explicit_stop"
    duration_sec: float = 0.0


class SpawnFailed(Exception):
    """Raised when subprocess could not be started (binary missing, etc.)."""


# StdoutCallback — invoked on each chunk read; supervisor passes watchdog.touch.
StdoutCallback = Callable[[str], None]


def _claude_path() -> str | None:
    """Locate `claude` CLI — prefer Homebrew native binary over nvm.

    Order of preference:
      1. /opt/homebrew/bin/claude — native binary 2.x, no node version issues
      2. /usr/local/bin/claude    — Intel-mac Homebrew
      3. shutil.which("claude")   — PATH-resolved (may pick stale nvm version)
      4. nvm fallback             — older 0.2.x, may have node-version issues
    """
    for cand in (
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    fp = shutil.which("claude")
    if fp:
        return fp
    cand = Path.home() / ".nvm" / "versions" / "node" / "v18.20.4" / "bin" / "claude"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    return None


def _codex_path() -> str | None:
    """Locate `codex` CLI."""
    fp = shutil.which("codex")
    if fp:
        return fp
    for cand in (
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


class BaseAdapter:
    """Common spawn helper — handles process lifecycle + streamed stdout.

    Subclasses provide `_argv(prompt_file, workdir, agent_slug, run_id, **kw)`
    returning the subprocess command vector.
    """

    name: str = "base"

    async def spawn(
        self,
        *,
        run_id: str,
        agent_slug: str,
        workdir: str,
        prompt: str,
        on_stdout_chunk: StdoutCallback | None = None,
        env: dict[str, str] | None = None,
    ) -> SpawnResult:
        argv = self._argv_with_prompt(prompt, workdir, agent_slug, run_id)
        if argv is None:
            raise SpawnFailed(f"{self.name}: cannot resolve binary")

        loop = asyncio.get_event_loop()
        start = loop.time()

        # tmp prompt file — agents see prompt content via stdin or arg
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".prompt", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_path = f.name

        try:
            # Substitute placeholder in argv with actual prompt file
            argv = [a.replace("{PROMPT_FILE}", prompt_path) for a in argv]

            proc_env = os.environ.copy()
            if env:
                proc_env.update(env)

            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workdir,
                env=proc_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []

            async def read_stream(stream, sink: list[str], on_chunk: StdoutCallback | None):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    sink.append(decoded)
                    if on_chunk:
                        try:
                            on_chunk(decoded)
                        except Exception:
                            # Watchdog touch failure must not break process
                            pass

            await asyncio.gather(
                read_stream(proc.stdout, stdout_chunks, on_stdout_chunk),
                read_stream(proc.stderr, stderr_chunks, None),
            )
            exit_code = await proc.wait()
            duration = loop.time() - start

            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)
            parsed = self._try_parse_json(stdout)

            return SpawnResult(
                run_id=run_id,
                agent_slug=agent_slug,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                parsed=parsed,
                duration_sec=duration,
            )
        finally:
            try:
                os.unlink(prompt_path)
            except OSError:
                pass

    async def kill(self, pid: int, *, escalate_after: float = 5.0) -> None:
        """SIGTERM, wait `escalate_after` seconds, then SIGKILL if still alive.

        Concept §7.4: kill-switch + watchdog-trip — SIGTERM → 5s → SIGKILL.
        """
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        await asyncio.sleep(escalate_after)
        try:
            os.kill(pid, 0)
            # Still alive — escalate
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    @staticmethod
    def _try_parse_json(stdout: str) -> dict | None:
        """Attempt to parse `--output-format json` envelope from claude -p."""
        if not stdout.strip():
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # Maybe last line is the JSON envelope; try line-by-line from end
            for line in reversed(stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return None

    def _argv_with_prompt(
        self, prompt: str, workdir: str, agent_slug: str, run_id: str
    ) -> list[str] | None:
        raise NotImplementedError


class ClaudeAdapter(BaseAdapter):
    """Direct `claude -p` invocation — Phase 1 simplification.

    Spawns `claude -p` directly so the agent picks up its project's
    CLAUDE.md, skills, hooks, and MCP config from cwd. Session-id caching
    (warm resume) is supported via `--resume` when `warm_session=True`
    in the agent's `.orchestration.yaml`.
    """

    name = "claude"

    def __init__(self, *, resume_session_id: str | None = None) -> None:
        self.resume_session_id = resume_session_id

    def _argv_with_prompt(
        self, prompt: str, workdir: str, agent_slug: str, run_id: str
    ) -> list[str] | None:
        binary = _claude_path()
        if not binary:
            return None
        # Newer claude 2.x: --output-format json gives {result, session_id, ...}
        # Older 0.2.x: --json gives {result, cost_usd}. Newer flag is forward-
        # compatible and what the current binary accepts.
        argv = [binary, "-p", prompt, "--output-format", "json"]
        if self.resume_session_id:
            argv += ["--resume", self.resume_session_id]
        return argv


class CodexAdapter(BaseAdapter):
    """Direct subprocess to `codex exec` — concept §16."""

    name = "codex"

    def _argv_with_prompt(
        self, prompt: str, workdir: str, agent_slug: str, run_id: str
    ) -> list[str] | None:
        binary = _codex_path()
        if not binary:
            return None
        # codex exec reads prompt from a CLI arg; pass directly.
        return [binary, "exec", prompt]


def make_adapter(runtime: str, **kw) -> BaseAdapter:
    """Factory for use in supervisor: pick adapter by agent's `runtime` field."""
    if runtime == "claude":
        return ClaudeAdapter(**kw)
    elif runtime == "codex":
        return CodexAdapter(**kw)
    raise ValueError(f"unknown runtime: {runtime!r}")


__all__ = [
    "BaseAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "SpawnResult",
    "SpawnFailed",
    "make_adapter",
]
