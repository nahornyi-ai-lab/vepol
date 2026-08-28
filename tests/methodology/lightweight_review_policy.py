#!/usr/bin/env python3
"""Regression contract for the one-pass lightweight spec review policy."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(rel: str, *needles: str) -> None:
    text = read(rel)
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"{rel} missing {missing}"


def forbid(rel: str, *needles: str) -> None:
    text = read(rel)
    found = [needle for needle in needles if needle in text]
    assert not found, f"{rel} still contains {found}"


def main() -> None:
    require(
        "docs/methodology/development-loop.md",
        "**4. Lightweight spec review",
        "exactly one independent reviewer",
        "GO / QUESTIONS / BLOCK",
        "A changed spec hash alone never triggers another review",
    )
    forbid(
        "docs/methodology/development-loop.md",
        "**5.5. Implementation review",
        "≥2 independent reviewers",
        "exact final version",
    )
    require(
        "docs/methodology/cross-agent-review.md",
        "## Canonical reviewer prompt",
        "QUESTIONS (maximum 3)",
        "If unsure between QUESTIONS and GO, choose GO",
        "New findings are not accepted during the delta check",
    )
    require(
        "claude/skills/development-loop/SKILL.md",
        "exactly one independent reviewer",
        "maximum three short questions",
        "A changed hash alone never triggers another review",
    )
    forbid(
        "claude/skills/development-loop/SKILL.md",
        "**5.5. Implementation review",
        "≥2 independent reviewers",
    )
    forbid("bin/new-wiki", "enable-review-gate", "review gate enabled")
    require(
        "AGENTS.md",
        "one lightweight independent spec review",
        "Do not restart review merely because the spec hash changed",
    )
    forbid("AGENTS.md", "Do not skip the cross-agent review gate")
    require(
        "knowledge/AGENTS.md",
        "ровно один лёгкий независимый review",
        "GO / QUESTIONS / BLOCK",
    )
    forbid(
        "knowledge/AGENTS.md",
        "≥2 НЕЗАВИСИМЫХ ревьюера",
        "5.5. **Implementation review",
    )
    print("lightweight review policy: PASS")


if __name__ == "__main__":
    main()
