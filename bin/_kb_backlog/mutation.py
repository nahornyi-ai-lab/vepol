"""mutation.py — `_apply_mutation` primitive (CR10-N4 + CR11-N2).

Single code path for both CLI ops and recovery. Implements the full
prepared/write/committed protocol with atomic rename:

    1. tx_id = uuid4()
    2. before_hash = sha256(current); before_line_hashes = [...]
    3. compute target text per `op` and arguments
    4. if after_hash == before_hash → no-op, NO journal entry, return.
    5. journal.write_prepared(...)
    6. write target to <path>.tx-<tx_id>; fsync; rename → <path>; fsync(parent)
    7. journal.write_committed(...)

Held-locks are passed as `set[LockId]`. The primitive asserts
`required_locks_for_op(slug, op) ⊆ held_locks`.
"""
from __future__ import annotations

import os
import pathlib
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from . import journal, locks, parsing


@dataclass
class MutationResult:
    tx_id: str
    op: str
    slug: str
    no_op: bool
    before_hash: str
    after_hash: str
    line: Optional[int]
    new_text: str


def _fsync_file(p: pathlib.Path) -> None:
    fd = os.open(str(p), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_parent(p: pathlib.Path) -> None:
    try:
        fd = os.open(str(p.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


# Function shape: TextTransform(text: str) -> tuple[str, Optional[int], dict]
# returns (new_text, target_lineno, extra_metadata_for_prepared).
TextTransform = Callable[[str], tuple[str, Optional[int], dict]]


def apply_mutation(
    *,
    slug: str,
    backlog_path: pathlib.Path,
    op: str,
    actor: str,
    transform: TextTransform,
    held_locks: set[locks.LockId],
    extra_required_locks: Optional[set[locks.LockId]] = None,
) -> MutationResult:
    """Apply `transform` to `backlog_path` atomically with full journaling.

    Args:
        slug: backlog identifier (project slug or "hub").
        backlog_path: absolute path to backlog.md.
        op: operation name (append/update/tombstone/close/claim/revert).
        actor: who initiated the op (e.g. "<user>", "executor", "hub").
        transform: callable(current_text) -> (new_text, target_lineno, extra).
        held_locks: set of LockIds the caller has already acquired.
        extra_required_locks: additional locks the caller must hold (e.g. xfer).
    """
    required = locks.required_locks_for_op(slug, op) if op != "_internal" else set()
    if extra_required_locks:
        required |= extra_required_locks
    missing = required - held_locks
    if missing:
        names = ", ".join(sorted(m.name for m in missing))
        held_names = ", ".join(sorted(h.name for h in held_locks))
        raise RuntimeError(
            f"apply_mutation: missing required locks for slug={slug!r} op={op!r}: "
            f"{{{names}}}; held {{{held_names}}}"
        )

    # CR1-N2: opportunistic segment rotation. We hold <slug>.lock and
    # spawns.lock per the canonical order, so rotation can safely check the
    # active-spawn registry. If rotation is deferred (active spawn on the
    # current segment), we proceed without rotating — rotation will retry on
    # the next mutation.
    try:
        from . import spawns as _spawns_mod
        journal.rotate_if_needed(slug, _spawns_mod.has_active_on_segment)
    except RuntimeError:
        pass  # rotation deferred: active spawns; OK to proceed without rotating

    current_text = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    before_hash = journal.sha256_text(current_text)
    before_line_hashes = journal.hash_lines(current_text)

    new_text, target_line, extra = transform(current_text)
    after_hash = journal.sha256_text(new_text)
    after_line_hashes = journal.hash_lines(new_text)

    if after_hash == before_hash:
        # No-op transactions are explicitly NOT journaled (per spec).
        return MutationResult(
            tx_id="",
            op=op,
            slug=slug,
            no_op=True,
            before_hash=before_hash,
            after_hash=after_hash,
            line=target_line,
            new_text=new_text,
        )

    tx_id = str(uuid.uuid4())

    # Step P (prepared)
    journal.write_prepared(
        slug,
        tx_id=tx_id,
        op=op,
        actor=actor,
        line=target_line,
        before_hash=before_hash,
        after_hash=after_hash,
        before_line_hashes=before_line_hashes,
        after_line_hashes=after_line_hashes,
        extra=extra,
    )

    # Step W (write)
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = backlog_path.with_name(f"{backlog_path.name}.tx-{tx_id}")
    tmp_path.write_text(new_text, encoding="utf-8")
    _fsync_file(tmp_path)
    os.replace(tmp_path, backlog_path)
    _fsync_parent(backlog_path)

    # Step C (committed)
    journal.write_committed(slug, tx_id, recovered=False)

    return MutationResult(
        tx_id=tx_id,
        op=op,
        slug=slug,
        no_op=False,
        before_hash=before_hash,
        after_hash=after_hash,
        line=target_line,
        new_text=new_text,
    )
