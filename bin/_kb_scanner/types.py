"""Closed-enum types and dataclasses for the scanner.

Mirrors the YAML output contract from spec § Scanner output contract.
All enums are closed; runtime rejects any value outside these sets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Closed enums — runtime fail-closed on any value outside these.

FAMILIES = ("A", "B", "C", "D", "E")

SEVERITIES = ("low", "medium", "high", "critical")

MATCH_TYPES = (
    "literal-case-sensitive",
    "literal-case-insensitive",
    "regex",
    "regex-codepoint-class",
)

DEFAULT_VERDICTS = ("flagged", "refused")

VERDICTS = ("clean", "flagged", "refused")

VERDICT_REASONS = (
    "clean",
    "injection-phrase",
    "invisible-unicode",
    "tool-call-token",
    "format-anomaly",
    "unknown-pattern-high-entropy",
    "catalogue-unavailable",
    "scanner-internal-error",
    "input-too-large",
    "batch-timeout",
    "self-injection-in-metadata",
)

INPUT_ORIGINS = (
    "runtime-generated",
    "user-typed-here",
    "external-pasted",
    "external-api",
    "message-channel",
    "cross-project-shared",
)

DECODERS = ("nfc", "nfd", "nfkc", "nfkd", "base64", "rot13", "percent")

# Maps verdict_reason → family letter
FAMILY_FOR_REASON = {
    "injection-phrase": "A",
    "invisible-unicode": "B",
    "tool-call-token": "C",
    "format-anomaly": "D",
    "unknown-pattern-high-entropy": "E",
}

REASON_FOR_FAMILY = {v: k for k, v in FAMILY_FOR_REASON.items()}


@dataclass(frozen=True)
class Signature:
    """One parsed catalogue signature entry."""

    signature_id: str           # e.g. "sig-A-0001"
    family: str                 # A..E
    pattern_label: str
    pattern: str                # decoded pattern body (or "" for Family E)
    match_type: str
    severity: str
    default_verdict: str        # flagged | refused
    added_date: str
    source_ref: str = ""
    notes: str = ""


@dataclass
class SignatureHit:
    signature_id: str
    via_decoder: Optional[str] = None     # None = original-form match


@dataclass
class Verdict:
    """Structured scanner output. One record per scanned input."""

    verdict: str                                  # clean | flagged | refused
    verdict_reason: str
    signatures_hit: List[SignatureHit]
    input_id: str                                 # sha256 of normalized bytes
    input_byte_length: int
    input_origin: str
    scanner_version: str
    catalogue_revision: str
    scanned_at: str                               # ISO 8601 UTC, second resolution
    calling_capability_slug: str
    cache_status: str = "miss"                    # hit | miss | bypassed
    decode_budget_exhausted: bool = False
    schema_version: int = 2

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "signatures_hit": [
                {"signature_id": h.signature_id, "via_decoder": h.via_decoder}
                for h in self.signatures_hit
            ],
            "input_id": self.input_id,
            "input_byte_length": self.input_byte_length,
            "input_origin": self.input_origin,
            "scanner_version": self.scanner_version,
            "catalogue_revision": self.catalogue_revision,
            "scanned_at": self.scanned_at,
            "calling_capability_slug": self.calling_capability_slug,
            "cache_status": self.cache_status,
            "decode_budget_exhausted": self.decode_budget_exhausted,
        }


@dataclass
class ScanRecord:
    """One record in a batch scan call."""

    input_origin: str
    bytes_: bytes
    calling_capability_slug: str
    input_id: Optional[str] = None  # filled by scanner if absent
