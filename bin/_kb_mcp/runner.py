"""McpHostRunner — single point of contact with the MCP host.

Hosts: `claude -p` first, `codex exec` as fallback when Claude cannot
answer at all (binary missing, usage limit, timeout, non-zero exit).
The class is shaped so a future host can be slotted in without
touching module code.

Spec: docs/methodology/mcp-first-sources.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
from typing import Callable, Optional

from _kb_claude_runner import run_command as run_unbounded_command

# ──────────────────────────────────────────────────────────────────
# Exceptions — three-way separation so callers can react usefully.
# ──────────────────────────────────────────────────────────────────


class McpHostError(Exception):
    """Subprocess-level failure: claude binary missing, exit non-zero,
    timeout, etc. The host itself didn't respond cleanly."""


class McpResponseError(Exception):
    """Envelope-validation failure: not JSON at all, structural
    schema violation, preamble before the JSON object, trailing
    non-whitespace after the JSON object."""


class McpToolError(Exception):
    """Envelope was structurally valid but signaled `ok: false`.
    The MCP tool reached us, but reported an upstream problem
    (auth missing, scope denied, network down on its side, etc.).

    Attributes:
        error:  short error code from the envelope (e.g. "auth_required")
        detail: human-readable elaboration
    """

    def __init__(self, error: str, detail: str):
        super().__init__(f"{error}: {detail}")
        self.error = error
        self.detail = detail


# ──────────────────────────────────────────────────────────────────
# Strict envelope parsing. Forgiving parsers turn failures into
# silent partial successes; every step here either accepts or fails.
# ──────────────────────────────────────────────────────────────────


def _strict_envelope_parse(stdout: str) -> dict:
    """Parse stdout as a single JSON object envelope. Reject any
    preamble or trailing non-whitespace.

    Returns the parsed dict on success.
    Raises McpResponseError on any structural problem.
    """
    text = stdout.strip()
    if not text:
        raise McpResponseError("empty response from host")
    if not text.startswith("{"):
        raise McpResponseError(
            "expected single JSON object, got non-JSON preamble; "
            f"first 200 chars: {text[:200]!r}"
        )
    try:
        envelope, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as e:
        raise McpResponseError(
            f"malformed JSON envelope: {e}; first 200 chars: {text[:200]!r}"
        )
    trailing = text[end:].strip()
    if trailing:
        raise McpResponseError(
            "trailing non-whitespace after JSON envelope; "
            f"first 200 chars: {trailing[:200]!r}"
        )
    if not isinstance(envelope, dict):
        raise McpResponseError(
            f"envelope is not a JSON object (got {type(envelope).__name__})"
        )
    if "ok" not in envelope:
        raise McpResponseError(
            f"envelope missing 'ok' field; keys: {list(envelope.keys())}"
        )
    return envelope


def _validate_success_envelope(envelope: dict) -> None:
    """Validate an `ok: true` envelope's required shape."""
    if not isinstance(envelope.get("items"), list):
        raise McpResponseError(
            f"ok=true envelope missing 'items' list; keys: {list(envelope.keys())}"
        )
    stats = envelope.get("stats")
    if not isinstance(stats, dict):
        raise McpResponseError(
            f"ok=true envelope missing 'stats' dict; keys: {list(envelope.keys())}"
        )
    for required in ("n_items", "fetched_at"):
        if required not in stats:
            raise McpResponseError(
                f"stats missing {required!r}; keys: {list(stats.keys())}"
            )


def _validate_failure_envelope(envelope: dict) -> None:
    """Validate an `ok: false` envelope's required shape."""
    for required in ("error", "detail"):
        if required not in envelope:
            raise McpResponseError(
                f"ok=false envelope missing {required!r}; keys: {list(envelope.keys())}"
            )


# ──────────────────────────────────────────────────────────────────
# The runner.
# ──────────────────────────────────────────────────────────────────


