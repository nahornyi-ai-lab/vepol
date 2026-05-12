"""Stdout-silence watchdog — concept §7.4 + Q9.

Each spawned agent process is monitored: if it doesn't write to stdout for
more than `watchdog_silence_sec` (default 900s = 15 min), supervisor sends
SIGTERM. After SIGTERM, supervisor waits 5s then SIGKILL (concept §7.4
kill-switch + watchdog semantics).

This module owns the per-run last_stdout_ts state and provides a single
`expired_runs(now)` query. Supervisor's event loop polls this periodically
(e.g., every 5s) and kills runs that exceed silence threshold.

stdout updates come from spawner.py: every time it reads a chunk from the
subprocess's stdout pipe, it calls watchdog.touch(run_id) — this is the
single "I'm alive" signal.

Why not OS-level mechanism (e.g., a timer per process)? Because supervisor
also needs to track these timestamps for diagnostic reporting ("процесс
молчал 15 мин, прервал" — concept §7.8) and for catchup-on-restart logic.
In-memory dict on supervisor instance is simplest.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Dict


def _now_epoch() -> float:
    return dt.datetime.now(dt.timezone.utc).timestamp()


@dataclasses.dataclass
class WatchedRun:
    """Runtime watchdog state for one spawned agent process.

    `last_stdout_ts` updates each time spawner reads a chunk. `silence_sec`
    is per-agent override or default 900s. `pid` for SIGTERM/SIGKILL.
    """

    run_id: str
    agent_slug: str
    pid: int
    started_at: float  # epoch seconds
    last_stdout_ts: float  # epoch seconds, updates over run lifetime
    silence_sec: int = 900
    hard_timeout_sec: int | None = None  # optional, off by default


class Watchdog:
    """Per-supervisor watchdog registry.

    Instances live for supervisor process lifetime. Add() when spawn starts,
    touch() on stdout activity, remove() on completion or kill.
    """

    def __init__(self) -> None:
        self._watched: Dict[str, WatchedRun] = {}

    def add(
        self,
        run_id: str,
        agent_slug: str,
        pid: int,
        silence_sec: int = 900,
        hard_timeout_sec: int | None = None,
        now: float | None = None,
    ) -> None:
        """Register a new spawned run for watchdog monitoring."""
        n = now if now is not None else _now_epoch()
        self._watched[run_id] = WatchedRun(
            run_id=run_id,
            agent_slug=agent_slug,
            pid=pid,
            started_at=n,
            last_stdout_ts=n,
            silence_sec=silence_sec,
            hard_timeout_sec=hard_timeout_sec,
        )

    def touch(self, run_id: str, now: float | None = None) -> None:
        """Mark stdout activity — called by spawner on each chunk read.

        Silently no-op for unknown run_id (race during kill is acceptable).
        """
        wr = self._watched.get(run_id)
        if wr is None:
            return
        wr.last_stdout_ts = now if now is not None else _now_epoch()

    def remove(self, run_id: str) -> None:
        """Stop watching this run — called when process exits naturally or after kill."""
        self._watched.pop(run_id, None)

    def get(self, run_id: str) -> WatchedRun | None:
        return self._watched.get(run_id)

    def __contains__(self, run_id: str) -> bool:
        return run_id in self._watched

    def __len__(self) -> int:
        return len(self._watched)

    def expired_runs(self, now: float | None = None) -> list[tuple[WatchedRun, str]]:
        """Return runs that should be killed, with reason.

        Reason is "silence" if stdout-quiet too long, "timeout" if hard
        timeout exceeded. Caller (supervisor) iterates and issues SIGTERM
        per result.

        Returns list of (WatchedRun, reason_string) tuples.
        """
        n = now if now is not None else _now_epoch()
        out: list[tuple[WatchedRun, str]] = []
        for wr in self._watched.values():
            silence_age = n - wr.last_stdout_ts
            if silence_age >= wr.silence_sec:
                out.append((wr, "silence"))
                continue
            if wr.hard_timeout_sec is not None:
                run_age = n - wr.started_at
                if run_age >= wr.hard_timeout_sec:
                    out.append((wr, "timeout"))
        return out

    def all_runs(self) -> list[WatchedRun]:
        """Snapshot for diagnostics."""
        return list(self._watched.values())


__all__ = ["Watchdog", "WatchedRun"]
