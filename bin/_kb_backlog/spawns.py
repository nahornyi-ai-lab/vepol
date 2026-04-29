"""spawns.py — active-spawn registry (`spawns-active.json`).

Format:

    [
      {"spawn_id": "<uuid>", "pid": 12345, "slug": "<slug>",
       "segment_id": "<uuid>", "offset": 12345, "started_at": "<iso>"},
      ...
    ]

Operations are guarded by `spawns.lock`. Used for:
- Pre-spawn snapshot register (executor).
- Post-spawn unregister (executor).
- Rotation refusal check (journal).
- Recovery's spawn-window discovery.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Optional

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))
SPAWNS_PATH = HUB / ".orchestrator" / "spawns-active.json"


def _read() -> list[dict]:
    if not SPAWNS_PATH.is_file():
        return []
    try:
        return json.loads(SPAWNS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write(records: list[dict]) -> None:
    """Atomic write with fsync on temp + parent dir (CR1-N1).

    The plan requires durable pre-spawn registration: spawn registry survives
    process/kernel crash so post-spawn analysis can find the (segment_id,
    offset) baseline.
    """
    SPAWNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SPAWNS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(records, indent=2))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, SPAWNS_PATH)
    try:
        fd = os.open(str(SPAWNS_PATH.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def register(*, spawn_id: str, pid: int, slug: str, segment_id: str,
             offset: int, started_at: str) -> None:
    """Register an active spawn. Caller must hold `spawns.lock`."""
    records = _read()
    records.append({
        "spawn_id": spawn_id,
        "pid": pid,
        "slug": slug,
        "segment_id": segment_id,
        "offset": offset,
        "started_at": started_at,
    })
    _write(records)


def unregister(spawn_id: str) -> Optional[dict]:
    """Remove a spawn record by spawn_id. Returns the removed record or None.
    Caller must hold `spawns.lock`."""
    records = _read()
    out: list[dict] = []
    removed: Optional[dict] = None
    for r in records:
        if r.get("spawn_id") == spawn_id:
            removed = r
        else:
            out.append(r)
    _write(out)
    return removed


def list_for_slug(slug: str) -> list[dict]:
    """Return all active spawns for `slug`. Caller must hold `spawns.lock`."""
    return [r for r in _read() if r.get("slug") == slug]


def has_active_on_segment(slug: str, segment_id: str) -> bool:
    """True iff any active spawn registered for slug+segment. Caller holds spawns.lock."""
    return any(r.get("slug") == slug and r.get("segment_id") == segment_id
               for r in _read())


def all_records() -> list[dict]:
    return _read()
