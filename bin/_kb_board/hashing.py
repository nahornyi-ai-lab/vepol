"""Content hashing for CAS over task meaning, not dynamic presentation."""
from __future__ import annotations

import hashlib
import json

from .model import CONTENT_FIELDS, TaskBlock
from .parsing import parse_depends_on


def _normalize_value(key: str, value: str) -> object:
    if key == "depends_on":
        return parse_depends_on(value)
    if "\n" in value:
        return "\n".join(line.rstrip() for line in value.strip().splitlines())
    return " ".join(value.strip().split())


def content_payload(task: TaskBlock) -> dict[str, object]:
    payload: dict[str, object] = {"title": " ".join(task.title.strip().split())}
    for key in CONTENT_FIELDS:
        if key in task.fields:
            payload[key] = _normalize_value(key, task.fields[key])
    return payload


def content_hash(task: TaskBlock) -> str:
    data = json.dumps(content_payload(task), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
