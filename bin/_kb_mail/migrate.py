"""Idempotent processes.yaml migration for the mail briefing integration.

Turns the mail feature on for existing installs without hand-editing config:
insert `mail-morning` and `mail-evening` and rewire `daily` to run
`after:mail-morning` and `retro` to run `after:mail-evening` so mail is
GUARANTEED to be in the morning brief and evening retro (spec: Process graph,
AC1, AC12). Every other process and every other edge is preserved exactly.

The mail times are DERIVED from each install's own daily/retro times (one tick
== 15 min earlier), so the dependents keep ~their original time on any install —
a worst-case ~1-tick shift, as the owner approved. The original time is
recoverable from the mail-* `when`, which makes `revert` lossless for any install
time (not a hardcoded owner-specific value).

`_kb_processes.py` is read-only today (it has no writer), so this is the net-new,
highest-risk piece and is deliberately fail-closed:

  1. the input is parsed + validated through `_kb_processes.parse_processes_text`
     FIRST — a malformed source raises ProcessConfigError and nothing is emitted;
  2. an already-migrated file is returned byte-for-byte unchanged (no-op);
  3. the RESULT is re-validated through the same parser before returning, so a
     broken/partial config is never emitted.

These are pure text -> text transforms (no file IO). `kb-mail-migrate` owns the
atomic 0600 rewrite. The edit is text-surgical, not a full re-serialization, so
comments and existing formatting survive the rewrite (the live processes.yaml
carries operational documentation that a re-serialize would destroy).

Spec:  knowledge/decisions/mail-briefing-integration-2026-06-29.md
       (spec-contract:sha256:799cd78067cf4961ca95f1a63339d3070efae1afd342c572f374dd46fc32ce26)
Plan:  knowledge/decisions/mail-briefing-integration-build-plan-2026-07-01.md
"""
from __future__ import annotations

import os
import re
import sys

# _kb_processes lives at the bin/ root, a sibling of this package. Reuse its
# validator and line grammar instead of re-implementing a second parser that
# could drift from the launchd-critical reader.
_BIN = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from _kb_processes import (  # noqa: E402
    ProcessConfigError,
    parse_processes_text,
    _BLOCK_START_RE,
    _FIELD_RE,
    _strip_quotes,
)

# kb-tick cadence: one tick == 15 minutes. mail-* is placed one tick BEFORE its
# dependent's original fixed time, so the dependent (which runs `after:` on the
# next tick) stays at ~its original time — a worst-case ~1-tick shift, as the
# owner approved. The original time is recoverable from the mail-* `when`, which
# makes revert lossless for any install time (not just the owner's).
_TICK_MIN = 15
_HHMM_RE = re.compile(r'^"?([01]\d|2[0-3]):([0-5]\d)"?$')

# Fallback times only for the (corrupt) partial state where the dependent is
# already rewired but its mail-* block is missing, so the original time is gone.
_FALLBACK_MORNING_WHEN = "07:15"
_FALLBACK_EVENING_WHEN = "20:30"


def _shift_hhmm(when_value: str, delta_min: int) -> str | None:
    """Shift a quoted-or-bare `HH:MM` by delta minutes (wrapping at midnight),
    returned quoted. Returns None if `when_value` is not a fixed HH:MM time
    (e.g. `after:x` / `on-demand`)."""
    m = _HHMM_RE.match(when_value.strip())
    if not m:
        return None
    total = (int(m.group(1)) * 60 + int(m.group(2)) + delta_min) % (24 * 60)
    return f'"{total // 60:02d}:{total % 60:02d}"'


def _mail_block(mail_id: str, when_quoted: str, period: str) -> list[str]:
    """A five-field mail process block plus one trailing blank separator."""
    return [
        f"- id: {mail_id}",
        "  enabled: true",
        f"  when: {when_quoted}",
        f"  run: kb-mail-brief --period {period} --write",
        "  outputs: [file]",
        "",
    ]


