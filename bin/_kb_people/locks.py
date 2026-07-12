"""locks.py — shared `.cards.lock` for the _kb_people domain.

Per Codex Layer-2 review (2026-05-07) of
~/knowledge/concepts/people-extraction-from-projects.md, point 7 / IP-C
"Card/index atomicity prerequisite":

    All card + _index.yaml RMWs (kb-contact, kb-calendar-sync, extractor
    approve/apply, plus card.create itself) must use the shared
    .cards.lock.

This module provides a single fcntl-based exclusive file lock used by
card.py and index.py. It is intentionally small and dependency-free:
no third-party `filelock` package, no JSON state, no canonical lock
ordering machinery (the people domain is leaf-level — `.cards.lock`
sits below `people-extraction.lock` and `.cycle.lock` in the global
order; nothing else here acquires both).

Usage:

    from _kb_people.locks import cards_lock

    with cards_lock():
        # Read-modify-write _index.yaml and/or per-card files.
        ...

The lock file lives at `<PEOPLE_DIR>/.cards.lock` by default; tests
that override `PEOPLE_DIR` automatically see their isolated lock.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path
from typing import Iterator


def _lock_path() -> Path:
    """Resolve the lock path lazily so that test overrides of
    `card.PEOPLE_DIR` are honoured. We import at call time, not at
    module import, because `card.PEOPLE_DIR` is the canonical pointer
    that tests mutate."""
    from . import card as _card  # local import avoids cycle at load
    return _card.PEOPLE_DIR / ".cards.lock"


@contextlib.contextmanager
def cards_lock(timeout_s: float = 30.0) -> Iterator[None]:
    """Acquire an exclusive lock on `<PEOPLE_DIR>/.cards.lock`.

    Blocks (with periodic retries) up to `timeout_s` seconds. Raises
    TimeoutError on contention failure — callers should treat this as
    "another writer holds the lock too long, abort and retry the user
    operation".

    The lock is released on exit even if the body raises.
    """
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Open in append mode so the file exists across runs without us
    # rewriting it; fcntl operates on the FD, not the file content.
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        # Try non-blocking first, then fall back to blocking with a
        # deadline so we can raise on real contention rather than
        # sit forever.
        import time
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"cards_lock: contention on {lock_path} "
                        f"exceeded {timeout_s}s"
                    )
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                # Releasing on a closed fd is benign; surface nothing.
                pass
    finally:
        os.close(fd)
