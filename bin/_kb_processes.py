#!/usr/bin/env python3
"""_kb_processes — reader/validator for personal/processes.yaml.

Every background process is declared with exactly five fields:

    - id: daily
      enabled: true
      when: "07:30"
      run: kb-brief
      outputs: [telegram, file]

`when` semantics (release contract):
  - "HH:MM"            eligible once per day at/after that wall-clock time
  - after:<process_id> eligible on the next tick after <process_id>
                       succeeded for the same day
  - on-demand          never scheduled by the background tick

`outputs` semantics: telegram/people/calendar are user-facing channels;
`file` is internal agent memory and never counts as user delivery;
`notebooklm_audio` is allowed only for on-demand (manual) processes —
background NotebookLM is banned in this release.

The file is a strict, hand-parseable YAML subset: blank lines, full-line
`#` comments, blocks starting with `- id: <id>`, fields indented exactly
two spaces, inline `[a, b]` lists. Parsed with stdlib only — this module
sits on the launchd-critical path (kb-tick) and must not depend on
PyYAML being importable by whatever python3 launchd resolves.

Fail-closed: any unrecognized structure, field, value, or invariant
violation raises ProcessConfigError; kb-tick then runs no processes for
that tick and logs why.

Contract: processes release 2026-06-09 (five-field processes.yaml).

CLI: python3 _kb_processes.py <path>   → exit 0 valid / 1 invalid
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

REQUIRED_FIELDS = ("id", "enabled", "when", "run", "outputs")
ALLOWED_OUTPUTS = ("telegram", "people", "calendar", "file", "notebooklm_audio")

_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_HHMM_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_BLOCK_START_RE = re.compile(r"^- id:\s*(.+?)\s*$")
_FIELD_RE = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$")

DEFAULT_PROCESSES_YAML = """\
# Vepol background processes — the single switchboard read by kb-tick.
# Exactly five fields per process: id, enabled, when, run, outputs.
# when: "HH:MM" | after:<process_id> | on-demand (never scheduled).
# An invalid file fails closed: kb-tick runs nothing and logs why.

- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram, file]

- id: retro
  enabled: true
  when: "20:45"
  run: kb-retro
  outputs: [telegram, file]

# arXiv-only learning digest to Telegram; NotebookLM stays manual-only.
- id: learning
  enabled: true
  when: after:daily
  run: kb-learning-arxiv --text-only
  outputs: [telegram, file]

# Enable only after watermark bootstrap: kb-extract-people --init-watermarks
- id: people-extract
  enabled: false
  when: after:retro
  run: kb-extract-people --hub ~/knowledge --no-llm --quiet
  outputs: [people, telegram, file]

# Enable only after the launchd-equivalent smoke passes (see release spec).
- id: people-remind
  enabled: false
  when: "09:00"
  run: kb-people-remind --horizon 0
  outputs: [telegram]

# kb-calendar-sync is attendee→People ingestion, not a calendar writer.
- id: calendar
  enabled: false
  when: on-demand
  run: kb-calendar-sync --dry-run
  outputs: [file]

# Self-improvement is proposal + eval + review only; never auto-apply.
- id: process-improve
  enabled: false
  when: on-demand
  run: kb-evolution check-policy
  outputs: [file]
