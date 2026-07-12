"""Mail source — read `mail-people/v1` senders-identity envelopes.

Per the People Notebook v1 spec (D2) and the 2026-07-05 build plan
(shared contracts), the people connector reads ONLY the minimized
senders-identity envelope written by `kb-mail-brief` at
`<hub>/personal/mail/people/<YYYY-MM-DD>-<period>.json` — never Gmail,
never the brief envelope, never message bodies. The envelope carries
bounded sender identity fields only (name/address/domain/timestamps/
count); validation rejects unknown keys so message content can never
be smuggled through this path.

Per-envelope idempotency is a processed-watermark at
`<hub>/people/.mail-envelopes-processed.json`:

    {"schema_version": 1, "processed": {"<date>-<period>": "<sha256-of-file>"}}

An envelope is consumed at most once per content hash — re-running
after approve/reject re-proposes nothing.

Public interface:
    validate_envelope(env) -> bool
    MailSource(hub).pending_envelopes() -> (items, warnings)
    MailSource(hub).filter_senders(senders) -> (kept, dropped_count)
    read_processed(hub) / mark_processed(hub, key, sha)
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path

from . import ContactSource
# Filter regexes + owner-emails loader are shared with the other
# sources so mail/calendar/project keep one filtering vocabulary.
from .. import filters
from .project_source import (
    _BOT_LOCAL_PART_RE, _RESOURCE_CAL_RE, _load_owner_emails,
)
# Writer-side strict envelope validator (single source of truth).
from _kb_mail import validate_people_envelope as _validate_people_envelope

SCHEMA = "mail-people/v1"
PROCESSED_FILENAME = ".mail-envelopes-processed.json"

_NAME_CAP = 200


def envelopes_dir(hub: Path) -> Path:
    return Path(hub) / "personal" / "mail" / "people"


def processed_path(hub: Path) -> Path:
    return Path(hub) / "people" / PROCESSED_FILENAME


def envelope_key(env: dict) -> str:
    return f"{env['date']}-{env['period']}"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(1 << 16)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def validate_envelope(env) -> bool:
    """True iff ``env`` is a complete, clean mail-people/v1 envelope.

    Delegates to the writer's own validator
    (`_kb_mail.validate_people_envelope`) so reader and writer can
    never drift apart: the writer's rules (exact key sets, markup-free
    bounded sender names, lowercase address, domain==address domain,
    count >= 1, <= 200 senders, available:false => senders == []) are
    the single source of truth.
    """
    return _validate_people_envelope(env)


# ---------------------------------------------------------------------------
# Processed-watermark (per-envelope idempotency).
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, obj: dict) -> None:
    """tempfile + os.replace in the same directory (module idiom)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-",
                               suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_processed(hub: Path) -> dict:
    """Load the watermark file; malformed/missing → empty schema-1 doc."""
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

class MailSource(ContactSource):
    """Read validated, not-yet-processed senders-identity envelopes.

    The apply policy (known address → live sighting; new/ambiguous →
    staged) lives in kb-extract-people, which owns dedup and staging;
    this class owns envelope IO, validation, filtering and the
    processed-watermark keys.
    """

    def __init__(self, hub: Path):
        self.hub = Path(hub)

    def pending_envelopes(self) -> tuple[list[dict], list[dict]]:
        """Return ([{path, env, key, sha}, …], warnings).

        Only structurally valid envelopes whose content hash is not in
        the processed-watermark are returned, sorted by filename
        (chronological for the `<date>-<period>.json` naming).
        Corrupt or invalid files produce warnings and are NOT marked
        processed — a broken envelope stays visible, never silently
        consumed.
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
                warnings.append({"kind": "mail_envelope_unreadable",
                                 "path": str(p), "detail": str(e)})
                continue
            if not validate_envelope(env):
                warnings.append({"kind": "mail_envelope_invalid",
                                 "path": str(p)})
                continue
            key = envelope_key(env)
            # The processed-watermark stores one hash per logical key
            # (<date>-<period>). A second file carrying the same date/period
            # under a non-canonical name (e.g. a copied `…-old.json`) would
            # share that key and could be reprocessed forever as the two
            # files' hashes fight over the single slot. Accept only the
            # canonical `<date>-<period>.json` name so one key ↔ one file.
            if p.name != f"{key}.json":
                warnings.append({"kind": "mail_envelope_noncanonical_name",
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

        Filters (build-plan contract): bot/noreply/system local parts,
        resource-calendar addresses, owner-self addresses
        (`<PEOPLE_DIR>/.owner-emails.txt`). `.rejected.yaml` filtering
        happens at apply time in kb-extract-people (it also covers
        name-keyed rejections). Kept items are normalized contact
        dicts: {"name", "email" (lowercased), "count"}.
        """
        owner_emails = _load_owner_emails()
        kept: list[dict] = []
        dropped = 0
        for s in senders:
            email = s["address"].strip().lower()
            if (_BOT_LOCAL_PART_RE.match(email)
                    or filters.is_role_email(email)
                    or filters.is_reserved_example_email(email)
                    or _RESOURCE_CAL_RE.search(email)
                    or email in owner_emails):
                dropped += 1
                continue
            kept.append({
                "name": (s.get("name") or "").strip()[:_NAME_CAP],
                "email": email,
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
                c["context"] = f"{c['count']} messages"
                c["envelope_key"] = item["key"]
                c["source_ref"] = f"mail:{env['period']}-{env['date']}"
                out.append(c)
        return out
