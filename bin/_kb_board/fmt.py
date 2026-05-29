"""Canonical formatter for multiline kb-board markdown."""
from __future__ import annotations

from .model import FIELD_ORDER, MARKER_BY_STATUS, MULTILINE_FIELDS, STATUS_ORDER, Board, TaskBlock
from .parsing import parse_board, parse_depends_on


def _field_keys(task: TaskBlock) -> list[str]:
    ordered = [key for key in FIELD_ORDER if key in task.fields]
    extra = sorted(k for k in task.fields if k not in FIELD_ORDER and k != "status")
    return ordered + extra


def _normalize_inline_value(key: str, value: str) -> str:
    if key == "depends_on":
        deps = parse_depends_on(value)
        return "[" + ", ".join(deps) + "]"
    return " ".join(value.strip().split()) if "\n" not in value else value.rstrip()


def _render_task(task: TaskBlock) -> list[str]:
    marker = MARKER_BY_STATUS.get(task.status, task.marker)
    out = [f"- {marker} {task.title.strip()}"]
    for key in _field_keys(task):
        value = task.fields[key]
        if key in MULTILINE_FIELDS or "\n" in value:
            out.append(f"  {key}: |")
            if value:
                for line in value.rstrip("\n").splitlines():
                    out.append(f"    {line.rstrip()}")
        else:
            out.append(f"  {key}: {_normalize_inline_value(key, value)}")
    return out


def format_board(board: Board) -> str:
    out = [f"# {board.title.strip()}", ""]
    for status in STATUS_ORDER:
        tasks = board.sections.get(status, [])
        if not tasks:
            continue
        out.append(f"## {status}")
        out.append("")
        for idx, task in enumerate(tasks):
            out.extend(_render_task(task))
            if idx != len(tasks) - 1:
                out.append("")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def format_board_text(text: str) -> str:
    return format_board(parse_board(text))