"""


class ProcessConfigError(Exception):
    """Raised on any invalid processes.yaml shape. Callers fail closed."""


def _strip_quotes(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        return val[1:-1]
    return val


def parse_processes_text(text: str) -> list[dict]:
    """Parse + validate; returns processes in file order or raises."""
    procs: list[dict] = []
    current: dict | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and line.startswith("-"):
            m = _BLOCK_START_RE.match(line)
            if not m:
                raise ProcessConfigError(
                    f"line {lineno}: process blocks must start with '- id: <id>'"
                )
            current = {"id": _strip_quotes(m.group(1))}
            procs.append(current)
            continue
        m = _FIELD_RE.match(line)
        if m is None or current is None:
            raise ProcessConfigError(
                f"line {lineno}: unrecognized structure: {stripped!r}"
            )
        key, val = m.group(1), m.group(2)
        if key in current:
            raise ProcessConfigError(
                f"line {lineno}: duplicate field {key!r} in process "
                f"{current.get('id')!r}"
            )
        current[key] = val

    if not procs:
        raise ProcessConfigError("no processes declared")

    seen_ids: set[str] = set()
    for p in procs:
        pid_raw = p.get("id", "")
        extra = sorted(set(p) - set(REQUIRED_FIELDS))
        if extra:
            raise ProcessConfigError(
                f"process {pid_raw!r}: unknown field(s) {extra} — "
                f"exactly five fields are allowed: {list(REQUIRED_FIELDS)}"
            )
        missing = [f for f in REQUIRED_FIELDS if f not in p]
        if missing:
            raise ProcessConfigError(
                f"process {pid_raw!r}: missing field(s) {missing}"
            )
        pid = _strip_quotes(pid_raw)
        if not _ID_RE.match(pid):
            raise ProcessConfigError(
                f"process id {pid!r}: must match {_ID_RE.pattern}"
            )
        if pid in seen_ids:
            raise ProcessConfigError(f"duplicate process id {pid!r}")
        seen_ids.add(pid)
        p["id"] = pid

        enabled = _strip_quotes(p["enabled"])
        if enabled not in ("true", "false"):
            raise ProcessConfigError(
                f"process {pid!r}: enabled must be literal true or false, "
                f"got {p['enabled']!r}"
            )
        p["enabled"] = enabled == "true"

        run = _strip_quotes(p["run"])
        if not run:
            raise ProcessConfigError(f"process {pid!r}: run must be non-empty")
        p["run"] = run

        out_raw = p["outputs"].strip()
        m = re.match(r"^\[(.*)\]$", out_raw)
        if not m:
            raise ProcessConfigError(
                f"process {pid!r}: outputs must be an inline list like "
                f"[telegram, file], got {out_raw!r}"
            )
        inner = m.group(1).strip()
        items = [_strip_quotes(x) for x in inner.split(",")] if inner else []
        if not items or any(not it for it in items):
            raise ProcessConfigError(
                f"process {pid!r}: outputs must be a non-empty list"
            )
        for it in items:
            if it not in ALLOWED_OUTPUTS:
                raise ProcessConfigError(
                    f"process {pid!r}: unknown output {it!r} "
                    f"(allowed: {list(ALLOWED_OUTPUTS)})"
                )
        if len(set(items)) != len(items):
            raise ProcessConfigError(f"process {pid!r}: duplicate outputs")
        p["outputs"] = items

        p["when"] = _strip_quotes(p["when"])

    all_ids = {p["id"] for p in procs}
    for p in procs:
        when = p["when"]
        if when == "on-demand" or _HHMM_RE.match(when):
            pass
        elif when.startswith("after:"):
            parent = when[len("after:"):]
            if parent == p["id"]:
                raise ProcessConfigError(
                    f"process {p['id']!r}: after:* cannot reference itself"
                )
            if parent not in all_ids:
                raise ProcessConfigError(
                    f"process {p['id']!r}: after:{parent} references an "
                    f"undeclared process"
                )
        else:
            raise ProcessConfigError(
                f"process {p['id']!r}: when must be \"HH:MM\", "
                f"after:<process_id>, or on-demand — got {when!r}"
            )
        if "notebooklm_audio" in p["outputs"] and when != "on-demand":
            raise ProcessConfigError(
                f"process {p['id']!r}: background notebooklm_audio is not "
                f"allowed in this release (on-demand only)"
            )

    # after:* chains must be acyclic, else dependents would deadlock silently.
    parent_of = {
        p["id"]: p["when"][len("after:"):]
        for p in procs
        if p["when"].startswith("after:")
    }
    for start in parent_of:
        chain = {start}
        cur = parent_of.get(start)
        while cur is not None:
            if cur in chain:
                raise ProcessConfigError(
                    f"after-cycle detected involving process {cur!r}"
                )
            chain.add(cur)
            cur = parent_of.get(cur)

    return procs


def load_processes(path, create_default: bool = False) -> list[dict]:
    """Read + validate processes.yaml. Optionally self-heal a missing file
    with safe release defaults (risky processes disabled)."""
    path = os.fspath(path)
    if not os.path.exists(path):
        if not create_default:
            raise ProcessConfigError(f"config not found: {path}")
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".processes.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(DEFAULT_PROCESSES_YAML)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    with open(path, encoding="utf-8") as f:
        return parse_processes_text(f.read())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: _kb_processes.py <processes.yaml>", file=sys.stderr)
        return 2
    try:
        procs = load_processes(argv[1])
    except (ProcessConfigError, OSError) as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {len(procs)} processes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
