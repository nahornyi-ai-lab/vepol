"""Title and last message of any terminal agent's session, read from the agent's own local store.

One call, card(), dispatches to a reader per runtime. Each reader finds the agent's session for this
terminal (by process id for Claude; by folder + process start time for the others) and returns its id so
the conversation keeps it after the agent exits. Display only: stores are opened read-only and never
written. Every failure returns None so a board request never breaks on it.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.parse

from . import claude_titles

# A session row may be stamped slightly before `ps` reports the process start.
_SLACK_MS = 5000

_DEFAULT_HOMES = {
    "codex": "~/.codex",
    "grok": "~/.grok",
    "agy": "~/.gemini/antigravity-cli",
    "hermes": "~/.hermes",
    "opencode": "~/.local/share/opencode",
}

_cache: dict[tuple, tuple[tuple, object]] = {}
_lock = threading.Lock()


def home(agent: str) -> pathlib.Path:
    override = os.environ.get(f"VEPOL_AGENT_HOME_{agent.upper()}")
    return pathlib.Path(override) if override else pathlib.Path(_DEFAULT_HOMES[agent]).expanduser()


def process_start_ms(pid: int | None) -> int | None:
    """Start time of a process in epoch ms, from `ps -o lstart=` (local time)."""
    if not pid:
        return None
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))], capture_output=True, text=True,
                             timeout=5, env={**os.environ, "LC_ALL": "C"}).stdout.strip()
        return int(time.mktime(time.strptime(" ".join(out.split()), "%a %b %d %H:%M:%S %Y")) * 1000)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _stamp(*paths: pathlib.Path) -> tuple:
    stamp = []
    for path in paths:
        try:
            st = path.stat()
            stamp.append((st.st_size, st.st_mtime_ns))
        except OSError:
            stamp.append(None)
    return tuple(stamp)


def _cached(key: tuple, files: list[pathlib.Path], compute):
    """compute() once per change of the files' size + mtime."""
    stamp = _stamp(*files)
    with _lock:
        hit = _cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    value = compute()
    with _lock:
        _cache[key] = (stamp, value)
    return value


