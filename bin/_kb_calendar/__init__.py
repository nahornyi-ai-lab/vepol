"""Shared calendar surface for follow-up reminders v1.

Spec: knowledge/decisions/calendar-backed-followups-v1-2026-06-25.md
(spec-contract:sha256:16543b12f3249e6f338657aa6f361d4071311fb831466f2bd228b41d8174d700)

This package is the single chokepoint for reading and writing the owner's
Google Calendar from the knowledge base. There is exactly one live writer:
the adapter here. CLI surfaces (kb-followup, kb-task, kb-idea) route through it
so idempotency, fail-closed behavior, and tests stay consistent.
"""
from .errors import (
    CalendarError,
    CalendarDisabled,
    CalendarUnavailable,
    CalendarWriteError,
    CalendarUncertain,
    DateParseError,
)

__all__ = [
    "CalendarError",
    "CalendarDisabled",
    "CalendarUnavailable",
    "CalendarWriteError",
    "CalendarUncertain",
    "DateParseError",
]
