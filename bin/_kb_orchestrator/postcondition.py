"""Postcondition check for kb-orchestrator-cycle.

Spec: the project's audit page for kb-orchestrator-cycle, § "Postcondition definition".
v2.1: decisions/autonomy-mode.md §"Mode: autonomous" requirement 6 — after each
run, re-read the side effects from disk and verify the capability actually
produced what it reported.

Returns rc=0 (all clear) or rc=8 (postcondition failure → autodemotion per
v2.1 §"Demotion (automatic)" item 2). Caller writes incident on rc=8.

Pure stdlib. Read-only; never mutates KB.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Iterable, Optional

VALID_REPORT_STATUSES = {"success", "done", "error", "timeout", "partial", "skipped"}


class PostconditionResult:
    """Aggregate result of a postcondition run.

    Each step appends a (step, ok, detail) tuple to `checks`. `ok` is False
    for any failed step; `failures` is the filtered list. `rc` mirrors the
    cycle exit convention: 0 = pass, 8 = postcondition failure.
    """

    def __init__(self, run_id: str, date: str) -> None:
        self.run_id = run_id
        self.date = date
        self.checks: list[tuple[str, bool, str]] = []

    def add(self, step: str, ok: bool, detail: str = "") -> None:
        self.checks.append((step, ok, detail))

    @property
    def failures(self) -> list[tuple[str, bool, str]]:
        return [c for c in self.checks if not c[1]]

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def rc(self) -> int:
        return 0 if self.ok else 8

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "date": self.date,
            "ok": self.ok,
            "rc": self.rc,
            "checks": [
                {"step": s, "ok": o, "detail": d} for s, o, d in self.checks
            ],
            "failures": [
                {"step": s, "detail": d} for s, _, d in self.failures
            ],
        }

    def render_markdown(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [
            f"postcondition: {status} (rc={self.rc}) date={self.date} run_id={self.run_id}",
        ]
        for step, ok, detail in self.checks:
            mark = "ok" if ok else "FAIL"
            suffix = f" — {detail}" if detail else ""
            lines.append(f"  [{mark}] {step}{suffix}")
        return "\n".join(lines)


def _wave_line_re(date: str, slug: str, run_id: str) -> re.Pattern:
    return re.compile(
        rf"^## \[{re.escape(date)}\] cycle \| {re.escape(slug)} \| .*"
        rf"run_id={re.escape(run_id)}(?:\s|$)",
    )


def _file_contains_wave_line(path: pathlib.Path, date: str, slug: str,
                              run_id: str) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    pat = _wave_line_re(date, slug, run_id)
    return any(pat.match(line) for line in text.splitlines())


def _parse_report_status(report_path: pathlib.Path) -> Optional[str]:
    if not report_path.is_file():
        return None
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("status:"):
            return s.split(":", 1)[1].strip()
    return None


def _extract_daily_refs(log_path: pathlib.Path) -> list[tuple[str, str]]:
    """Pull (line, daily_ref) pairs from log lines that mention `daily=...`."""
    out: list[tuple[str, str]] = []
    if not log_path.is_file():
        return out
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return out
    pat = re.compile(r"daily=([^\s]+\.md)")
    for line in text.splitlines():
        m = pat.search(line)
        if m:
            out.append((line, m.group(1)))
    return out


def check(
    hub_root: pathlib.Path,
    date: str,
    run_id: str,
    project_paths: Iterable[tuple[str, pathlib.Path]],
    *,
    orchestrator_dir: Optional[pathlib.Path] = None,
) -> PostconditionResult:
    """Run all 6 postcondition checks.

    Args:
        hub_root: ~/knowledge/
        date: ISO date string (the cycle's `--date`).
        run_id: cycle_run_id of the run we're verifying.
        project_paths: iterable of (slug, knowledge_path) for every project
            that participated in the cycle.
        orchestrator_dir: hub_root/.orchestrator by default.
    """
    if orchestrator_dir is None:
        orchestrator_dir = hub_root / ".orchestrator"
    res = PostconditionResult(run_id=run_id, date=date)

    hub_log = hub_root / "log.md"
    daily_path = hub_root / "daily" / f"{date}.md"
    cycle_json = orchestrator_dir / f"cycle-{date}.json"

    # Step 1: hub log.md wave-rollup line present for this run_id.
    if _file_contains_wave_line(hub_log, date, "hub", run_id):
        res.add("hub-log-wave-line", True, str(hub_log))
    else:
        res.add(
            "hub-log-wave-line", False,
            f"missing hub-wave line for run_id={run_id} in {hub_log}",
        )

    # Step 2: daily/<date>.md exists and has a section referencing this cycle.
    if not daily_path.is_file():
        res.add("daily-file-present", False, f"missing {daily_path}")
    else:
        text = daily_path.read_text(encoding="utf-8", errors="replace")
        if "### Cycle summary" in text or run_id in text:
            res.add("daily-file-present", True, str(daily_path))
        else:
            res.add(
                "daily-file-present", False,
                f"{daily_path} has no '### Cycle summary' section nor run_id reference",
            )

    # Step 3: no orphan wave lines — every wave-line in hub log.md whose
    # run_id is NOT this run must still be a valid historical line (the line
    # itself plus a parseable summary file or matching daily). We can't
    # diff history without state, so the check is narrower: this run's
    # line must not be duplicated, and there must not be a wave-line that
    # references a daily file that no longer exists.
    duplicate_count = 0
    if hub_log.is_file():
        text = hub_log.read_text(encoding="utf-8", errors="replace")
        pat = _wave_line_re(date, "hub", run_id)
        duplicate_count = sum(1 for ln in text.splitlines() if pat.match(ln))
    if duplicate_count <= 1:
        res.add("no-duplicate-wave-lines", True, f"count={duplicate_count}")
    else:
        res.add(
            "no-duplicate-wave-lines", False,
            f"{duplicate_count} duplicate wave lines for run_id={run_id}",
        )

    # Step 4: cycle-<date>.json parseable + has expected run_id.
    if not cycle_json.is_file():
        res.add("cycle-json-roundtrip", False, f"missing {cycle_json}")
    else:
        try:
            payload = json.loads(cycle_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            res.add(
                "cycle-json-roundtrip", False,
                f"unparseable: {exc!r}",
            )
        else:
            stored_run = payload.get("cycle_run_id") or payload.get("run_id")
            if stored_run == run_id:
                res.add("cycle-json-roundtrip", True, str(cycle_json))
            else:
                res.add(
                    "cycle-json-roundtrip", False,
                    f"run_id mismatch: stored={stored_run!r} expected={run_id!r}",
                )

    # Step 5: per-project reports exist (where claimed) with valid status.
    project_paths_list = list(project_paths)
    missing: list[str] = []
    bad_status: list[str] = []
    for slug, kp in project_paths_list:
        rp = pathlib.Path(kp) / "reports" / f"{date}.md"
        if not rp.is_file():
            missing.append(f"{slug}:{rp}")
            continue
        status = _parse_report_status(rp)
        if status is None or status not in VALID_REPORT_STATUSES:
            bad_status.append(f"{slug}:status={status!r}")
    if missing or bad_status:
        detail_parts = []
        if missing:
            detail_parts.append("missing=" + ",".join(missing))
        if bad_status:
            detail_parts.append("bad_status=" + ",".join(bad_status))
        res.add("project-reports-valid", False, "; ".join(detail_parts))
    else:
        res.add(
            "project-reports-valid", True,
            f"checked {len(project_paths_list)} project(s)",
        )

    # Step 6: no log.md wave-line points at a missing daily/ file.
    daily_refs = _extract_daily_refs(hub_log)
    dangling: list[str] = []
    for line, daily_ref in daily_refs:
        # Only check this run's date-bound references (avoid false-positives
        # on historical entries whose daily/ files may have been pruned by
        # cleanup tooling).
        if date not in line:
            continue
        candidate = hub_root / daily_ref
        if not candidate.is_file():
            dangling.append(daily_ref)
    if dangling:
        res.add(
            "no-dangling-daily-refs", False,
            "missing=" + ",".join(dangling),
        )
    else:
        res.add(
            "no-dangling-daily-refs", True,
            f"checked {sum(1 for l, _ in daily_refs if date in l)} ref(s) for {date}",
        )

    return res


def write_incident(hub_root: pathlib.Path, result: PostconditionResult) -> None:
    """Append a structured incident line + body to ~/knowledge/incidents.md.

    Skips if rc=0. Idempotent enough — appends one section per call; callers
    that detect repeated failures should de-duplicate at policy level.
    """
    if result.ok:
        return
    incidents = hub_root / "incidents.md"
    incidents.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"## [{result.date}] incident | kb-orchestrator-cycle | "
        f"postcondition-failure | run_id={result.run_id}"
    )
    body_lines = [header, "", "```", result.render_markdown(), "```", ""]
    text = "\n".join(body_lines)
    prefix = ""
    if incidents.is_file():
        existing = incidents.read_text(encoding="utf-8", errors="replace")
        if not existing.endswith("\n"):
            prefix = "\n"
    with incidents.open("a", encoding="utf-8") as fh:
        fh.write(prefix + text)
