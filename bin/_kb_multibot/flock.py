"""Per-agent file lock — enforces "one process per agent globally" (concept §7.4).

Implementation: fcntl.flock on `~/.orchestrator/multibot/watchdog/<agent_slug>.lock`.
Each supervisor task that wants to spawn an agent first calls `acquire`. If
another spawn is already holding the lock (i.e., that agent is currently
running), the queue dispatcher waits (or queues, depending on caller policy).

Non-blocking try-acquire is the primary mode — supervisor uses queue logic to
defer rather than block on a lock. Blocking acquire is available for tests.

The lock file also doubles as a marker for activity_ts (last touched time) —
watchdog.py reads file mtime to detect stuck processes that crashed without
releasing the lock.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import time
from pathlib import Path


class AgentLockBusy(Exception):
    """Raised by try_acquire when another holder owns the lock."""


class AgentLock:
    """fcntl.flock-based exclusive lock per agent_slug.

    Lock file: `~/.orchestrator/multibot/watchdog/<agent_slug>.lock`
    Created on first acquire; not deleted on release (keeps mtime history).
    """

    def __init__(self, lock_dir: str | Path, agent_slug: str):
        if not agent_slug or "/" in agent_slug or ".." in agent_slug:
            raise ValueError(f"invalid agent_slug: {agent_slug!r}")
        self._dir = Path(lock_dir)
        self._slug = agent_slug
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        return self._dir / f"{self._slug}.lock"

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def try_acquire(self) -> None:
        """Non-blocking acquire. Raises AgentLockBusy if held by another process.

        Caller's responsibility to release via `release()` or use as context
        manager. Re-entrant acquire from the same process raises ValueError
        (avoid double-locking bugs).
        """
        if self._fd is not None:
            raise ValueError(f"lock {self._slug} already held by this instance")
        self._ensure_dir()
        # O_CREAT|O_RDWR — owned by user, perms 0644 (lock file content is
        # irrelevant, just used for flock semantics).
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise AgentLockBusy(f"agent {self._slug} is currently running")
            raise
        self._fd = fd
        # Touch mtime — watchdog reads this for activity check
        os.utime(self.path, None)

    def acquire_blocking(self, timeout: float | None = None) -> None:
        """Blocking acquire with optional timeout in seconds.

        Implemented via polling (try + sleep) since flock has no timeout
        natively. For tests; supervisor uses non-blocking.
        """
        if self._fd is not None:
            raise ValueError(f"lock {self._slug} already held")
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            try:
                self.try_acquire()
                return
            except AgentLockBusy:
                if deadline is not None and time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    def touch_activity(self) -> None:
        """Update mtime on lock file — watchdog uses to detect liveness.

        Called by spawner each time it reads new stdout chunk from spawned
        process. Watchdog separately checks mtime against silence threshold.
        """
        if not self.path.exists():
            return
        os.utime(self.path, None)

    def last_activity_ts(self) -> float | None:
        """Return lock file's mtime as epoch seconds, or None if no file."""
        try:
            return self.path.stat().st_mtime
        except FileNotFoundError:
            return None

    def release(self) -> None:
        """Release the lock. Idempotent — safe to call when not held."""
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def is_held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> AgentLock:
        self.try_acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


@contextlib.contextmanager
def with_agent_lock(lock_dir: str | Path, agent_slug: str):
    """Context-manager convenience wrapper."""
    lock = AgentLock(lock_dir, agent_slug)
    lock.try_acquire()
    try:
        yield lock
    finally:
        lock.release()


__all__ = ["AgentLock", "AgentLockBusy", "with_agent_lock"]