def _query(db: pathlib.Path, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    """Rows from a store opened read-only; if that fails, from a throwaway copy of db + wal + shm."""
    def run(path: pathlib.Path) -> list[sqlite3.Row]:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    if not db.is_file():
        return []
    files = [db, db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")]

    def compute() -> list[sqlite3.Row]:
        try:
            return run(db)
        except sqlite3.Error:
            pass
        with tempfile.TemporaryDirectory() as tmp:
            for src in files:
                if src.exists():
                    shutil.copy2(src, pathlib.Path(tmp) / src.name)
            return run(pathlib.Path(tmp) / db.name)

    return _cached(("sql", str(db), sql, args), files, compute)


def _folders(cwd: str) -> list[str]:
    folders = [cwd.rstrip("/") or "/"]
    try:
        real = os.path.realpath(cwd)
    except OSError:
        real = cwd
    if real not in folders:
        folders.append(real)
    return folders


def _short(text, limit: int) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()[:limit]


def _first_line(text) -> str | None:
    text = _short(text, 10_000)
    return text.splitlines()[0][:60] if text else None


def _iso_ms(value) -> int | None:
    try:
        return int(_dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _pick(candidates: list[dict], start_ms: int | None, known_id: str | None, claimed: set[str]) -> dict | None:
    """The known session while it still fits this process, else the unclaimed one nearest after the start.

    Each candidate: {"id", "created" (epoch ms or None), ...}.
    """
    floor = start_ms - _SLACK_MS if start_ms is not None else None
    by_id = {c["id"]: c for c in candidates}
    known = by_id.get(known_id) if known_id else None
    if known and (floor is None or (known["created"] or 0) >= floor):
        return known
    if floor is None:
        return known
    fresh = [c for c in candidates
             if c["id"] not in claimed and c["created"] is not None and c["created"] >= floor]
    fresh.sort(key=lambda c: c["created"])
    return fresh[0] if fresh else known


# --- readers: (pid, cwd, known_id, claimed) -> {"id", "title", "preview"} | None ---


def _claude(pid, cwd, known_id, claimed):
    sid = claude_titles.session_for_pid(pid) or known_id
    if not sid:
        return None
    info = claude_titles.read(sid) or {}
    return {"id": sid, "title": info.get("title"), "preview": info.get("preview")}


def _codex_preview(rollout: str | None) -> str | None:
    if not rollout:
        return None
    path = pathlib.Path(rollout)
    if not path.is_file():
        return None

    def compute():
        final = said = None
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    payload = (json.loads(line) or {}).get("payload") or {}
                except (ValueError, AttributeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "task_complete" and payload.get("last_agent_message"):
                    final = payload["last_agent_message"]
                elif payload.get("type") == "item_completed":
                    item = payload.get("item") or {}
                    if isinstance(item, dict) and item.get("type") == "AgentMessage":
                        parts = [c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict)]
                        said = "\n".join(p for p in parts if p).strip() or said
        return _short(final or said, 200)

    return _cached(("codex-rollout", str(path)), [path], compute)


def _codex(pid, cwd, known_id, claimed):
    rows = _query(home("codex") / "state_5.sqlite",
                  "SELECT id, source, created_at_ms, name, first_user_message, rollout_path FROM threads"
                  f" WHERE cwd IN ({','.join('?' * len(_folders(cwd)))}) OR id = ?",
                  (*_folders(cwd), known_id or ""))
    # Only interactive threads: a `codex exec` or IDE run in the same folder is never this terminal's.
    candidates = [{"id": r["id"], "created": r["created_at_ms"], "row": r}
                  for r in rows if r["source"] == "cli"]
    hit = _pick(candidates, process_start_ms(pid), known_id, claimed)
    if not hit:
        return None
    row = hit["row"]
    return {"id": row["id"], "title": _short(row["name"], 60) or _first_line(row["first_user_message"]),
            "preview": _codex_preview(row["rollout_path"])}


def _grok(pid, cwd, known_id, claimed):
    candidates = []
    for folder in _folders(cwd):
        base = home("grok") / "sessions" / urllib.parse.quote(folder, safe="")
        if not base.is_dir():
            continue
        for summary in base.glob("*/summary.json"):
            def compute(summary=summary):
                try:
                    return json.loads(summary.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return None
            blob = _cached(("grok", str(summary)), [summary], compute)
            if not isinstance(blob, dict):
                continue
            sid = (blob.get("info") or {}).get("id") or summary.parent.name
            candidates.append({"id": sid, "created": _iso_ms(blob.get("created_at")), "blob": blob})
    hit = _pick(candidates, process_start_ms(pid), known_id, claimed)
    if not hit:
        return None
    blob = hit["blob"]
    return {"id": hit["id"], "title": _short(blob.get("generated_title"), 60),
            "preview": _short(blob.get("session_summary"), 200)}


def _agy(pid, cwd, known_id, claimed):
    rows = _query(home("agy") / "conversation_summaries.db",
                  "SELECT conversation_id, title, preview, workspace_uris, last_modified_time, last_user_input_time"
                  " FROM conversation_summaries")
    uris = {pathlib.Path(f).as_uri() for f in _folders(cwd)}
    candidates = []
    for r in rows:
        try:
            workspaces = set(json.loads(r["workspace_uris"] or "[]"))
        except (ValueError, TypeError):
            workspaces = set()
        if r["conversation_id"] == known_id or workspaces & uris:
            # agy keeps no creation time; the first/last input time is the closest stand-in.
            created = _iso_ms(r["last_user_input_time"]) or _iso_ms(r["last_modified_time"])
            candidates.append({"id": r["conversation_id"], "created": created, "row": r})
    hit = _pick(candidates, process_start_ms(pid), known_id, claimed)
    if not hit:
        return None
    row = hit["row"]
    return {"id": row["conversation_id"], "title": _short(row["title"], 60) or _first_line(row["preview"]),
            "preview": _short(row["preview"], 200)}


def _hermes(pid, cwd, known_id, claimed):
    folders = _folders(cwd)
    rows = _query(home("hermes") / "state.db",
                  "SELECT id, source, title, display_name, last_activity_description, started_at FROM sessions"
                  f" WHERE cwd IN ({','.join('?' * len(folders))}) OR id = ?", (*folders, known_id or ""))
    # Only interactive sessions: gateway, cron and subagent sessions in the same folder are never this terminal's.
    candidates = [{"id": r["id"], "row": r, "created": int(r["started_at"] * 1000) if r["started_at"] else None}
                  for r in rows if r["source"] == "cli"]
    hit = _pick(candidates, process_start_ms(pid), known_id, claimed)
    if not hit:
        return None
    row = hit["row"]
    return {"id": row["id"], "title": _short(row["title"] or row["display_name"], 60),
            "preview": _short(row["last_activity_description"], 200)}


def _opencode(pid, cwd, known_id, claimed):
    folders = _folders(cwd)
    rows = _query(home("opencode") / "opencode.db",
                  "SELECT id, title, time_created FROM session"
                  f" WHERE (directory IN ({','.join('?' * len(folders))}) AND parent_id IS NULL) OR id = ?",
                  (*folders, known_id or ""))
    candidates = [{"id": r["id"], "created": r["time_created"], "row": r} for r in rows]
    hit = _pick(candidates, process_start_ms(pid), known_id, claimed)
    if not hit:
        return None
    title = hit["row"]["title"]
    # OpenCode names an untitled session "New session - <timestamp>"; that is not a title.
    if isinstance(title, str) and title.startswith("New session - "):
        title = None
    return {"id": hit["id"], "title": _short(title, 60), "preview": None}


_READERS = {"claude": _claude, "codex": _codex, "grok": _grok, "agy": _agy, "hermes": _hermes,
            "opencode": _opencode}


def card(runtime: str, pid: int | None, cwd: str, known_id: str | None, claimed: set[str]) -> dict | None:
    """{"id", "title", "preview"} of the agent's own session for this terminal, or None."""
    try:
        reader = _READERS.get(runtime)
        if reader is None or (not pid and not known_id):
            return None
        return reader(pid, str(cwd or ""), known_id, set(claimed or ()))
    except Exception:  # noqa: BLE001 - the board must render whatever happens here
        return None
