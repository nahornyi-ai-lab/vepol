"""Turn a raw Gmail thread into one bounded, privacy-safe envelope item.

Minimization is a HARD privacy/trust boundary (spec: Data locations, AC2), not a
best-effort copy. Everything crossing it is treated as untrusted: raw body, MIME,
attachments, recipient lists, and raw sender addresses are DROPPED; every kept
field is length-bounded, value-whitelisted, and type-strict. Raw sender addresses
never enter a briefing envelope — they belong only in a private action proposal
once the owner chooses a reply.
"""
from __future__ import annotations

import re

_SUBJECT_MAX = 200
_LABEL_MAX = 120
_SUMMARY_MAX = 240
_REF_MAX = 256
_MAX_ACTIONS = 6
_MAX_FLAGS = 8

_CLASSIFICATIONS = {
    "needs_reply", "calendar", "waiting", "receipt", "ops_alert",
    "newsletter", "fyi", "noise", "unknown",
}
_URGENCIES = {"high", "normal", "low"}
_CONFIDENCES = {"high", "medium", "low"}
_ACTION_TYPES = {
    "reply_draft", "calendar_followup", "calendar_event", "backlog_task",
    "label_or_archive", "none",
}
_ALLOWED_FLAGS = {
    "external_instruction_present", "attachment_present",
    "link_present", "sensitive", "automated",
}

