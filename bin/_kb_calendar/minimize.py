"""Privacy minimization at the agenda reader boundary.

Every event — meeting or follow-up — is reduced to bounded
date/time/title/source/status BEFORE it can reach a durable brief artifact or
the LLM prompt. Attendee emails, meeting links, and full descriptions are
dropped here, so AC8's privacy guarantee holds for non-follow-up events too
(spec: Daily Brief Integration, AC8).
"""
from __future__ import annotations

_TITLE_MAX = 120


def _bounded(s, n: int = _TITLE_MAX) -> str:
    s = (s or "").strip()
    return s[:n]


def _split_dt(iso: str):
    iso = (iso or "").strip()
    if "T" in iso:
        d, t = iso.split("T", 1)
        return d, t[:5]  # HH:MM only
    if " " in iso:
        d, t = iso.split(" ", 1)
        return d, t[:5]
    return iso, ""


def minimize_event(raw: dict, *, source: str, status: str = "confirmed") -> dict:
    """Return only the bounded, non-sensitive fields.

    `source` is "calendar" for connector meetings or "followup" for approved
    reminders. Nothing else from `raw` is carried forward.
    """
    start = raw.get("start") or raw.get("start_time") or raw.get("when") or ""
    date_str, time_str = _split_dt(start if isinstance(start, str) else "")
    title = raw.get("title") or raw.get("summary") or "(untitled)"
    return {
        "date": date_str,
        "time": time_str,
        "title": _bounded(title),
        "source": source,
        "status": status,
    }
