"""Signature catalogue loader (spec § Catalogue location and protocol).

Reads the YAML-block-per-entry catalogue from
`~/knowledge/security/scanner-signatures/rNNN.md` referenced by
`current.yaml`, verifies its sha256 against `current.yaml`, then cross-checks
against the ledger entry in `~/knowledge/security/scanner-signatures-ledger.md`.

Strict validation. Fail-closed on any mismatch.

Stdlib only — we parse a minimal YAML subset (block scalars, flat keys,
quoted strings). PyYAML is intentionally not a dependency.
"""
from __future__ import annotations

import hashlib
import os
import re
import base64 as _b64
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .types import (
    DEFAULT_VERDICTS,
    FAMILIES,
    MATCH_TYPES,
    SEVERITIES,
    Signature,
)

HUB_ROOT = Path(os.path.expanduser("~/knowledge"))
SECURITY_ROOT = HUB_ROOT / "security"
SIGNATURES_DIR = SECURITY_ROOT / "scanner-signatures"
CURRENT_POINTER = SIGNATURES_DIR / "current.yaml"
LEDGER_PATH = SECURITY_ROOT / "scanner-signatures-ledger.md"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REV_ID = re.compile(r"^r\d{3,}$")
_SIG_ID = re.compile(r"^sig-[A-E]-\d{4}$")
_PATTERN_LABEL = re.compile(r"^[a-z0-9-]{3,80}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CatalogueError(Exception):
    """Raised on any catalogue load / parse / verification failure.

    Caller MUST treat this as fail-closed: every scan refuses with
    `verdict_reason: catalogue-unavailable` until restored.
    """


# --------------------------------------------------------------------------- #
# Minimal YAML subset parser
# --------------------------------------------------------------------------- #

def _parse_simple_yaml(text: str) -> dict:
    """Parse a flat YAML mapping. Supports:
      key: value
      key: "quoted value"
      key: |          (block scalar — captures indented continuation lines)
        line1
        line2
      key:            (mapping — captures nested key/values one indent level deeper)
        nested_key: value
        nested_key2: value
    No lists, no flow style, no anchors. Strict — unknown shapes raise.
    """
    result: dict = {}
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            i += 1
            continue
        # Top-level key: detect indentation depth = 0
        indent = len(line) - len(line.lstrip(" "))
        if indent != 0:
            raise CatalogueError(f"unexpected indent at line {i+1}: {line!r}")
        if ":" not in stripped:
            raise CatalogueError(f"missing colon at line {i+1}: {line!r}")
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "|":
            # Block scalar — gather indented lines
            block_lines = []
            i += 1
            while i < n:
                nxt = lines[i]
                if nxt.strip() == "":
                    block_lines.append("")
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent == 0:
                    break
                block_lines.append(nxt[2:] if nxt.startswith("  ") else nxt.lstrip(" "))
                i += 1
            # Strip trailing blanks
            while block_lines and block_lines[-1] == "":
                block_lines.pop()
            result[key] = "\n".join(block_lines)
            continue
        if rest == "":
            # Could be: (a) empty scalar (next non-blank is top-level), or
            # (b) nested mapping (next non-blank is indented).
            # Peek ahead.
            j = i + 1
            peek_indent = None
            while j < n:
                if lines[j].strip() == "" or lines[j].lstrip().startswith("#"):
                    j += 1
                    continue
                peek_indent = len(lines[j]) - len(lines[j].lstrip(" "))
                break
            if peek_indent is None or peek_indent == 0:
                # Empty scalar
                result[key] = ""
                i += 1
                continue
            # Nested mapping — gather indented k:v pairs
            sub: dict = {}
            i += 1
            while i < n:
                nxt = lines[i]
                if nxt.strip() == "" or nxt.lstrip().startswith("#"):
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent == 0:
                    break
                sub_stripped = nxt.strip()
                if ":" not in sub_stripped:
                    raise CatalogueError(f"missing colon in nested at line {i+1}")
                sk, _, sv = sub_stripped.partition(":")
                sub[sk.strip()] = _unquote(sv.strip())
                i += 1
            result[key] = sub
            continue
        # Scalar value
        result[key] = _unquote(rest)
        i += 1
    return result


def _unquote(s: str) -> str:
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


# --------------------------------------------------------------------------- #
# current.yaml + revision file
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CataloguePointer:
    revision_id: str
    catalogue_sha256: str
    catalogue_path: Path


def _load_pointer() -> CataloguePointer:
    if not CURRENT_POINTER.is_file():
        raise CatalogueError(f"current.yaml not found at {CURRENT_POINTER}")
    try:
        text = CURRENT_POINTER.read_text(encoding="utf-8")
    except OSError as e:
        raise CatalogueError(f"unreadable current.yaml: {e}") from e
    data = _parse_simple_yaml(text)
    rev = data.get("revision_id")
    sha = data.get("catalogue_sha256")
    if not isinstance(rev, str) or not _REV_ID.fullmatch(rev):
        raise CatalogueError(f"current.yaml: invalid revision_id {rev!r}")
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        raise CatalogueError(f"current.yaml: invalid catalogue_sha256 {sha!r}")
    path = SIGNATURES_DIR / f"{rev}.md"
    if not path.is_file():
        raise CatalogueError(f"revision file missing: {path}")
    return CataloguePointer(revision_id=rev, catalogue_sha256=sha, catalogue_path=path)


def _verify_sha256(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise CatalogueError(
            f"sha256 mismatch on {path.name}: expected={expected} actual={actual}"
        )
    return raw


# --------------------------------------------------------------------------- #
# Ledger chain verification (PATCH 1 anchor)
# --------------------------------------------------------------------------- #

_LEDGER_HEADING = re.compile(r"^##\s+\[[^\]]+\]\s+catalogue-revision\s*\|\s*(r\d{3,})\s*$", re.M)
_YAML_BLOCK = re.compile(r"```yaml\s*\n(.*?)\n```", re.S)


def _verify_ledger_chain(pointer: CataloguePointer) -> None:
    """Walk ledger entries, verify the entry for `pointer.revision_id` exists
    with matching catalogue_sha256, and (for non-r001 revisions) that the
    previous_catalogue_sha256 matches the prior revision's recorded hash.

    Fail-closed on missing entry, mismatched hash, or broken chain.
    """
    if not LEDGER_PATH.is_file():
        raise CatalogueError(f"ledger missing: {LEDGER_PATH}")
    text = LEDGER_PATH.read_text(encoding="utf-8")
    blocks = _YAML_BLOCK.findall(text)
    if not blocks:
        raise CatalogueError("ledger contains no YAML blocks")

    # Parse every block; index by revision_id
    by_rev: Dict[str, dict] = {}
    for block in blocks:
        try:
            entry = _parse_simple_yaml(block)
        except CatalogueError as e:
            raise CatalogueError(f"ledger block parse error: {e}") from e
        if entry.get("type") != "catalogue-revision":
            continue
        rev = entry.get("revision_id")
        if not isinstance(rev, str) or not _REV_ID.fullmatch(rev):
            raise CatalogueError(f"ledger entry: invalid revision_id {rev!r}")
        # Required fields
        for required in ("entry_id", "catalogue_sha256", "date", "written_by"):
            if required not in entry:
                raise CatalogueError(
                    f"ledger entry r={rev}: missing required field {required!r}"
                )
        # written_by must include both human and reviewer_capability — multi-party authz
        wb_text = block  # raw block text — robust against parser shape choices
        if "human:" not in wb_text or "reviewer_capability:" not in wb_text:
            raise CatalogueError(
                f"ledger entry r={rev}: missing multi-party written_by (need human + reviewer_capability)"
            )
        if rev in by_rev:
            raise CatalogueError(f"ledger: duplicate revision_id {rev}")
        by_rev[rev] = entry

    target = by_rev.get(pointer.revision_id)
    if target is None:
        raise CatalogueError(
            f"ledger: no entry for revision_id {pointer.revision_id}"
        )
    if target.get("catalogue_sha256") != pointer.catalogue_sha256:
        raise CatalogueError(
            f"ledger: catalogue_sha256 mismatch for {pointer.revision_id}"
        )

    # Chain integrity: previous_catalogue_sha256 must match the prior revision's
    # recorded hash (skipped for genesis r001).
    if pointer.revision_id != "r001":
        prev_rev = target.get("previous_revision_id")
        if not isinstance(prev_rev, str) or not _REV_ID.fullmatch(prev_rev):
            raise CatalogueError(
                f"ledger: invalid previous_revision_id for {pointer.revision_id}"
            )
        prev_entry = by_rev.get(prev_rev)
        if prev_entry is None:
            raise CatalogueError(
                f"ledger: previous revision {prev_rev} not found for chain check"
            )
        if target.get("previous_catalogue_sha256") != prev_entry.get("catalogue_sha256"):
            raise CatalogueError(
                f"ledger: chain broken between {prev_rev} and {pointer.revision_id}"
            )


# --------------------------------------------------------------------------- #
# Per-signature parsing
# --------------------------------------------------------------------------- #

_SIG_HEADING = re.compile(r"^##\s+(sig-[A-E]-\d{4})\s*$", re.M)


def _parse_signatures(text: str) -> List[Signature]:
    """Parse signatures from the catalogue markdown body.

    Each signature is introduced by `## sig-X-NNNN` followed by a YAML block
    fenced with ```yaml ... ```. The YAML block is parsed strictly.
    """
    sigs: List[Signature] = []
    # Find all heading positions, then the next ```yaml block after each.
    positions = [(m.start(), m.group(1)) for m in _SIG_HEADING.finditer(text)]
    if not positions:
        raise CatalogueError("catalogue contains no signatures")
    for idx, (pos, sig_id) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        chunk = text[pos:end]
        block_match = _YAML_BLOCK.search(chunk)
        if not block_match:
            raise CatalogueError(f"signature {sig_id}: no YAML block")
        data = _parse_simple_yaml(block_match.group(1))
        sig = _build_signature(sig_id, data)
        sigs.append(sig)
    # No duplicate ids
    ids = [s.signature_id for s in sigs]
    if len(set(ids)) != len(ids):
        raise CatalogueError("duplicate signature_id in catalogue")
    return sigs


def _build_signature(sig_id: str, data: dict) -> Signature:
    if not _SIG_ID.fullmatch(sig_id):
        raise CatalogueError(f"invalid signature_id format {sig_id!r}")
    family = data.get("family", "")
    if family not in FAMILIES:
        raise CatalogueError(f"{sig_id}: invalid family {family!r}")
    if not sig_id.startswith(f"sig-{family}-"):
        raise CatalogueError(f"{sig_id}: family/id mismatch")
    pattern_label = data.get("pattern_label", "")
    if not _PATTERN_LABEL.fullmatch(pattern_label):
        raise CatalogueError(f"{sig_id}: invalid pattern_label {pattern_label!r}")
    severity = data.get("severity", "")
    if severity not in SEVERITIES:
        raise CatalogueError(f"{sig_id}: invalid severity {severity!r}")
    default_verdict = data.get("default_verdict", "")
    if default_verdict not in DEFAULT_VERDICTS:
        raise CatalogueError(f"{sig_id}: invalid default_verdict {default_verdict!r}")
    match_type = data.get("match_type", "")
    if family != "E" and match_type not in MATCH_TYPES:
        raise CatalogueError(f"{sig_id}: invalid match_type {match_type!r}")
    added_date = data.get("added_date", "")
    if not _ISO_DATE.fullmatch(added_date):
        raise CatalogueError(f"{sig_id}: invalid added_date {added_date!r}")

    # Decode pattern (base64) — Family E may have empty pattern (entropy thresholds).
    pattern_encoding = data.get("pattern_encoding", "plain")
    pattern_raw = data.get("pattern", "")
    if family == "E":
        pattern = ""  # not used for matching; entropy logic is hard-coded
    else:
        if pattern_encoding == "base64":
            try:
                pattern_bytes = _b64.b64decode(pattern_raw, validate=True)
                pattern = pattern_bytes.decode("utf-8")
            except Exception as e:
                raise CatalogueError(f"{sig_id}: base64 decode failed: {e}") from e
        elif pattern_encoding == "plain":
            pattern = pattern_raw
        else:
            raise CatalogueError(f"{sig_id}: unknown pattern_encoding {pattern_encoding!r}")
        if len(pattern.encode("utf-8")) > 4096:
            raise CatalogueError(f"{sig_id}: pattern exceeds 4 KiB cap")

    # Regex compile-check for regex match types
    if match_type in ("regex", "regex-codepoint-class") and pattern:
        try:
            re.compile(pattern)
        except re.error as e:
            raise CatalogueError(f"{sig_id}: regex compile failed: {e}") from e

    return Signature(
        signature_id=sig_id,
        family=family,
        pattern_label=pattern_label,
        pattern=pattern,
        match_type=match_type,
        severity=severity,
        default_verdict=default_verdict,
        added_date=added_date,
        source_ref=str(data.get("source_ref", ""))[:1024],
        notes=str(data.get("notes", ""))[:1024],
    )


# --------------------------------------------------------------------------- #
# Public loader
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Catalogue:
    revision_id: str
    signatures: Tuple[Signature, ...]


def load_catalogue() -> Catalogue:
    """Load + verify the active catalogue. Fail-closed on any error.

    Verification order (all must pass):
      1. current.yaml parses; revision_id valid; revision file exists.
      2. revision file bytes hash to current.yaml's catalogue_sha256.
      3. Ledger contains a catalogue-revision entry for revision_id with
         matching sha256.
      4. Ledger entry's previous_catalogue_sha256 matches the prior revision's
         recorded hash (skipped for r001 genesis).
      5. Each signature parses + validates strictly.
    """
    pointer = _load_pointer()
    raw = _verify_sha256(pointer.catalogue_path, pointer.catalogue_sha256)
    _verify_ledger_chain(pointer)
    text = raw.decode("utf-8")
    sigs = _parse_signatures(text)
    return Catalogue(revision_id=pointer.revision_id, signatures=tuple(sigs))