class MailMigrationError(Exception):
    """Raised when a valid processes.yaml cannot be migrated/reverted — e.g. it
    has no `daily`/`retro` block to rewire. Distinct from ProcessConfigError
    (invalid shape); both make `kb-mail-migrate` fail closed without a rewrite."""


class _Block:
    __slots__ = ("id", "start", "when")

    def __init__(self, pid: str, start: int) -> None:
        self.id = pid          # process id
        self.start = start     # line index of the `- id: <id>` line
        self.when = None       # line index of the `  when:` field, or None


def _find_blocks(lines: list[str]) -> dict[str, _Block]:
    """Map process id -> _Block over already-validated text. Trusts the strict
    grammar: a block starts with `- id:` at column 0, fields are 2-space indented,
    comments/blank lines sit only between blocks."""
    blocks: dict[str, _Block] = {}
    cur: _Block | None = None
    for i, raw in enumerate(lines):
        s = raw.rstrip()
        if s and not s.startswith(" ") and s.startswith("-"):
            m = _BLOCK_START_RE.match(s)
            if m:
                cur = _Block(_strip_quotes(m.group(1)), i)
                blocks[cur.id] = cur
            continue
        fm = _FIELD_RE.match(s)
        if fm and cur is not None and fm.group(1) == "when" and cur.when is None:
            cur.when = i
    return blocks


def _block_span(lines: list[str], start: int) -> tuple[int, int, bool]:
    """Return (start, end_exclusive, trailing_blank) for the block whose header is
    at `start`. The body is the contiguous run of 2-space-indented field lines;
    a single blank separator directly after is reported so removal can collapse it."""
    end = start + 1
    n = len(lines)
    while end < n and lines[end].startswith("  ") and _FIELD_RE.match(lines[end].rstrip()):
        end += 1
    trailing_blank = end < n and lines[end].strip() == ""
    return start, end, trailing_blank


def _set_when(lines: list[str], idx: int, quoted_value: str) -> None:
    """Rewrite the `when:` line in place, preserving the two-space indentation."""
    lines[idx] = f"  when: {quoted_value}"


def migrate_processes(text: str) -> str:
    """Return `text` with the mail processes inserted and daily/retro rewired.

    Fail-closed: invalid input raises ProcessConfigError (from the initial parse)
    and an unmigratable-but-valid input raises MailMigrationError; an
    already-migrated input is returned byte-for-byte unchanged (idempotent).
    """
    procs = parse_processes_text(text)  # (1) validate first; raises on malformed
    pmap = {p["id"]: p for p in procs}

    if "daily" not in pmap or "retro" not in pmap:
        raise MailMigrationError(
            "cannot migrate: processes.yaml has no 'daily'/'retro' block to rewire"
        )

    # (2) already migrated? (both mail processes present AND both edges rewired)
    if (
        "mail-morning" in pmap
        and "mail-evening" in pmap
        and pmap["daily"]["when"] == "after:mail-morning"
        and pmap["retro"]["when"] == "after:mail-evening"
    ):
        return text

    # Derive mail-* times from the CURRENT daily/retro fixed times (one tick
    # earlier), BEFORE rewiring, so the dependents keep ~their original time on
    # any install — not just the owner's. Fail closed if a dependent is not at a
    # fixed HH:MM (we cannot preserve a time that isn't there).
    daily_when = pmap["daily"]["when"]
    retro_when = pmap["retro"]["when"]
    morning_when = (_shift_hhmm(daily_when, -_TICK_MIN)
                    if "mail-morning" not in pmap else None)
    evening_when = (_shift_hhmm(retro_when, -_TICK_MIN)
                    if "mail-evening" not in pmap else None)
    if "mail-morning" not in pmap and morning_when is None:
        if daily_when == "after:mail-morning":       # corrupt partial: time lost
            morning_when = f'"{_FALLBACK_MORNING_WHEN}"'
        else:
            raise MailMigrationError(
                f"cannot migrate: 'daily' is not at a fixed HH:MM time "
                f"(when={daily_when!r}); mail timing can't be derived"
            )
    if "mail-evening" not in pmap and evening_when is None:
        if retro_when == "after:mail-evening":
            evening_when = f'"{_FALLBACK_EVENING_WHEN}"'
        else:
            raise MailMigrationError(
                f"cannot migrate: 'retro' is not at a fixed HH:MM time "
                f"(when={retro_when!r}); mail timing can't be derived"
            )

    lines = text.split("\n")
    blocks = _find_blocks(lines)

    # (3a) rewire edges in place (no index shift) — heals partial states too.
    _set_when(lines, blocks["daily"].when, "after:mail-morning")
    _set_when(lines, blocks["retro"].when, "after:mail-evening")

    # (3b) insert missing mail blocks; apply highest index first so lower indices
    # stay valid. Skip a block that already exists (partial-migration safe).
    inserts: list[tuple[int, list[str]]] = []
    if "mail-morning" not in blocks:
        inserts.append((blocks["daily"].start, _mail_block("mail-morning", morning_when, "morning")))
    if "mail-evening" not in blocks:
        inserts.append((blocks["retro"].start, _mail_block("mail-evening", evening_when, "evening")))
    for idx, block_lines in sorted(inserts, key=lambda t: t[0], reverse=True):
        lines[idx:idx] = block_lines

    result = "\n".join(lines)

    # (4) never emit a broken config: re-validate; raise on any violation.
    parse_processes_text(result)
    return result


