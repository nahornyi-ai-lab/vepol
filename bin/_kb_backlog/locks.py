"""locks.py — global lock order + flock acquisition.

Canonical global lock order (CR8-B2 + CR9-N1):

    _xfer.lock < <slug-A>.lock < <slug-B>.lock < ... < spawns.lock

where per-slug locks are sorted alphabetically.

Subset rule: any path may acquire a *subset* of these locks, but the relative
order must be preserved. Examples:

    Normal single-backlog mutation:  <slug>.lock then spawns.lock
    Xfer:                            _xfer.lock then <slug-A>.lock then <slug-B>.lock then spawns.lock
    Detector:                        <slug>.lock then spawns.lock

Held-locks are passed explicitly between functions as `set[LockId]`. The
internal mutation primitive asserts `required_locks ⊆ held_locks`.
"""
from __future__ import annotations

import errno
import fcntl
import os
import pathlib
import time
from contextlib import contextmanager
from dataclasses import dataclass

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))
LOCK_DIR = HUB / ".orchestrator" / "locks"

# Ranks for the canonical global lock order. Lower rank = acquired first.
RANK_XFER = 0
RANK_SLUG_BASE = 100  # _slug locks share this rank, sorted by name within
RANK_SPAWNS = 1000


@dataclass(frozen=True, eq=True, order=True)
class LockId:
    """Canonical identifier for a lock.

    Comparing two LockIds with `<` follows the global order:
    `_xfer < <slug-A> < <slug-B> < spawns` (per-slug alphabetical).
    """
    rank: int
    name: str

    @property
    def path(self) -> pathlib.Path:
        return LOCK_DIR / f"{self.name}.lock"

    @classmethod
    def xfer(cls) -> "LockId":
        return cls(RANK_XFER, "_xfer")

    @classmethod
    def spawns(cls) -> "LockId":
        return cls(RANK_SPAWNS, "spawns")

    @classmethod
    def slug(cls, slug: str) -> "LockId":
        if slug in ("_xfer", "spawns"):
            raise ValueError(f"reserved slug name: {slug!r}")
        # Use slug name itself as tiebreaker — alphabetical ordering.
        return cls(RANK_SLUG_BASE, slug)

    def __str__(self) -> str:
        return self.name


def canonical_order(lock_ids: list[LockId]) -> list[LockId]:
    """Return the lock_ids sorted in canonical acquisition order."""
    return sorted(set(lock_ids))


def is_canonical_subset_order(acquired_sequence: list[LockId]) -> bool:
    """Lint helper: returns True iff acquired_sequence is in canonical order
    (i.e. is a subset of the global order with relative positions preserved).

    Used by tests/lock-order/ linter.
    """
    sorted_seq = canonical_order(acquired_sequence)
    return acquired_sequence == sorted_seq


class LockTimeout(Exception):
    """Raised when flock acquisition exceeded the timeout."""

    def __init__(self, lock_id: LockId, timeout_s: float):
        self.lock_id = lock_id
        self.timeout_s = timeout_s
        super().__init__(f"lock {lock_id.name!r} not acquired within {timeout_s}s")


def _ensure_lock_file(lock_id: LockId) -> pathlib.Path:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    p = lock_id.path
    if not p.exists():
        p.touch()
    return p


def _flock_with_timeout(fh, lock_id: LockId, timeout_s: float):
    """Acquire fcntl.LOCK_EX with deadline + exponential backoff.

    Initial sleep 50 ms, doubling up to 1.5 s, capped at 90 s overall by
    LockTimeout caller (per Phase 1b CR5-N2: 30s default, exp retry up to 90s).
    """
    deadline = time.monotonic() + timeout_s
    delay = 0.05
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except (BlockingIOError, OSError) as exc:
            if isinstance(exc, OSError) and exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
        if time.monotonic() >= deadline:
            raise LockTimeout(lock_id, timeout_s)
        time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
        delay = min(delay * 2, 1.5)


@contextmanager
def acquire(lock_ids: list[LockId], timeout_s: float = 30.0):
    """Acquire a list of locks in canonical order. Yields the held set.

    On any timeout, releases everything already acquired and re-raises.
    """
    sorted_ids = canonical_order(lock_ids)
    handles: list[tuple[LockId, "object"]] = []
    try:
        for lid in sorted_ids:
            p = _ensure_lock_file(lid)
            fh = open(p, "w")
            try:
                _flock_with_timeout(fh, lid, timeout_s)
            except LockTimeout:
                fh.close()
                raise
            handles.append((lid, fh))
        held = set(lid for lid, _ in handles)
        yield held
    finally:
        # Release in reverse order.
        for lid, fh in reversed(handles):
            try:
                fcntl.flock(fh, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                fh.close()
            except Exception:
                pass


def required_locks_for_op(slug: str, op: str) -> set[LockId]:
    """Returns the set of locks required for a given operation on `slug`.

    Used by mutation primitive `_apply_mutation` to assert held_locks ⊇ required.
    """
    base = {LockId.slug(slug), LockId.spawns()}
    if op == "xfer":
        # xfer requires both src+dst slug locks plus xfer coordinator —
        # caller passes its own slug pair via separate API.
        raise ValueError("xfer ops resolved through xfer.required_locks_for_xfer()")
    return base


def required_locks_for_xfer(src: str, dst: str) -> set[LockId]:
    """Returns the canonical lock set for a cross-backlog xfer."""
    if src == dst:
        raise ValueError(f"xfer src == dst not allowed: {src!r}")
    return {
        LockId.xfer(),
        LockId.slug(src),
        LockId.slug(dst),
        LockId.spawns(),
    }


def assert_required_held(slug: str, op: str, held: set[LockId]) -> None:
    """Raises RuntimeError if held does not contain required locks."""
    required = required_locks_for_op(slug, op)
    missing = required - held
    if missing:
        names = ", ".join(sorted(m.name for m in missing))
        raise RuntimeError(
            f"_apply_mutation called without required locks for slug={slug!r} op={op!r}: "
            f"missing {{{names}}}; held {{{', '.join(sorted(h.name for h in held))}}}"
        )