# A test-injectable callable: (prompt, timeout_s) -> stdout_text.
# Production default constructs this from `claude -p` subprocess.
RunnerFn = Callable[[str, int], str]


# Headless calls pin their own model: the interactive default can be a model
# whose usage limit is exhausted, and then `claude -p` exits rc=1 with the
# limit notice on stdout. Override with KB_MCP_MODEL.
DEFAULT_MODEL = "sonnet"


_FENCE_RE = re.compile(r"\A```[A-Za-z]*[ \t]*\n(.*)\n```\Z", re.DOTALL)


def _unfenced_json(stdout: str) -> str:
    """Return the JSON object text of a Claude reply, removing exactly one
    outer markdown fence if present. Anything else that is not a single JSON
    object raises McpHostError, so the caller still falls back to Codex."""
    text = stdout.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpHostError(
            f"claude -p returned no JSON object: {exc}; stdout tail: {text[-300:]!r}"
        ) from exc
    if not isinstance(value, dict):
        raise McpHostError("claude -p returned JSON that is not an object")
    return text


def _claude_runner(
    prompt: str, timeout_s: int, *, tolerate_fence: bool = False, extra_args=()
) -> str:
    """Run `claude -p <prompt>` and return stdout. Raises McpHostError
    on subprocess problems. ``timeout_s`` is retained for the public callable
    shape but never limits the Claude lane. With ``tolerate_fence`` the run
    uses text mode and one outer markdown fence is removed; the reply must
    still be a single JSON object. Non-empty ``extra_args`` (tool isolation)
    go before ``--`` so multi-value flags cannot swallow the prompt."""
    claude = shutil.which("claude")
    if claude is None:
        raise McpHostError(
            "claude binary not found in PATH; install Claude Code first "
            "(see docs/methodology/mcp-first-sources.md § Preflight)"
        )
    model = os.environ.get("KB_MCP_MODEL", DEFAULT_MODEL)
    env = None
    if extra_args:
        argv = [claude, "-p", "--model", model, *extra_args, "--", prompt]
        # --restricted skips settings and hooks, so the first turn can start
        # before the claude.ai connectors list their tools (some runs saw no
        # connector tools at all). Wait for MCP connections instead.
        env = {**os.environ, "MCP_CONNECTION_NONBLOCKING": "false"}
    else:
        argv = [claude, "-p", "--model", model, prompt]
    try:
        proc = run_unbounded_command(
            argv,
            cwd=os.getcwd(),
            output_mode="text" if tolerate_fence else "json",
            kind="claude",
            metadata={"caller": "_kb_mcp.runner"},
            env=env,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise McpHostError(f"claude durable runner failed: {exc}") from exc
    if proc.returncode != 0:
        # The limit/auth notice lands on stdout, not stderr — report both.
        raise McpHostError(
            f"claude -p (model={model}) exited rc={proc.returncode}; "
            f"stderr tail: {proc.stderr.strip()[-300:]!r}; "
            f"stdout tail: {proc.stdout.strip()[-300:]!r}"
        )
    if tolerate_fence:
        return _unfenced_json(proc.stdout)
    return proc.stdout


def _extract_envelope_text(text: str) -> Optional[str]:
    """Return the LAST balanced {...} object carrying an 'ok' key, re-serialized.

    Codex prints plugin guidance, tool traces and token counts around its answer,
    so its stdout is never a bare envelope. Scanning with a JSON decoder finds
    multi-line envelopes too, and the last valid one is Codex's final answer.
    Re-serializing keeps the strict parser downstream unchanged."""
    decoder = json.JSONDecoder()
    last = None
    i, n = 0, len(text)
    while i < n:
        if text[i] == "{":
            try:
                obj, end = decoder.raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            if isinstance(obj, dict) and "ok" in obj:
                last = obj
            i = max(end, i + 1)
        else:
            i += 1
    return None if last is None else json.dumps(last)


def _codex_runner(prompt: str, timeout_s: int, extra_args=()) -> str:
    """Fallback host: read-only `codex exec`. When Claude cannot answer, Codex
    takes the call rather than the pipeline losing the source. Codex carries
    its own `google-calendar` plugin, so it does not depend on the claude.ai
    connector or on Claude's usage limits."""
    import sys

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from _kb_codex import CodexUnavailable, codex_bin  # type: ignore
    except ImportError as e:
        raise McpHostError(f"codex fallback unavailable: {e}")
    try:
        binary = codex_bin()
    except CodexUnavailable as e:
        raise McpHostError(str(e))
    try:
        proc = subprocess.Popen(
            [binary, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
             *extra_args, prompt],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError:
        raise McpHostError("codex binary not found")
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        # Codex spawns MCP children; kill the whole group or they outlive us.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.communicate(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            pass
        raise McpHostError(f"codex exec timed out after {timeout_s}s")
    if proc.returncode != 0:
        raise McpHostError(
            f"codex exec exited rc={proc.returncode}; "
            f"stderr tail: {(stderr or '').strip()[-300:]!r}"
        )
    envelope = _extract_envelope_text(stdout)
    if envelope is None:
        raise McpHostError(
            f"codex exec returned no JSON envelope; stdout tail: {stdout.strip()[-300:]!r}"
        )
    return envelope


def _default_runner(
    prompt: str,
    timeout_s: int,
    *,
    tolerate_fence: bool = False,
    claude_args=(),
    codex_args=(),
    fallback: bool = True,
) -> str:
    """Claude first, Codex if Claude could not answer.

    Only host-level failures fall through: a Claude run that returns an
    envelope — including `ok: false` — is an answer, and re-asking Codex would
    double the work and the tokens for no new information. ``claude_args`` and
    ``codex_args`` are passed to their own lane unchanged. ``fallback=False``
    (or KB_MCP_NO_FALLBACK=1) never starts Codex: a caller that writes must
    not re-send a prompt after a host failure whose outcome is unknown."""
    try:
        return _claude_runner(
            prompt, timeout_s, tolerate_fence=tolerate_fence, extra_args=claude_args)
    except McpHostError as claude_error:
        if not fallback or os.environ.get("KB_MCP_NO_FALLBACK") == "1":
            raise
        try:
            return _codex_runner(prompt, timeout_s, codex_args)
        except McpHostError as codex_error:
            raise McpHostError(
                f"both hosts failed — claude: {claude_error}; codex: {codex_error}"
            )


class McpHostRunner:
    """Run a structured prompt via the MCP host and return its
    validated envelope.

    Production usage:
        runner = McpHostRunner()
        envelope = runner.call(prompt)
        for item in envelope["items"]:
            ...

    Test usage:
        runner = McpHostRunner(runner=fake_runner_fn)

    The `runner` parameter is the test-injectable subprocess
    replacement. It receives (prompt, timeout_s) and returns the
    stdout text the host would have produced.
    """

    def __init__(self, *, runner: Optional[RunnerFn] = None):
        self._runner: RunnerFn = runner if runner is not None else _default_runner

    def call(self, prompt: str, *, timeout_s: int = 120) -> dict:
        """Run prompt, return parsed envelope dict.

        On `ok: true`, returns the full envelope (caller reads
        `envelope["items"]`).

        On `ok: false`, raises McpToolError with `.error` and `.detail`.
        On structural problems, raises McpResponseError.
        On host problems (subprocess/timeout/missing binary), raises
        McpHostError.
        """
        stdout_text = self._runner(prompt, timeout_s)
        envelope = _strict_envelope_parse(stdout_text)
        ok = envelope.get("ok")
        if ok is True:
            _validate_success_envelope(envelope)
            return envelope
        if ok is False:
            _validate_failure_envelope(envelope)
            raise McpToolError(envelope["error"], envelope["detail"])
        raise McpResponseError(f"envelope.ok must be bool; got: {ok!r}")
