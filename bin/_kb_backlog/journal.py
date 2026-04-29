"""journal.py — append-only audit journal per backlog.

Layout:

    ~/knowledge/.orchestrator/audit/
    ├── _xfer/                     # cross-backlog xfer coordinator segments
    │   └── <segment_id>.jsonl
    ├── _xfer-current.txt          # pointer to current xfer segment_id
    ├── <slug>/
    │   ├── <segment_id>.jsonl     # append-only segment
    │   └── ...
    └── <slug>-current.txt         # pointer to current <slug> segment_id

Each segment starts with a `segment_init` record:

    {"segment_init": true, "segment_id": "<uuid>", "prev_segment_id": "<uuid|null>", "started_at": "<iso>"}

Subsequent records (per-file):

    {"tx_id": "<uuid>", "phase": "prepared", "op": "append|update|tombstone|close|claim|revert",
     "actor": "<who>", "line": <int|null>, "before_hash": "<sha>", "after_hash": "<sha>",
     "before_line_hashes": ["<sha>", ...], "after_line_hashes": [...], "ts": "<iso>"}
    {"tx_id": "<uuid>", "phase": "committed|committed-recovered|aborted|escalated-orphan", "ts": "<iso>"}

Rotation: per-segment rotation when size > 10 MB OR start of new month.
Rotation must coordinate with active spawns — see `rotate_if_needed()`.

Terminal phases per tx_id (CR8-B3 + CR9-N2):
    Exactly one of {committed, committed-recovered, aborted, escalated-orphan}.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import time
import uuid
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))
AUDIT_DIR = HUB / ".orchestrator" / "audit"

ROTATION_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

TERMINAL_PHASES = {"committed", "committed-recovered", "aborted", "escalated-orphan"}
NON_TERMINAL_PHASES = {"prepared"}


# ──────────────────────────────────────────────────────────────────────────
# Hashing helpers
# ──────────────────────────────────────────────────────────────────────────

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def hash_lines(text: str) -> list[str]:
    """sha256 of each line (without terminator)."""
    return [sha256_text(line) for line in text.splitlines()]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ──────────────────────────────────────────────────────────────────────────
# Segment management
# ──────────────────────────────────────────────────────────────────────────

def _slug_audit_dir(slug: str) -> pathlib.Path:
    if slug == "_xfer":
        return AUDIT_DIR / "_xfer"
    return AUDIT_DIR / slug


def _current_pointer_path(slug: str) -> pathlib.Path:
    if slug == "_xfer":
        return AUDIT_DIR / "_xfer-current.txt"
    return AUDIT_DIR / f"{slug}-current.txt"


def _read_current_segment_id(slug: str) -> Optional[str]:
    p = _current_pointer_path(slug)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8").strip() or None


def _write_current_segment_id(slug: str, segment_id: str) -> None:
    p = _current_pointer_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(segment_id, encoding="utf-8")
    os.replace(tmp, p)
    _fsync_dir(p.parent)


def _segment_path(slug: str, segment_id: str) -> pathlib.Path:
    return _slug_audit_dir(slug) / f"{segment_id}.jsonl"


def _fsync_dir(d: pathlib.Path) -> None:
    try:
        fd = os.open(str(d), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _open_for_append(p: pathlib.Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    return open(p, "ab")


def _segment_init_record(segment_id: str, prev_segment_id: Optional[str]) -> dict:
    return {
        "segment_init": True,
        "segment_id": segment_id,
        "prev_segment_id": prev_segment_id,
        "started_at": now_iso(),
    }


def _create_segment(slug: str, prev_segment_id: Optional[str]) -> str:
    """Create a new segment for `slug` and atomically point _current to it.

    Returns new segment_id.
    """
    segment_id = str(uuid.uuid4())
    p = _segment_path(slug, segment_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    record = _segment_init_record(segment_id, prev_segment_id)
    with _open_for_append(p) as fh:
        fh.write(_jsonl(record))
        fh.flush()
        os.fsync(fh.fileno())
    _fsync_dir(p.parent)
    _write_current_segment_id(slug, segment_id)
    return segment_id


def ensure_current_segment(slug: str) -> str:
    """Return current segment_id for `slug`, creating one if missing."""
    sid = _read_current_segment_id(slug)
    if sid is None or not _segment_path(slug, sid).is_file():
        return _create_segment(slug, prev_segment_id=None)
    return sid


def _jsonl(record: dict) -> bytes:
    return (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def append_record(slug: str, record: dict) -> tuple[str, int]:
    """Append a record to current segment. Returns (segment_id, byte_offset_after).

    Caller must already hold `<slug>.lock` (per-file segments) or `_xfer.lock`
    (xfer coordinator).

    CR2-N2: opportunistic rotation runs here for `_xfer` segments too (the
    per-slug rotation is wired separately via mutation primitive). For `_xfer`,
    we use a special active-segment check that always returns False (xfer
    coordinator is not pinned by spawn-window snapshots — there's no
    chain-replay equivalent for the coordinator).
    """
    if slug == "_xfer":
        # _xfer rotation: no spawn-window pinning, always rotate when ready.
        try:
            rotate_if_needed(slug, _never_active)
        except RuntimeError:
            pass  # rotation deferred (shouldn't happen for _xfer); proceed
    sid = ensure_current_segment(slug)
    p = _segment_path(slug, sid)
    encoded = _jsonl(record)
    with _open_for_append(p) as fh:
        fh.write(encoded)
        fh.flush()
        os.fsync(fh.fileno())
    return sid, p.stat().st_size


def _never_active(_slug, _segment_id) -> bool:
    """Stub for _xfer rotation: no per-segment active-spawn pinning exists."""
    return False


def segment_size(slug: str, segment_id: str) -> int:
    p = _segment_path(slug, segment_id)
    return p.stat().st_size if p.is_file() else 0


def list_segments_chain(slug: str) -> list[str]:
    """Return all segment_ids for `slug` in chronological order (oldest → newest).

    Walks `prev_segment_id` chain backward from current.
    """
    cur = _read_current_segment_id(slug)
    if cur is None:
        return []
    chain = []
    visited: set[str] = set()
    sid: Optional[str] = cur
    while sid is not None and sid not in visited:
        visited.add(sid)
        chain.append(sid)
        init = _read_segment_init(slug, sid)
        sid = init.get("prev_segment_id") if init else None
    return list(reversed(chain))


def _read_segment_init(slug: str, segment_id: str) -> Optional[dict]:
    p = _segment_path(slug, segment_id)
    if not p.is_file():
        return None
    try:
        with open(p, "rb") as fh:
            line = fh.readline()
        if not line:
            return None
        rec = json.loads(line)
        return rec if rec.get("segment_init") else None
    except Exception:
        return None


def iter_records(slug: str, segment_id: Optional[str] = None) -> Iterator[dict]:
    """Yield all records (excluding segment_init) from a single segment.

    If `segment_id` is None, uses current segment.
    """
    sid = segment_id or _read_current_segment_id(slug)
    if sid is None:
        return
    p = _segment_path(slug, sid)
    if not p.is_file():
        return
    with open(p, "rb") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("segment_init"):
                continue
            yield rec


def iter_records_chain(slug: str) -> Iterator[dict]:
    """Yield all records across all segments (oldest first)."""
    for sid in list_segments_chain(slug):
        for rec in iter_records(slug, sid):
            yield rec


def iter_records_window(
    slug: str,
    start_segment_id: str,
    start_offset: int,
    end_segment_id: Optional[str] = None,
    end_offset: Optional[int] = None,
) -> Iterator[dict]:
    """Yield records inside the (segment, offset) window.

    Useful for the post-spawn detector: `start_*` is the snapshot before spawn,
    `end_*` is the moment of detection. Walks segment chain forward from
    start_segment_id through end_segment_id.
    """
    chain = list_segments_chain(slug)
    if start_segment_id not in chain:
        return
    start_idx = chain.index(start_segment_id)
    end_idx = chain.index(end_segment_id) if (end_segment_id and end_segment_id in chain) else len(chain) - 1
    for i in range(start_idx, end_idx + 1):
        sid = chain[i]
        p = _segment_path(slug, sid)
        if not p.is_file():
            continue
        with open(p, "rb") as fh:
            if i == start_idx and start_offset > 0:
                fh.seek(start_offset)
            stop = end_offset if (i == end_idx and end_offset is not None) else None
            while True:
                if stop is not None and fh.tell() >= stop:
                    break
                line = fh.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if rec.get("segment_init"):
                    continue
                yield rec


# ──────────────────────────────────────────────────────────────────────────
# Tx_id collapse (terminal phase resolution)
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class TxState:
    tx_id: str
    prepared: Optional[dict]
    terminals: list[dict]  # all terminal records (should be 0 or 1)

    @property
    def terminal_count(self) -> int:
        return len(self.terminals)

    @property
    def terminal(self) -> Optional[dict]:
        return self.terminals[0] if self.terminals else None

    @property
    def is_committed_like(self) -> bool:
        """True if any terminal is committed or committed-recovered."""
        return any(t.get("phase") in ("committed", "committed-recovered") for t in self.terminals)


def collapse_by_tx(records: Iterable[dict]) -> dict[str, TxState]:
    """Group records by tx_id, returning a TxState per tx_id.

    Records without a tx_id (e.g. segment_init) are silently skipped.
    """
    grouped: dict[str, TxState] = {}
    for rec in records:
        tid = rec.get("tx_id")
        if not tid:
            continue
        st = grouped.setdefault(tid, TxState(tx_id=tid, prepared=None, terminals=[]))
        phase = rec.get("phase")
        if phase == "prepared":
            st.prepared = rec
        elif phase in TERMINAL_PHASES:
            st.terminals.append(rec)
    return grouped


def collapse_xfer_by_id(records: Iterable[dict]) -> dict[str, "XferState"]:
    """Group _xfer.jsonl records by xfer_id. Returns XferState per id."""
    grouped: dict[str, XferState] = {}
    for rec in records:
        xid = rec.get("xfer_id")
        if not xid:
            continue
        phase = rec.get("phase")
        st = grouped.setdefault(xid, XferState(xfer_id=xid, prepared=None, terminals=[]))
        if phase == "xfer-prepared":
            st.prepared = rec
        elif phase in {"xfer-committed", "xfer-committed-recovered", "xfer-aborted", "xfer-escalated-orphan"}:
            st.terminals.append(rec)
    return grouped


@dataclass
class XferState:
    xfer_id: str
    prepared: Optional[dict]
    terminals: list[dict]

    @property
    def terminal_count(self) -> int:
        return len(self.terminals)

    @property
    def terminal(self) -> Optional[dict]:
        return self.terminals[0] if self.terminals else None


# ──────────────────────────────────────────────────────────────────────────
# Rotation
# ──────────────────────────────────────────────────────────────────────────

def rotate_if_needed(slug: str, active_spawn_check) -> Optional[str]:
    """Rotate segment for `slug` if size > ROTATION_SIZE_BYTES or month boundary.

    `active_spawn_check(slug, segment_id) -> bool` returns True iff there is
    any active spawn registered for this slug+segment.

    Lock requirements:
    - For per-slug rotation (slug != "_xfer"): caller must hold
      `<slug>.lock + spawns.lock`. The spawns.lock is required because we
      consult `spawns-active.json` via `active_spawn_check` and writers
      can't append a new spawn record while we evaluate.
    - For `_xfer` coordinator rotation (CR2-N2 + CR3-N1): caller holds only
      `_xfer.lock`. The `_xfer` coordinator has no spawn-window pinning —
      `active_spawn_check` is `_never_active`, which always returns False.
      Spawns register only per-slug cursors (see `spawns.py::register`),
      and `_xfer` readers use full chain replay, not baseline-window
      pinning, so rotation can always proceed.

    Returns new segment_id if rotated, else None. Raises RuntimeError if
    rotation is deferred (active spawn pinned to current segment, per-slug
    case only).
    """
    sid = _read_current_segment_id(slug)
    if sid is None:
        return None
    p = _segment_path(slug, sid)
    if not p.is_file():
        return None
    size_ok = p.stat().st_size > ROTATION_SIZE_BYTES
    init = _read_segment_init(slug, sid) or {}
    started_at = init.get("started_at", "")
    month_ok = False
    try:
        d = dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        month_ok = (d.year, d.month) != (now.year, now.month)
    except (ValueError, TypeError):
        pass

    if not (size_ok or month_ok):
        return None

    # Refuse if any active spawn is on this slug+segment.
    if active_spawn_check(slug, sid):
        raise RuntimeError(
            f"rotation deferred: active spawn on segment {sid} for slug={slug}"
        )

    return _create_segment(slug, prev_segment_id=sid)


# ──────────────────────────────────────────────────────────────────────────
# High-level append helpers (used by mutation primitive + xfer)
# ──────────────────────────────────────────────────────────────────────────

def write_prepared(
    slug: str,
    *,
    tx_id: str,
    op: str,
    actor: str,
    line: Optional[int],
    before_hash: str,
    after_hash: str,
    before_line_hashes: list[str],
    after_line_hashes: list[str],
    extra: Optional[dict] = None,
) -> tuple[str, int]:
    rec = {
        "tx_id": tx_id,
        "phase": "prepared",
        "op": op,
        "actor": actor,
        "line": line,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "before_line_hashes": before_line_hashes,
        "after_line_hashes": after_line_hashes,
        "ts": now_iso(),
    }
    if extra:
        rec.update(extra)
    return append_record(slug, rec)


def write_committed(slug: str, tx_id: str, recovered: bool = False) -> tuple[str, int]:
    rec = {
        "tx_id": tx_id,
        "phase": "committed-recovered" if recovered else "committed",
        "ts": now_iso(),
    }
    return append_record(slug, rec)


def write_aborted(slug: str, tx_id: str) -> tuple[str, int]:
    rec = {"tx_id": tx_id, "phase": "aborted", "ts": now_iso()}
    return append_record(slug, rec)


def write_escalated_orphan(slug: str, tx_id: str, reason: str = "") -> tuple[str, int]:
    rec = {"tx_id": tx_id, "phase": "escalated-orphan", "reason": reason, "ts": now_iso()}
    return append_record(slug, rec)


# ──────────────────────────────────────────────────────────────────────────
# Recovery
# ──────────────────────────────────────────────────────────────────────────

def recover_pending(slug: str, current_text: str) -> list[dict]:
    """Scan all segments for `slug`, find prepared transactions without a
    terminal phase, and write the appropriate terminal record by comparing
    `current_text` hash against `before_hash`/`after_hash`.

    Returns a list of resolution dicts: [{tx_id, phase, action, ...}]

    Caller must already hold `<slug>.lock` and `spawns.lock`. This is
    idempotent — re-running after partial completion does not duplicate
    terminals (existing terminal_count > 0 → skip).
    """
    current_hash = sha256_text(current_text)
    grouped = collapse_by_tx(iter_records_chain(slug))
    resolutions: list[dict] = []
    for tid, st in grouped.items():
        if st.prepared is None:
            continue
        if st.terminal_count >= 1:
            continue
        before = st.prepared.get("before_hash")
        after = st.prepared.get("after_hash")
        if current_hash == after:
            write_committed(slug, tid, recovered=True)
            resolutions.append({"tx_id": tid, "phase": "committed-recovered"})
        elif current_hash == before:
            write_aborted(slug, tid)
            resolutions.append({"tx_id": tid, "phase": "aborted"})
        else:
            write_escalated_orphan(slug, tid, reason="current hash matches neither before nor after")
            resolutions.append({"tx_id": tid, "phase": "escalated-orphan"})
    return resolutions
