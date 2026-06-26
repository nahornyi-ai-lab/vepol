"""Deterministic RU/EN follow-up date parsing.

All parsing accepts an explicit `now` so tests are reproducible. If the phrase
cannot be resolved to a definite date, parsing raises DateParseError — it must
never silently pick a date (spec: Date Parsing, AC4).

Supported (case-insensitive, keyword may sit inside a longer phrase):
  tomorrow / tomorrow 09:00 / today
  in N days
  next <weekday>
  завтра / завтра в 09:00 / послезавтра / сегодня
  через N дней
  (в) следующий <weekday>
  ISO date (YYYY-MM-DD) and ISO datetime
"""
from __future__ import annotations

import re
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from .errors import DateParseError

DEFAULT_TZ = "Europe/Madrid"
DEFAULT_TIME = (9, 0)
DEFAULT_DURATION_MIN = 15

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "понедельник": 0, "вторник": 1, "среда": 2, "среду": 2, "четверг": 3,
    "пятница": 4, "пятницу": 4, "суббота": 5, "субботу": 5, "воскресенье": 6,
}


def _coerce_now(now) -> datetime:
    if now is None:
        return datetime.now().astimezone()
    if isinstance(now, datetime):
        return now
    if isinstance(now, str):
        try:
            return datetime.fromisoformat(now)
        except ValueError as e:
            raise DateParseError(f"invalid --now value {now!r}: {e}")
    raise DateParseError(f"unsupported now type: {type(now).__name__}")


def _next_weekday(d: date, target: int) -> date:
    ahead = (target - d.weekday()) % 7
    if ahead == 0:
        ahead = 7  # "next <weekday>" is always in the future
    return d + timedelta(days=ahead)


def _build(start_dt: datetime, tz: str, duration_minutes: int) -> dict:
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return {
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "timezone": tz,
        "all_day": False,
    }


def _try_iso(raw: str, zone: ZoneInfo, default_time, tz: str, duration_minutes: int):
    # date-only → apply default time (not midnight). Fail closed (clean error,
    # never a traceback) on an ISO-shaped but invalid calendar date.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            raise DateParseError(f"{raw!r} is not a valid calendar date")
        start = datetime.combine(d, dtime(*default_time), zone)
        return _build(start, tz, duration_minutes)
    # full ISO datetime (with or without offset / space or T separator)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    return _build(dt, tz, duration_minutes)


def parse_when(
    text: str,
    *,
    now,
    tz: str = DEFAULT_TZ,
    default_time=DEFAULT_TIME,
    duration_minutes: int = DEFAULT_DURATION_MIN,
) -> dict:
    """Resolve a follow-up phrase to {start, end, timezone, all_day}.

    Raises DateParseError if the phrase is not a definite date/time.
    """
    raw = (text or "").strip()
    if not raw:
        raise DateParseError("empty --when; give a phrase or an ISO date/time")

    zone = ZoneInfo(tz)

    # ISO date/datetime is absolute and needs no `now`.
    iso = _try_iso(raw, zone, default_time, tz, duration_minutes)
    if iso is not None:
        return iso

    # Relative phrases ("tomorrow", "через 10 дней", …) resolve against `now`.
    now_dt = _coerce_now(now)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=zone)
    now_local = now_dt.astimezone(zone)

    low = raw.lower()

    # optional explicit HH:MM (won't match "10 days" — requires a colon)
    hh, mm = default_time
    tmatch = re.search(r"(?:в\s+|at\s+)?(\d{1,2}):(\d{2})", low)
    if tmatch:
        hh, mm = int(tmatch.group(1)), int(tmatch.group(2))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise DateParseError(f"invalid time {hh:02d}:{mm:02d} in {raw!r}")

    target: date | None = None

    if re.search(r"\bпослезавтра\b", low):
        target = (now_local + timedelta(days=2)).date()
    elif re.search(r"\bзавтра\b", low) or re.search(r"\btomorrow\b", low):
        target = (now_local + timedelta(days=1)).date()
    elif re.search(r"\bсегодня\b", low) or re.search(r"\btoday\b", low):
        target = now_local.date()
    else:
        m = re.search(r"(?:in|через)\s+(\d+)\s+(?:days?|день|дн\w*)", low)
        if m:
            target = (now_local + timedelta(days=int(m.group(1)))).date()
        else:
            m2 = re.search(r"(?:next|следующ\w+)\s+([a-zа-яё]+)", low)
            if m2 and m2.group(1) in _WEEKDAYS:
                target = _next_weekday(now_local.date(), _WEEKDAYS[m2.group(1)])

    if target is None:
        raise DateParseError(
            f"could not parse a definite date from {raw!r}; "
            "give an explicit ISO date/time (e.g. 2026-07-01T09:00)"
        )

    start = datetime.combine(target, dtime(hh, mm), zone)
    return _build(start, tz, duration_minutes)
