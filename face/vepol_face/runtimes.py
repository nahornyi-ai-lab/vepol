"""Runtime capability read-model.

Core rule (spec runtime-capability-registry-2026-08-15, and Face MVP-13):
a runtime is available ONLY on a successful observation. An elapsed cooldown,
a binary on PATH, and the absence of a recorded failure are all insufficient.
Absence of evidence is `unknown`, and `unknown` renders as degraded.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
from dataclasses import dataclass, field

BROKER_STATE = pathlib.Path(os.path.expanduser("~/knowledge/.orchestrator/state.json"))
CLI_TSV = pathlib.Path(os.path.expanduser("~/knowledge/.orchestrator/cli-tools.tsv"))

# Success older than this stops counting as evidence of "right now".
STALE_AFTER = dt.timedelta(hours=24)


@dataclass
class Availability:
    available: bool
    state: str            # available | blocked | unknown | missing
    reason: str = ""
    blocked_until: str | None = None
    last_success_at: str | None = None


@dataclass
class Runtime:
    name: str
    installed: bool
    state: str
    available: bool
    reason: str = ""
    blocked_until: str | None = None
    last_success_at: str | None = None
    when: str = ""
    capabilities: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "installed": self.installed,
            "state": self.state,
            "available": self.available,
            "reason": self.reason,
            "blocked_until": self.blocked_until,
            "last_success_at": self.last_success_at,
            "when": self.when,
            "capabilities": self.capabilities,
        }


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def availability_from_observation(
    blocked_until: str | None,
    last_success_at: str | None,
    last_category: str | None,
    now: str | dt.datetime,
) -> Availability:
    now_dt = _parse(now) if isinstance(now, str) else now
    if now_dt is None:
        now_dt = dt.datetime.now(dt.timezone.utc)

    blocked = _parse(blocked_until)
    success = _parse(last_success_at)

    if blocked and blocked > now_dt:
        return Availability(
            False, "blocked",
            f"blocked until {blocked_until}", blocked_until, last_success_at,
        )

    if success is None:
        return Availability(
            False, "unknown",
            "no successful observation on record — cooldown expiry is not availability",
            blocked_until, None,
        )

    if now_dt - success > STALE_AFTER:
        return Availability(
            False, "unknown",
            f"last success {last_success_at} is stale (> {STALE_AFTER})",
            blocked_until, last_success_at,
        )

    return Availability(True, "available", "last observation succeeded", blocked_until, last_success_at)


def _read_roster(roster: pathlib.Path | None) -> dict[str, dict]:
    """Parse the declarative CLI registry. Never invents runtimes."""
    path = roster if roster is not None else CLI_TSV
    out: dict[str, dict] = {}
    try:
        raw = pathlib.Path(path).read_text()
    except OSError:
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        name, kind, candidates, when = parts[0], parts[1], parts[2], parts[3]
        found = False
        for cand in candidates.split(":"):
            cand = os.path.expandvars(cand.replace("$HOME", os.path.expanduser("~")))
            if os.path.isabs(cand):
                found = os.path.isfile(cand) and os.access(cand, os.X_OK)
            else:
                found = shutil.which(cand) is not None
            if found:
                break
        out[name] = {"installed": found, "when": when, "kind": kind}
    return out


def load_runtimes(
    broker_state: pathlib.Path | None = None,
    roster: pathlib.Path | None = None,
    now: str | dt.datetime | None = None,
) -> dict[str, Runtime]:
    """Read-only view. Never mutates broker state."""
    now = now or dt.datetime.now(dt.timezone.utc).isoformat()
    state_path = broker_state if broker_state is not None else BROKER_STATE

    providers: dict[str, dict] = {}
    try:
        blob = json.loads(pathlib.Path(state_path).read_text())
        if isinstance(blob, dict) and isinstance(blob.get("providers"), dict):
            providers = blob["providers"]
    except (OSError, ValueError):
        providers = {}

    known = _read_roster(roster)
    names = sorted(set(known) | set(providers))

    out: dict[str, Runtime] = {}
    for name in names:
        meta = known.get(name, {"installed": False, "when": "", "kind": ""})
        prov = providers.get(name, {})
        if not meta["installed"] and name not in providers:
            out[name] = Runtime(name, False, "missing", False, "binary not found", when=meta["when"])
            continue
        avail = availability_from_observation(
            prov.get("blocked_until"),
            prov.get("last_success_at"),
            prov.get("last_category"),
            now,
        )
        if not meta["installed"] and name in providers:
            out[name] = Runtime(name, False, "missing", False, "binary not found", when=meta["when"])
            continue
        out[name] = Runtime(
            name=name,
            installed=True,
            state=avail.state,
            available=avail.available,
            reason=avail.reason,
            blocked_until=avail.blocked_until,
            last_success_at=avail.last_success_at,
            when=meta["when"],
            capabilities={
                "brokered": name in ("claude", "codex"),
                "interactive": name in ("claude", "codex", "agy"),
            },
        )
    return out
