"""Senders-identity envelope (mail-people/v1) for the People Notebook.

The same single kb-mail-brief run that writes the brief envelope additionally
writes one people envelope per period under $HUB/personal/mail/people/. It
carries ONLY bounded sender identity — name, address, domain, first/last
timestamps, count — never subjects, bodies, or snippets. The people connector
(kb-extract-people MailSource) reads only this envelope, never Gmail and never
the brief envelope.

Spec:  the People Notebook v1 spec (dev KB, decisions/people-notebook-spec-2026-07-04.md) (D2)
Plan:  its build plan (decisions/people-notebook-build-plan-2026-07-05.md) (C1)
"""
from __future__ import annotations

import pathlib
import re

from .envelope import mail_dir, _clean_meta, _META_STR_MAX
from .minimize import _clip_text, contains_markup, _ADDRISH_RE, _DATE_RE, _TIME_RE

PEOPLE_SCHEMA = "mail-people/v1"
_PERIODS = ("morning", "evening")

_ENV_KEYS = {"schema", "date", "period", "generated_at", "available", "senders"}
_SENDER_KEYS = {"name", "address", "domain", "first_ts", "last_ts", "count"}
_NAME_MAX = 200
_ADDR_MAX = 254
_MAX_SENDERS = 200

# A full, lowercase email address — nothing looser is allowed to persist.
_FULL_ADDR_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


def people_path(period: str, day: str, hub: pathlib.Path | None = None) -> pathlib.Path:
    return mail_dir(hub) / "people" / f"{day}-{period}.json"


def _thread_ts(raw: dict, fallback: str) -> str:
    """Bounded timestamp for one raw thread from its own date/time fields,
    falling back to the run timestamp when they are absent or malformed."""
    date = str(raw.get("date") or "")
    time = str(raw.get("time") or "")
    if _DATE_RE.match(date) and _TIME_RE.match(time):
        return f"{date}T{time}:00"
    return fallback[:_META_STR_MAX]


def collect_senders(raw_threads: list[dict], *, fallback_ts: str) -> list[dict]:
    """Aggregate raw (pre-minimize) threads into unique sender identities.

    Unique by lowercased address; a thread without a well-formed sender address
    contributes nothing (never guess an identity). The display name is bounded
    and stripped of markup/addresses — the address lives ONLY in its own field.
    Output is sorted by address for a deterministic envelope.
    """
    agg: dict[str, dict] = {}
    for raw in raw_threads:
        if not isinstance(raw, dict):
            continue
        addr = str(raw.get("sender_email") or raw.get("sender_address") or "")
        addr = addr.strip().lower()
        if len(addr) > _ADDR_MAX or not _FULL_ADDR_RE.match(addr):
            continue
        name = _clip_text(raw.get("sender_name") or raw.get("sender_label"), _NAME_MAX)
        ts = _thread_ts(raw, fallback_ts)
        cur = agg.get(addr)
        if cur is None:
            agg[addr] = {
                "name": name,
                "address": addr,
                "domain": addr.split("@", 1)[1],
                "first_ts": ts,
                "last_ts": ts,
                "count": 1,
            }
        else:
            cur["count"] += 1
            if ts < cur["first_ts"]:
                cur["first_ts"] = ts
            if ts > cur["last_ts"]:
                cur["last_ts"] = ts
            if not cur["name"] and name:
                cur["name"] = name
    return [agg[a] for a in sorted(agg)][:_MAX_SENDERS]


def build_people_envelope(*, period: str, day: str, generated_at: str,
                          senders: list[dict], available: bool = True) -> dict:
    """Assemble a mail-people/v1 envelope from already-collected senders."""
    if period not in _PERIODS:
        raise ValueError(f"bad period: {period!r}")
    return {
        "schema": PEOPLE_SCHEMA,
        "date": day,
        "period": period,
        "generated_at": generated_at,
        "available": bool(available),
        "senders": list(senders) if available else [],
    }


def validate_people_envelope(env) -> bool:
    """True iff ``env`` is a complete, clean mail-people envelope: EXACT key
    sets at both levels (no subject/body/snippet field can exist), bounded
    clean metadata, full lowercase addresses unique across senders, domain
    consistent with the address, strict positive integer counts. Mirrors
    validate_envelope strictness — this is the persisted trust boundary the
    people connector relies on; a tampered file must read as invalid, never as
    a partially-usable envelope."""
    if not isinstance(env, dict):
        return False
    if set(env.keys()) != _ENV_KEYS:
        return False
    if env["schema"] != PEOPLE_SCHEMA:
        return False
    if env["period"] not in _PERIODS:
        return False
    if not isinstance(env["date"], str) or not _DATE_RE.match(env["date"]):
        return False
    if not _clean_meta(env["generated_at"], _META_STR_MAX):
        return False
    if not isinstance(env["available"], bool):
        return False
    senders = env["senders"]
    if not isinstance(senders, list) or len(senders) > _MAX_SENDERS:
        return False
    if not env["available"] and senders != []:
        return False
    seen = set()
    for s in senders:
        if not isinstance(s, dict) or set(s.keys()) != _SENDER_KEYS:
            return False
        name = s["name"]
        if not isinstance(name, str) or len(name) > _NAME_MAX:
            return False
        if contains_markup(name) or _ADDRISH_RE.search(name):
            return False
        addr = s["address"]
        if not isinstance(addr, str) or len(addr) > _ADDR_MAX:
            return False
        if not _FULL_ADDR_RE.match(addr):
            return False
        if addr in seen:
            return False
        seen.add(addr)
        if s["domain"] != addr.split("@", 1)[1]:
            return False
        for k in ("first_ts", "last_ts"):
            if not _clean_meta(s[k], _META_STR_MAX):
                return False
        count = s["count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return False
    return True


def read_people_envelope(period: str, day: str,
                         hub: pathlib.Path | None = None):
    """Return the validated people envelope, or None if missing / corrupt /
    invalid. Never raises — a broken file degrades to None. Callers must NOT
    perform a hidden Gmail read here (mirror of read_same_day_envelope)."""
    import json
    path = people_path(period, day, hub)
    try:
        if not path.exists():
            return None
        env = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return env if validate_people_envelope(env) else None
