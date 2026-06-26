"""Locking primitives for Personal Idea OS card writes."""
from __future__ import annotations

import contextlib
import fcntl
import os
import time
from pathlib import Path
from typing import Iterator


def _lock_path(hub: Path) -> Path:
    return hub / "personal" / "ideas" / ".ideas.lock"


@contextlib.contextmanager
def ideas_lock(hub: Path, timeout_s: float = 30.0) -> Iterator[None]:
    """Acquire the per-hub Personal Idea OS writer lock."""
    lock_path = _lock_path(hub)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"ideas_lock: contention on {lock_path} exceeded {timeout_s}s"
                    )
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
    finally:
        os.close(fd)

