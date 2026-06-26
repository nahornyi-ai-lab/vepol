"""Append-only JSONL ledger for follow-up proposals.

Each line is one immutable state-transition record, never an edited blob. The
effective state of a follow-up is derived by replaying records by `id`. The
ledger holds only pending/provenance/idempotency data — Google Calendar is the
canonical user-visible surface after approval. No secret tokens ever land here.

Path: $KB_HUB/personal/calendar-followups.jsonl
"""
from __future__ import annotations

import json
import os
import pathlib


def hub_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))


def ledger_path() -> pathlib.Path:
    return hub_path() / "personal" / "calendar-followups.jsonl"


def append(record: dict) -> None:
    """Append one transition record."""
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_records() -> list[dict]:
    p = ledger_path()
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # a corrupt line must not poison replay; skip it
            continue
    return out


def replay() -> dict:
    """Return {id: effective_state} by merging transition records in order."""
    state: dict[str, dict] = {}
    for r in _read_records():
        fid = r.get("id")
        if not fid:
            continue
        merged = dict(state.get(fid, {}))
        merged.update(r)
        state[fid] = merged
    return state


def get(fid: str) -> dict | None:
    return replay().get(fid)


def next_id(date_str: str) -> str:
    """Mint fup-YYYYMMDD-NNN with the next free sequence for that date."""
    prefix = f"fup-{date_str}-"
    existing = [k for k in replay().keys() if k.startswith(prefix)]
    seq = 0
    for k in existing:
        tail = k[len(prefix):]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"{prefix}{seq + 1:03d}"
