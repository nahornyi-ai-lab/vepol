"""Adapter over kb-orchestrator-run.

Two rules this module exists to enforce:
  * consume the broker's structured --json-status result, never parse stdout;
  * exit code 0 is not an answer. A run that returns nothing is degraded.
    (Verified live 2026-08-15: `claude -p` returned rc 0 with zero output.)
"""
from __future__ import annotations

import json
import os
import pathlib
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass

BROKER = pathlib.Path(
    os.environ.get("VEPOL_FACE_BROKER", os.path.expanduser("~/knowledge/bin/kb-orchestrator-run"))
)
RUNS_DIR = pathlib.Path(os.path.expanduser("~/knowledge/.orchestrator/runs"))
BROKER_RUNTIMES = ("claude", "codex")

FAILURE_CATEGORIES = {
    "rate_limit", "auth", "network", "timeout",
    "code_error", "crash", "other", "unavailable",
}


class UnknownRuntime(ValueError):
    """Raised when a runtime is not a broker backend."""


# Markers of an *active* agent session. They identify the parent session and
# must never be inherited by a runtime Vepol Face spawns: a child that inherits
# them behaves as a nested session (verified 2026-08-15 — a nested `claude -p`
# hung indefinitely or exited 0 with no output). Vepol Face may be launched
# from inside an agent, so it always hands the broker a clean environment.
SESSION_ENV_PREFIXES = (
    "CLAUDE_CODE_",
    "CLAUDE_AGENT_SDK_",
    "CODEX_COMPANION_",
)
SESSION_ENV_EXACT = (
    "CLAUDECODE",
    "CLAUDE_EFFORT",
    "CLAUDE_PLUGIN_DATA",
    "AI_AGENT",
    "ANTHROPIC_BASE_URL",
)


def clean_env(base: dict | None = None) -> dict:
    """Environment with the parent agent-session markers removed."""
    env = dict(base if base is not None else os.environ)
    for key in list(env):
        if key in SESSION_ENV_EXACT or key.startswith(SESSION_ENV_PREFIXES):
            env.pop(key, None)
    return env


@dataclass
class Verdict:
    ok: bool
    degraded: bool
    reason: str
    category: str | None = None
    text: str = ""
    lane: str = "broker"      # broker | direct
    lane_note: str = ""       # why the lane changed, when it did
    stderr_seen: bool = False  # the runtime wrote a diagnosis to stderr


def is_silent_failure(v: "Verdict") -> bool:
    """A failure that told us nothing: unclassified, no text, no diagnosis.

    This is the shape the hub broker produced on 2026-08-15 — claude exited 65
    with zero bytes on both streams and the broker reported `other`. It is the
    one failure worth retrying on a different lane, because it carries no
    evidence that the runtime itself refused.

    Stderr counts as evidence. A runtime that printed a specific complaint has
    refused for a reason a second lane will hit too, so retrying only spends
    another call and stacks a second, unrelated error on the first.
    """
    return (
        not v.ok
        and v.category in (None, "other")
        and not v.text.strip()
        and not v.stderr_seen
    )


def interpret_result(
    returncode: int, stdout: str, stderr: str, category: str | None
) -> Verdict:
    text = (stdout or "").strip()
    loud = bool((stderr or "").strip())

    if category in FAILURE_CATEGORIES:
        return Verdict(False, True, _explain(category, stderr), category, text,
                       stderr_seen=loud)

    if returncode != 0:
        return Verdict(
            False, True,
            f"runtime exited {returncode} without a recognised category"
            + (f": {stderr.strip()[:200]}" if loud else " and no stderr"),
            category or "other", text, stderr_seen=loud,
        )

    if not text:
        return Verdict(
            False, True,
            "runtime exited 0 but returned empty output — treated as a failure, "
            "not as an answer",
            "empty_success", "",
        )

    return Verdict(True, False, "ok", category or "ok", text)


def _explain(category: str, stderr: str) -> str:
    human = {
        "rate_limit": "rate limited",
        "auth": "not authenticated, or account-level usage cap reached",
        "network": "network failure",
        "timeout": "timed out",
        "code_error": "runtime reported a code error",
        "crash": "runtime crashed",
        "unavailable": "runtime binary unavailable",
        "other": "unclassified failure",
    }.get(category, category)
    tail = stderr.strip()[:200]
    return f"{human}{': ' + tail if tail else ''}"


def resume_key(conversation_id: str, target_slug: str, runtime: str) -> str:
    return f"vepol-face:{conversation_id}:{target_slug}:{runtime}"


