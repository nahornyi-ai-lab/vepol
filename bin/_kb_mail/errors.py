"""Mail error taxonomy.

Separate types so callers fail closed precisely: a disabled connector, a
connector that is down, and a durable-write that failed are different risks.
Mirror of _kb_calendar/errors.py for the mail surface.
"""
from __future__ import annotations


class MailError(Exception):
    """Base for all mail surface errors."""


class MailDisabled(MailError):
    """KB_MAIL_DISABLE=1 — the Gmail connector must not be touched at all."""


class MailUnavailable(MailError):
    """Gmail is unreachable: host missing, not connected, auth missing, network
    down, malformed response. No mail was read. Degrade to an available:false
    envelope; never block the morning brief."""


class MailWriteError(MailError):
    """Writing the envelope/watermark file to disk failed. This is a real local
    bug and must surface as a non-zero exit that blocks the dependent process."""
