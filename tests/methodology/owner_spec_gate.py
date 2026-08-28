#!/usr/bin/env python3
"""Owner-approved specification gate documentation contract tests.

Spec: vepol-dev/knowledge/decisions/owner-spec-approval-gate-2026-06-21.md
Build plan: vepol-dev/knowledge/decisions/owner-spec-approval-gate-build-plan-2026-06-21.md

These tests exercise the methodology/docs rollout as a process contract:
material work must flow through research -> reviewed spec -> owner approval ->
build plan -> RED/E2E tests -> implementation.
"""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

PASS = 0
FAIL = 0


def ok(label: str) -> None:
    global PASS
    print(f"  PASS {label}")
    PASS += 1


def bad(label: str, detail: str = "") -> None:
    global FAIL
    print(f"  FAIL {label}")
    if detail:
        print(f"    {detail}")
    FAIL += 1


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def require_all(rel: str, label: str, needles: list[str]) -> None:
    text = read(rel)
    missing = [needle for needle in needles if needle not in text]
    if missing:
        bad(label, f"{rel} missing: {missing}")
    else:
        ok(label)


def require_order(rel: str, label: str, needles: list[str]) -> None:
    text = read(rel)
    positions: list[int] = []
    missing: list[str] = []
    for needle in needles:
        idx = text.find(needle)
        if idx < 0:
            missing.append(needle)
        positions.append(idx)
    if missing:
        bad(label, f"{rel} missing: {missing}")
        return
    if positions != sorted(positions):
        bad(label, f"{rel} order wrong: {list(zip(needles, positions))}")
        return
    ok(label)


def test_development_loop_gate() -> None:
    rel = "docs/methodology/development-loop.md"
    require_all(
        rel,
        "development-loop documents owner approval gate",
        [
            "Lightweight spec review",
            "knowledge/spec-approvals.md",
            "spec-contract",
            "Build plan",
            "mandatory E2E",
            "RED tests",
        ],
    )
    require_order(
        rel,
        "development-loop preserves gate order",
        [
            "**3. Specification.",
            "**4. Lightweight spec review",
            "**4.5. Owner approval.",
            "**4.6. Build plan.",
            "**5. Tests → implementation.",
        ],
    )


def test_spec_driven_workflow_contract() -> None:
    require_all(
        "docs/methodology/spec-driven-workflow.md",
        "spec-driven workflow lists required spec contents",
        [
            "Product context",
            "Place in Vepol",
            "Software 3.0",
            "owner approval",
            "spec-contract",
            "mandatory E2E path",
            "technically impossible",
            "build plan",
            "Changes requested",
        ],
    )


def test_lightweight_review_contract() -> None:
    require_all(
        "docs/methodology/cross-agent-review.md",
        "lightweight review stays narrow and anti-loop",
        [
            "exactly one pass",
            "QUESTIONS (maximum 3)",
            "file:line",
            "A changed spec hash alone never invalidates the review",
            "New findings are not accepted during the delta check",
        ],
    )


def test_idea_intake_material_path() -> None:
    rel = "docs/modules/idea-intake.md"
    require_all(
        rel,
        "idea-intake routes material ideas through approval gate",
        [
            "Material Idea Path",
            "research",
            "owner-approved specification",
            "knowledge/spec-approvals.md",
            "post-approval build plan",
            "RED tests including E2E",
            "kb-board task owns execution state",
        ],
    )
    require_order(
        rel,
        "idea-intake material path order",
        [
            "capture",
            "research",
            "owner-approved specification",
            "post-approval build plan",
            "RED tests including E2E",
            "kb-board task",
        ],
    )


def test_agent_entrypoints_expose_compact_rule() -> None:
    for rel in ["AGENTS.md", "knowledge/AGENTS.md", "_template/AGENTS.md"]:
        require_all(
            rel,
            f"{rel} exposes compact owner approval rule",
            [
                "owner-approved spec",
                "knowledge/spec-approvals.md",
                "spec-contract",
                "build plan",
                "mandatory E2E path",
            ],
        )


def main() -> int:
    test_development_loop_gate()
    test_spec_driven_workflow_contract()
    test_lightweight_review_contract()
    test_idea_intake_material_path()
    test_agent_entrypoints_expose_compact_rule()
    print(f"\nowner-spec gate methodology tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
