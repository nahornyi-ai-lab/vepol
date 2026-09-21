"""Known-token probes and nesting detection.

Probe contract (spec): success = exit 0 AND the expected token present in
whitespace-normalized stdout. Exit 0 with empty stdout is a failure. A probe
never runs inside an agent session — the nesting markers below are the same
list Vepol Face strips in vepol_face/broker.py (SESSION_ENV_PREFIXES /
SESSION_ENV_EXACT; the hub cannot import Face, so the list is copied).

Every argv flag traces to ~/knowledge/solutions/cli-agent-runtime-launch.md:
codex needs `--skip-git-repo-check` (non-git hub dir), `--sandbox read-only`
and stdin /dev/null (open stdin hangs); agy needs `--add-dir`; grok takes a
prompt file, bounded turns and `--disable-web-search` for a non-live pass;
hermes uses `-z` (one-shot: prints only the final response) and
`--ignore-rules` (no AGENTS.md/SOUL.md/memory/skill injection from the hub
cwd), both verified live 2026-09-02 (`HERMES_OK`, rc 0, 7 s).
The Claude probe goes through $HUB/bin/kb-claude-run synchronously with no
wall-clock cap (hub hard rule for owned headless Claude launches).
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .observations import fmt_ts
from .paths import Paths
from .roster import RosterEntry

SESSION_ENV_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CODEX_COMPANION_")
SESSION_ENV_EXACT = (
    "CLAUDECODE",
    "CLAUDE_EFFORT",
    "CLAUDE_PLUGIN_DATA",
    "AI_AGENT",
    "ANTHROPIC_BASE_URL",
)

DEFAULT_TIMEOUT_SEC = 300.0
OPENCODE_MODEL_ENV = "KB_OPENCODE_PROBE_MODEL"
OPENCODE_MODEL_DEFAULT = "opencode/big-pickle"  # listed by `opencode models` 2026-08-27


def nesting_markers(env=None) -> List[str]:
    source = os.environ if env is None else env
    found = [k for k in source if k in SESSION_ENV_EXACT or k.startswith(SESSION_ENV_PREFIXES)]
    return sorted(found)


def _ask(token: str) -> str:
    return f"Reply with exactly the token {token} and nothing else."


@dataclass
class Launch:
    argv: List[str]
    cwd: Optional[str] = None
    timeout: Optional[float] = None  # None = no wall-clock cap
    cleanup: Optional[Callable[[], None]] = None


@dataclass
class ProbeSpec:
    runtime: str
    token: str
    build: Callable[[str, Paths, float], Launch]


def _claude(binary: str, paths: Paths, timeout: float) -> Launch:
    launcher = str(paths.claude_run)
    argv = [launcher, "--", binary, "-p", _ask("CLAUDE_OK"),
            "--output-format", "text", "--no-session-persistence"]
    return Launch(argv=argv, cwd=str(paths.hub), timeout=None)


def _codex(binary: str, paths: Paths, timeout: float) -> Launch:
    argv = [binary, "exec", "--skip-git-repo-check", "--sandbox", "read-only", _ask("CODEX_OK")]
    return Launch(argv=argv, cwd=str(paths.hub), timeout=timeout)


def _agy(binary: str, paths: Paths, timeout: float) -> Launch:
    argv = [binary, "--add-dir", str(paths.hub), "--print", _ask("AGY_OK"), "--print-timeout", "5m"]
    return Launch(argv=argv, cwd=str(paths.hub), timeout=timeout)


def _grok(binary: str, paths: Paths, timeout: float) -> Launch:
    fd, prompt_path = tempfile.mkstemp(prefix="kb-runtime-registry-grok-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(_ask("GROK_OK") + "\n")
    argv = [binary, "--cwd", str(paths.hub), "--prompt-file", prompt_path,
            "--output-format", "plain", "--permission-mode", "acceptEdits",
            "--max-turns", "3", "--no-subagents", "--no-memory", "--disable-web-search"]

    def cleanup() -> None:
        try:
            os.unlink(prompt_path)
        except OSError:
            pass

    return Launch(argv=argv, cwd=str(paths.hub), timeout=timeout, cleanup=cleanup)


def _opencode(binary: str, paths: Paths, timeout: float) -> Launch:
    model = os.environ.get(OPENCODE_MODEL_ENV) or OPENCODE_MODEL_DEFAULT
    argv = [binary, "run", "--dir", str(paths.hub), "-m", model, _ask("OPENCODE_OK")]
    return Launch(argv=argv, cwd=str(paths.hub), timeout=timeout)


def _hermes(binary: str, paths: Paths, timeout: float) -> Launch:
    argv = [binary, "-z", _ask("HERMES_OK"), "--ignore-rules"]
    return Launch(argv=argv, cwd=str(paths.hub), timeout=timeout)


PROBES: Dict[str, ProbeSpec] = {
    "claude": ProbeSpec("claude", "CLAUDE_OK", _claude),
    "codex": ProbeSpec("codex", "CODEX_OK", _codex),
    "agy": ProbeSpec("agy", "AGY_OK", _agy),
    "grok": ProbeSpec("grok", "GROK_OK", _grok),
    "opencode": ProbeSpec("opencode", "OPENCODE_OK", _opencode),
    "hermes": ProbeSpec("hermes", "HERMES_OK", _hermes),
}


@dataclass
class ProbeResult:
    runtime: str
    outcome: str  # success | failure | skipped
    reason: str
    observed_at: Optional[dt.datetime]
    rc: Optional[int] = None
    stdout_bytes: int = 0

    @property
    def evidence(self) -> str:
        rc = "n/a" if self.rc is None else str(self.rc)
        return f"probe {self.runtime} rc={rc} stdout_bytes={self.stdout_bytes}: {self.reason}"

    def as_cache_record(self) -> dict:
        return {
            "observed_at": fmt_ts(self.observed_at),
            "outcome": self.outcome,
            "reason": self.reason,
            "evidence": self.evidence,
            "rc": self.rc,
            "stdout_bytes": self.stdout_bytes,
        }

    def as_json(self) -> dict:
        return {
            "runtime": self.runtime,
            "outcome": self.outcome,
            "reason": self.reason,
            "observed_at": fmt_ts(self.observed_at),
        }


def normalize(stdout: bytes) -> str:
    return " ".join(stdout.decode("utf-8", errors="replace").split())


def probe_timeout() -> float:
    raw = os.environ.get("KB_RUNTIME_REGISTRY_PROBE_TIMEOUT")
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT_SEC
    except ValueError:
        return DEFAULT_TIMEOUT_SEC


def run_probe(entry: RosterEntry, paths: Paths, now: dt.datetime) -> ProbeResult:
    spec = PROBES.get(entry.name)
    if spec is None:
        return ProbeResult(entry.name, "skipped", "no probe defined for this runtime", None)
    if not entry.resolved:
        return ProbeResult(entry.name, "failure", "binary not installed", now)
    if entry.name == "claude" and not (paths.claude_run.is_file() and os.access(paths.claude_run, os.X_OK)):
        return ProbeResult(entry.name, "failure", f"launcher missing: {paths.claude_run}", now)

    launch = spec.build(entry.resolved, paths, probe_timeout())
    try:
        proc = subprocess.run(
            launch.argv,
            cwd=launch.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=launch.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(entry.name, "failure", f"timeout after {launch.timeout:.0f}s", now)
    except OSError as exc:
        return ProbeResult(entry.name, "failure", f"launch error: {exc}", now)
    finally:
        if launch.cleanup:
            launch.cleanup()

    out = proc.stdout or b""
    size = len(out)
    if proc.returncode != 0:
        return ProbeResult(entry.name, "failure", f"exit {proc.returncode}", now, proc.returncode, size)
    if not out.strip():
        return ProbeResult(entry.name, "failure", "empty stdout", now, proc.returncode, size)
    if spec.token not in normalize(out):
        return ProbeResult(entry.name, "failure", f"token {spec.token} missing from stdout", now,
                           proc.returncode, size)
    return ProbeResult(entry.name, "success", f"token {spec.token} present", now, proc.returncode, size)
