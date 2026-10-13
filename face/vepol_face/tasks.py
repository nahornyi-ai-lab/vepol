"""Tasks view: every project's backlog through the hub's kb-board.

The app never writes backlog.md itself: reading and the one change it offers
(close a task, undo that close) both go through kb-board.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
from concurrent.futures import ThreadPoolExecutor

from . import targets as targets_mod

LIST_TIMEOUT = 10
CHANGE_TIMEOUT = 20
STALE_MESSAGE = "The task changed since the list was loaded — refreshed."
UNDO_REASON = "undo of a close in Vepol Desktop"


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
         "status": r.get("status"), "owner": r.get("claim_owner"), "content_hash": r.get("content_hash")}
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


class TaskChangeRefused(Exception):
    """kb-board refused or failed the change; status is the HTTP code for the page."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _board_of(hub: pathlib.Path, project: str) -> pathlib.Path:
    """The backlog.md of a known project. Unknown slug or no board -> KeyError."""
    for t in targets_mod.discover_targets(hub):
        if t.slug == project:
            board = pathlib.Path(t.knowledge) / "backlog.md"
            if board.is_file():
                return board
            break
    raise KeyError(project)


def change_task(hub: pathlib.Path, op: str, body: dict) -> dict:
    """Close (op "cancel") or undo a close (op "reopen") of one task through kb-board.

    Bad input -> ValueError, unknown project -> KeyError, kb-board refusal or failure -> TaskChangeRefused.
    """
    hub = pathlib.Path(hub)
    project, item, expected = (body.get(k) for k in ("project", "plan_item_id", "content_hash"))
    if not all(isinstance(v, str) and v.strip() for v in (project, item, expected)):
        raise ValueError("project, plan_item_id and content_hash are required")
    if op == "cancel":
        reason = body.get("reason") or ""
        if not isinstance(reason, str):
            raise ValueError("reason must be text")
        extra = [f"--reason={' '.join(reason.split())}"] if reason.strip() else []
    elif op == "reopen":
        to = body.get("to")
        if to not in ("Ready", "Backlog"):
            raise ValueError("to must be Ready or Backlog")
        extra = [f"--to={to}", f"--reason={UNDO_REASON}"]
    else:
        raise ValueError(f"unsupported change {op!r}")
    board = _board_of(hub, project)
    kb_board = hub / "bin" / "kb-board"
    if not kb_board.is_file():
        raise TaskChangeRefused(502, f"kb-board not found: {kb_board}")
    # "--opt=value" so a value starting with "-" is never read as an option.
    argv = [str(kb_board), op, str(board), f"--plan-item-id={item}", f"--expected-hash={expected}",
            "--actor=owner", *extra, "--json"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=CHANGE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise TaskChangeRefused(502, f"kb-board did not answer within {CHANGE_TIMEOUT} s")
    except OSError as exc:
        raise TaskChangeRefused(502, str(exc))
    try:
        reply = json.loads(proc.stdout)
    except ValueError:
        reply = None
    if not isinstance(reply, dict):
        reply = {}
    if proc.returncode == 0 and reply:
        return reply
    if reply.get("code") == "EHASH":
        raise TaskChangeRefused(409, STALE_MESSAGE)
    if reply.get("code") == "ETRANSITION":
        raise TaskChangeRefused(409, str(reply.get("message") or "ETRANSITION"))
    lines = [line.strip() for line in proc.stderr.splitlines() if line.strip()]
    raise TaskChangeRefused(502, lines[-1] if lines else str(reply.get("message") or f"kb-board exited {proc.returncode}"))
