"""Observation sources: broker state (read-only) and the probe cache.

Broker state (`kb-orchestrator-run`) semantics, verified 2026-09-01:
  * on success the broker sets `last_success_at` and pops `last_category`;
  * on failure it sets `last_category` (+ `last_stderr_snippet`, maybe
    `blocked_until`) and `last_seen_at` moves on every run;
  * an elapsed `blocked_until` is popped on the next run.
So `last_category` present == the latest broker observation was a failure.

The cache is a cache, not truth: missing -> empty, malformed -> warning + empty.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import CACHE_SCHEMA

SOURCE_PRIORITY = {"probe": 1, "broker-state": 0}


@dataclass
class Observation:
    observed_at: dt.datetime
    outcome: str  # "success" | "failure"
    source: str  # "probe" | "broker-state"
    category: Optional[str] = None
    reason: Optional[str] = None
    evidence: str = ""

    def sort_key(self) -> Tuple[dt.datetime, int]:
        return (self.observed_at, SOURCE_PRIORITY.get(self.source, -1))


def parse_ts(value) -> Optional[dt.datetime]:
    """ISO-8601 with `Z`, an offset, or naive (taken as UTC). None when unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def fmt_ts(value: Optional[dt.datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json_file(path: pathlib.Path, label: str) -> Tuple[dict, List[str]]:
    if not path.exists():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, [f"{label} malformed at {path}: {exc}; treated as empty"]
    if not isinstance(data, dict):
        return {}, [f"{label} malformed at {path}: top level is not an object; treated as empty"]
    return data, []


def load_broker_state(path: pathlib.Path) -> Tuple[Dict[str, dict], List[str]]:
    data, warnings = load_json_file(path, "broker state")
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, dict):
        return {}, warnings
    return {k: v for k, v in providers.items() if isinstance(v, dict)}, warnings


def broker_observation(provider: dict) -> Tuple[Optional[Observation], Optional[dt.datetime]]:
    """(latest broker observation or None, blocked_until or None)."""
    blocked_until = parse_ts(provider.get("blocked_until"))
    category = provider.get("last_category")
    seen = parse_ts(provider.get("last_seen_at"))
    success = parse_ts(provider.get("last_success_at"))
    if isinstance(category, str) and category:
        when = seen or blocked_until or success
        if when is None:
            return None, blocked_until
        snippet = provider.get("last_stderr_snippet")
        evidence = f"broker run failed ({category})"
        if isinstance(snippet, str) and snippet.strip():
            evidence += f": {snippet.strip()[:160]}"
        return Observation(when, "failure", "broker-state", category=category,
                           reason=category, evidence=evidence), blocked_until
    if success is not None:
        return Observation(success, "success", "broker-state",
                           evidence="broker run succeeded"), blocked_until
    return None, blocked_until


def load_cache(path: pathlib.Path) -> Tuple[Dict[str, dict], List[str]]:
    data, warnings = load_json_file(path, "registry cache")
    if not data:
        return {}, warnings
    probes = data.get("probes")
    if data.get("schema") != CACHE_SCHEMA or not isinstance(probes, dict):
        return {}, warnings + [f"registry cache malformed at {path}: unexpected shape; treated as empty"]
    valid: Dict[str, dict] = {}
    for name, record in probes.items():
        if not isinstance(record, dict) or parse_ts(record.get("observed_at")) is None \
                or record.get("outcome") not in ("success", "failure"):
            warnings.append(f"registry cache: probe record for '{name}' malformed; ignored")
            continue
        valid[name] = record
    return valid, warnings


def cache_observation(record: dict) -> Observation:
    return Observation(
        observed_at=parse_ts(record["observed_at"]),
        outcome=record["outcome"],
        source="probe",
        category=None,
        reason=str(record.get("reason") or ""),
        evidence=str(record.get("evidence") or ""),
    )


def save_cache(path: pathlib.Path, probes: Dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": CACHE_SCHEMA, "probes": probes}
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
