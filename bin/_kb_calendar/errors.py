"""Calendar error taxonomy.

Separate types so callers (and the approval gate) can fail closed precisely:
a disabled connector, a connector that is down, a write that definitely failed,
and a write whose result is unknown are all different risks.
"""
from __future__ import annotations


class CalendarError(Exception):
    """Base for all calendar surface errors."""


class CalendarDisabled(CalendarError):
    """KB_CALENDAR_DISABLE=1 — the connector must not be touched at all."""


class CalendarUnavailable(CalendarError):
    """Connector is unreachable: host missing, auth missing, network down,
    malformed response. No event was created."""


class CalendarWriteError(CalendarError):
    """A create was attempted and definitively failed. Nothing was written;
    the proposal stays retryable."""


class CalendarUncertain(CalendarError):
    """A create may have succeeded on the calendar but the result was lost
    (timeout / crash window). Must NOT be retried with a fresh event — only
    with the same deterministic idempotency key, which dedupes server-side.

    Attributes:
        idempotency_key: the deterministic key used, for reconciliation.
    """

    def __init__(self, message: str, *, idempotency_key: str | None = None):
        super().__init__(message)
        self.idempotency_key = idempotency_key


class DateParseError(CalendarError):
    """A follow-up phrase could not be resolved to a definite date/time.
    Callers must fail closed and ask for an explicit ISO date/time."""
