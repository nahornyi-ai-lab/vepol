"""watermark.py — incremental-scan watermarks for project_source.

Per IP-B in ~/knowledge/concepts/people-extraction-from-projects.md.

Schema of `<project>/knowledge/.kb-people-extracted`:

    {
      "schema_version": 1,
      "last_run_at": "<ISO-8601 UTC>",
      "files": {
        "<rel-path>": {"size": <int>, "sha256": "<hex>" | null}
      }
    }

`determine_scan_range(path, mark)` decides what byte range to scan:
  - first-scan       — no prior mark → (0, cur_size, "first-scan")
  - no-change        — size + hash unchanged → (size, size, "no-change")
  - incremental      — size grew + prefix-hash matches → (mark.size, cur_size)
  - shrink-fallback  — file got smaller → (0, cur_size) full rescan
  - prefix-changed   — same/larger size but stored hash differs → full rescan

`safe_mark_write` re-stats / re-hashes the scanned snapshot before
recording the new watermark; if the file mutated mid-run, the old mark
is left intact and an audit warning is emitted (Codex Layer-2 point 5).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WATERMARK_FILENAME = ".kb-people-extracted"
SCHEMA_VERSION = 1


def _sha256_of_first_n(path: Path, n: int) -> str:
    """Hash the first `n` bytes of `path`. If `n >= file size`, this
    hashes the whole file (which is exactly what we want for the
    same-size-different-content detection case)."""
    h = hashlib.sha256()
    remaining = n
    chunk = 1 << 16  # 64 KiB
    with open(path, "rb") as f:
        while remaining > 0:
            buf = f.read(min(chunk, remaining))
            if not buf:
                break
            h.update(buf)
            remaining -= len(buf)
    return h.hexdigest()


def determine_scan_range(
    path: Path, mark: dict | None
) -> tuple[int, int, str]:
    """Decide what byte range of `path` to scan given a stored mark.

    Returns (start_offset, end_offset, reason).
    - `start == end == 0` plus reason `skip-empty` for empty files.
    - `start == end == cur_size` plus reason `no-change` when nothing
       to do.
    """
    cur_size = path.stat().st_size
    if cur_size == 0:
        return (0, 0, "skip-empty")
    if mark is None or mark.get("sha256") in (None, ""):
        return (0, cur_size, "first-scan")
    stored_size = int(mark.get("size", 0))
    stored_hash = mark.get("sha256", "")

    if cur_size < stored_size:
        return (0, cur_size, "shrink-fallback")

    # Hash whatever portion the stored mark claimed to cover.
    prefix_hash = _sha256_of_first_n(path, stored_size)
    if prefix_hash != stored_hash:
        return (0, cur_size, "prefix-changed-fallback")

    if cur_size == stored_size:
        return (cur_size, cur_size, "no-change")

    return (stored_size, cur_size, "incremental")


def read_watermark(project_dir: Path) -> dict:
    """Load watermark file; returns empty schema-shape on missing."""
    path = project_dir / WATERMARK_FILENAME
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Corrupt watermark — treat as missing; first-scan behaviour
        # follows. Caller may want to log this.
        return {"schema_version": SCHEMA_VERSION, "files": {}}


def write_watermark(project_dir: Path, files_marks: dict) -> None:
    """Atomic write of the project's watermark file."""
    project_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "schema_version": SCHEMA_VERSION,
        "last_run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files_marks,
    }
    target = project_dir / WATERMARK_FILENAME
    fd, tmp_name = tempfile.mkstemp(prefix=".kb-people-extracted.",
                                    suffix=".tmp",
                                    dir=str(project_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def safe_mark_write(
    path: Path,
    scanned_size: int,
    scanned_hash: str,
    audit: dict,
) -> bool:
    """Verify the file still matches the snapshot we scanned, then
    return True if it's safe to advance the watermark for this file.

    Returns False (and emits an audit warning) if the file changed
    between the start of scanning and now. Caller leaves the old
    watermark for this file in place and re-tries on the next run.

    `audit` must be a dict with a `warnings` list (initialised by
    caller); warnings are appended in-place.
    """
    audit.setdefault("warnings", [])
    cur_size = path.stat().st_size
    if cur_size != scanned_size:
        audit["warnings"].append({
            "kind": "file_mutated_during_scan",
            "path": str(path),
            "scanned_size": scanned_size,
            "current_size": cur_size,
        })
        return False
    cur_hash = _sha256_of_first_n(path, cur_size)
    if cur_hash != scanned_hash:
        audit["warnings"].append({
            "kind": "file_mutated_during_scan",
            "path": str(path),
            "scanned_hash": scanned_hash[:16],
            "current_hash": cur_hash[:16],
        })
        return False
    return True
