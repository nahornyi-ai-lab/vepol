"""Parser for multiline task blocks in `knowledge/backlog.md`."""
from __future__ import annotations

import re

from .model import Board, STATUS_ORDER, TaskBlock, VALID_MARKERS

SECTION_RE = re.compile(r"^##\s+(?P<status>.+?)\s*$")
TASK_RE = re.compile(r"^-\s*(?P<marker>\[[ xX>~]\])\s+(?P<title>.+?)\s*$")
FIELD_RE = re.compile(r"^  (?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:\s*(?P<value>.*))?$")


def _is_section(line: str) -> str | None:
    m = SECTION_RE.match(line)
    if not m:
        return None
    status = m.group("status")
    return status if status in STATUS_ORDER else None


def _is_task(line: str) -> bool:
    m = TASK_RE.match(line)
    return bool(m and m.group("marker") in VALID_MARKERS)


def parse_board(text: str) -> Board:
    """Parse board markdown into a Board model.

    Task boundaries are column-0 status headings (`## <Status>`) or column-0
    task list items. Indented headings/list items inside literal block fields
    remain body text.
    """
    lines = text.splitlines()
    title = "Backlog"
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    board = Board(title=title, sections={status: [] for status in STATUS_ORDER})
    current_status: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        section = _is_section(line)
        if section is not None:
            current_status = section
            i += 1
            continue

        task_match = TASK_RE.match(line)
        if task_match and current_status in STATUS_ORDER:
            marker = task_match.group("marker")
            if marker == "[X]":
                marker = "[x]"
            task = TaskBlock(
                title=task_match.group("title").rstrip(),
                status=current_status,
                marker=marker,
                fields={},
                line=i + 1,
            )
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if _is_section(next_line) is not None or _is_task(next_line):
                    break
                fm = FIELD_RE.match(next_line)
                if not fm:
                    i += 1
                    continue
                key = fm.group("key")
                value = (fm.group("value") or "").rstrip()
                if value == "|":
                    i += 1
                    block: list[str] = []
                    while i < len(lines):
                        body_line = lines[i]
                        if _is_section(body_line) is not None or _is_task(body_line):
                            break
                        if FIELD_RE.match(body_line):
                            break
                        if body_line.startswith("    "):
                            block.append(body_line[4:])
                        elif body_line.startswith("  "):
                            block.append(body_line[2:])
                        else:
                            block.append(body_line)
                        i += 1
                    task.fields[key] = "\n".join(block).rstrip("\n")
                    continue
                task.fields[key] = value
                i += 1
            board.sections.setdefault(current_status, []).append(task)
            continue

        i += 1
    return board


def parse_depends_on(value: str | None) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [part.strip() for part in raw.split(",") if part.strip()]
