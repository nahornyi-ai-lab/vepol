"""Subprocess spawning — ClaudeAdapter and CodexAdapter.

ClaudeAdapter runs `claude -p <prompt> --output-format json` directly in the
agent's workdir (it does not go through `kb-spawn-project`). CodexAdapter runs
`codex exec <prompt>` directly.

Both adapters share the same async interface so supervisor doesn't care which
runtime an agent uses. They take prompt text + workdir + agent_slug + run_id,
return SpawnResult with stdout, exit code, parsed JSON.

stdout is streamed incrementally so watchdog.touch() can be called on each
chunk — keeping the silence-detector honest.

The child's real pid is reported through `on_started` as soon as the process
exists, so the supervisor can watch and, if needed, stop exactly that process.
Children run in the supervisor's process group (no new session), so only the
child pid itself is ever signalled — never a group, never pid <= 1.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Callable

from _kb_codex import CodexUnavailable, codex_bin


logger = logging.getLogger("kb-multibot")


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
# StartedCallback — invoked once with the child's real pid right after start.
StartedCallback = Callable[[int], None]


def _refuse_signal(pid: object) -> bool:
    """True (and an error is logged) when `pid` must never be signalled.

    os.kill(-1, ...) signals every process the user owns, os.kill(0, ...) the
    whole process group, other negative values a group, and 1 is launchd.
    The supervisor itself and its parent are never valid targets either.
    """
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 1
        or pid in (os.getpid(), os.getppid())
    ):
        logger.error("refusing to signal pid=%r: not a spawned agent process", pid)
        return True
    return False


def _executable(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if p.is_file() and os.access(p, os.X_OK):
        return str(p)
    return None


def _claude_path() -> str | None:
    """Locate the `claude` CLI; the first executable hit wins.

    Order (shared with the rest of Vepol):
      1. $KB_CLAUDE_BIN
      2. `claude` on the current PATH
      3. ~/.local/bin/claude      — native installer; not on launchd's PATH
      4. /opt/homebrew/bin/claude — Apple-silicon Homebrew
      5. /usr/local/bin/claude    — Intel-mac Homebrew
      6. legacy nvm install       — older 0.2.x, may have node-version issues
    """
    for cand in (
        os.environ.get("KB_CLAUDE_BIN", "").strip(),
        shutil.which("claude"),
        Path.home() / ".local" / "bin" / "claude",
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        Path.home() / ".nvm" / "versions" / "node" / "v18.20.4" / "bin" / "claude",
    ):
        found = _executable(cand)
        if found:
            return found
    return None


def _codex_path() -> str | None:
    """Resolve the one production Codex CLI."""
    try:
        return codex_bin()
    except CodexUnavailable:
        return None


class BaseAdapter:
    """Common spawn helper — handles process lifecycle + streamed stdout.

    Subclasses provide `_argv(prompt_file, workdir, agent_slug, run_id, **kw)`
    returning the subprocess command vector.
    """

    name: str = "base"
    # The live child while spawn() runs; kill() signals through this handle,
    # which refuses to signal once the child has been reaped (no pid reuse).
    _proc: asyncio.subprocess.Process | None = None

    async def spawn(
        self,
        *,
        run_id: str,
        agent_slug: str,
        workdir: str,
        prompt: str,
        on_stdout_chunk: StdoutCallback | None = None,
        env: dict[str, str] | None = None,
        on_started: StartedCallback | None = None,
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
                # codex exec >=0.138 blocks forever reading an inherited open
                # stdin (waits for EOF); always hand children a closed stdin.
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._proc = proc
            if on_started is not None:
                try:
                    on_started(proc.pid)
                except BaseException:
                    # Never leave a child running that nobody watches.
                    proc.kill()
                    await proc.wait()
                    raise

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
            self._proc = None
            try:
                os.unlink(prompt_path)
            except OSError:
                pass

    async def kill(self, pid: int, *, escalate_after: float = 5.0) -> bool:
        """SIGTERM, wait up to `escalate_after` seconds, then SIGKILL if still alive.

        Concept §7.4: kill-switch + watchdog-trip — SIGTERM → 5s → SIGKILL.

        Only the single process `pid` is signalled. pid <= 1, the supervisor
        itself and its parent are refused with a logged error and False is
        returned (os.kill(-1) would signal every process the user owns).
        When `pid` is the child this adapter is running, the asyncio process
        handle is used, so a child that has already exited (and whose pid
        may be reused) is never signalled.
        """
        if _refuse_signal(pid):
            return False
        proc = self._proc
        if proc is not None and proc.pid == pid:
            if proc.returncode is not None:
                return True
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                return True
            try:
                await asyncio.wait_for(proc.wait(), timeout=escalate_after)
                return True
            except asyncio.TimeoutError:
                pass
            try:
                proc.send_signal(signal.SIGKILL)
            except ProcessLookupError:
                pass
            return True

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        await asyncio.sleep(escalate_after)
        try:
            os.kill(pid, 0)
            # Still alive — escalate
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return True

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
        # The supervisor passes resume_session_id for every runtime; codex
        # has no warm resume here, so drop it instead of a TypeError.
        kw.pop("resume_session_id", None)
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
