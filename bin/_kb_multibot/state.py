"""Service state IO — atomic file operations for queues, runs, observer offset, locks.

Concept §7.2: supervisor хранит operational state в `~/.orchestrator/multibot/`:
  queues/<agent_slug>.json       FIFO per agent
  runs/<run_id>.json             one run per file
  observer/last_seen_msg_id.json per-chat for catchup
  watchdog/<agent_slug>.lock     per-agent flock (managed in flock.py, not here)
  cache/<chat_id>.json           rolling buffer (in-memory primary, opt. persisted)

All file writes are atomic (tmp+rename in same directory). Reads tolerate missing
files (return empty defaults). No locking inside this module — caller coordinates
via flock.py if multiple writers possible. Supervisor is single-process, so most
writes are single-writer by construction.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .events import QueueEntry, RunState


# Default state root — overridable by tests via env var or constructor.
DEFAULT_STATE_ROOT = Path.home() / ".orchestrator" / "multibot"


class StateStore:
    """Service state IO root. All paths derived from `root`."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else DEFAULT_STATE_ROOT
        self.queues = self.root / "queues"
        self.runs = self.root / "runs"
        self.observer = self.root / "observer"
        self.watchdog = self.root / "watchdog"
        self.cache = self.root / "cache"

    def ensure_dirs(self) -> None:
        """Create all subdirs idempotently — called on supervisor startup."""
        for d in (self.queues, self.runs, self.observer, self.watchdog, self.cache):
            d.mkdir(parents=True, exist_ok=True)

    # ----- Atomic write helper -----

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """tmp+rename atomic write in the same directory.

        os.replace is atomic on POSIX (rename(2)). Tmp file in same dir so
        rename doesn't cross filesystem boundary. fsync of file before rename
        for crash safety (concept R6 supervisor SPOF + R7 catchup).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    # ----- Queues -----

    def queue_path(self, agent_slug: str) -> Path:
        return self.queues / f"{agent_slug}.json"

    def read_queue(self, agent_slug: str) -> list[QueueEntry]:
        path = self.queue_path(agent_slug)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [QueueEntry.from_dict(e) for e in data]

    def write_queue(self, agent_slug: str, queue: list[QueueEntry]) -> None:
        content = json.dumps(
            [e.to_dict() for e in queue], ensure_ascii=False, indent=2
        )
        self._atomic_write(self.queue_path(agent_slug), content)

    # ----- Runs -----

    def run_path(self, run_id: str) -> Path:
        # run_id is sanitized to filename — supervisor uses UUID hex so safe.
        if not run_id or "/" in run_id or ".." in run_id:
            raise ValueError(f"invalid run_id: {run_id!r}")
        return self.runs / f"{run_id}.json"

    def read_run(self, run_id: str) -> RunState | None:
        path = self.run_path(run_id)
        if not path.is_file():
            return None
        try:
            return RunState.from_json(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return None

    def write_run(self, run: RunState) -> None:
        self._atomic_write(self.run_path(run.run_id), run.to_json())

    def list_runs(self) -> list[RunState]:
        if not self.runs.is_dir():
            return []
        out: list[RunState] = []
        for p in sorted(self.runs.glob("*.json")):
            try:
                out.append(RunState.from_json(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                continue
        return out

    def children_of_parent_run(self, parent_run_id: str) -> list[RunState]:
        """parent → children tracking via parent_run_id linkage.

        Supervisor uses this to build "children status" summary injected into
        parent's resume prompt.
        """
        return [r for r in self.list_runs() if r.parent_run_id == parent_run_id]

    # ----- Observer offset (catchup) -----

    def observer_path(self) -> Path:
        return self.observer / "last_seen_msg_id.json"

    def read_observer_offsets(self) -> dict[int, int]:
        """Map chat_id (int) → last seen message_id (int).

        JSON object keys are strings — we coerce to int. On corrupted file
        returns empty dict and supervisor will resync from latest (no catchup).
        """
        path = self.observer_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[int, int] = {}
        for k, v in data.items():
            try:
                out[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
        return out

    def write_observer_offset(self, chat_id: int, message_id: int) -> None:
        offsets = self.read_observer_offsets()
        offsets[chat_id] = message_id
        content = json.dumps({str(k): v for k, v in offsets.items()}, indent=2)
        self._atomic_write(self.observer_path(), content)


__all__ = ["StateStore", "DEFAULT_STATE_ROOT"]
