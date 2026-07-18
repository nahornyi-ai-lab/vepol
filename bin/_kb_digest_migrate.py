"""Idempotent processes.yaml migration for the daily audio digests.

Turns the audio digests on for existing installs without hand-editing config:
insert `evening-digest` (after:retro) and `morning-digest` anchored to the LAST
enabled SCHEDULED morning process — `after:money-radar` when money-radar
exists, is enabled, and is scheduled; else `after:learning` under the same
conditions; else `after:daily` — so the digest never misses an enabled morning
process or races it as a sibling.

Managed re-anchor (spec D6): when `morning-digest` already exists and its block
is MANAGED — run equals the allowlisted digest command (basename-normalized)
and `when` is one of this migration's own anchors — a re-run recomputes the
anchor without caring which independent channel flags are enabled. A customized
block (any other run/when) is left byte-identical and reported as a
notice, never rewritten. This is what makes
"enable money-radar later, re-run kb-digest-migrate" mechanically true.

Same fail-closed discipline as `_kb_mail/migrate.py` (whose text-surgery
helpers this module reuses): the input is parsed + validated FIRST, an
already-migrated file round-trips byte-for-byte, and the RESULT is re-validated
before returning so a broken/partial config is never emitted. Pure text ->
text; `kb-digest-migrate` owns the atomic 0600 rewrite.

Spec: decisions/local-tts-v0-6-dual-backend-addendum-2026-07-11.md
      (spec-contract:sha256:64c99d1d0e31cc701bcedcbe371b603ef179991db5ab508a17abb31ea8d99062)
"""
from __future__ import annotations

import os
import sys

_BIN = os.path.dirname(os.path.realpath(__file__))
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from _kb_processes import (  # noqa: E402
    ProcessConfigError,
    SCHEDULED_TELEGRAM_AUDIO_ALLOWED,
    normalized_run_argv,
    parse_processes_text,
)
from _kb_mail.migrate import (  # noqa: E402
    _block_span,
    _find_blocks,
    _set_when,
)

_MORNING_RUN = SCHEDULED_TELEGRAM_AUDIO_ALLOWED["morning-digest"]
_EVENING_RUN = SCHEDULED_TELEGRAM_AUDIO_ALLOWED["evening-digest"]
_MANAGED_ANCHORS = ("after:money-radar", "after:learning", "after:daily")
_DEFAULT_OUTPUTS = ["file", "notebooklm_audio"]


class DigestMigrationError(Exception):
    """Raised when a valid processes.yaml cannot be migrated — e.g. it has no
    `retro`/`daily` to anchor the digests to. Distinct from ProcessConfigError
    (invalid shape); both make `kb-digest-migrate` fail closed without a
    rewrite."""


def _digest_block(pid: str, when: str, run: str, outputs: list[str]) -> list[str]:
    return [
        f"- id: {pid}",
        "  enabled: true",
        f"  when: {when}",
        f"  run: {run}",
        f"  outputs: {_format_outputs(outputs)}",
    ]


def _format_outputs(outputs: list[str]) -> str:
    return (
        "{file: true, "
        f"telegram_audio: {'true' if 'telegram_audio' in outputs else 'false'}, "
        f"notebooklm_audio: {'true' if 'notebooklm_audio' in outputs else 'false'}"
        "}"
    )


def _morning_anchor(pmap: dict) -> str:
    """Last enabled SCHEDULED morning process; an enabled on-demand process is
    never an anchor (spec D6)."""
    for pid in ("money-radar", "learning"):
        p = pmap.get(pid)
        if p and p["enabled"] and p["when"] != "on-demand":
            return f"after:{pid}"
    if "daily" in pmap:
        return "after:daily"
    raise DigestMigrationError(
        "cannot migrate: processes.yaml has no 'daily' block to anchor "
        "morning-digest to"
    )


def _is_managed(p: dict, run: str, anchors: tuple[str, ...]) -> bool:
    return (
        normalized_run_argv(p["run"]) == normalized_run_argv(run)
        and p["when"] in anchors
    )


def _parse_source(text: str) -> list[dict]:
    """Validate the source before any text surgery."""
    return parse_processes_text(text)


def migrate_processes(text: str) -> tuple[str, list[str]]:
    """Return (migrated text, notices).

    Fail-closed: invalid input raises ProcessConfigError, an unmigratable-but-
    valid input raises DigestMigrationError; an already-migrated input is
    returned byte-for-byte unchanged (idempotent, including right after a
    managed re-anchor).
    """
    procs = _parse_source(text)
    pmap = {p["id"]: p for p in procs}
    notices: list[str] = []

    if "retro" not in pmap:
        raise DigestMigrationError(
            "cannot migrate: processes.yaml has no 'retro' block to anchor "
            "evening-digest to"
        )
    anchor = _morning_anchor(pmap)

    lines = text.split("\n")
    blocks = _find_blocks(lines)
    appends: list[list[str]] = []

    morning = pmap.get("morning-digest")
    if morning is None:
        appends.append(_digest_block(
            "morning-digest", anchor, _MORNING_RUN, _DEFAULT_OUTPUTS,
        ))
    elif _is_managed(morning, _MORNING_RUN, _MANAGED_ANCHORS):
        if morning["when"] != anchor:
            # Managed re-anchor: ONLY the when: line changes (spec D6).
            _set_when(lines, blocks["morning-digest"].when, anchor)
    else:
        notices.append(
            "morning-digest exists but is customized (run/when differ "
            "from the managed block); left untouched — re-anchor it by hand if "
            "you want it behind the newest morning process"
        )

    evening = pmap.get("evening-digest")
    if evening is None:
        appends.append(_digest_block(
            "evening-digest", "after:retro", _EVENING_RUN, _DEFAULT_OUTPUTS,
        ))
    elif _is_managed(evening, _EVENING_RUN, ("after:retro",)):
        pass
    else:
        notices.append(
            "evening-digest exists but is customized (run/when differ "
            "from the managed block); left untouched"
        )

    result = "\n".join(lines)
    for blk in appends:
        if not result.endswith("\n"):
            result += "\n"
        result += "\n" + "\n".join(blk) + "\n"

    if result != text:
        parse_processes_text(result)  # never emit a broken config
    return result, notices


def revert_processes(text: str) -> str:
    """Idempotent inverse: remove the morning-digest/evening-digest blocks,
    preserve everything else, re-validate. A file without them is returned
    unchanged."""
    _parse_source(text)  # validate first; raises on malformed
    lines = text.split("\n")
    blocks = _find_blocks(lines)

    removals: list[tuple[int, int]] = []
    for pid in ("morning-digest", "evening-digest"):
        if pid in blocks:
            start, end, trailing_blank = _block_span(lines, blocks[pid].start)
            # Also collapse the single blank separator BEFORE the block when the
            # block sits at/near EOF (the migrate append shape), so a
            # migrate -> revert round-trip is byte-identical.
            if not trailing_blank and start > 0 and lines[start - 1].strip() == "":
                start -= 1
            removals.append((start, end + (1 if trailing_blank else 0)))
    if not removals:
        return text
    for start, end in sorted(removals, key=lambda t: t[0], reverse=True):
        del lines[start:end]

    result = "\n".join(lines)
    parse_processes_text(result)  # never emit a broken config
    return result
