"""Standalone validator for the multiline kb-board format."""
from __future__ import annotations

from dataclasses import dataclass, field

from .fmt import format_board_text
from .model import MARKER_BY_STATUS, REQUIRED_FIELDS, STATUS_ORDER, TaskBlock
from .parsing import parse_board, parse_depends_on


@dataclass
class CheckError:
    code: str
    message: str
    plan_item_id: str | None = None
    line: int | None = None


@dataclass
class CheckResult:
    ok: bool
    errors: list[CheckError] = field(default_factory=list)


def _claim_fields(task: TaskBlock) -> set[str]:
    return {key for key in ("claim_owner", "claim_id", "claim_expires_at") if task.fields.get(key)}


def _add(errors: list[CheckError], code: str, message: str, task: TaskBlock | None = None) -> None:
    errors.append(
        CheckError(
            code=code,
            message=message,
            plan_item_id=task.fields.get("plan_item_id") if task else None,
            line=task.line if task else None,
        )
    )


def _check_dep_cycles(tasks: list[TaskBlock], errors: list[CheckError]) -> None:
    by_id = {t.fields.get("plan_item_id"): t for t in tasks if t.fields.get("plan_item_id")}
    graph = {
        pid: [dep for dep in parse_depends_on(task.fields.get("depends_on")) if dep in by_id]
        for pid, task in by_id.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(pid: str, path: list[str]) -> None:
        if pid in visited:
            return
        if pid in visiting:
            cycle = path[path.index(pid):] + [pid] if pid in path else path + [pid]
            _add(errors, "EDEPENDS_CYCLE", "depends_on cycle: " + " -> ".join(cycle), by_id.get(pid))
            return
        visiting.add(pid)
        for dep in graph.get(pid, []):
            dfs(dep, path + [dep])
        visiting.remove(pid)
        visited.add(pid)

    for pid in list(graph):
        dfs(pid, [pid])


def check_board_text(text: str) -> CheckResult:
    board = parse_board(text)
    errors: list[CheckError] = []
    seen: dict[str, TaskBlock] = {}
    tasks = board.tasks

    for task in tasks:
        pid = task.fields.get("plan_item_id")
        if "status" in task.fields:
            _add(errors, "ESTATUS_FIELD", "status field is forbidden; section is the only status", task)
        missing = sorted(key for key in REQUIRED_FIELDS if not task.fields.get(key))
        if missing:
            _add(errors, "EREQUIRED", "missing required fields: " + ", ".join(missing), task)
        if pid:
            if pid in seen:
                _add(errors, "EDUPLICATE_ID", f"duplicate plan_item_id {pid}", task)
            seen[pid] = task
        expected_marker = MARKER_BY_STATUS.get(task.status)
        if expected_marker and task.marker != expected_marker:
            _add(errors, "EMARKER", f"{task.status} marker must be {expected_marker}", task)
        claims = _claim_fields(task)
        if task.status in {"In Progress", "Review"}:
            missing_claim = {"claim_owner", "claim_id", "claim_expires_at"} - claims
            if missing_claim:
                _add(errors, "ECLAIM_FIELDS", "missing claim fields: " + ", ".join(sorted(missing_claim)), task)
        elif claims:
            _add(errors, "ECLAIM_FIELDS", "claim fields are only allowed in In Progress or Review", task)

    ids = set(seen)
    for task in tasks:
        for dep in parse_depends_on(task.fields.get("depends_on")):
            if dep not in ids:
                _add(errors, "EDEPENDS_MISSING", f"depends_on reference does not exist: {dep}", task)

    _check_dep_cycles(tasks, errors)

    try:
        formatted = format_board_text(text)
        if formatted != text:
            # Keep this as a warning-like validation error only when no more
            # precise marker issue already explains a common fmt drift.
            marker_errors = any(e.code == "EMARKER" for e in errors)
            if not marker_errors:
                _add(errors, "EFMT", "board is not canonical fmt output")
    except Exception as exc:
        _add(errors, "EPARSE", f"format parse failed: {exc}")

    # Do not require every section to be present; sparse fixture boards are valid.
    unknown_sections = [s for s in board.sections if s not in STATUS_ORDER]
    for section in unknown_sections:
        _add(errors, "ESECTION", f"unknown section: {section}")

    return CheckResult(ok=not errors, errors=errors)
