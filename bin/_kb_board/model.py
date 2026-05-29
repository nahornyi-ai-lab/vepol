"""Data model for the multiline markdown board."""
from __future__ import annotations

from dataclasses import dataclass, field

STATUS_ORDER = [
    "Backlog",
    "Ready",
    "In Progress",
    "Blocked",
    "Review",
    "Done",
    "Cancelled",
]

MARKER_BY_STATUS = {
    "Backlog": "[ ]",
    "Ready": "[ ]",
    "In Progress": "[>]",
    "Blocked": "[ ]",
    "Review": "[>]",
    "Done": "[x]",
    "Cancelled": "[~]",
}

VALID_MARKERS = {"[ ]", "[>]", "[x]", "[X]", "[~]"}

DYNAMIC_FIELDS = {"updated", "claim_owner", "claim_id", "claim_expires_at"}

CONTENT_FIELDS = [
    "plan_item_id",
    "priority",
    "owner",
    "depends_on",
    "acceptance",
    "evidence",
    "body",
    "blocked_reason",
    "reopen_reason",
]

FIELD_ORDER = [
    "plan_item_id",
    "priority",
    "owner",
    "depends_on",
    "created",
    "updated",
    "claim_owner",
    "claim_id",
    "claim_expires_at",
    "blocked_reason",
    "acceptance",
    "evidence",
    "body",
    "reopen_reason",
]

MULTILINE_FIELDS = {"acceptance", "evidence", "body", "blocked_reason", "reopen_reason"}

REQUIRED_FIELDS = {"plan_item_id", "priority", "owner", "created", "updated", "acceptance"}


@dataclass
class TaskBlock:
    title: str
    status: str
    marker: str
    fields: dict[str, str] = field(default_factory=dict)
    line: int = 0

    @property
    def plan_item_id(self) -> str | None:
        return self.fields.get("plan_item_id")

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.fields.get(key, default)


@dataclass
class Board:
    title: str = "Backlog"
    sections: dict[str, list[TaskBlock]] = field(default_factory=dict)

    @property
    def tasks(self) -> list[TaskBlock]:
        out: list[TaskBlock] = []
        for status in STATUS_ORDER:
            out.extend(self.sections.get(status, []))
        for status, tasks in self.sections.items():
            if status not in STATUS_ORDER:
                out.extend(tasks)
        return out
