"""The single calendar writer/reader.

Backends:
  - DisabledBackend   — KB_CALENDAR_DISABLE=1; never touches the connector.
  - FakeBackend       — tests; records calls, dedupes by idempotency key,
                        simulates ok / fail / uncertain. No network.
  - ProductionBackend — Google Calendar MCP via the runtime host (preferred),
                        reusing _kb_mcp.McpHostRunner. Not exercised by tests.

Idempotency: the event id is derived deterministically from the follow-up id so
a retry after a crash/timeout dedupes server-side instead of creating a second
event (spec: Calendar Event Shape, AC3, AC10).
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib

from .errors import (
    CalendarDisabled,
    CalendarUnavailable,
    CalendarUncertain,
    CalendarWriteError,
)


def idempotency_key(fid: str) -> str:
    """Deterministic, Google-Calendar-id-safe key (base32hex charset a-v0-9)."""
    return "vepolfup" + hashlib.sha1(fid.encode("utf-8")).hexdigest()[:20]


class CalendarAdapter:
    def __init__(self, backend):
        self.backend = backend

    @property
    def name(self) -> str:
        return type(self.backend).__name__

    def create_event(self, proposal: dict) -> dict:
        """Create (or idempotently confirm) one event. Returns an event pointer:
        {event_id, event_url, idempotency_key, calendar}."""
        return self.backend.create_event(proposal)

    def list_events(self, start: str, end: str) -> list[dict]:
        """Return raw events in [start, end). Caller minimizes them."""
        return self.backend.list_events(start, end)


# ── disabled ───────────────────────────────────────────────────────────────
class DisabledBackend:
    def create_event(self, proposal: dict) -> dict:
        raise CalendarDisabled("KB_CALENDAR_DISABLE=1: calendar writes are off")

    def list_events(self, start: str, end: str) -> list[dict]:
        raise CalendarDisabled("KB_CALENDAR_DISABLE=1: calendar reads are off")


# ── fake (tests) ────────────────────────────────────────────────────────────
class FakeBackend:
    """File-driven fake. KB_CALENDAR_FAKE_DIR holds:
        mode             : ok | fail | uncertain  (default ok)
        create-calls.jsonl : one line appended per create attempt
        store.jsonl        : the fake "server" — keyed by idempotency_key
        list-events.json   : array of raw events returned by list_events
    """

    def __init__(self, directory: str):
        self.dir = pathlib.Path(directory)

    def _mode(self) -> str:
        f = self.dir / "mode"
        return f.read_text(encoding="utf-8").strip() if f.exists() else "ok"

    def _load_store(self) -> dict:
        store = self.dir / "store.jsonl"
        out: dict[str, dict] = {}
        if store.exists():
            for line in store.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    r = json.loads(line)
                    out[r["idempotency_key"]] = r
        return out

    def create_event(self, proposal: dict) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        key = idempotency_key(proposal["id"])
        # record the attempt first — even a failed/uncertain call is an attempt
        with open(self.dir / "create-calls.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": proposal["id"], "idempotency_key": key}) + "\n")

        mode = self._mode()
        if mode == "fail":
            raise CalendarWriteError("fake: connector create failed")

        # ok and uncertain both "create" server-side, idempotently by key
        store = self._load_store()
        if key not in store:
            rec = {
                "idempotency_key": key,
                "event_id": "evt-" + key,
                "event_url": "https://calendar.google.com/event?eid=" + key,
                "summary": proposal.get("summary"),
                "start": proposal.get("start"),
                "end": proposal.get("end"),
            }
            with open(self.dir / "store.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            store[key] = rec
        rec = store[key]

        if mode == "uncertain":
            # the event exists server-side, but the response was lost
            raise CalendarUncertain("fake: response lost after create", idempotency_key=key)

        return {
            "event_id": rec["event_id"],
            "event_url": rec["event_url"],
            "idempotency_key": key,
            "calendar": "primary",
        }

    def list_events(self, start: str, end: str) -> list[dict]:
        f = self.dir / "list-events.json"
        if not f.exists():
            return []
        with open(self.dir / "list-calls.jsonl", "a", encoding="utf-8") as log:
            log.write(json.dumps({"start": start, "end": end}) + "\n")
        return json.loads(f.read_text(encoding="utf-8"))


# ── production (Google Calendar MCP via runtime host) ───────────────────────
class ProductionBackend:
    """Preferred backend: the runtime's Google Calendar MCP surface, reached
    through _kb_mcp.McpHostRunner. Imported lazily so tests never need it."""

    def __init__(self):
        self._runner = None

    def _host(self):
        if self._runner is None:
            try:
                import sys
                here = os.path.dirname(os.path.realpath(__file__))
                parent = os.path.dirname(here)
                if parent not in sys.path:
                    sys.path.insert(0, parent)
                from _kb_mcp.runner import McpHostRunner  # type: ignore
            except Exception as e:  # pragma: no cover - host wiring
                raise CalendarUnavailable(f"MCP host unavailable: {e}")
            self._runner = McpHostRunner()
        return self._runner

    def create_event(self, proposal: dict) -> dict:
        key = idempotency_key(proposal["id"])
        prompt = (
            "Create exactly one Google Calendar event on the primary calendar "
            "using mcp__claude_ai_Google_Calendar__create_event. "
            "Use these fields and DO NOT invent attendees:\n"
            f"- id (client-assigned, for idempotency): {key}\n"
            f"- summary: [Vepol] {proposal.get('summary','')}\n"
            f"- start: {proposal.get('start')}\n"
            f"- end: {proposal.get('end')}\n"
            f"- timezone: {proposal.get('timezone', 'Europe/Madrid')}\n"
            "- transparency: transparent\n"
            "- reminder: popup 0 minutes before\n"
            f"- description: Vepol follow-up {proposal.get('id')} "
            f"({proposal.get('source','')})\n\n"
            "If an event with that id already exists, return it instead of "
            "creating a second one. Reply with ONLY a single JSON object: "
            '{"ok": true, "items": [{"event_id": "...", "event_url": "..."}], '
            '"stats": {"n_items": 1, "fetched_at": "<iso>"}} on success, or '
            '{"ok": false, "error": "<code>", "detail": "<text>"} on failure.'
        )
        try:
            envelope = self._host().call(prompt, timeout_s=90)
        except Exception as e:
            # We cannot tell whether the event was created → uncertain, not a
            # blind failure. Retry will dedupe via the client-assigned id.
            raise CalendarUncertain(str(e), idempotency_key=key)
        items = envelope.get("items") or []
        if not items:
            raise CalendarUncertain("create returned no item", idempotency_key=key)
        item = items[0]
        return {
            "event_id": item.get("event_id") or key,
            "event_url": item.get("event_url", ""),
            "idempotency_key": key,
            "calendar": "primary",
        }

    def list_events(self, start: str, end: str) -> list[dict]:
        prompt = (
            "List Google Calendar events on the primary calendar between "
            f"{start} and {end} using mcp__claude_ai_Google_Calendar__list_events. "
            "Reply with ONLY a single JSON object: "
            '{"ok": true, "items": [{"title": "...", "start": "<iso>", '
            '"end": "<iso>"}], "stats": {"n_items": <n>, "fetched_at": "<iso>"}}. '
            "Do not include attendee emails, meeting links, or descriptions."
        )
        try:
            envelope = self._host().call(prompt, timeout_s=60)
        except Exception as e:
            raise CalendarUnavailable(str(e))
        return list(envelope.get("items") or [])


def get_adapter() -> CalendarAdapter:
    """Select the backend from the environment (disabled > fake > production)."""
    if os.environ.get("KB_CALENDAR_DISABLE") == "1":
        return CalendarAdapter(DisabledBackend())
    fake = os.environ.get("KB_CALENDAR_FAKE_DIR")
    if fake:
        return CalendarAdapter(FakeBackend(fake))
    return CalendarAdapter(ProductionBackend())