def build_broker_argv(
    prompt: str, cwd: str, resume_key: str, runtime: str, run_id: str
) -> list[str]:
    if runtime not in BROKER_RUNTIMES:
        raise UnknownRuntime(
            f"{runtime!r} is not a broker backend; expected one of {BROKER_RUNTIMES}"
        )
    # No --timeout: the Claude lane is owned by the durable detached runner and
    # must wait for natural exit.
    return [
        str(BROKER),
        "--backend", runtime,
        "--cwd", str(cwd),
        "--resume-key", resume_key,
        "--json-status",
        "--run-id", run_id,
        prompt,
    ]


def new_run_id() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------- stop support
# MVP-10: a running turn must be stoppable. Every lane subprocess is
# registered under the Face run id while it runs; `stop_face_run` terminates
# its whole process group.

@dataclass
class _Active:
    proc: subprocess.Popen | None = None
    stopped: bool = False


_ACTIVE: dict[str, _Active] = {}
_ACTIVE_LOCK = threading.Lock()


def begin_face_run(face_run_id: str) -> None:
    """Register stop intent tracking for a run *before* any subprocess exists.

    Caught by the 2026-08-20 live smoke: the KB snapshot that precedes the
    subprocess can take ~10s on the hub target, and a stop issued in that
    window found nothing to kill. The entry lives from the API call until
    `execute` finishes, so a stop at any point either kills the process or
    prevents it from launching.
    """
    with _ACTIVE_LOCK:
        _ACTIVE.setdefault(face_run_id, _Active())


def end_face_run(face_run_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.pop(face_run_id, None)


@dataclass
class ExecOut:
    returncode: int
    stdout: str
    stderr: str


def _execute_argv(
    argv: list[str], cwd: str, env: dict, face_run_id: str | None = None,
) -> "Verdict | ExecOut":
    """Run one lane subprocess, registered for stop while it runs.

    Returns ExecOut on natural exit, or a `stopped` Verdict when
    `stop_face_run` killed it. `start_new_session` puts the child in its own
    process group so the stop reaches grandchildren too.
    """
    created_here = False
    entry: _Active | None = None
    if face_run_id:
        with _ACTIVE_LOCK:
            entry = _ACTIVE.get(face_run_id)
            if entry is None:
                entry = _Active()
                _ACTIVE[face_run_id] = entry
                created_here = True
            if entry.stopped:
                if created_here:
                    _ACTIVE.pop(face_run_id, None)
                return Verdict(
                    False, False, "stopped by user before the runtime started",
                    "stopped", "",
                )

    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=cwd, env=env, stdin=subprocess.DEVNULL, start_new_session=True,
    )
    if entry is not None:
        with _ACTIVE_LOCK:
            entry.proc = proc
            stopped_in_window = entry.stopped
        if stopped_in_window:
            # A stop landed between the launch decision and the proc attach —
            # kill what just started so the intent is honoured.
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    try:
        stdout, stderr = proc.communicate()
    finally:
        if entry is not None:
            with _ACTIVE_LOCK:
                entry.proc = None
                if created_here:
                    _ACTIVE.pop(face_run_id, None)
    if entry is not None and entry.stopped:
        return Verdict(
            False, False, "stopped by user before the runtime finished",
            "stopped", (stdout or "").strip(),
        )
    return ExecOut(proc.returncode, stdout or "", stderr or "")


def stop_face_run(face_run_id: str) -> bool:
    """Stop a Face run: kill its subprocess if one is live, or mark the intent
    so a not-yet-launched subprocess never starts. True if the run was hit."""
    with _ACTIVE_LOCK:
        entry = _ACTIVE.get(face_run_id)
        if entry is None:
            return False
        entry.stopped = True
        proc = entry.proc
    if proc is None or proc.poll() is not None:
        return True  # intent recorded; nothing live to kill
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    # Escalate if the group ignores SIGTERM.
    def _force_kill():
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    threading.Timer(5.0, _force_kill).start()
    return True


def read_json_status(run_id: str, runs_dir: pathlib.Path | None = None) -> dict:
    path = (runs_dir or RUNS_DIR) / f"{run_id}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


CLI_BINARIES = {
    "claude": os.environ.get("VEPOL_FACE_CLAUDE_BIN", "claude"),
    "codex": os.environ.get("VEPOL_FACE_CODEX_BIN", os.path.expanduser("~/.local/bin/codex")),
}
DEFAULT_CLAUDE_MODEL = os.environ.get("VEPOL_FACE_CLAUDE_MODEL", "claude-opus-4-7")