def revert_processes(text: str) -> str:
    """Idempotent inverse of `migrate_processes`.

    Remove `mail-morning`/`mail-evening`, restore `daily` to "06:30" and `retro`
    to "20:45" (the current live fixed values), preserve every other process and
    edge, and re-validate. A file that is not migrated is returned unchanged.
    """
    procs = parse_processes_text(text)  # validate first; raises on malformed
    pmap = {p["id"]: p for p in procs}

    needs_revert = (
        "mail-morning" in pmap
        or "mail-evening" in pmap
        or (pmap.get("daily") or {}).get("when") == "after:mail-morning"
        or (pmap.get("retro") or {}).get("when") == "after:mail-evening"
    )
    if not needs_revert:
        return text

    lines = text.split("\n")
    blocks = _find_blocks(lines)

    # Restore each dependent's ORIGINAL fixed time, recovered losslessly from its
    # mail-* block (mail-* sits one tick earlier, so original = mail-* + a tick).
    # Only restore where it currently points at the mail edge, so a non-standard
    # time is never clobbered. Fall back to the default install time only in the
    # corrupt case where the mail-* time is gone/unreadable.
    if "daily" in blocks and pmap.get("daily", {}).get("when") == "after:mail-morning":
        restored = _shift_hhmm(pmap.get("mail-morning", {}).get("when", ""), _TICK_MIN)
        _set_when(lines, blocks["daily"].when, restored or '"07:30"')
    if "retro" in blocks and pmap.get("retro", {}).get("when") == "after:mail-evening":
        restored = _shift_hhmm(pmap.get("mail-evening", {}).get("when", ""), _TICK_MIN)
        _set_when(lines, blocks["retro"].when, restored or '"20:45"')

    # Remove mail blocks (+ their trailing blank) from highest start index down.
    removals: list[tuple[int, int]] = []
    for mail_id in ("mail-morning", "mail-evening"):
        if mail_id in blocks:
            start, end, trailing_blank = _block_span(lines, blocks[mail_id].start)
            removals.append((start, end + (1 if trailing_blank else 0)))
    for start, end in sorted(removals, key=lambda t: t[0], reverse=True):
        del lines[start:end]

    result = "\n".join(lines)

    parse_processes_text(result)  # never emit a broken config
    return result
