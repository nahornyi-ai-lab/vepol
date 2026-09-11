"""Tri-state derivation. The core rule: available only on a successful,
fresh observation with no active cooldown. Everything else is `unknown`
(or `no` where a failure says so) and renders as degraded.

STALE_AFTER matches the Face read-model (vepol_face/runtimes.py) so both
surfaces agree about the same broker state.
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

from .observations import Observation, fmt_ts

STALE_AFTER = dt.timedelta(hours=24)
CAPABILITY_SOURCE = "table/v1"

# Static capabilities: value + evidence. `unknown` wherever nothing is on record.
CAPABILITIES: Dict[str, Dict[str, Tuple[str, str]]] = {
    "claude": {
        "resumable": ("yes", "E7 two-turn resume smoke 2026-08-20"),
        "interactive": ("yes", "tmux/PTY session takeover (Vepol Face sessions)"),
        "web_current": ("unknown", "no verified current-web smoke on record"),
        "edit_capable": ("yes", "KB write-back smoke 2026-06-06"),
    },
    "codex": {
        "resumable": ("yes", "E8 `codex exec resume` smoke 2026-08-20"),
        "interactive": ("yes", "interactive TUI; tmux takeover"),
        "web_current": ("unknown", "no verified current-web smoke on record"),
        "edit_capable": ("yes", "`--sandbox workspace-write`"),
    },
    "agy": {
        "resumable": ("unknown", "no resume smoke on record"),
        "interactive": ("yes", "interactive CLI; tmux takeover"),
        "web_current": ("unknown", "no verified current-web smoke on record"),
        "edit_capable": ("yes", "writes durable notes (launch matrix 2026-06-11)"),
    },
    "grok": {
        "resumable": ("unknown", "no resume smoke on record"),
        "interactive": ("yes", "interactive CLI; tmux takeover"),
        "web_current": ("yes", "web smoke 2026-06-13 (launch matrix)"),
        "edit_capable": ("yes", "`--permission-mode acceptEdits`"),
    },
    "notebooklm": {
        "resumable": ("no", "artifact CLI, not an agent"),
        "interactive": ("no", "artifact CLI, not an agent"),
        "web_current": ("no", "artifact CLI, not an agent"),
        "edit_capable": ("no", "artifact CLI, not an agent"),
    },
    "opencode": {
        "resumable": ("unknown", "no resume smoke on record"),
        "interactive": ("yes", "interactive TUI; tmux takeover"),
        "web_current": ("unknown", "model-dependent; no verified smoke"),
        "edit_capable": ("yes", "agentic edit mode"),
    },
    "hermes": {
        "resumable": ("unknown", "`--resume SESSION` exists; no resume smoke on record"),
        "interactive": ("yes", "REPL/TUI (`hermes chat`); tmux takeover"),
        "web_current": ("unknown", "web toolset exists; no verified current-web smoke"),
        "edit_capable": ("unknown", "tools load in one-shot mode; no verified edit smoke"),
    },
}
CAPABILITY_FIELDS = ("resumable", "interactive", "web_current", "edit_capable")


def humanize_age(seconds: Optional[int]) -> str:
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 48 * 3600:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def newest(observations: List[Observation]) -> Optional[Observation]:
    candidates = [o for o in observations if o is not None and o.observed_at is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda o: o.sort_key())


def derive_row(
    name: str,
    *,
    installed: str,
    obs: Optional[Observation],
    blocked_until: Optional[dt.datetime],
    now: dt.datetime,
    row_source: str,
    fallback_of: Optional[str],
    probe_refused: bool = False,
) -> dict:
    reasons: List[str] = []
    healthy = authenticated = quota = "unknown"
    age_seconds: Optional[int] = None
    fresh_success = False

    if installed == "no":
        reasons.append("binary not installed")
    if row_source == "broker-state-only":
        reasons.append("no roster row (broker state only)")

    if obs is None:
        reasons.append("no observation")
    else:
        age_seconds = max(0, int((now - obs.observed_at).total_seconds()))
        if obs.outcome == "success":
            if age_seconds <= STALE_AFTER.total_seconds():
                healthy = authenticated = quota = "yes"
                fresh_success = True
            else:
                reasons.append(f"last success {humanize_age(age_seconds)} ago exceeds the 24h window")
        else:
            healthy = "no"
            if obs.category == "auth":
                authenticated = "no"
            elif obs.category == "rate_limit":
                quota = "no"
            reasons.append(f"last observation failed ({obs.category or obs.reason or 'unspecified'})")

    cooldown_active = blocked_until is not None and blocked_until > now
    if cooldown_active:
        quota = "no"
        reasons.append(f"cooldown active until {fmt_ts(blocked_until)}")
    if probe_refused:
        reasons.append("probe refused: nested agent session")

    available = bool(fresh_success and not cooldown_active)

    caps = CAPABILITIES.get(name, {})
    row = {
        "name": name,
        "installed": installed,
        "authenticated": authenticated,
        "quota_available": quota,
        "healthy": healthy,
    }
    for field in CAPABILITY_FIELDS:
        row[field] = caps.get(field, ("unknown", ""))[0]
    row["available"] = available
    row["fallback_of"] = fallback_of
    row["capability_source"] = CAPABILITY_SOURCE
    source = row_source
    if row_source != "broker-state-only":
        source = obs.source if obs is not None else "none"
    row["provenance"] = {
        "source": source,
        "observed_at": fmt_ts(obs.observed_at) if obs is not None else None,
        "age_seconds": age_seconds,
        "evidence": (obs.evidence or None) if obs is not None else None,
        "blocked_until": fmt_ts(blocked_until),
        "category": (obs.category if obs is not None else None),
    }
    row["reasons"] = reasons
    return row