_ADDR_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# Broader "address-like" token: any local-part + '@' + optional domain part,
# so a truncated address fragment (e.g. "bob@evil" with no TLD, left behind by a
# mid-address clip) is still caught. Matches only when a non-space precedes '@',
# so "meeting @ 3pm" is not flagged.
_ADDRISH_RE = re.compile(r"[^\s@]+@[^\s@]*")
_REF_SAFE_RE = re.compile(r"[^A-Za-z0-9._\-:/+=]")
_REF_OK_RE = re.compile(r"^[A-Za-z0-9._\-:/+=]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def contains_address(text) -> bool:
    """True if the string carries an email-address-like token (full or fragment)."""
    return bool(_ADDRISH_RE.search(text)) if isinstance(text, str) else False


def contains_markup(text) -> bool:
    """True if the string carries angle-bracket markup (tag-injection risk)."""
    return isinstance(text, str) and ("<" in text or ">" in text)


ALLOWED_ITEM_KEYS = {
    "thread_ref", "message_ref", "date", "time", "sender_label", "subject",
    "classification", "urgency", "action_needed", "summary",
    "proposed_actions", "privacy_flags", "confidence",
}


def _clip(value, limit: int) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return s[:limit]


def _strip_addresses(text: str) -> str:
    """Remove raw email addresses from free text (audit B5). Full addresses
    become their bare domain (useful context); any residual address-like token,
    including a truncated fragment, is reduced to whatever follows '@'. Applies
    to every persisted free-text field, not just sender_label."""
    text = _ADDR_RE.sub(lambda m: m.group(1), text)
    return _ADDRISH_RE.sub(lambda m: m.group(0).split("@", 1)[1], text)


def _strip_markup(text: str) -> str:
    """Neutralize angle-bracket markup so persisted free text can never carry a
    tag (e.g. a hostile `</untrusted-source>`) (audit B9)."""
    return text.replace("<", " ").replace(">", " ")


def _clip_text(value, limit: int) -> str:
    """Bounded free text with addresses AND markup stripped BEFORE clipping, so a
    clip can never cut a full address into a surviving `local@` fragment (audit:
    clipped address fragments) and no tag survives (audit B9)."""
    return _clip(_strip_markup(_strip_addresses(_clip(value, 4 * limit))), limit)


def _clip_ref(value) -> str:
    """Opaque provider refs: bounded and restricted to id-safe characters (no
    '@', no markup) so a poisoned ref can never carry an address or free text
    downstream."""
    return _REF_SAFE_RE.sub("", _clip(value, _REF_MAX))


def _strict_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return False


def minimize_thread(raw: dict) -> dict:
    """Map a raw thread dict to a strictly bounded envelope item.

    The raw thread carries classification fields already resolved (the fake
    backend supplies them from a fixture; the production backend resolves them
    via the wrapped classification step). Anything not on the allowed field list
    is dropped — including body, attachments, recipients, and raw sender email
    addresses — and every kept value is bounded, whitelisted, or type-coerced.
    """
    classification = raw.get("classification", "unknown")
    if classification not in _CLASSIFICATIONS:
        classification = "unknown"
    urgency = raw.get("urgency", "normal")
    if urgency not in _URGENCIES:
        urgency = "normal"
    confidence = raw.get("confidence", "medium")
    if confidence not in _CONFIDENCES:
        confidence = "medium"

    actions = []
    for a in (raw.get("proposed_actions") or [])[:_MAX_ACTIONS]:
        if not isinstance(a, dict):
            continue
        atype = a.get("type", "none")
        if atype not in _ACTION_TYPES:
            atype = "none"
        actions.append({"type": atype, "summary": _clip_text(a.get("summary"), _SUMMARY_MAX)})

    flags = []
    for f in (raw.get("privacy_flags") or []):
        f = str(f)
        if f in _ALLOWED_FLAGS and f not in flags:
            flags.append(f)
        if len(flags) >= _MAX_FLAGS:
            break

    return {
        "thread_ref": _clip_ref(raw.get("thread_ref")),
        "message_ref": _clip_ref(raw.get("message_ref")),
        "date": (lambda d: d if _DATE_RE.match(d) else "")(_clip(raw.get("date"), 10)),
        "time": (lambda t: t if _TIME_RE.match(t) else "")(_clip(raw.get("time"), 5)),
        "sender_label": _clip_text(raw.get("sender_label"), _LABEL_MAX),
        "subject": _clip_text(raw.get("subject"), _SUBJECT_MAX),
        "classification": classification,
        "urgency": urgency,
        "action_needed": _strict_bool(raw.get("action_needed", False)),
        "summary": _clip_text(raw.get("summary"), _SUMMARY_MAX),
        "proposed_actions": actions,
        "privacy_flags": flags,
        "confidence": confidence,
    }


def validate_item(item) -> bool:
    """True iff ``item`` is a strictly-minimized envelope item: only allowed
    keys (no raw body/recipients/sender_email), whitelisted enums, bounded
    sizes, strict types. A consumer that reads a persisted envelope uses this so
    a tampered/oversized/leaky item degrades the whole envelope to
    available:false instead of reaching a composer."""
    if not isinstance(item, dict):
        return False
    # Exact key set: no extra keys (no raw body/recipients/address) AND no
    # missing keys — a partial/corrupt persisted item is invalid, not tolerated.
    if set(item.keys()) != ALLOWED_ITEM_KEYS:
        return False
    for k in ("thread_ref", "message_ref", "date", "time", "sender_label",
              "subject", "summary"):
        if not isinstance(item.get(k), str):
            return False
    if len(item["subject"]) > _SUBJECT_MAX: return False
    if len(item["summary"]) > _SUMMARY_MAX: return False
    if len(item["sender_label"]) > _LABEL_MAX: return False
    if len(item["thread_ref"]) > _REF_MAX: return False
    if len(item["message_ref"]) > _REF_MAX: return False
    if item["date"] and not _DATE_RE.match(item["date"]): return False
    if item["time"] and not _TIME_RE.match(item["time"]): return False
    # Address + markup policy on EVERY persisted free-text field, including
    # truncated fragments (audit B5, B9, clipped-fragment finding).
    _text_fields = ("sender_label", "subject", "summary")
    if any(_ADDRISH_RE.search(item[k]) for k in _text_fields):
        return False
    if any(contains_markup(item[k]) for k in _text_fields):
        return False
    # Refs must be id-safe (no '@', no markup, no free text) (audit B2/B5).
    if not _REF_OK_RE.match(item["thread_ref"]): return False
    if not _REF_OK_RE.match(item["message_ref"]): return False
    if item["classification"] not in _CLASSIFICATIONS: return False
    if item["urgency"] not in _URGENCIES: return False
    if item["confidence"] not in _CONFIDENCES: return False
    if not isinstance(item["action_needed"], bool): return False
    flags = item["privacy_flags"]
    if not isinstance(flags, list) or len(flags) > _MAX_FLAGS: return False
    if any(f not in _ALLOWED_FLAGS for f in flags): return False
    actions = item["proposed_actions"]
    if not isinstance(actions, list) or len(actions) > _MAX_ACTIONS: return False
    for a in actions:
        if not isinstance(a, dict) or set(a.keys()) != {"type", "summary"}:
            return False
        if a.get("type", "none") not in _ACTION_TYPES: return False
        s = a.get("summary", "")
        if not isinstance(s, str) or len(s) > _SUMMARY_MAX: return False
        if _ADDRISH_RE.search(s) or contains_markup(s): return False
    return True
