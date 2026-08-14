"""Claim lease helpers for kb-board."""
from __future__ import annotations

import datetime as dt
import pathlib

from .check import check_board_text
from .fmt import format_board
from .locks import acquire_file_lock
from .mutation import _clear_claim, _fsync_parent, _iso, _parse_now, ensure_original_mutable
from .parsing import parse_board


def _expired(value: str | None, now: dt.datetime) -> bool:
    if not value:
        return False
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        expires = dt.datetime.fromisoformat(raw)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    return expires.astimezone(dt.timezone.utc) < now


def sweep_expired_file(*, path: pathlib.Path, actor: str, now: str | None = None, timeout_s: float = 30.0) -> int:
    path = pathlib.Path(path)
    parsed_now = _parse_now(now)
    lock_path = path.with_name(path.name + ".lock")
    changed = 0
    with acquire_file_lock(lock_path, timeout_s=timeout_s):
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        board = parse_board(original)
        for task in list(board.sections.get("In Progress", [])):
            if _expired(task.fields.get("claim_expires_at"), parsed_now):
                board.sections["In Progress"].remove(task)
                task.status = "Ready"
                _clear_claim(task)
                task.fields["updated"] = _iso(parsed_now)
                board.sections.setdefault("Ready", []).append(task)
                changed += 1
        if changed:
            # Publish gate: a sweep that would rewrite the file must not drop
            # unrecognized content. A sweep with nothing to move stays a
            # silent no-op on any board, canonical or not.
            ensure_original_mutable(original, path)
            candidate = format_board(board)
            result = check_board_text(candidate)
            if not result.ok:
                from .mutation import BoardMutationError
                raise BoardMutationError("ECHECK", "sweep candidate failed check")
            tmp = path.with_name(path.name + ".sweep-tmp")
            tmp.write_text(candidate, encoding="utf-8")
            tmp.replace(path)
            _fsync_parent(path)
    return changed
