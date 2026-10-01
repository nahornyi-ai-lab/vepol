"""Read-only Memory view: what each knowledge base remembers, per target.

Cards for Memory Home and the data of one Project Memory page, read from the
target's state.md, backlog.md (through the hub's kb-board), decisions/, log.md
and incidents.md. Nothing here writes; every read is confined to the realpath
of the target's knowledge root and obeys knowledge_files.MAX_FILE_BYTES
(log.md is read from its last LOG_TAIL_BYTES only).
"""
from __future__ import annotations

import datetime
import os
import pathlib
import re
import stat
from concurrent.futures import ThreadPoolExecutor

from . import targets as targets_mod
from .knowledge_files import MAX_FILE_BYTES
from .tasks import _read_board

LOG_TAIL_BYTES = 256 * 1024
NOW_MAX_CHARS = 200
HISTORY_LIMIT = 30
STALE_DAYS = 3
DECISION_HEAD_BYTES = 16 * 1024  # frontmatter and title sit at the top of a decision

_LOG_HEADING = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})[^\]]*\]\s*(.*)$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _confined(real_root: str, rel: str) -> str | None:
    """Realpath of rel inside real_root if it is a regular file there, else None."""
    try:
        real = os.path.realpath(os.path.join(real_root, rel))
        if real == real_root or os.path.commonpath([real_root, real]) != real_root:
            return None
        if not stat.S_ISREG(os.stat(real).st_mode):
            return None
    except (OSError, ValueError):
        return None
    return real


def _read(real_root: str, rel: str) -> tuple[str | None, bool]:
    """(text, too_large). text is None when the file is missing, unreadable or over the cap."""
    real = _confined(real_root, rel)
    if real is None:
        return None, False
    try:
        with open(real, "rb") as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None, False
    if len(raw) > MAX_FILE_BYTES:
        return None, True
    return raw.decode("utf-8", errors="replace"), False


def _read_log_tail(real_root: str) -> str:
    real = _confined(real_root, "log.md")
    if real is None:
        return ""
    try:
        with open(real, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - LOG_TAIL_BYTES))
            raw = fh.read(LOG_TAIL_BYTES)
    except OSError:
        return ""
    if size > LOG_TAIL_BYTES:
        cut = raw.find(b"\n")
        raw = raw[cut + 1:] if cut >= 0 else b""
    return raw.decode("utf-8", errors="replace")


def _mtime_date(real_root: str, rel: str) -> str | None:
    real = _confined(real_root, rel)
    if real is None:
        return None
    try:
        return datetime.date.fromtimestamp(os.stat(real).st_mtime).isoformat()
    except (OSError, ValueError, OverflowError):
        return None