def direct_lane_carries_history(runtime: str) -> bool:
    """Whether the direct lane for this runtime continues the conversation.

    Claude accepts a caller-chosen `--session-id`, so the direct lane resumes
    the same thread the broker used. Codex mints its own session id and only
    resumes by that id, which the direct lane never learns — so a direct codex
    turn is a fresh, historyless run and must be surfaced as one (MVP-2).
    """
    return runtime == "claude"


def build_direct_argv(prompt: str, runtime: str, session_id: str | None) -> list[str]:
    """Call the CLI itself, without the durable-runner wrapper."""
    if runtime not in CLI_BINARIES:
        raise UnknownRuntime(f"{runtime!r} has no direct lane")
    if runtime == "claude":
        argv = [CLI_BINARIES["claude"], "-p", prompt, "--model", DEFAULT_CLAUDE_MODEL]
        if session_id:
            argv += ["--session-id", session_id]
        return argv
    # Vepol targets are knowledge trees, not git repos: without
    # --skip-git-repo-check codex exits 1 before doing any work.
    return [CLI_BINARIES["codex"], "exec", prompt, "--skip-git-repo-check"]


def _stable_session_id(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vepol-face/{key}"))


def run_broker_lane(
    prompt: str, cwd: str, key: str, runtime: str,
    runs_dir: pathlib.Path | None = None,
    face_run_id: str | None = None,
) -> Verdict:
    run_id = new_run_id()
    argv = build_broker_argv(prompt, cwd, key, runtime, run_id)
    try:
        res = _execute_argv(argv, cwd, clean_env(), face_run_id)
    except OSError as exc:
        return Verdict(False, True, f"could not launch broker: {exc}", "unavailable", "")
    if isinstance(res, Verdict):
        res.lane = "broker"
        return res

    status = read_json_status(run_id, runs_dir)
    verdict = interpret_result(
        status.get("returncode", res.returncode),
        status.get("output") or res.stdout or "",
        status.get("stderr") or res.stderr or "",
        status.get("category"),
    )
    verdict.lane = "broker"
    return verdict


def run_direct_lane(
    prompt: str, cwd: str, key: str, runtime: str,
    face_run_id: str | None = None,
) -> Verdict:
    try:
        res = _execute_argv(
            build_direct_argv(prompt, runtime, _stable_session_id(key)),
            cwd, clean_env(), face_run_id,
        )
    except OSError as exc:
        v = Verdict(False, True, f"could not launch {runtime}: {exc}", "unavailable", "")
        v.lane = "direct"
        return v
    if isinstance(res, Verdict):
        res.lane = "direct"
        return res

    verdict = interpret_result(res.returncode, res.stdout, res.stderr, None)
    verdict.lane = "direct"
    return verdict


def execute(
    prompt: str, cwd: str, conversation_id: str, target_slug: str, runtime: str,
    runs_dir: pathlib.Path | None = None,
    lane: str | None = None,
    face_run_id: str | None = None,
) -> Verdict:
    """Run one turn and interpret it. Never raises on runtime failure.

    Lanes: `broker` (default, the spec's integration point), `direct` (the CLI
    without the durable-runner wrapper), `auto` (broker, then direct once if the
    broker fails silently). The chosen lane is always reported, never hidden.
    """
    lane = lane or os.environ.get("VEPOL_FACE_LANE", "auto")
    key = resume_key(conversation_id, target_slug, runtime)
    if face_run_id:
        begin_face_run(face_run_id)
    try:
        if lane == "direct":
            return run_direct_lane(prompt, cwd, key, runtime, face_run_id)

        verdict = run_broker_lane(prompt, cwd, key, runtime, runs_dir, face_run_id)
        if verdict.category == "stopped" or lane != "auto" or not is_silent_failure(verdict):
            return verdict

        first_reason = verdict.reason
        retried = run_direct_lane(prompt, cwd, key, runtime, face_run_id)
        retried.lane_note = f"broker lane failed silently ({first_reason}); retried direct"
        if not direct_lane_carries_history(runtime):
            retried.lane_note += (
                f" — the direct {runtime} lane starts a fresh session, "
                "so this answer does not see earlier turns"
            )
        if not retried.ok:
            retried.reason = f"{retried.reason} — after: {first_reason}"
        return retried
    finally:
        if face_run_id:
            end_face_run(face_run_id)
