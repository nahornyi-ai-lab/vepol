"""date_attribution.py — deterministic ISO date for a log/daily line.

Per IP-I Q1 (closed by Codex Layer-2 review 2026-05-07):

    Walk back to nearest `## [YYYY-MM-DD]` heading in the file. If
    absent and path is `daily/YYYY-MM-DD.md`, use date from filename.
    Otherwise today. NEVER mtime.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path


_HEADING_DATE_RE = re.compile(r"^##\s*\[(\d{4}-\d{2}-\d{2})\]")
_DAILY_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def _is_daily_path(path: Path) -> tuple[bool, str | None]:
    """Returns (True, date_str) if path matches `**/daily/<YYYY-MM-DD>.md`."""
    if path.parent.name != "daily":
        return (False, None)
    m = _DAILY_FILENAME_RE.match(path.name)
    if not m:
        return (False, None)
    return (True, m.group(1))


def attribute_date(file_path: Path, line_no: int, file_text: str) -> str:
    """Return the canonical ISO date for `(file_path, line_no)`.

    Algorithm:
      1. Walk backward through `file_text` from `line_no` looking for
         the nearest `## [YYYY-MM-DD]` heading; return its date.
      2. If no heading found and `file_path` matches
         `<...>/daily/YYYY-MM-DD.md`, return the date from the filename.
      3. Otherwise return today's ISO date.

    Never reads filesystem metadata (mtime, ctime, etc.).
    """
    lines = file_text.splitlines()
    # Walk backward from min(line_no, len(lines)) toward 1.
    start = min(max(line_no, 1), len(lines))
    for i in range(start, 0, -1):
        line = lines[i - 1]
        m = _HEADING_DATE_RE.match(line)
        if m:
            return m.group(1)

    # No heading found — try daily/<date>.md filename.
    is_daily, daily_date = _is_daily_path(file_path)
    if is_daily and daily_date:
        return daily_date

    return date.today().isoformat()