def _frontmatter(text: str) -> tuple[dict, list[str]]:
    """Top-level `key: value` pairs of a leading --- block, and the remaining lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines
    meta: dict = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() in ("---", "..."):
            return meta, lines[i + 1:]
        key, sep, value = line.partition(":")
        if sep and key and not key[0].isspace() and key.strip() not in meta:
            meta[key.strip()] = value.strip().strip("'\"")
    return {}, lines  # unclosed block: not frontmatter


def _strip_markdown(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _now(state_text: str) -> str | None:
    _, lines = _frontmatter(state_text)
    start = next((i + 1 for i, l in enumerate(lines) if l.startswith("## ")), None)
    if start is None:
        start = next((i + 1 for i, l in enumerate(lines) if l.startswith("# ")), 0)
    para: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("_("):
            continue
        if stripped.startswith("#") or not stripped:
            if para or stripped.startswith("#"):
                break
            continue
        para.append(re.sub(r"^(>\s*|[-*+]\s+|\d+[.)]\s+)", "", stripped))
    text = _strip_markdown(" ".join(para))
    if not text:
        return None
    if len(text) > NOW_MAX_CHARS:
        text = text[:NOW_MAX_CHARS - 1].rstrip() + "…"
    return text


def _log_entries(log_text: str) -> list[dict]:
    """Dated log entries, newest first (later in the file wins within a date)."""
    entries: list[dict] = []
    current: dict | None = None
    for line in log_text.splitlines():
        if line.startswith("## "):
            match = _LOG_HEADING.match(line)
            current = {"date": match.group(1), "heading": match.group(2).strip(), "body": []} if match else None
            if current:
                entries.append(current)
        elif current is not None:
            current["body"].append(line)
    for entry in entries:
        entry["body"] = "\n".join(entry["body"]).strip()
    entries.reverse()
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def _decisions(real_root: str) -> list[dict]:
    """decisions/*.md with title, date and status, newest first."""
    directory = os.path.join(real_root, "decisions")
    try:
        names = sorted(n for n in os.listdir(directory) if n.endswith(".md") and not n.startswith("."))
    except OSError:
        return []
    found = []
    for name in names:
        rel = f"decisions/{name}"
        real = _confined(real_root, rel)
        if real is None:
            continue
        try:
            with open(real, "rb") as fh:
                text = fh.read(DECISION_HEAD_BYTES).decode("utf-8", errors="replace")
            mtime = os.stat(real).st_mtime
        except OSError:
            continue
        meta, body = _frontmatter(text)
        date = meta.get("date", "")
        if not _DATE.match(date):
            date = datetime.date.fromtimestamp(mtime).isoformat()
        title = meta.get("title") or next(
            (l[2:].strip() for l in body if l.startswith("# ") and l[2:].strip()), name)
        found.append({"path": rel, "title": title, "date": date[:10],
                      "status": meta.get("status") or None, "_mtime": mtime})
    found.sort(key=lambda d: (d["date"], d["_mtime"]), reverse=True)
    for d in found:
        del d["_mtime"]
    return found


def _lessons(real_root: str) -> str | None:
    text, _ = _read(real_root, "incidents.md")
    if text is None:
        return None
    body: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if body is not None:
                break
            if line[3:].strip() == "Prevention rules":
                body = []
        elif body is not None:
            body.append(line)
    if body is None:
        return None
    return "\n".join(body).strip() or None


def _status(real_root: str, state_ok: bool, newest_log: str | None) -> str:
    if not state_ok:
        return "no_state"
    state_date = _mtime_date(real_root, "state.md")
    if newest_log and state_date:
        try:
            gap = datetime.date.fromisoformat(newest_log) - datetime.date.fromisoformat(state_date)
        except ValueError:
            return "up_to_date"
        if gap.days > STALE_DAYS:
            return "needs_review"
    return "up_to_date"


def _plans(kb_board: pathlib.Path, slug: str, real_root: str) -> dict:
    real_board = _confined(real_root, "backlog.md")
    if real_board is None:
        return {"state": "none"}
    if not kb_board.is_file():
        return {"state": "error", "reason": "kb-board not found"}
    result = _read_board(kb_board, slug, pathlib.Path(real_board))
    if result["state"] != "ok":
        return {k: v for k, v in result.items() if k != "project"}
    tasks = result["tasks"]
    in_progress = [t for t in tasks if t.get("status") == "In Progress"]
    ready = [t for t in tasks if t.get("status") == "Ready"]
    first = (in_progress or ready or [{}])[0]
    return {"state": "ok", "next": first.get("title"), "in_progress": len(in_progress),
            "ready": len(ready), "blocked": sum(t.get("status") == "Blocked" for t in tasks)}


def _base(target, real_root: str, state_present: bool, entries: list[dict]) -> dict:
    """Fields shared by a card and a project page."""
    newest_log = entries[0]["date"] if entries else None
    return {"slug": target.slug, "label": target.label, "kind": target.kind, "folder": target.cwd,
            "status": _status(real_root, state_present, newest_log)}


def _card(kb_board: pathlib.Path, target) -> dict:
    real_root = os.path.realpath(target.knowledge)
    entries = _log_entries(_read_log_tail(real_root))
    state_text, too_large = _read(real_root, "state.md")
    decisions = _decisions(real_root)
    last = decisions[0] if decisions else None
    activity = entries[0]["date"] if entries else max(
        filter(None, (_mtime_date(real_root, f) for f in ("state.md", "log.md", "backlog.md"))), default=None)
    card = _base(target, real_root, state_text is not None or too_large, entries)
    card.update({
        "now": _now(state_text) if state_text is not None else None,
        "plans": _plans(kb_board, target.slug, real_root),
        "last_decision": {"title": last["title"], "date": last["date"], "path": last["path"]} if last else None,
        "last_activity": activity,
    })
    return card


def cards(hub: pathlib.Path) -> dict:
    """One card per target: hub first, then newest activity first, then slug."""
    hub = pathlib.Path(hub)
    targets = targets_mod.discover_targets(hub)
    kb_board = hub / "bin" / "kb-board"
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = list(pool.map(lambda t: _card(kb_board, t), targets))
    found.sort(key=lambda c: c["slug"])
    found.sort(key=lambda c: c["last_activity"] or "", reverse=True)
    found.sort(key=lambda c: (c["kind"] != "hub", c["last_activity"] is None))
    return {"cards": found}


def project(hub: pathlib.Path, slug: str) -> dict:
    """Project Memory page data for one target. Unknown slug -> KeyError."""
    target = next((t for t in targets_mod.discover_targets(pathlib.Path(hub)) if t.slug == slug), None)
    if target is None:
        raise KeyError(slug)
    real_root = os.path.realpath(target.knowledge)
    entries = _log_entries(_read_log_tail(real_root))
    state_text, too_large = _read(real_root, "state.md")
    page = _base(target, real_root, state_text is not None or too_large, entries)
    if state_text is not None:
        state = {"text": state_text}
    else:
        state = {"text": None, "note": "too large to show" if too_large else "No state file"}
    page.update({
        "state": state,
        "now": _now(state_text) if state_text is not None else None,
        "state_date": _mtime_date(real_root, "state.md"),
        "decisions": _decisions(real_root),
        "history": entries[:HISTORY_LIMIT],
        "lessons": _lessons(real_root),
    })
    return page
