"""Calendar source — fetch Google Calendar attendees via MCP host.

Replaces the prior google-api-python-client direct-OAuth implementation.
See docs/methodology/mcp-first-sources.md for the principle.

Public interface:
    CalendarSource(days_back).get_contacts() -> list[dict]

Returns a list of dicts shaped:
    {"name": "...", "email": "...", "date": "YYYY-MM-DD", "context": "..."}

Per-source schema validation:
- email is required (rows without email are skipped — calendar dedup
  is email-first, so an attendee without email cannot be carried).
- date is required.
- name and context are bounded length (200 / 500) to mitigate
  prompt-injection-derived bloat.
- email is lowercased and stripped.
"""
from __future__ import annotations

import re
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# _kb_mcp lives one level up, alongside _kb_people.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _kb_mcp.runner import McpHostRunner  # noqa: E402

from . import ContactSource


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Resource-calendar emails (Google room-bookings, etc.) — skip; these
# aren't people. Pattern lifted from the legacy implementation.
_RESOURCE_CAL_RE = re.compile(r"resource\.calendar\.google\.com$")

_NAME_CAP = 200
_CONTEXT_CAP = 500


PROMPT_TEMPLATE = """\
Use the Google Calendar MCP tool mcp__claude_ai_Google_Calendar__list_events
to list events between {start_date} and {end_date} (inclusive) on the
user's primary calendar.

For each (attendee, event) pair, output ONE JSON object. If the same
person attends N different events, that produces N items — one per
event. EXCLUDE the calendar owner (the "self" attendee) from every
event. EXCLUDE resource-calendar attendees (room bookings) — those
have emails ending in `resource.calendar.google.com`.

Output a single JSON object on stdout with NO preamble, NO markdown,
NO trailing content. Use this exact shape:

{{"ok": true, "items": [
  {{"name": "<display name or empty>", "email": "<address>", "date": "<YYYY-MM-DD>", "context": "<event title>"}}
], "stats": {{"n_items": <integer>, "fetched_at": "{fetched_at}"}}}}

If the calendar tool is unreachable or unauthorized, instead output:

{{"ok": false, "error": "<short_snake_case_code>", "detail": "<human-readable detail>"}}

Constraints:
- email must be a valid RFC-5322-ish address; if missing, omit the item entirely.
- date must be ISO YYYY-MM-DD.
- name <= 200 chars; context <= 500 chars.
- Output ONLY the JSON object. No commentary before or after.

Request ID: {request_id}.
"""


class CalendarSource(ContactSource):
    """Fetch calendar attendees via the MCP host.

    Args:
        days_back: how many days of history to scan (today minus N).
        reauth: legacy parameter from the OAuth implementation. Ignored
                in the MCP version (auth is handled by the MCP host).
                Kept for caller-API stability.
        runner: optional McpHostRunner override for tests.
    """

    def __init__(
        self,
        days_back: int,
        reauth: bool = False,  # noqa: ARG002 — accepted for API stability
        runner: McpHostRunner | None = None,
    ):
        if days_back < 1:
            raise ValueError(f"days_back must be >= 1, got {days_back}")
        self.days_back = days_back
        self.runner = runner if runner is not None else McpHostRunner()

    def get_contacts(self) -> list[dict]:
        end_date = date.today()
        start_date = end_date - timedelta(days=self.days_back)
        request_id = str(uuid.uuid4())
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prompt = PROMPT_TEMPLATE.format(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            fetched_at=fetched_at,
            request_id=request_id,
        )
        envelope = self.runner.call(prompt, timeout_s=120)
        return self._sanitize(envelope.get("items", []), request_id=request_id)

    @staticmethod
    def _sanitize(items: list, *, request_id: str = "") -> list[dict]:
        """Per-source field validation. Items that fail are dropped, not raised.

        Each surviving item is tagged with `request_id` for provenance —
        per docs/methodology/mcp-first-sources.md § Security: provenance.
        """
        out: list[dict] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            email_raw = raw.get("email")
            if not isinstance(email_raw, str):
                continue
            email = email_raw.strip().lower()
            if not email or not _EMAIL_RE.match(email):
                continue
            if _RESOURCE_CAL_RE.search(email):
                continue  # room booking, not a person
            date_raw = raw.get("date")
            if not isinstance(date_raw, str):
                continue
            day = date_raw.strip()
            if not _ISO_DATE_RE.match(day):
                continue
            # Validate as a real date — regex accepts e.g. 2026-99-99.
            try:
                date.fromisoformat(day)
            except ValueError:
                continue
            name_raw = raw.get("name")
            name = (name_raw.strip() if isinstance(name_raw, str) else "")[:_NAME_CAP]
            context_raw = raw.get("context")
            context = (context_raw.strip() if isinstance(context_raw, str) else "")[:_CONTEXT_CAP]
            out.append({
                "name": name,
                "email": email,
                "date": day,
                "context": context,
                "request_id": request_id,
            })
        return out
