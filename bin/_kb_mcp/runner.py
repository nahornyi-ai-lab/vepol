"""McpHostRunner — single point of contact with the MCP host.

v1 implementation: Claude Code only (`claude -p "<prompt>"`).
The class is shaped so a future host can be slotted in without
touching module code.

Spec: docs/methodology/mcp-first-sources.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable, Optional


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


def _default_runner(prompt: str, timeout_s: int) -> str:
    """Run `claude -p <prompt>` and return stdout. Raises McpHostError
    on subprocess problems."""
    claude = shutil.which("claude")
    if claude is None:
        raise McpHostError(
            "claude binary not found in PATH; install Claude Code first "
            "(see docs/methodology/mcp-first-sources.md § Preflight)"
        )
    try:
        proc = subprocess.run(
            [claude, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        raise McpHostError(f"claude -p timed out after {timeout_s}s")
    if proc.returncode != 0:
        raise McpHostError(
            f"claude -p exited rc={proc.returncode}; "
            f"stderr tail: {proc.stderr.strip()[-300:]!r}"
        )
    return proc.stdout


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
