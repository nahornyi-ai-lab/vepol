"""Title and last message of a Claude terminal session, read from Claude's own files.

Display only: nothing here writes to Claude's files or affects how a session starts.
Every failure returns None so a board request never breaks on it.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading

_cache: dict[str, tuple[tuple[int, int], dict]] = {}
_lock = threading.Lock()


def claude_home() -> pathlib.Path:
    home = os.environ.get("VEPOL_AGENT_HOME_CLAUDE") or os.environ.get("VEPOL_CLAUDE_HOME")
    return pathlib.Path(home or pathlib.Path.home() / ".claude")


def session_for_pid(pid: int | None) -> str | None:
    """The Claude session id of a running agent process, from ~/.claude/sessions/<PID>.json."""
    if not pid:
        return None
    try:
        blob = json.loads((claude_home() / "sessions" / f"{int(pid)}.json").read_text())
    except (OSError, ValueError, TypeError):
        return None
    sid = blob.get("sessionId") if isinstance(blob, dict) else None
    return sid if isinstance(sid, str) and sid else None


def _transcript(session_id: str) -> pathlib.Path | None:
    if not session_id or "/" in session_id or session_id.startswith("."):
        return None
    try:
        return next((claude_home() / "projects").glob(f"*/{session_id}.jsonl"), None)
    except OSError:
        return None


def _prompt(record: dict) -> str | None:
    """A prompt the owner typed: plain string content, not a meta/command/hook wrapper."""
    if record.get("isMeta"):
        return None
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, str):
        return None
    text = content.strip()
    return text if text and not text.startswith("<") else None


def _assistant_text(record: dict) -> str | None:
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, list):
        return None
    parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    text = "\n".join(p for p in parts if p).strip()
    return text or None


def _parse(path: pathlib.Path) -> dict:
    custom = ai = first = last = None
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            kind = record.get("type")
            if kind == "custom-title" and record.get("customTitle"):
                custom = str(record["customTitle"])
            elif kind == "ai-title" and record.get("aiTitle"):
                ai = str(record["aiTitle"])
            elif kind == "user":
                text = _prompt(record)
                if text:
                    first = first or text
                    last = text
            elif kind == "assistant":
                text = _assistant_text(record)
                if text:
                    last = text
    title = custom or ai or (first.splitlines()[0][:60] if first else None)
    return {"title": title, "preview": last[:200] if last else None}


def read(session_id: str | None) -> dict | None:
    """{"title", "preview"} for a Claude session, or None when nothing can be read."""
    try:
        path = _transcript(session_id or "")
        if path is None:
            return None
        st = path.stat()
        key = (st.st_size, st.st_mtime_ns)
        with _lock:
            hit = _cache.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
        info = _parse(path)
        with _lock:
            _cache[str(path)] = (key, info)
        return info
    except OSError:
        return None
