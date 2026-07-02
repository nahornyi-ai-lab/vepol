"""Shared mail surface for mail briefing integration (read-only first slice).

Spec: knowledge/decisions/mail-briefing-integration-2026-06-29.md
(spec-contract:sha256:799cd78067cf4961ca95f1a63339d3070efae1afd342c572f374dd46fc32ce26)
Build plan: knowledge/decisions/mail-briefing-integration-build-plan-2026-07-01.md

This package is the single chokepoint for reading the owner's Gmail from the
knowledge base and turning it into one minimized, privacy-bounded envelope per
period. The first slice is read-only: no drafts, sends, labels, or deletes.
kb-brief / kb-retro / kb-morning-digest consume the envelope; they never touch
Gmail directly and never persist raw email content.
"""
from .errors import (
    MailError,
    MailDisabled,
    MailUnavailable,
    MailWriteError,
)
from .untrusted import wrap_untrusted
from .minimize import minimize_thread
from .envelope import (
    SCHEMA_VERSION,
    build_envelope,
    validate_envelope,
    write_envelope,
    read_same_day_envelope,
    brief_path,
)

__all__ = [
    "MailError",
    "MailDisabled",
    "MailUnavailable",
    "MailWriteError",
    "wrap_untrusted",
    "minimize_thread",
    "SCHEMA_VERSION",
    "build_envelope",
    "validate_envelope",
    "write_envelope",
    "read_same_day_envelope",
    "brief_path",
]
