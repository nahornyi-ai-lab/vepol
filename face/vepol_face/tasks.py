"""Read-only Tasks view: every project's backlog through the hub's kb-board.

The app never writes backlog.md; kb-board and the agents own it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
from concurrent.futures import ThreadPoolExecutor

from . import targets as targets_mod

LIST_TIMEOUT = 10


def _read_board(kb_board: pathlib.Path, slug: str, board: pathlib.Path) -> dict:
    if not board.is_file():
        return {"project": slug, "state": "none"}
    try:
        proc = subprocess.run(
            [str(kb_board), "list", str(board), "--all", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=LIST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"project": slug, "state": "error", "reason": "timeout"}
    except OSError as exc:
        return {"project": slug, "state": "error", "reason": str(exc)}
    lines = [line for line in proc.stderr.splitlines() if line.strip()]
    reason = lines[-1].strip() if lines else f"kb-board exited {proc.returncode}"
    if proc.returncode != 0:
        return {"project": slug, "state": "error", "reason": reason}
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return {"project": slug, "state": "error", "reason": reason if lines else "kb-board output is not a JSON list"}
    tasks = [
        {"id": r.get("plan_item_id"), "title": r.get("title"),
         "status": r.get("status"), "owner": r.get("claim_owner")}
        for r in rows
    ]
    return {"project": slug, "state": "ok", "tasks": tasks}


def list_tasks(hub: pathlib.Path, target: str | None) -> dict:
    """Tasks of one target (or all when target is empty). Unknown slug -> KeyError."""
    hub = pathlib.Path(hub)
    targets = targets_mod.discover_targets(hub)
    if target:
        targets = [t for t in targets if t.slug == target]
        if not targets:
            raise KeyError(target)
    kb_board = hub / "bin" / "kb-board"
    if not kb_board.is_file():
        return {"error": f"kb-board not found: {kb_board}"}
    with ThreadPoolExecutor(max_workers=8) as pool:
        projects = list(pool.map(
            lambda t: _read_board(kb_board, t.slug, pathlib.Path(t.knowledge) / "backlog.md"),
            targets,
        ))
    return {"projects": projects}
