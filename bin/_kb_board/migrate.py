"""Migration and dry-run cutover helpers for kb-board."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .check import check_board_text
from .fmt import format_board
from .model import Board, TaskBlock
from .mutation import BoardMutationError, _iso, _parse_now

LEGACY_TASK_RE = re.compile(r"^-\s*(?P<marker>\[[ xX>~]\])\s+(?P<body>.+?)\s*$")
LEGACY_FIELD_RE = re.compile(
    r"(?:^|\s—\s)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*"
    r"(?P<value>.+?)(?=\s—\s[A-Za-z_][A-Za-z0-9_-]*\s*:|$)"
)


@dataclass
class CutoverStep:
    action: str
    detail: str


@dataclass
class CutoverPlan:
    steps: list[CutoverStep]


def _legacy_fields(body: str) -> tuple[str, dict[str, str]]:
    parts = body.split(" — ")
    title_parts = [parts[0].strip()]
    fields: dict[str, str] = {}
    for part in parts[1:]:
        if part.startswith("opened "):
            fields["opened"] = part[len("opened "):].strip()
            continue
        m = re.match(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*)$", part)
        if m:
            fields[m.group("key")] = m.group("value").strip()
        else:
            title_parts.append(part.strip())
    return " — ".join(p for p in title_parts if p), fields


def _section_for(section: str | None, marker: str) -> str:
    if marker in {"[x]", "[X]"}:
        return "Done"
    if marker == "[~]":
        return "Cancelled"
    if marker == "[>]":
        return "In Progress"
    if section == "Done":
        return "Done"
    if section == "In Progress":
        return "In Progress"
    if section == "Cancelled":
        return "Cancelled"
    if section == "Blocked":
        return "Blocked"
    if section == "Ready":
        return "Ready"
    # Legacy `## Open` is intentionally conservative: ambiguous `[ ]` becomes
    # Backlog, not Ready.
    return "Backlog"


def _claim_owner(fields: dict[str, str], fallback: str) -> str:
    picked = fields.get("picked", "")
    m = re.search(r"\bby\s+(.+)$", picked)
    return m.group(1).strip() if m else fallback


def migrate_text(text: str, *, owner: str = "unassigned", now: str | None = None) -> str:
    parsed_now = _parse_now(now)
    now_date = _iso(parsed_now).split("T")[0]
    board = Board(title="Backlog", sections={})
    current_section: str | None = None

    for line in text.splitlines():
        if line.startswith("# "):
            board.title = line[2:].strip()
            continue
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        m = LEGACY_TASK_RE.match(line)
        if not m:
            continue
        marker = m.group("marker")
        title, legacy = _legacy_fields(m.group("body"))
        status = _section_for(current_section, marker)
        plan_item_id = legacy.get("plan_item_id") or legacy.get("cycle_source_id")
        if not plan_item_id:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "legacy"
            plan_item_id = f"legacy-{slug}"
        created = legacy.get("opened", "").split(" ", 1)[0] or now_date

        fields = {
            "plan_item_id": plan_item_id,
            "priority": legacy.get("priority", "P2"),
            "owner": legacy.get("owner", owner),
            "created": created,
            "updated": now_date,
            "acceptance": legacy.get("acceptance", "Migrated legacy task preserves title and context."),
            "body": legacy.get("context", legacy.get("prompt", "")) or "Migrated from legacy one-line backlog item.",
        }
        if status == "In Progress":
            fields["claim_owner"] = _claim_owner(legacy, owner)
            fields["claim_id"] = legacy.get("claim_id", "legacy-claim")
            fields["claim_expires_at"] = _iso(parsed_now.replace() + __import__("datetime").timedelta(minutes=15))
        if status in {"Done", "Cancelled"}:
            evidence = legacy.get("result") or legacy.get("closed") or "Migrated terminal legacy item."
            fields["evidence"] = evidence
        for key, value in legacy.items():
            if key in {
                "status",
                "plan_item_id",
                "priority",
                "owner",
                "context",
                "prompt",
                "acceptance",
                "claim_id",
            }:
                continue
            if key not in fields:
                fields[key] = value
        task = TaskBlock(title=title, status=status, marker=marker, fields=fields)
        board.sections.setdefault(status, []).append(task)

    migrated = format_board(board)
    result = check_board_text(migrated)
    if not result.ok:
        raise BoardMutationError("EMIGRATE", f"migrated board failed check: {result.errors!r}")
    return migrated


def fail_fast_stub_source() -> str:
    return """#!/usr/bin/env python3
import sys

sys.stderr.write(
    "fail-fast: legacy kb-backlog writer disabled after kb-board cutover; "
    "use kb-board for all task mutations.\\n"
)
raise SystemExit(64)
"""


def plan_cutover(*, board_path: str, old_writer_paths: list[str], candidate_path: str) -> CutoverPlan:
    writers = ", ".join(old_writer_paths)
    return CutoverPlan(
        steps=[
            CutoverStep("pause_writers", "pause agents/ticks before touching the live board"),
            CutoverStep("backup_live_board", f"copy {board_path} to a timestamped backup"),
            CutoverStep("install_old_writer_fail_fast", f"install fail-fast stubs for: {writers}"),
            CutoverStep("verify_old_writer_fail_fast", "smoke old writer paths and require non-zero fail-fast"),
            CutoverStep("generate_migration_candidate", f"write migrated candidate to {candidate_path}"),
            CutoverStep("fmt_candidate", "run kb-board fmt on the candidate"),
            CutoverStep("check_candidate", "run kb-board check on the candidate"),
            CutoverStep("diff_review", "human reviews backup-to-candidate diff"),
            CutoverStep("migrate_live_board", f"atomically replace {board_path} with checked candidate"),
            CutoverStep("wire_run_all", "wire kb-board tests into run-all after live cutover"),
            CutoverStep("resume_writers", "resume agents/ticks after post-cutover checks"),
        ]
    )
