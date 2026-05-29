from __future__ import annotations

import datetime as dt
import fcntl
import pathlib
import re
from contextlib import contextmanager
from typing import Any

import yaml

from . import scaffold
from .errors import EvolutionError


class LedgerError(EvolutionError):
    pass


ISO_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
FENCE_RE = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)


def _strict_iso_utc(value: Any, entry_id: str) -> str:
    if isinstance(value, dt.datetime):
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not isinstance(value, str) or not ISO_UTC_RE.match(value):
        raise LedgerError(f"{entry_id}: date must be strict ISO UTC second-resolution string")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise LedgerError(f"{entry_id}: date parse failed") from exc
    return value


def _validate_entry(data: Any, index: int) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LedgerError(f"entry #{index}: YAML block must be mapping")
    entry_id = data.get("entry_id")
    if not entry_id:
        raise LedgerError(f"entry #{index}: missing entry_id")
    data["date"] = _strict_iso_utc(data.get("date"), entry_id)
    if not data.get("type"):
        raise LedgerError(f"{entry_id}: missing type")
    if not data.get("written_by"):
        raise LedgerError(f"{entry_id}: missing written_by")
    typ = data["type"]
    if typ == "mutation":
        for key in ("proposal_id", "surface_type", "surface_target", "risk_tier", "evaluation"):
            if key not in data:
                raise LedgerError(f"{entry_id}: missing {key}")
    elif typ == "cancel-mutation":
        if not data.get("cancels_entry_id"):
            raise LedgerError(f"{entry_id}: missing cancels_entry_id")
    elif typ == "correction":
        if not data.get("corrects_entry_id"):
            raise LedgerError(f"{entry_id}: missing corrects_entry_id")
    else:
        raise LedgerError(f"{entry_id}: unsupported type {typ!r}")
    return data


def parse_ledger(path: pathlib.Path) -> list[dict[str, Any]]:
    """Parse mutations.md fail-closed."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise LedgerError(f"ledger missing: {path}")
    text = path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    for index, match in enumerate(FENCE_RE.finditer(text), start=1):
        try:
            raw = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise LedgerError(f"entry #{index}: YAML parse failed: {exc}") from exc
        entries.append(_validate_entry(raw, index))
    return entries


def _ledger_path(knowledge_path: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(knowledge_path) / "evolution" / "mutations.md"


def _lock_path(knowledge_path: pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(knowledge_path) / ".orchestrator" / "locks" / "evolution-mutations.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def _locked(knowledge_path: pathlib.Path):
    lock = _lock_path(knowledge_path)
    with open(lock, "w", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _writer_forbidden(entry: dict[str, Any], actor: str) -> bool:
    if actor == "mutation-engine":
        return True
    for item in entry.get("written_by") or []:
        if not isinstance(item, dict):
            return True
        if item.get("reviewer_capability") == "mutation-engine":
            return True
        if item.get("runtime") == "mutation-engine":
            return True
    return False


def _heading(entry: dict[str, Any]) -> str:
    date = str(entry["date"])[:10]
    typ = entry["type"]
    if typ == "cancel-mutation":
        surface = entry.get("cancels_entry_id", "unknown")
        slug = entry["entry_id"]
    else:
        surface = f"{entry.get('surface_type', 'unknown')}:{entry.get('surface_target', 'unknown')}"
        slug = entry["entry_id"]
    return f"## [{date}] {typ} | {surface} | {slug}"


def append_entry(knowledge_path: pathlib.Path, entry: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """Append one ledger entry with fcntl locking and fail-closed pre-parse."""
    if _writer_forbidden(entry, actor):
        raise LedgerError("self_write_forbidden: mutation engine cannot write mutations.md")
    # Validate before lock so caller gets a deterministic schema error.
    _validate_entry(entry, 1)
    scaffold.ensure_evolution_tree(pathlib.Path(knowledge_path))
    target = _ledger_path(knowledge_path)
    with _locked(knowledge_path):
        parse_ledger(target)
        block = yaml.safe_dump(entry, allow_unicode=True, sort_keys=False).rstrip()
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n\n" + _heading(entry) + "\n\n```yaml\n" + block + "\n```\n")
    return {"status": "appended", "entry_id": entry["entry_id"], "path": str(target)}


def current_state(entries: list[dict[str, Any]], *, proposal_id: str | None = None, surface_target: str | None = None) -> dict[str, Any]:
    """Resolve latest state with cancel-override semantics."""
    cancelled = {
        entry["cancels_entry_id"]
        for entry in entries
        if entry.get("type") == "cancel-mutation" and entry.get("cancels_entry_id")
    }
    relevant = []
    for entry in entries:
        if entry.get("type") != "mutation":
            continue
        if proposal_id and entry.get("proposal_id") != proposal_id:
            continue
        if surface_target and entry.get("surface_target") != surface_target:
            continue
        relevant.append(entry)
    if not relevant:
        return {"state": "none", "entry": None}
    if all(entry["entry_id"] in cancelled for entry in relevant):
        latest_cancelled = max(relevant, key=lambda e: e["date"])
        return {"state": "cancelled", "entry": latest_cancelled}
    active = [entry for entry in relevant if entry["entry_id"] not in cancelled]
    latest = max(active, key=lambda e: e["date"])
    return {"state": "applied", "entry": latest}
