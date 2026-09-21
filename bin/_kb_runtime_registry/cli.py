"""kb-runtime-registry [--report] [--probe [RUNTIME ...]] [--json] [--now ISO]

Exit codes: 0 report rendered (a failed probe is still a rendered report);
2 usage error (unknown runtime, missing roster); 3 probe refused because the
registry itself runs inside an agent session (nothing recorded).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Dict, List, Optional

from . import SCHEMA_VERSION
from .derive import derive_row, newest
from .observations import (
    Observation,
    broker_observation,
    cache_observation,
    fmt_ts,
    load_broker_state,
    load_cache,
    parse_ts,
    save_cache,
)
from .output import load_schema, render_markdown, validate
from .paths import Paths
from .probe import ProbeResult, nesting_markers, run_probe
from .roster import RosterEntry, parse_roster

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NESTED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kb-runtime-registry",
        description="Which agent CLIs can actually do work right now (tri-state, evidence-backed).",
    )
    parser.add_argument("--report", action="store_true", help="render the markdown table (default; never probes)")
    parser.add_argument("--probe", nargs="*", metavar="RUNTIME",
                        help="run known-token probes (all roster runtimes when none named), record, then report")
    parser.add_argument("--json", action="store_true", help="machine-readable output validated against schema.json")
    parser.add_argument("--now", help="ISO-8601 clock override (deterministic fixtures)")
    return parser


def _warn(msg: str) -> None:
    print(f"kb-runtime-registry: {msg}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    paths = Paths()

    now = dt.datetime.now(dt.timezone.utc)
    if args.now:
        parsed = parse_ts(args.now)
        if parsed is None:
            _warn(f"--now is not ISO-8601: {args.now!r}")
            return EXIT_USAGE
        now = parsed

    if not paths.roster.is_file():
        _warn(f"roster not found: {paths.roster} (cli-tools.tsv is the roster of record)")
        return EXIT_USAGE
    roster = parse_roster(paths.roster)
    for entry in roster:
        for warning in entry.warnings:
            _warn(warning)
    roster_by_name: Dict[str, RosterEntry] = {e.name: e for e in roster}

    providers, state_warnings = load_broker_state(paths.broker_state)
    probes, cache_warnings = load_cache(paths.cache)
    for warning in state_warnings + cache_warnings:
        _warn(warning)

    markers = nesting_markers()
    requested: List[str] = []
    results: List[ProbeResult] = []
    refused_reason: Optional[str] = None
    exit_code = EXIT_OK

    if args.probe is not None:
        requested = list(args.probe) if args.probe else [e.name for e in roster]
        unknown = [n for n in requested if n not in roster_by_name]
        if unknown:
            _warn(f"unknown runtime(s): {', '.join(unknown)}; roster: {', '.join(roster_by_name)}")
            return EXIT_USAGE
        if markers:
            refused_reason = (f"nested agent session detected ({', '.join(markers)}); "
                              f"probe refused, nothing recorded")
            _warn(refused_reason)
            exit_code = EXIT_NESTED
        else:
            for name in requested:
                result = run_probe(roster_by_name[name], paths, now)
                results.append(result)
                if result.outcome in ("success", "failure"):
                    probes[name] = result.as_cache_record()
            if results:
                save_cache(paths.cache, probes)

    refused = set(requested) if refused_reason else set()
    rows = []
    for entry in roster:
        observations: List[Observation] = []
        blocked_until = None
        if entry.name in probes:
            observations.append(cache_observation(probes[entry.name]))
        if entry.name in providers:
            obs, blocked_until = broker_observation(providers[entry.name])
            if obs is not None:
                observations.append(obs)
        rows.append(derive_row(
            entry.name,
            installed=entry.installed,
            obs=newest(observations),
            blocked_until=blocked_until,
            now=now,
            row_source="roster",
            fallback_of=entry.fallback_of,
            probe_refused=entry.name in refused,
        ))
    for name in sorted(n for n in providers if n not in roster_by_name):
        observations = []
        if name in probes:
            observations.append(cache_observation(probes[name]))
        obs, blocked_until = broker_observation(providers[name])
        if obs is not None:
            observations.append(obs)
        rows.append(derive_row(
            name,
            installed="unknown",
            obs=newest(observations),
            blocked_until=blocked_until,
            now=now,
            row_source="broker-state-only",
            fallback_of=None,
        ))

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": fmt_ts(now),
        "hub": str(paths.hub),
        "nested": {"detected": bool(markers), "markers": markers},
        "probe": {
            "requested": requested,
            "refused_reason": refused_reason,
            "results": [r.as_json() for r in results],
        },
        "runtimes": rows,
    }

    if args.json:
        errors = validate(doc, load_schema())
        if errors:
            _warn("internal error: --json output violates schema.json: " + "; ".join(errors[:5]))
            return 1
        sys.stdout.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(render_markdown(doc, str(paths.cache), str(paths.broker_state), len(probes)))
    return exit_code
