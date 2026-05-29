"""CAS mutation primitive for the multiline markdown board."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import pathlib
import uuid
from dataclasses import dataclass
from typing import Any

from .check import check_board_text
from .fmt import format_board
from .hashing import content_hash
from .locks import acquire_file_lock
from .model import Board, TaskBlock
from .parsing import parse_board
from .transitions import is_legal

LEASE_SECONDS = 15 * 60


class BoardMutationError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class MutationResult:
    status: str
    plan_item_id: str
    from_status: str
    to_status: str
    content_hash: str


def _parse_now(now: str | None) -> dt.datetime:
    if now is None:
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    raw = now.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_claim_id(plan_item_id: str, actor: str, now: dt.datetime) -> str:
    seed = f"{plan_item_id}:{actor}:{_iso(now)}:{uuid.uuid4()}".encode("utf-8")
    return "clm-" + hashlib.sha256(seed).hexdigest()[:12]


def _find_task(board: Board, plan_item_id: str) -> TaskBlock:
    for task in board.tasks:
        if task.fields.get("plan_item_id") == plan_item_id:
            return task
    raise BoardMutationError("ENOTFOUND", f"plan_item_id not found: {plan_item_id}")


def _move(board: Board, task: TaskBlock, target: str) -> None:
    source_tasks = board.sections.get(task.status, [])
    if task in source_tasks:
        source_tasks.remove(task)
    task.status = target
    board.sections.setdefault(target, []).append(task)


def _clear_claim(task: TaskBlock) -> None:
    for key in ("claim_owner", "claim_id", "claim_expires_at"):
        task.fields.pop(key, None)


def _mint_claim(task: TaskBlock, actor: str, now: dt.datetime) -> None:
    task.fields["claim_owner"] = actor
    task.fields["claim_id"] = _new_claim_id(task.fields.get("plan_item_id", ""), actor, now)
    task.fields["claim_expires_at"] = _iso(now + dt.timedelta(seconds=LEASE_SECONDS))


def _check_expected_hash(task: TaskBlock, expected_content_hash: str | None) -> None:
    if expected_content_hash is None:
        return
    current = content_hash(task)
    if current != expected_content_hash:
        raise BoardMutationError("EHASH", "expected_content_hash does not match current task content")


def _check_claim(task: TaskBlock, claim_id: str | None, *, active: bool) -> None:
    if not claim_id or task.fields.get("claim_id") != claim_id:
        raise BoardMutationError("ECLAIM", "claim_id provenance check failed")
    if active and not task.fields.get("claim_owner"):
        raise BoardMutationError("ECLAIM", "active claim_owner missing")


def _set_updated(task: TaskBlock, now: dt.datetime) -> None:
    task.fields["updated"] = _iso(now).split("T")[0] if "T00:00:00Z" in _iso(now) else _iso(now)


def _apply_updates(task: TaskBlock, updates: dict[str, Any] | None) -> None:
    if not updates:
        return
    for key, value in updates.items():
        if isinstance(value, list):
            task.fields[key] = "[" + ", ".join(str(v) for v in value) + "]"
        else:
            task.fields[key] = str(value)


def _mutate_board(
    board: Board,
    *,
    op: str,
    plan_item_id: str,
    actor: str,
    expected_content_hash: str | None,
    claim_id: str | None,
    now: dt.datetime,
    target_status: str | None,
    reason: str | None,
    outcome: str | None,
    updates: dict[str, Any] | None,
) -> MutationResult:
    task = _find_task(board, plan_item_id)
    source = task.status
    _check_expected_hash(task, expected_content_hash)

    if op == "claim":
        target = "In Progress"
        if not is_legal(source, target) or source != "Ready":
            raise BoardMutationError("ETRANSITION", f"{source} -> {target} is not legal for claim")
        _move(board, task, target)
        _mint_claim(task, actor, now)
        _set_updated(task, now)

    elif op == "ready":
        target = "Ready"
        if source not in {"Backlog", "Blocked"} or not is_legal(source, target):
            raise BoardMutationError("ETRANSITION", f"{source} -> {target} is not legal for ready")
        _move(board, task, target)
        _clear_claim(task)
        if source == "Blocked":
            task.fields.pop("blocked_reason", None)
        if reason:
            task.fields["ready_reason"] = f"ready by {actor} at {_iso(now)}: {reason}"
        _set_updated(task, now)

    elif op == "heartbeat":
        if source != "In Progress":
            raise BoardMutationError("ETRANSITION", "heartbeat requires In Progress")
        _check_claim(task, claim_id, active=True)
        task.fields["claim_expires_at"] = _iso(now + dt.timedelta(seconds=LEASE_SECONDS))

    elif op == "request-review":
        if source != "In Progress":
            raise BoardMutationError("ETRANSITION", "request-review requires In Progress")
        _check_claim(task, claim_id, active=True)
        _move(board, task, "Review")
        _set_updated(task, now)

    elif op == "close":
        if source != "Review":
            raise BoardMutationError("ETRANSITION", "close requires Review")
        _check_claim(task, claim_id, active=False)
        _move(board, task, "Done")
        _clear_claim(task)
        if outcome:
            task.fields["evidence"] = f"{outcome}"
        _set_updated(task, now)

    elif op == "return-from-review":
        if source != "Review":
            raise BoardMutationError("ETRANSITION", "return-from-review requires Review")
        _check_claim(task, claim_id, active=False)
        _move(board, task, "In Progress")
        _mint_claim(task, actor, now)
        _set_updated(task, now)

    elif op == "block-from-review":
        if source != "Review":
            raise BoardMutationError("ETRANSITION", "block-from-review requires Review")
        _check_claim(task, claim_id, active=False)
        _move(board, task, "Blocked")
        _clear_claim(task)
        if reason:
            task.fields["blocked_reason"] = reason
        _set_updated(task, now)

    elif op == "reopen":
        target = target_status or "Ready"
        if source not in {"Done", "Cancelled"} or target not in {"Ready", "Backlog"}:
            raise BoardMutationError("ETRANSITION", f"{source} -> {target} is not a legal reopen")
        if not reason:
            raise BoardMutationError("EBADARGS", "reopen requires reason")
        _move(board, task, target)
        task.fields["reopen_reason"] = f"reopen by {actor} at {_iso(now)}: {reason}"
        _set_updated(task, now)

    elif op == "progress":
        _apply_updates(task, updates)
        _set_updated(task, now)

    else:
        raise BoardMutationError("EBADARGS", f"unsupported op: {op}")

    return MutationResult(
        status=op,
        plan_item_id=plan_item_id,
        from_status=source,
        to_status=task.status,
        content_hash=content_hash(task),
    )


def _fsync_parent(path: pathlib.Path) -> None:
    try:
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _write_atomic(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4()}")
    tmp.write_text(text, encoding="utf-8")
    with open(tmp, "r", encoding="utf-8") as fh:
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_parent(path)


def mutate_file(
    *,
    path: pathlib.Path,
    op: str,
    plan_item_id: str,
    actor: str,
    expected_content_hash: str | None = None,
    claim_id: str | None = None,
    now: str | None = None,
    target_status: str | None = None,
    reason: str | None = None,
    outcome: str | None = None,
    updates: dict[str, Any] | None = None,
    simulate_crash_at: str | None = None,
    timeout_s: float = 30.0,
) -> MutationResult:
    path = pathlib.Path(path)
    lock_path = path.with_name(path.name + ".lock")
    with acquire_file_lock(lock_path, timeout_s=timeout_s):
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        board = parse_board(original)
        result = _mutate_board(
            board,
            op=op,
            plan_item_id=plan_item_id,
            actor=actor,
            expected_content_hash=expected_content_hash,
            claim_id=claim_id,
            now=_parse_now(now),
            target_status=target_status,
            reason=reason,
            outcome=outcome,
            updates=updates,
        )
        candidate = format_board(board)
        checked = check_board_text(candidate)
        if not checked.ok:
            raise BoardMutationError("ECHECK", "candidate board failed check before publish")
        if simulate_crash_at == "before_rename":
            raise BoardMutationError("ECRASH_SIMULATED", "simulated crash before atomic rename")
        _write_atomic(path, candidate)
        return result
