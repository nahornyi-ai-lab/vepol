"""Telegram source — read `telegram-people/v1` sender-identity envelopes.

Owner directive 2026-07-12: the multibot supervisor is deprecated, and
Telegram is read directly with the owner's credentials. The collector
(`kb-telegram-people`) connects read-only with a dedicated session,
aggregates WHO wrote (never message text) into a daily envelope at
`<hub>/personal/telegram/people/<YYYY-MM-DD>-daily.json`, and this
source consumes those envelopes staged-only — same D2 policy as mail:
no Telegram-derived identity can write a live card directly; a known
telegram locator may only upsert a live sighting.

The envelope carries bounded identity fields only (name/username/
user_id/phone/chat_type/timestamps/count); validation rejects unknown
keys so message content can never be smuggled through this path.

Per-envelope idempotency is a processed-watermark at
`<hub>/people/.telegram-envelopes-processed.json`:

    {"schema_version": 1, "processed": {"<date>-daily": "<sha256-of-file>"}}

Public interface:
    validate_envelope(env) -> bool
    TelegramSource(hub).pending_envelopes() -> (items, warnings)
    TelegramSource(hub).filter_senders(senders) -> (kept, dropped_count)
    read_processed(hub) / mark_processed(hub, key, sha)
    envelopes_dir(hub) / envelope_key(env) / file_sha256(path)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import ContactSource
from .. import filters
from .mail_source import _atomic_write_json, file_sha256  # shared idioms
from .project_source import (
    _TELEGRAM_SYSTEM_BLOCKLIST,
    _load_personal_telegram_blocklist,
)

SCHEMA = "telegram-people/v1"
PROCESSED_FILENAME = ".telegram-envelopes-processed.json"

_NAME_CAP = 200
_MAX_SENDERS = 500
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,31}$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{4,31}$")
_TOP_KEYS = {"schema", "date", "period", "generated_at", "available",
             "truncated", "senders"}
_SENDER_KEYS = {"name", "username", "user_id", "phone", "chat_type",
                "first_ts", "last_ts", "count"}
_CHAT_TYPES = {"private", "group"}


def envelopes_dir(hub: Path) -> Path:
    return Path(hub) / "personal" / "telegram" / "people"


def processed_path(hub: Path) -> Path:
    return Path(hub) / "people" / PROCESSED_FILENAME


def envelope_key(env: dict) -> str:
    return f"{env['date']}-{env['period']}"


def _clean_str(v, cap: int) -> bool:
    return (isinstance(v, str) and len(v) <= cap
            and "\n" not in v and "\r" not in v)


def validate_envelope(env) -> bool:
    """True iff ``env`` is a complete, clean telegram-people/v1 envelope.

    Strict by construction (mirrors the mail-people validator): exact
    key sets top-level and per sender, so subjects/bodies/free-text can
    never ride along; bounded newline-free names; lowercase usernames;
    positive non-bool ints; available:false => senders == []; duplicate
    user_ids rejected.
    """
    if not isinstance(env, dict) or set(env.keys()) != _TOP_KEYS:
        return False
    if env.get("schema") != SCHEMA:
        return False
    if not (isinstance(env.get("date"), str) and _DATE_RE.match(env["date"])):
        return False
    if env.get("period") != "daily":
        return False
    if not _clean_str(env.get("generated_at"), 64):
        return False
    if not isinstance(env.get("available"), bool):
        return False
    if not isinstance(env.get("truncated"), bool):
        return False
    senders = env.get("senders")
    if not isinstance(senders, list) or len(senders) > _MAX_SENDERS:
        return False
    if env["available"] is False and senders != []:
        return False
    seen_ids: set[int] = set()
    for s in senders:
        if not isinstance(s, dict) or set(s.keys()) != _SENDER_KEYS:
            return False
        if not _clean_str(s.get("name"), _NAME_CAP):
            return False
        u = s.get("username")
        if not isinstance(u, str) or (u and not _USERNAME_RE.match(u)):
            return False
        if not (s.get("name") or u):
            return False  # an identity needs at least a name or a username
        uid = s.get("user_id")
        if isinstance(uid, bool) or not isinstance(uid, int) or uid < 1:
            return False
        if uid in seen_ids:
            return False
        seen_ids.add(uid)
        ph = s.get("phone")
        if not isinstance(ph, str) or (ph and not _PHONE_RE.match(ph)):
            return False
        if s.get("chat_type") not in _CHAT_TYPES:
            return False
        if not (_clean_str(s.get("first_ts"), 64)
                and _clean_str(s.get("last_ts"), 64)):
            return False
        cnt = s.get("count")
        if isinstance(cnt, bool) or not isinstance(cnt, int) or cnt < 1:
            return False
    return True


# ---------------------------------------------------------------------------
# Processed-watermark (per-envelope idempotency) — same shape as mail.
# ---------------------------------------------------------------------------

def read_processed(hub: Path) -> dict:
    p = processed_path(hub)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "processed": {}}
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or not isinstance(data.get("processed"), dict)):
        return {"schema_version": 1, "processed": {}}
    return data


def mark_processed(hub: Path, key: str, sha: str) -> None:
    data = read_processed(hub)
    data["processed"][key] = sha
    _atomic_write_json(processed_path(hub), data)


# ---------------------------------------------------------------------------
# Source.
# ---------------------------------------------------------------------------

class TelegramSource(ContactSource):
    """Read validated, not-yet-processed telegram identity envelopes.

    The apply policy (known telegram locator → live sighting; new or
    ambiguous → staged) lives in kb-extract-people, which owns dedup
    and staging; this class owns envelope IO, validation, filtering and
    the processed-watermark keys.
    """

    def __init__(self, hub: Path):
        self.hub = Path(hub)

    def pending_envelopes(self) -> tuple[list[dict], list[dict]]:
        """Return ([{path, env, key, sha}, …], warnings).

        Same contract as the mail source: only structurally valid
        envelopes under their canonical `<date>-daily.json` name whose
        content hash is not in the processed-watermark; corrupt or
        invalid files warn and are never silently consumed.
        """
        d = envelopes_dir(self.hub)
        if not d.is_dir():
            return [], []
        processed = read_processed(self.hub).get("processed", {})
        out: list[dict] = []
        warnings: list[dict] = []
        for p in sorted(d.glob("*.json")):
            try:
                env = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                warnings.append({"kind": "telegram_envelope_unreadable",
                                 "path": str(p), "detail": str(e)})
                continue
            if not validate_envelope(env):
                warnings.append({"kind": "telegram_envelope_invalid",
                                 "path": str(p)})
                continue
            key = envelope_key(env)
            if p.name != f"{key}.json":
                warnings.append({"kind": "telegram_envelope_noncanonical_name",
                                 "path": str(p), "expected": f"{key}.json"})
                continue
            sha = file_sha256(p)
            if processed.get(key) == sha:
                continue
            out.append({"path": p, "env": env, "key": key, "sha": sha})
        return out, warnings

    @staticmethod
    def filter_senders(senders: list) -> tuple[list[dict], int]:
        """Drop non-people senders; return (kept, dropped_count).

        Filters: bot identities (handle/name heuristics shared with all
        sources), the packaged system handle blocklist, and the
        owner-curated personal blocklist
        (`<PEOPLE_DIR>/.blocklist-telegram.txt` — owner-self handles
        live there, never in shipped files). `.rejected.yaml` filtering
        happens at apply time in kb-extract-people. Kept items are
        normalized contact dicts:
        {"name", "telegram" ("@handle" or ""), "user_id", "phone",
         "chat_type", "count"}.
        """
        personal = _load_personal_telegram_blocklist()
        kept: list[dict] = []
        dropped = 0
        for s in senders:
            name = (s.get("name") or "").strip()[:_NAME_CAP]
            username = (s.get("username") or "").strip().lower()
            if filters.is_bot_identity(name=name, telegram=username):
                dropped += 1
                continue
            if username and (username in _TELEGRAM_SYSTEM_BLOCKLIST
                             or username in personal):
                dropped += 1
                continue
            kept.append({
                "name": name,
                "telegram": f"@{username}" if username else "",
                "user_id": s["user_id"],
                "phone": (s.get("phone") or "").strip(),
                "chat_type": s.get("chat_type", "private"),
                "count": s.get("count", 0),
            })
        return kept, dropped

    def get_contacts(self) -> list[dict]:
        """ContactSource protocol: flatten pending envelopes into
        contact dicts (does NOT advance the watermark — the consumer
        marks each envelope after applying it)."""
        out: list[dict] = []
        pending, _ = self.pending_envelopes()
        for item in pending:
            env = item["env"]
            kept, _dropped = self.filter_senders(env["senders"])
            for c in kept:
                c["date"] = env["date"]
                c["context"] = f"{c['count']} messages (telegram)"
                c["envelope_key"] = item["key"]
                c["source_ref"] = f"telegram:{env['period']}-{env['date']}"
                out.append(c)
        return out
