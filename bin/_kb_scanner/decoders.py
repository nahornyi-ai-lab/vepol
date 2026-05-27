"""Decode-then-scan pipeline (spec PATCH 4).

Bounded: max 4 decoder attempts per input, max depth 2, ≤ 50 ms wall-clock
per input. Decoder failures are silent; budget exhaustion is signalled in
the verdict metadata but does NOT auto-refuse (would be a CPU-DoS oracle).

Decoders:
  - Unicode normalization: NFC / NFD / NFKC / NFKD
  - Base64 (contiguous spans ≥ 16 chars with valid padding)
  - ROT13 (Latin-alphabetic)
  - URL percent-encoding
"""
from __future__ import annotations

import base64
import codecs
import re
import time
import unicodedata
import urllib.parse
from typing import Iterator, Tuple

DECODER_BUDGET_MS = 50
# Each decoder family (unicode-normalization, base64, rot13, percent) is a
# "decoder pass" — bounded at 4 pass-types per spec. Within each pass, we
# may yield multiple decoded forms (e.g. 4 Unicode forms, N base64 spans);
# the budget covers wall-clock and explicit attempt counters separately.
MAX_DECODER_PASSES = 4
MAX_BASE64_SPANS = 8         # cap per-input base64 spans to prevent fan-out
MAX_DEPTH = 2

# Contiguous base64-ish span: ≥ 16 chars from the base64 alphabet, optional padding.
# We require the span be padded to a multiple of 4 (after the optional `=` chars)
# to reduce false-positive decode attempts.
_BASE64_SPAN = re.compile(rb"[A-Za-z0-9+/]{16,}={0,2}")

_PRINTABLE_MIN_LEN = 8


def _is_printable_utf8(b: bytes) -> bool:
    """Return True if `b` decodes as UTF-8 and is mostly printable text."""
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if len(s) < _PRINTABLE_MIN_LEN:
        return False
    printable = sum(1 for ch in s if ch.isprintable() or ch in "\n\r\t ")
    return printable / max(1, len(s)) >= 0.85


class DecoderBudget:
    """Per-input decoder budget tracker. Stop yielding once exhausted.

    Two limits:
      - wall-clock: DECODER_BUDGET_MS (default 50 ms)
      - distinct decoder passes attempted: MAX_DECODER_PASSES (default 4)
    The Unicode-normalization family counts as ONE pass that emits up to
    4 forms (NFC/NFD/NFKC/NFKD), not 4 passes. Likewise base64 is one pass
    over up to MAX_BASE64_SPANS spans.
    """

    def __init__(self) -> None:
        self.start_ns = time.monotonic_ns()
        self.passes = 0
        self.exhausted = False

    def _check_time(self) -> bool:
        if self.exhausted:
            return False
        elapsed_ms = (time.monotonic_ns() - self.start_ns) / 1_000_000
        if elapsed_ms > DECODER_BUDGET_MS:
            self.exhausted = True
            return False
        return True

    def start_pass(self) -> bool:
        """Reserve one decoder-pass slot. Return False if budget exhausted."""
        if not self._check_time():
            return False
        if self.passes >= MAX_DECODER_PASSES:
            self.exhausted = True
            return False
        self.passes += 1
        return True

    def tick(self) -> bool:
        """Mid-pass wall-clock check. Yields stop early on time exhaustion."""
        return self._check_time()


def _decode_unicode_forms(text: str, budget: DecoderBudget) -> Iterator[Tuple[str, str]]:
    """Yield (decoder_label, normalized_text) for each NFC/NFD/NFKC/NFKD form
    that differs from the original. Counts as one decoder pass."""
    if not budget.start_pass():
        return
    for form in ("nfc", "nfd", "nfkc", "nfkd"):
        if not budget.tick():
            return
        try:
            norm = unicodedata.normalize(form.upper(), text)
        except (ValueError, TypeError):
            continue
        if norm != text:
            yield form, norm


def _decode_base64(raw: bytes, budget: DecoderBudget) -> Iterator[Tuple[str, str]]:
    """Yield ("base64", decoded_text) for each base64 span in `raw` that
    decodes to printable UTF-8. Counts as one decoder pass with up to
    MAX_BASE64_SPANS span attempts."""
    if not budget.start_pass():
        return
    spans_seen = 0
    for match in _BASE64_SPAN.finditer(raw):
        if not budget.tick():
            return
        spans_seen += 1
        if spans_seen > MAX_BASE64_SPANS:
            return
        span = match.group(0)
        # Normalize padding
        rem = len(span) % 4
        if rem == 2:
            span_p = span + b"=="
        elif rem == 3:
            span_p = span + b"="
        elif rem == 0:
            span_p = span
        else:
            continue
        try:
            decoded = base64.b64decode(span_p, validate=True)
        except (ValueError, Exception):
            continue
        if _is_printable_utf8(decoded):
            yield "base64", decoded.decode("utf-8")


def _decode_rot13(text: str, budget: DecoderBudget) -> Iterator[Tuple[str, str]]:
    if not budget.start_pass():
        return
    try:
        rot = codecs.decode(text, "rot_13")
    except Exception:
        return
    if rot != text:
        yield "rot13", rot


def _decode_percent(text: str, budget: DecoderBudget) -> Iterator[Tuple[str, str]]:
    if not budget.start_pass():
        return
    if "%" not in text:
        return
    try:
        unq = urllib.parse.unquote(text, errors="strict")
    except Exception:
        return
    if unq != text and any(ch.isprintable() for ch in unq):
        yield "percent", unq


def decoded_forms(text: str, raw: bytes, budget: DecoderBudget, depth: int = 0):
    """Yield (decoder_label, decoded_text) for every successful decode of the
    input. Depth is bounded by MAX_DEPTH; the outer scanner is responsible
    for stopping recursion once depth is exceeded.

    NOTE: each decoder is applied independently against the *original* input;
    we do not chain decoders by default (chaining would explode the budget
    for marginal value). Recursive re-decoding of decoded forms is the
    caller's option (and is itself budget-tracked).
    """
    if depth >= MAX_DEPTH:
        return
    for label, form in _decode_unicode_forms(text, budget):
        yield label, form
    for label, form in _decode_base64(raw, budget):
        yield label, form
    for label, form in _decode_rot13(text, budget):
        yield label, form
    for label, form in _decode_percent(text, budget):
        yield label, form
