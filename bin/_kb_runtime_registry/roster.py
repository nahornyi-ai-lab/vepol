"""cli-tools.tsv is the roster of record; this mirrors kb-cli-roster's detection.

Format (pipe-delimited): name | kind | candidates | when-text [| fallback-of: <name>]
  kind = which-any -> installed if any candidate resolves on PATH
  kind = path-any  -> installed if any candidate (abs path or name) is executable
  candidates       -> colon-separated, $HOME expanded, tried in order
"""
from __future__ import annotations

import os
import pathlib
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

KNOWN_KINDS = ("which-any", "path-any")


@dataclass
class RosterEntry:
    name: str
    kind: str
    candidates: List[str]
    when: str = ""
    fallback_of: Optional[str] = None
    resolved: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def installed(self) -> str:
        return "yes" if self.resolved else "no"


def _expand(candidate: str) -> str:
    home = os.environ.get("HOME") or str(pathlib.Path.home())
    return os.path.expanduser(candidate.replace("$HOME", home))


def resolve_candidates(candidates: List[str]) -> Optional[str]:
    """First candidate that is an executable file (abs path) or resolves on PATH."""
    for raw in candidates:
        cand = _expand(raw.strip())
        if not cand:
            continue
        if "/" in cand:
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
            continue
        found = shutil.which(cand)
        if found:
            return found
    return None


def parse_roster(path: pathlib.Path) -> List[RosterEntry]:
    entries: List[RosterEntry] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("|")]
        if len(fields) < 3 or not fields[0]:
            entries_warning = f"{path}:{lineno}: malformed roster line skipped"
            if entries:
                entries[-1].warnings.append(entries_warning)
            continue
        name, kind, cands = fields[0], fields[1], fields[2]
        when = fields[3] if len(fields) > 3 else ""
        fallback_of = None
        for extra in fields[4:]:
            if extra.startswith("fallback-of:"):
                fallback_of = extra[len("fallback-of:"):].strip() or None
        entry = RosterEntry(
            name=name,
            kind=kind,
            candidates=[c for c in cands.split(":") if c.strip()],
            when=when,
            fallback_of=fallback_of,
        )
        if kind not in KNOWN_KINDS:
            entry.warnings.append(f"{path}:{lineno}: unknown kind '{kind}' for '{name}' (generic detection)")
        entry.resolved = resolve_candidates(entry.candidates)
        entries.append(entry)
    return entries
