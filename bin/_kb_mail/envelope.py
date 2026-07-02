"""Mail brief envelope: schema, atomic private write, and same-day read.

The envelope is the ONLY thing that crosses from the mail reader into the rest
of the system. It lives under $HUB/personal/mail/ with mode 0600 and is written
atomically so a concurrent brief/cycle read never sees a partial JSON file.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

from .errors import MailWriteError
from .minimize import (
    minimize_thread, validate_item, contains_address, contains_markup,
)

SCHEMA_VERSION = "mail-brief/v1"
_PERIODS = ("morning", "evening")

_ENV_KEYS = {
    "schema_version", "generated_at", "period", "window", "available",
    "account_ref", "watermark", "stats", "items", "errors",
}
_STAT_KEYS = {"messages_seen", "threads_seen", "threads_included", "threads_deferred"}
_META_STR_MAX = 64
_ERR_STR_MAX = 200
_MAX_ERRORS = 20


def _clean_meta(s, maxlen: int) -> bool:
    """A bounded metadata string with no address token and no markup."""
    return (isinstance(s, str) and len(s) <= maxlen
            and not contains_address(s) and not contains_markup(s))


def hub_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("KB_HUB") or os.path.expanduser("~/knowledge"))


def mail_dir(hub: pathlib.Path | None = None) -> pathlib.Path:
    return (hub or hub_root()) / "personal" / "mail"


def brief_path(period: str, day: str, hub: pathlib.Path | None = None) -> pathlib.Path:
    return mail_dir(hub) / "briefs" / f"{day}-{period}.json"


def build_envelope(*, period: str, day: str, generated_at: str, window: dict,
                   items: list[dict], available: bool = True,
                   account_ref: str = "primary", watermark=None,
                   errors: list[str] | None = None,
                   stats: dict | None = None) -> dict:
    """Assemble a mail-brief/v1 envelope from already-minimized items."""
    if period not in _PERIODS:
        raise ValueError(f"bad period: {period!r}")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "period": period,
        "window": window,
        "available": bool(available),
        "account_ref": account_ref,
        "watermark": watermark,
        "stats": stats or {
            "messages_seen": 0, "threads_seen": len(items),
            "threads_included": len(items), "threads_deferred": 0,
        },
        "items": list(items),
        "errors": list(errors or []),
    }


def unavailable_envelope(*, period: str, day: str, generated_at: str,
                         window: dict, reason: str) -> dict:
    """The safe degraded envelope: shape is identical, available:false."""
    return build_envelope(
        period=period, day=day, generated_at=generated_at, window=window,
        items=[], available=False, watermark=None,
        errors=[f"gmail_unavailable:{reason}"],
        stats={"messages_seen": 0, "threads_seen": 0,
               "threads_included": 0, "threads_deferred": 0},
    )


def validate_envelope(env) -> bool:
    """True iff ``env`` is a complete, clean mail-brief envelope: EXACT top-level
    keys (no smuggled `raw_body` etc.), every metadata field bounded and free of
    addresses/markup, exact non-negative integer stats, bounded clean errors, and
    every item a strictly-minimized item. This is the persisted-envelope trust
    boundary — a tampered or leaky file degrades to available:false instead of
    reaching a composer (audit B4/B7/B8)."""
    if not isinstance(env, dict):
        return False
    if set(env.keys()) != _ENV_KEYS:
        return False
    if env["schema_version"] != SCHEMA_VERSION:
        return False
    if env["period"] not in _PERIODS:
        return False
    if not isinstance(env["available"], bool):
        return False
    if not _clean_meta(env["generated_at"], _META_STR_MAX):
        return False
    if not _clean_meta(env["account_ref"], _META_STR_MAX):
        return False
    if env["watermark"] is not None and not _clean_meta(env["watermark"], _META_STR_MAX):
        return False
    win = env["window"]
    if not isinstance(win, dict) or set(win.keys()) != {"from", "to"}:
        return False
    if not _clean_meta(win["from"], _META_STR_MAX) or not _clean_meta(win["to"], _META_STR_MAX):
        return False
    stats = env["stats"]
    if not isinstance(stats, dict) or set(stats.keys()) != _STAT_KEYS:
        return False
    for k in _STAT_KEYS:
        v = stats[k]
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            return False
    errs = env["errors"]
    if not isinstance(errs, list) or len(errs) > _MAX_ERRORS:
        return False
    if any(not _clean_meta(e, _ERR_STR_MAX) for e in errs):
        return False
    items = env["items"]
    if not isinstance(items, list):
        return False
    return all(validate_item(it) for it in items)


def write_envelope(env: dict, path: pathlib.Path) -> None:
    """Atomically write ``env`` to ``path`` with mode 0600 in a 0700 dir.

    Temp file in the same directory → flush/fsync → atomic os.replace. A partial
    write never becomes the live file. Raises MailWriteError on failure so a real
    disk problem blocks the dependent process instead of shipping a broken file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = json.dumps(env, ensure_ascii=False, indent=2).encode("utf-8")
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        os.chmod(path, 0o600)
    except MailWriteError:
        raise
    except Exception as e:
        raise MailWriteError(f"could not write envelope {path}: {e}")


def read_same_day_envelope(period: str, day: str,
                           hub: pathlib.Path | None = None):
    """Return the validated same-day envelope, or None if missing / corrupt /
    invalid. Never raises — a broken file degrades to None (caller injects an
    available:false block). Callers must NOT perform a hidden Gmail read here."""
    path = brief_path(period, day, hub)
    try:
        if not path.exists():
            return None
        env = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return env if validate_envelope(env) else None
