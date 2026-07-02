"""CodexHostRunner — the mail reader's host is Codex, not `claude -p`.

Gmail is reachable from the background only through Codex's `gmail@openai-curated`
plugin (owner directive: "именно кодекс должен читать"). A headless `claude -p`
does not carry the claude.ai Gmail connector, so the mail ProductionBackend
spawns `codex exec` instead. Calendar keeps using _kb_mcp.McpHostRunner; only the
mail surface routes through Codex.

Codex stdout is noisy (plugin guidance, tool traces, token counts), so the
envelope is extracted leniently: the last JSON object carrying an `ok` key. The
call is read-only (`--sandbox read-only`) and stdin is closed so a headless run
never hangs waiting for EOF.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from .errors import MailUnavailable


def _codex_bin() -> str:
    return (os.environ.get("KB_CODEX_BIN")
            or shutil.which("codex")
            or "/Applications/Codex.app/Contents/Resources/codex")


def _is_envelope(obj) -> bool:
    """A well-formed result envelope — strict enough that a stray `{"ok": true}`
    example in Codex's guidance/trace is NOT mistaken for a real read. A success
    envelope MUST carry an items list; a failure envelope MUST carry an error."""
    if not isinstance(obj, dict) or "ok" not in obj:
        return False
    if obj["ok"] is True:
        return isinstance(obj.get("items"), list)
    if obj["ok"] is False:
        return bool(obj.get("error"))
    return False


def _extract_envelope(text: str):
    """Return the LAST well-formed result envelope embedded in noisy Codex output,
    or None. Uses a JSON decoder to scan for every balanced {...} object — so a
    MULTI-LINE / pretty-printed envelope is found, not just single-line ones — and
    validates each with _is_envelope, so a stray ok:true fragment is never latched
    onto as a real read. The last valid envelope wins (Codex's final answer)."""
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
            if _is_envelope(obj):
                last = obj
            i = max(end, i + 1)
        else:
            i += 1
    return last


class CodexHostRunner:
    """Same surface as _kb_mcp.McpHostRunner: `.call(prompt, timeout_s) -> dict`.

    ``runner`` is injectable for tests — a callable (prompt, timeout_s) -> stdout
    string — so the mail read/classify path can be exercised without spawning
    Codex or touching the network."""

    def __init__(self, *, runner=None):
        self._runner = runner

    def call(self, prompt: str, *, timeout_s: int = 120) -> dict:
        if self._runner is not None:
            out = self._runner(prompt, timeout_s)  # test seam: trusted stdout
        else:
            try:
                proc = subprocess.run(
                    [_codex_bin(), "exec", "--skip-git-repo-check",
                     "--sandbox", "read-only", prompt],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired:
                raise MailUnavailable(f"codex timeout after {timeout_s}s")
            except FileNotFoundError:
                raise MailUnavailable("codex binary not found")
            except Exception as e:  # pragma: no cover - subprocess wiring
                raise MailUnavailable(f"codex host error: {e}")
            # A non-zero exit means the read did not complete — never try to
            # salvage a "success" envelope from a failed run.
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                raise MailUnavailable(
                    f"codex exited {proc.returncode}: {(tail[-1] if tail else '')[:120]}"
                )
            out = proc.stdout
        env = _extract_envelope(out)
        if env is None:
            raise MailUnavailable("codex returned no valid JSON envelope")
        return env
