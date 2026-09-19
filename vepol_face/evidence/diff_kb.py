"""KB write-back evidence. MVP-11.

Every completed durable task either lists the KB files it changed, or says
plainly that nothing durable changed. Silence is not an option.
"""
from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field

# Runtime plumbing, not durable knowledge. A run that only touched these
# changed nothing a human would call a KB write-back.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".obsidian",
    ".orchestrator", "logs", ".venv", ".worktrees",
}
# Auto-captured session extracts. Not durable knowledge, but never invisible
# either: review blocker 2026-08-20 (agy #1) — dropping them made the UI claim
# "nothing changed" while a session capture had landed. They are reported in
# their own bucket instead.
SESSION_CAPTURE_DIRS = {"daily"}
MAX_FILES = 20_000


@dataclass
class Evidence:
    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    session_capture: list[str] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "changed": self.changed,
            "added": self.added,
            "removed": self.removed,
            "session_capture": self.session_capture,
            "summary": self.summary,
        }


def snapshot(root: pathlib.Path) -> dict[str, str]:
    """Map of relative posix path -> content digest."""
    root = pathlib.Path(root)
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for path in root.rglob("*"):
        if len(out) >= MAX_FILES:
            break
        if not path.is_file() or path.is_symlink():
            continue
        parts = path.relative_to(root).parts
        # Skip named plumbing dirs and every hidden directory.
        if any(p in SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        out[path.relative_to(root).as_posix()] = digest
    return out


def _is_session_capture(path: str) -> bool:
    return path.split("/", 1)[0] in SESSION_CAPTURE_DIRS


def compare(before: dict[str, str], after: dict[str, str]) -> Evidence:
    touched = (
        (set(after) - set(before))
        | (set(before) - set(after))
        | {p for p in set(before) & set(after) if before[p] != after[p]}
    )
    capture = sorted(p for p in touched if _is_session_capture(p))
    durable = {p for p in touched if not _is_session_capture(p)}

    added = sorted(p for p in durable if p not in before)
    removed = sorted(p for p in durable if p not in after)
    modified = sorted(p for p in durable if p in before and p in after)
    changed = sorted(set(added) | set(modified))

    capture_note = (
        f"session capture: {len(capture)} file(s)" if capture else ""
    )

    if not changed and not removed:
        summary = "No durable knowledge changed."
        if capture_note:
            summary += f" ({capture_note})"
        return Evidence(session_capture=capture, summary=summary)

    bits = []
    if modified:
        bits.append(f"{len(modified)} changed")
    if added:
        bits.append(f"{len(added)} added")
    if removed:
        bits.append(f"{len(removed)} removed")
    summary = "KB write-back: " + ", ".join(bits)
    if capture_note:
        summary += f"; {capture_note}"
    return Evidence(
        changed=changed, added=added, removed=removed,
        session_capture=capture, summary=summary,
    )
