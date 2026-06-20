#!/usr/bin/env python3
"""Vepol Idea Intake acceptance tests.

Spec: docs/modules/idea-intake.md

These tests intentionally exercise the full thin vertical:
capture -> canonical card -> dashboard -> triage -> brief proposal ->
promotion handoff -> calendar approval -> outcome write-back.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import frontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bin"))

from _kb_ideas import card  # noqa: E402

PASS = 0
FAIL = 0


def ok(msg: str) -> None:
    global PASS
    print(f"  ✓ {msg}")
    PASS += 1


def fail(msg: str) -> None:
    global FAIL
    print(f"  ✗ {msg}")
    FAIL += 1


def make_hub() -> Path:
    root = Path(tempfile.mkdtemp(prefix="kb-idea-os-"))
    (root / "personal" / "ideas").mkdir(parents=True)
    (root / "personal" / "priority-profile.md").write_text(
        "# Priority Profile\n\nCurrent drivers: L0 income, L8 visible proof.\n",
        encoding="utf-8",
    )
    (root / "personal" / "ideas.md").write_text("# Ideas\n", encoding="utf-8")
    (root / "log.md").write_text("", encoding="utf-8")
    os.environ["KB_HUB"] = str(root)
    return root


def read_post(path: Path) -> frontmatter.Post:
    with path.open(encoding="utf-8") as f:
        return frontmatter.load(f)


def test_capture_creates_card_and_dashboard() -> None:
    hub = make_hub()
    created = card.capture(
        "Сделать Vepol Idea Intake как процесс, а не список идей.",
        source="chat",
        now="2026-06-16T10:35:00+02:00",
        hub=hub,
    )

    idea_id = created["id"]
    path = Path(created["path"])
    if idea_id != "idea-20260616-1035-vepol-idea-intake":
        fail(f"capture id mismatch: {idea_id}")
        return
    if not path.exists():
        fail("capture did not create canonical card")
        return
    post = read_post(path)
    required_sections = [
        "## Raw idea",
        "## Interpretation",
        "## Why it matters",
        "## Dedupe",
        "## Critique",
        "## Priority",
        "## Next action",
        "## Promotion",
        "## Outcome",
    ]
    missing = [s for s in required_sections if s not in post.content]
    if missing:
        fail(f"capture card missing sections: {missing}")
        return
    dashboard = (hub / "personal" / "ideas.md").read_text(encoding="utf-8")
    if idea_id not in dashboard or "captured" not in dashboard:
        fail("dashboard did not render captured idea")
        return
    ok("test_capture_creates_card_and_dashboard")


def test_capture_is_atomic_on_serializer_crash() -> None:
    hub = make_hub()
    canonical = hub / "personal" / "ideas" / "idea-20260616-1040-crashy-idea.md"
    raised = False
    try:
        with patch("frontmatter.dumps", side_effect=OSError("simulated serializer crash")):
            card.capture(
                "Crashy idea",
                source="chat",
                now="2026-06-16T10:40:00+02:00",
                hub=hub,
            )
    except OSError:
        raised = True

    if not raised:
        fail("atomic capture did not surface serializer crash")
        return
    if canonical.exists():
        fail("atomic capture leaked canonical partial file")
        return
    debris = list((hub / "personal" / "ideas").glob("*.tmp"))
    if debris:
        fail(f"atomic capture leaked temp debris: {debris}")
        return
    ok("test_capture_is_atomic_on_serializer_crash")


def test_triage_ready_and_brief() -> None:
    hub = make_hub()
    created = card.capture(
        "Запустить идею дня в брифинге с evidence.",
        source="chat",
        now="2026-06-16T11:00:00+02:00",
        hub=hub,
    )
    idea_id = created["id"]

    card.triage(
        idea_id,
        priority="P0",
        materiality="cheap-test",
        strategic_lines=["L0", "L8"],
        next_action="45 минут: подготовить первый idea-derived action",
        expected_evidence="1 completed action or explicit kill decision",
        hub=hub,
    )

    post = read_post(Path(created["path"]))
    if post["status"] != "ready" or post["priority"] != "P0":
        fail(f"triage did not make idea ready/P0: {post['status']} {post['priority']}")
        return
    brief = card.brief(limit=3, hub=hub)
    if idea_id not in brief or "45 минут" not in brief or "Evidence:" not in brief:
        fail(f"brief did not include ready proposal:\n{brief}")
        return
    ok("test_triage_ready_and_brief")


def test_promotion_handoff_sets_kb_board_pointer_not_execution_state() -> None:
    hub = make_hub()
    created = card.capture(
        "Продвинуть идею в kb-board после approval.",
        source="chat",
        now="2026-06-16T12:00:00+02:00",
        hub=hub,
    )
    idea_id = created["id"]
    card.triage(
        idea_id,
        priority="P0",
        materiality="cheap-test",
        next_action="Create execution task",
        expected_evidence="kb-board task pointer exists",
        hub=hub,
    )
    card.promote(
        idea_id,
        project_slug="hub",
        plan_item_id="plan-abc",
        hub=hub,
    )

    post = read_post(Path(created["path"]))
    if post["status"] != "promoted":
        fail(f"promotion did not set promoted status: {post['status']}")
        return
    if "plane_id" in post:
        fail("promotion must not persist Plane pointer fields")
        return
    if post["plan_item_id"] != "plan-abc":
        fail("promotion did not persist kb-board plan_item_id")
        return
    if post.get("execution_status"):
        fail("idea card must not own kb-board execution status after promotion")
        return
    if "Plane" in post.content:
        fail("promotion body must not describe Plane as execution owner")
        return
    ok("test_promotion_handoff_sets_kb_board_pointer_not_execution_state")


def test_promotion_can_create_markdown_board_task() -> None:
    hub = make_hub()
    (hub / "backlog.md").write_text(
        "# Backlog\n\n"
        "## Backlog\n\n"
        "## Ready\n\n"
        "## In Progress\n\n"
        "## Blocked\n\n"
        "## Review\n\n"
        "## Done\n\n"
        "## Cancelled\n",
        encoding="utf-8",
    )
    created = card.capture(
        "Создать markdown task из идеи без приватной зависимости.",
        source="chat",
        now="2026-06-16T12:30:00+02:00",
        hub=hub,
    )
    idea_id = created["id"]
    card.triage(
        idea_id,
        priority="P0",
        materiality="cheap-test",
        next_action="Create board task",
        expected_evidence="Ready task exists in backlog.md",
        hub=hub,
    )
    result = card.promote(
        idea_id,
        project_slug="hub",
        create_task=True,
        hub=hub,
    )
    board = (hub / "backlog.md").read_text(encoding="utf-8")
    if result.get("plan_item_id", "") not in board or f"idea_id: {idea_id}" not in board:
        fail("promotion did not create linked markdown kb-board task")
        return
    post = read_post(Path(created["path"]))
    if post["status"] != "promoted" or post["plan_item_id"] != result["plan_item_id"]:
        fail("promotion did not mirror kb-board plan_item_id back to card")
        return
    ok("test_promotion_can_create_markdown_board_task")


def test_calendar_approval_and_outcome_writeback() -> None:
    hub = make_hub()
    created = card.capture(
        "Поставить календарный блок только после approve token.",
        source="chat",
        now="2026-06-16T13:00:00+02:00",
        hub=hub,
    )
    idea_id = created["id"]
    card.triage(
        idea_id,
        priority="P1",
        materiality="cheap-test",
        next_action="Schedule protected focus block",
        expected_evidence="Calendar event id recorded",
        hub=hub,
    )
    proposal = card.propose_calendar(
        idea_id,
        title="Idea OS focus block",
        start="2026-06-17T10:00:00+02:00",
        end="2026-06-17T10:45:00+02:00",
        proposal_id="cal-20260617-01",
        hub=hub,
    )

    post_before = read_post(Path(created["path"]))
    if post_before.get("calendar_event_ids") != []:
        fail("calendar proposal created an event before explicit approval")
        return
    if proposal["proposal_id"] != "cal-20260617-01":
        fail("calendar proposal id mismatch")
        return

    card.approve_calendar(
        idea_id,
        proposal_id="cal-20260617-01",
        event_id="gcal-event-123",
        approved_at="2026-06-16T13:10:00+02:00",
        hub=hub,
    )
    card.mark_done(
        idea_id,
        outcome="Focus block created and used as first Software 3.0 deploy proof.",
        hub=hub,
    )

    post = read_post(Path(created["path"]))
    if post["calendar_event_ids"] != ["gcal-event-123"]:
        fail("approved calendar event id not written back")
        return
    if post["status"] != "done" or "Software 3.0" not in post.content:
        fail("outcome was not written back as terminal mirror")
        return
    ok("test_calendar_approval_and_outcome_writeback")


def main() -> int:
    print("=== Vepol Idea Intake acceptance ===")
    test_capture_creates_card_and_dashboard()
    test_capture_is_atomic_on_serializer_crash()
    test_triage_ready_and_brief()
    test_promotion_handoff_sets_kb_board_pointer_not_execution_state()
    test_promotion_can_create_markdown_board_task()
    test_calendar_approval_and_outcome_writeback()
    print(f"  Passed: {PASS}, Failed: {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
