"""parsing.py — backlog line parsing utilities.

A backlog line follows this canonical pattern:

    - [<marker>] <body>

where <marker> is one of `[ ]`, `[>]`, `[x]`, `[X]`, `[~]`. Body is a
free-form string with `field: value` pairs separated by ` — ` (em-dash with
spaces). Known fields:

    opened: <YYYY-MM-DD>
    by: <hub|user|self|...>
    due: <when>
    context: <text>
    auto: <true|false>
    prompt: <inline text up to next ` — ` or ` -- ` separator>
    cycle_source_id: <uuid>
    plan_item_id: <uuid>
    claim_id: <token>
    picked: <YYYY-MM-DD by ...>
    closed: <YYYY-MM-DD>
    result: <text>
    timeout: <YYYY-MM-DD>
    tombstoned-by-<reason>: <text>

The parser is permissive — unknown fields are kept in a generic dict so they
round-trip through `update`/`tombstone` without loss.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

LINE_RE = re.compile(r"^(?P<indent>\s*)-\s*(?P<marker>\[[ xX>~]\])\s*(?P<body>.+?)\s*$")
MARKER_TO_STATUS = {
    "[ ]": "open",
    "[>]": "in_progress",
    "[x]": "done",
    "[X]": "done",
    "[~]": "tombstoned",
}
STATUS_TO_MARKER = {v: k for k, v in MARKER_TO_STATUS.items()}

# Field name → regex that captures its value up to the next ` — ` separator
# or end-of-string. `prompt` is special because it may itself contain ` — `
# in agent-template content; we use a dedicated extraction.
FIELD_PATTERN = re.compile(
    r"(?:^|\s—\s)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*"
    r"(?P<value>.+?)(?=\s—\s[A-Za-z_][A-Za-z0-9_-]*\s*:|$)"
)


@dataclass
class BacklogLine:
    """A parsed backlog line.

    Round-trip invariant: rendering an unmodified BacklogLine reproduces the
    original line bytes character-for-character. Modifications go through
    `set_field` / `remove_field` which preserve insertion order of unchanged
    fields.
    """

    raw: str
    indent: str
    marker: str
    title: str
    fields: list[tuple[str, str]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return MARKER_TO_STATUS.get(self.marker, "unknown")

    def get(self, key: str) -> Optional[str]:
        for k, v in self.fields:
            if k == key:
                return v
        return None

    def set_field(self, key: str, value: str) -> None:
        for i, (k, _) in enumerate(self.fields):
            if k == key:
                self.fields[i] = (key, value)
                return
        self.fields.append((key, value))

    def remove_field(self, key: str) -> bool:
        for i, (k, _) in enumerate(self.fields):
            if k == key:
                del self.fields[i]
                return True
        return False

    def set_marker(self, marker: str) -> None:
        if marker not in MARKER_TO_STATUS:
            raise ValueError(f"unknown marker {marker!r}")
        self.marker = marker

    def render(self) -> str:
        parts = [self.title.rstrip()]
        for k, v in self.fields:
            parts.append(f"{k}: {v}")
        body = " — ".join(parts)
        return f"{self.indent}- {self.marker} {body}"


def parse_line(line: str) -> Optional[BacklogLine]:
    """Parse a single line into a BacklogLine, or return None if not a task."""
    m = LINE_RE.match(line)
    if not m:
        return None
    indent = m.group("indent") or ""
    marker = m.group("marker")
    body = m.group("body")
    if marker not in MARKER_TO_STATUS:
        return None

    # Split body into title + key:value pairs by ` — `.
    # The first segment is always the title; subsequent segments that match
    # `<key>: <value>` are fields. Anything that doesn't match is appended
    # back to the title (preserves unrecognised content like em-dashes inside
    # quoted strings — best-effort, common case has no embedded ` — ` inside title).
    segments = body.split(" — ")
    title = segments[0]
    fields: list[tuple[str, str]] = []
    for seg in segments[1:]:
        kv = re.match(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*)$", seg)
        if kv:
            fields.append((kv.group("key"), kv.group("value")))
        else:
            # Unrecognised — append back to title with separator preserved.
            title = f"{title} — {seg}"
    return BacklogLine(raw=line, indent=indent, marker=marker, title=title, fields=fields)


def parse_lines(text: str) -> list[tuple[int, Optional[BacklogLine]]]:
    """Parse all lines, returning (lineno_1based, BacklogLine | None) for each."""
    out: list[tuple[int, Optional[BacklogLine]]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        out.append((lineno, parse_line(line)))
    return out


def find_by_field(text: str, key: str, value: str) -> list[tuple[int, BacklogLine]]:
    """Return [(lineno, BacklogLine)] for every line where field key==value."""
    matches: list[tuple[int, BacklogLine]] = []
    for lineno, parsed in parse_lines(text):
        if parsed is None:
            continue
        if parsed.get(key) == value:
            matches.append((lineno, parsed))
    return matches


def find_line(text: str, lineno: int) -> Optional[BacklogLine]:
    """Return the parsed BacklogLine at a specific 1-based line number."""
    for ln, parsed in parse_lines(text):
        if ln == lineno:
            return parsed
    return None


def replace_line(text: str, lineno: int, new_raw: str) -> str:
    """Replace the line at 1-based lineno with new_raw. Preserves trailing newline."""
    lines = text.splitlines(keepends=False)
    has_trailing_nl = text.endswith("\n")
    if lineno < 1 or lineno > len(lines):
        raise IndexError(f"lineno {lineno} out of range (file has {len(lines)} lines)")
    lines[lineno - 1] = new_raw
    out = "\n".join(lines)
    if has_trailing_nl:
        out += "\n"
    return out


def append_to_open_section(text: str, line: str) -> str:
    """Append `line` to the end of the `## Open` section.

    Creates `## Open` at end-of-file if missing. Returns new text. Idempotency
    is the caller's responsibility — this function appends unconditionally.
    """
    if not text:
        text = ""
    open_re = re.compile(r"^##\s*Open\s*$", re.MULTILINE)
    m = open_re.search(text)
    if m is None:
        prefix = text.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + "## Open\n\n" + line + "\n"

    # Find next "## " header after Open or end of file.
    start = m.end()
    next_hdr = re.search(r"\n##\s+\S", text[start:])
    section_end = start + (next_hdr.start() if next_hdr else len(text) - start)
    before = text[:section_end].rstrip()
    after = text[section_end:]
    sep = "" if before.endswith("\n") else "\n"
    new_text = before + sep + line + "\n"
    if after:
        if not after.startswith("\n"):
            new_text += "\n"
        new_text += after
    elif not new_text.endswith("\n"):
        new_text += "\n"
    return new_text


def is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def make_uuid() -> str:
    return str(uuid.uuid4())


def has_any_marker(line: str) -> bool:
    return parse_line(line) is not None
