#!/usr/bin/env python3
"""Docs regression contract: statements the code proved wrong stay fixed, and
every relative link and #anchor in the user and contributor docs resolves.

Standard library only; reads files, runs nothing. VEPOL_DOCS_ROOT points the
check at another checkout (default: this repository).
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(os.environ.get("VEPOL_DOCS_ROOT") or Path(__file__).resolve().parents[2])

FAILURES: list[str] = []


def read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except FileNotFoundError:
        FAILURES.append(f"{rel}: file not found")
        return ""


def require(rel: str, *needles: str) -> None:
    text = read(rel)
    for needle in needles:
        if needle not in text:
            FAILURES.append(f"{rel}: missing {needle!r}")


def forbid(rel: str, *needles: str) -> None:
    text = read(rel)
    for needle in needles:
        if needle in text:
            FAILURES.append(f"{rel}: still contains {needle!r}")


def facts() -> None:
    # Multi-bot stops signal only the agent's own child now (spawner._refuse_signal).
    forbid("docs/multibot-runbook.md", "Known issue", "pid -1")
    forbid("docs/methodology/multibot-agent-runtime.md", "pid -1", "do not use `/stop`")
    require("docs/methodology/multibot-agent-runtime.md", "SIGTERM, then SIGKILL", "`watchdog_silence_sec`")
    require("docs/multibot-runbook.md", "`watchdog_silence_sec`")
    # The supervisor sends no Telegram message when it stops a run (status table: "Not built").
    require("docs/methodology/multibot-agent-runtime.md", "no message is sent yet")

    # --allow-edits jobs get a bare Bash rule (any command, any folder), and Desktop's
    # broker lane is the first lane of one-shot runs, not a fallback.
    forbid("CHANGELOG.md", "get only the permissions their job needs", "falls back to it cannot edit")

    # Contributor setup: Desktop test deps, explicit Python 3.11+, pytest for run-all.sh.
    for rel in ("CONTRIBUTING.md", ".github/pull_request_template.md"):
        require(rel, "pip install -r requirements.txt pytest httpx", "python3 -m pip install --user pytest")
    require("CONTRIBUTING.md", '"$(brew --prefix)/bin/python3" -m venv .venv', "must print 3.11 or later")

    # One lightweight review for every non-trivial spec (cross-agent-review.md).
    forbid("README.md", "for an architectural one")
    forbid("CONTRIBUTING.md", "review for architectural changes")

    # Claude Code skips AGENTS.md when a CLAUDE.md exists, so the repo CLAUDE.md imports it.
    if not re.search(r"(?m)^@AGENTS\.md\s*$", read("CLAUDE.md")):
        FAILURES.append("CLAUDE.md: no `@AGENTS.md` import line")
    forbid("CLAUDE.md", "exists because Claude Code looks for project instructions")

    # Packages go into the python3 on PATH, never a bare pip3.
    forbid("docs/daily-routine.md", "pip3 install")
    forbid("requirements.txt", "inside a venv")

    # Scheduled audio finds `notebooklm` via KB_NOTEBOOKLM_BIN, PATH or ~/.local/bin (pipx).
    forbid("README.md", "# people, ideas, NotebookLM")
    for rel in ("README.md", "docs/getting-started.md"):
        require(rel, "pipx install notebooklm-py")

    # Calendar reads and mcp-check use the shared claude lookup (_kb_mcp.runner._find_claude).
    forbid("docs/dependency-matrix.md", "only on that `PATH`")
    forbid("docs/methodology/mcp-first-sources.md", "- `claude` is in `PATH`.")

    # README's kb-session-start line matches the project AGENTS.md wording.
    require("README.md", 'kb-session-start --print --cwd "$PWD"')

    # The visuals index names the README section that really holds the picture.
    m = re.search(r'Used in the "([^"]+)" section of the \[main README\]', read("docs/visuals/README.md"))
    if not m or not re.search(rf"(?m)^## {re.escape(m.group(1))}\s*$", read("README.md")):
        FAILURES.append("docs/visuals/README.md: names a README section that does not exist")


# --- relative links and anchors ------------------------------------------------

DOCS = [
    "README.md", "CONTRIBUTING.md", "CLAUDE.md", "AGENTS.md", "SETUP.prompt.md",
    "CHANGELOG.md", ".github/pull_request_template.md", "face/README.md", "demo/README.md",
    "docs/visuals/README.md",
]
for sub in ("docs", "docs/modules", "docs/methodology"):
    DOCS += sorted(str(p.relative_to(ROOT)) for p in (ROOT / sub).glob("*.md"))

LINK_RE = re.compile(
    r'(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\!\[[^\]]*\]\(([^)\s]+)\)|(?:src|href|srcset)="([^"]+)"'
)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
_anchor_cache: dict[Path, set[str]] = {}


def slugify(heading: str) -> str:
    """GitHub's heading anchor: lower case, punctuation dropped, spaces to dashes."""
    h = re.sub(r"<[^>]+>", "", heading).strip().lower()
    h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h).replace("`", "")
    keep = [c for c in h if c in "-_ " or unicodedata.category(c)[0] in "LN"]
    return "".join(keep).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    if path not in _anchor_cache:
        found: set[str] = set()
        seen: dict[str, int] = {}
        in_code = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if FENCE_RE.match(line):
                in_code = not in_code
                continue
            if in_code:
                continue
            m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if m:
                base = slugify(m.group(2))
                n = seen.get(base, 0)
                found.add(base if n == 0 else f"{base}-{n}")
                seen[base] = n + 1
            found.update(re.findall(r'<a\s+(?:id|name)="([^"]+)"', line))
        _anchor_cache[path] = found
    return _anchor_cache[path]


def links() -> None:
    for rel in DOCS:
        path = ROOT / rel
        if not path.is_file():
            continue
        in_code = False
        for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE_RE.match(line):
                in_code = not in_code
                continue
            if in_code:
                continue
            for m in LINK_RE.finditer(re.sub(r"`[^`]*`", "", line)):
                target = m.group(1) or m.group(2) or m.group(3)
                if not target or re.match(r"^[a-z]+:", target) or target.startswith("//"):
                    continue
                file_part, _, frag = target.partition("#")
                dest = (path.parent / file_part).resolve() if file_part else path
                if file_part and not dest.exists():
                    FAILURES.append(f"{rel}:{ln}: link target not found: {target}")
                    continue
                if frag and dest.suffix == ".md" and dest.is_file() and frag not in anchors(dest):
                    FAILURES.append(f"{rel}:{ln}: anchor not found: {target}")


def main() -> int:
    facts()
    links()
    if FAILURES:
        for f in FAILURES:
            print(f"FAIL {f}")
        print(f"docs consistency: {len(FAILURES)} problem(s)")
        return 1
    print(f"docs consistency: PASS ({len(DOCS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
