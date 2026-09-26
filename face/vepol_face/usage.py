"""Claude and Codex plan-usage windows for the status bar.

Local files only: no network call, no credential or Keychain read.
- Codex: the newest rollout-*.jsonl under $CODEX_HOME/sessions (last 8 days)
  that has an event carrying rate_limits with a numeric used_percent; its last
  such event. A just-started session has none yet, so older files are checked
  (at most MAX_ROLLOUTS of them).
- Claude: <state_dir>/claude-rate-limits.json, written by the owner's
  statusline script as {"rate_limits": {...}, "at": <epoch>}.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import pathlib

RECENT_DAYS = 8
TAIL_BYTES = 256 * 1024
MAX_ROLLOUTS = 50
STALE_AFTER = dt.timedelta(hours=6)
CLAUDE_FILE = "claude-rate-limits.json"


def _number(value) -> float | None:
    # json.loads accepts NaN/Infinity; those are not usable numbers.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _iso_from_epoch(value) -> str | None:
    seconds = _number(value)
    if seconds is None:
        return None
    try:
        return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _parse_time(value) -> dt.datetime | None:
    if _number(value) is not None:
        try:
            return dt.datetime.fromtimestamp(float(value), dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    return None


def _part(windows: list[dict], as_of: dt.datetime, source: str, now: dt.datetime) -> dict | None:
    if not windows:
        return None
    return {"windows": windows, "as_of": as_of.isoformat(), "source": source,
            "stale": now - as_of > STALE_AFTER}


def _codex_label(minutes) -> str:
    n = _number(minutes)
    if n == 300:
        return "5h"
    if n == 10080:
        return "7d"
    return f"{int(n)}m" if n is not None else "?"


def _codex_windows(rate_limits) -> list[dict]:
    if not isinstance(rate_limits, dict):
        return []
    windows = []
    for key in ("primary", "secondary"):
        window = rate_limits.get(key)
        if not isinstance(window, dict) or _number(window.get("used_percent")) is None:
            continue
        resets = window.get("resets_at")
        windows.append({"label": _codex_label(window.get("window_minutes")),
                        "used_percent": _number(window["used_percent"]),
                        "resets_at": _iso_from_epoch(resets) or (resets if isinstance(resets, str) else None)})
    return windows


def _last_codex_event(path: pathlib.Path) -> tuple[list[dict], dt.datetime | None] | None:
    try:
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            start = max(0, size - TAIL_BYTES)
            fh.seek(start)
            chunk = fh.read()
    except OSError:
        return None
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # first line is cut mid-way
    for line in reversed(lines):
        if '"rate_limits"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        rate_limits = event.get("rate_limits")
        if rate_limits is None and isinstance(payload, dict):
            rate_limits = payload.get("rate_limits")
        windows = _codex_windows(rate_limits)
        if windows:
            return windows, _parse_time(event.get("timestamp"))
    return None


def read_codex(codex_home: str | os.PathLike | None, now: dt.datetime) -> dict | None:
    home = pathlib.Path(codex_home or os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"))
    cutoff = now.timestamp() - RECENT_DAYS * 86400
    recent = []
    for dirpath, dirnames, filenames in os.walk(home / "sessions"):
        for name in filenames:
            if name.startswith("rollout-") and name.endswith(".jsonl"):
                path = pathlib.Path(dirpath) / name
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime >= cutoff:
                    recent.append((mtime, path))
    if not recent:
        return None
    # Background Codex runs start new files every few minutes, so the newest
    # file often has no numbers yet; use the newest that does.
    for mtime, path in sorted(recent, reverse=True)[:MAX_ROLLOUTS]:
        found = _last_codex_event(path)
        if found:
            windows, as_of = found
            as_of = as_of or dt.datetime.fromtimestamp(mtime, dt.timezone.utc)
            return _part(windows, as_of, str(path), now)
    return None


def read_claude(state_dir: str | os.PathLike, now: dt.datetime) -> dict | None:
    path = pathlib.Path(state_dir) / CLAUDE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mtime = path.stat().st_mtime
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("rate_limits"), dict):
        return None
    windows = []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        window = data["rate_limits"].get(key)
        if not isinstance(window, dict):
            continue
        used = _number(window.get("used_percentage"))
        if used is None:
            used = _number(window.get("used_percent"))
        if used is None:
            continue
        resets = window.get("resets_at")
        windows.append({"label": label, "used_percent": used,
                        "resets_at": _iso_from_epoch(resets) or (resets if isinstance(resets, str) else None)})
    as_of = _parse_time(data.get("at")) or dt.datetime.fromtimestamp(mtime, dt.timezone.utc)
    return _part(windows, as_of, str(path), now)


def read_usage(state_dir: str | os.PathLike, codex_home: str | os.PathLike | None = None,
               now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    return {"claude": read_claude(state_dir, now), "codex": read_codex(codex_home, now)}
