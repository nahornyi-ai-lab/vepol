"""Legal transition table for kb-board mutations."""
from __future__ import annotations

LEGAL_TARGETS = {
    "Backlog": {"Ready", "Cancelled"},
    "Ready": {"In Progress", "Backlog", "Cancelled"},
    "In Progress": {"Blocked", "Review", "Ready", "Cancelled"},
    "Blocked": {"In Progress", "Ready", "Cancelled"},
    "Review": {"Done", "In Progress", "Blocked", "Cancelled"},
    "Done": {"Ready", "Backlog"},
    "Cancelled": {"Ready", "Backlog"},
}


def is_legal(source: str, target: str) -> bool:
    return target in LEGAL_TARGETS.get(source, set())
