"""Automations read model: every scheduled process, its state and why.

Reads only files kb-tick, launchd and Hermes already write. Nothing in the hub
is written, locked or created, and no evidence means "Unknown", never "OK".
"""
from __future__ import annotations

import json
import os
import pathlib
import plistlib
import re
import shlex
import subprocess
import types
from datetime import date as Date, datetime, time, timedelta

HISTORY_DAYS = 14
TICK_GRACE = timedelta(minutes=20)  # one 900 s tick + 5 min
# after:P needs two ticks: one records P's success, the next sees it and launches.
AFTER_GRACE = timedelta(minutes=35)
REASON_MAX = 160
TAIL_BYTES = 64 * 1024
TAIL_LINES = 200
LOG_BYTES = 4 * 1024 * 1024

LEDGER_CALLERS = {"kb-tick", "kb-tick-outbox"}
ACTIVE = {"created", "starting", "running", "claim_degraded"}
LEGACY_FIRED_KEYS = {"daily": "brief_fired", "retro": "retro_fired", "learning": "daily_research_fired"}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Outcome files for processes whose exit code 0 is known to hide failure.
MAIL_OUTCOMES = {"mail-morning": "morning", "mail-evening": "evening"}
DIGEST_OUTCOMES = {
    "learning": "learning-arxiv", "money-radar": "money-radar",
    "morning-digest": "morning-digest", "evening-digest": "evening-digest",
}
PROCESS_LOGS = {
    "daily": "brief.log", "retro": "retro.log", "learning": "learning-arxiv.log",
    "money-radar": "money-radar.log", "morning-digest": "morning-digest.log",
    "evening-digest": "morning-digest.log",
}

SCHEDULER_LABELS = ("com.knowledge.tick", "com.knowledge.planner")
BACKUP_LABEL = "com.knowledge.backup"
LAUNCH_AGENTS = pathlib.Path.home() / "Library" / "LaunchAgents"

STATE_TEXT = {
    "disabled": "Disabled", "manual": "Manual only", "not_its_day": "Not its day",
    "failed_in_result": "Failed in result", "unknown": "Unknown", "ok": "OK",
    "failed": "Failed", "blocked": "Blocked", "waiting": "Waiting", "missed": "Did not start",
}
BLOCKING_STATES = {"failed", "blocked", "missed", "disabled", "manual"}

_LOG_TS = re.compile(
    r"^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?)\]\s?(.*)$"
)
_DATE_RE = re.compile(r"^\d{4}-\d\d-\d\d$")

_MODULES: dict[str, tuple[int, types.ModuleType]] = {}
_LEDGER: dict[str, dict[str, tuple[tuple[int, int], object]]] = {}
_LOGS: dict[str, tuple[tuple[int, int], list]] = {}
_UNREADABLE = object()


def launchctl_list(label: str) -> tuple[int, str] | None:
    """Read-only `launchctl list <label>`; None when launchctl itself fails.
    Tests replace this function so they never depend on this Mac's launchd."""
    try:
        res = subprocess.run(
            ["launchctl", "list", label], capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.returncode, (res.stdout or "") + (res.stderr or "")


# ------------------------------------------------------------------ helpers

def _parse_ts(value, tz) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=tz) if t.tzinfo is None else t.astimezone(tz)


def _iso(t: datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= REASON_MAX else text[: REASON_MAX - 1] + "…"


def _tail_text(path: pathlib.Path, limit: int) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - limit))
            data = fh.read()
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def _last_line(path: pathlib.Path) -> str:
    for line in reversed(_tail_text(path, TAIL_BYTES).splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _tail_lines(path: pathlib.Path) -> str:
    """Last TAIL_LINES whole lines: read backwards until enough newlines or LOG_BYTES."""
    try:
        with open(path, "rb") as fh:
            end = fh.seek(0, os.SEEK_END)
            start, data = end, b""
            while start > 0 and data.count(b"\n") <= TAIL_LINES and end - start < LOG_BYTES:
                step = min(TAIL_BYTES, start, LOG_BYTES - (end - start))
                start -= step
                fh.seek(start)
                data = fh.read(step) + data
    except OSError:
        return ""
    lines = data.decode("utf-8", "replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # partial first line
    return "\n".join(lines[-TAIL_LINES:])


def _read_json(path: pathlib.Path):
    """(data, None) | (None, 'missing') | (None, 'unreadable')."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError):
        return None, "unreadable"


def _fired_key(pid: str) -> str:
    return LEGACY_FIRED_KEYS.get(pid, pid.replace("-", "_") + "_fired")


def _argv(run: str) -> list[str]:
    try:
        return shlex.split(run)
    except ValueError:
        return []


def _flag(argv: list[str], name: str) -> str | None:
    for i, tok in enumerate(argv):
        if tok == name and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith(name + "="):
            return tok.split("=", 1)[1]
    return None


def _gate(run: str) -> list[str] | None:
    """Weekdays from a self-gating `--days a,b` / `--weekday x` flag. Numeric
    values (kb-calendar-sync --days 2) are a window, not a gate."""
    argv = _argv(run)
    for name in ("--days", "--weekday"):
        val = _flag(argv, name)
        days = [d.strip().lower() for d in (val or "").split(",") if d.strip()]
        if days and all(d in WEEKDAYS for d in days):
            return days
    return None


def _gate_text(gate: list[str]) -> str:
    return "only " + ", ".join(d.capitalize() for d in gate)


# ------------------------------------------------------------------ sources

def _processes_module(hub: pathlib.Path) -> types.ModuleType:
    """kb-tick's own validator, executed from source so no __pycache__ is written."""
    path = hub / "bin" / "_kb_processes.py"
    stamp = path.stat().st_mtime_ns
    hit = _MODULES.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    mod = types.ModuleType("_kb_processes_face")
    mod.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), mod.__dict__)
    _MODULES[str(path)] = (stamp, mod)
    return mod


def _load_registry(hub: pathlib.Path) -> tuple[list[dict], str | None, str]:
    path = hub / "personal" / "processes.yaml"
    try:
        text = path.read_text(encoding="utf-8")
        return _processes_module(hub).parse_processes_text(text), None, text
    except Exception as exc:  # the parser's ProcessConfigError, or an unreadable file
        return [], f"processes.yaml invalid: {exc}", ""


def _read_run(folder: str, state_path: str):
    try:
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return _UNREADABLE
    meta = state.get("metadata") if isinstance(state, dict) else None
    if not isinstance(meta, dict) or meta.get("caller") not in LEDGER_CALLERS:
        return None
    # worker_token and claim never leave this function.
    return {
        "run_id": os.path.basename(folder),
        "folder": folder,
        "process_id": str(meta.get("process_id") or ""),
        "date": str(meta.get("occurrence_date") or ""),
        "status": state.get("status"),
        "returncode": state.get("returncode"),
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
        "updated_at": state.get("updated_at"),
    }


def _scan_ledger(hub: pathlib.Path, today: Date) -> tuple[list[dict], dict[str, str]]:
    """Scheduled runs of the last 14 days; parsed state is cached by file mtime."""
    root = hub / ".orchestrator" / "claude-runs"
    old = _LEDGER.get(str(root), {})
    new: dict[str, tuple[tuple[int, int], object]] = {}
    runs: list[dict] = []
    unreadable: dict[str, str] = {}
    oldest = (today - timedelta(days=HISTORY_DAYS - 1)).isoformat()
    newest = today.isoformat()
    try:
        entries = list(os.scandir(root))
    except OSError:
        return [], {}
    for entry in entries:
        if not entry.name.startswith("kbcr-"):
            continue
        state_path = os.path.join(entry.path, "state.json")
        try:
            st = os.stat(state_path)
        except FileNotFoundError:
            continue
        except OSError:
            unreadable[entry.name] = state_path
            continue
        stamp = (st.st_mtime_ns, st.st_size)
        hit = old.get(entry.name)
        rec = hit[1] if hit and hit[0] == stamp else _read_run(entry.path, state_path)
        new[entry.name] = (stamp, rec)
        if rec is _UNREADABLE:
            unreadable[entry.name] = state_path
        elif rec and oldest <= rec["date"] <= newest:
            runs.append(rec)
    _LEDGER[str(root)] = new
    return runs, unreadable


def _log_entries(path: pathlib.Path) -> list[tuple[str, list[str]]]:
    """(timestamp, lines) per entry: a timestamped line plus its continuation lines."""
    try:
        st = path.stat()
    except OSError:
        return []
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _LOGS.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    entries: list[tuple[str, list[str]]] = []
    for line in _tail_text(path, LOG_BYTES).splitlines():
        m = _LOG_TS.match(line)
        if m:
            entries.append((m.group(1), [line]))
        elif entries and line.strip():
            entries[-1][1].append(line)
    _LOGS[str(path)] = (stamp, entries)
    return entries


def _launchd(label: str) -> dict:
    res = launchctl_list(label)
    loaded: bool | None = None
    last_exit: int | None = None
    if res is not None:
        rc, out = res
        if rc == 0:
            loaded = True
            m = re.search(r'"LastExitStatus"\s*=\s*(-?\d+);', out)
            last_exit = int(m.group(1)) if m else None
        elif rc == 113 or "Could not find service" in out:
            loaded = False
    return {"label": label, "loaded": loaded, "last_exit": last_exit}


def _scheduler() -> dict:
    jobs = [_launchd(label) for label in SCHEDULER_LABELS]
    bad = [j for j in jobs if j["loaded"] and j["last_exit"] not in (0, None)]
    if any(j["loaded"] is False for j in jobs):
        state, text = "not_loaded", "Scheduler not loaded — processes do not run"
    elif any(j["loaded"] is None for j in jobs):
        state, text = "unknown", "State unknown"
    elif bad:
        state, text = "exit_code", f"exit code {bad[0]['last_exit']}"
    else:
        state, text = "running", "Scheduler running"
    return {"state": state, "text": text, "jobs": jobs}


def _calendar_text(interval) -> str:
    items = interval if isinstance(interval, list) else [interval]
    parts = []
    for item in items:
        if not isinstance(item, dict) or "Hour" not in item:
            return "—"
        hm = f"{int(item['Hour']):02d}:{int(item.get('Minute', 0)):02d}"
        if "Weekday" in item:
            parts.append(f"{WEEKDAYS[(int(item['Weekday']) - 1) % 7].capitalize()} {hm}")
        else:
            parts.append(f"daily {hm}")
    return ", ".join(parts) or "—"


def _backup_row() -> dict | None:
    """None when the backup job is neither loaded nor installed: Vepol does not install it."""
    plist_path = LAUNCH_AGENTS / f"{BACKUP_LABEL}.plist"
    job = _launchd(BACKUP_LABEL)
    if job["loaded"] is not True and not plist_path.exists():
        return None
    try:
        with open(plist_path, "rb") as fh:
            plist = plistlib.load(fh)
    except Exception:  # missing or malformed plist: no schedule to show
        plist = {}
    if job["loaded"] is None:
        state, text, reason = "unknown", "Unknown", "State unknown"
    elif job["loaded"] is False:
        state, text, reason = "not_loaded", "Not loaded", ""
    elif job["last_exit"] not in (0, None):
        state, text, reason = "failed", f"Failed, exit {job['last_exit']}", ""
    else:
        state, text, reason = "ok", "OK", ""
    return {
        "source": "launchd", "name": "Backup", "label": BACKUP_LABEL,
        "schedule_text": _calendar_text(plist.get("StartCalendarInterval") if isinstance(plist, dict) else None),
        "enabled": bool(job["loaded"]), "job_state": None,
        "state": state, "state_text": text, "reason": reason,
        "last_run_at": None, "next_run_at": None, "failure_streak": None,
    }


def _hermes_rows(notes: list[dict]) -> list[dict]:
    home = pathlib.Path(os.environ.get("HERMES_HOME") or pathlib.Path.home() / ".hermes").expanduser()
    path = home / "cron" / "jobs.json"
    data, err = _read_json(path)
    if err == "missing":
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else data
    if err or not isinstance(jobs, list):
        notes.append({"level": "info", "text": f"Could not read {path}"})
        return []
    rows = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = job.get("last_status")
        if status == "error":
            state, text = "failed", "Failed"
        elif status == "ok":
            state, text = "ok", "OK"
        elif status is None:
            state, text = "never_run", "never run yet"
        else:
            state, text = "unknown", f"Unknown: {status}"
        schedule = job.get("schedule")
        error = str(job.get("last_error") or "").strip()
        rows.append({
            "source": "hermes", "name": job.get("name"), "label": None,
            "schedule_text": schedule.get("display") if isinstance(schedule, dict) else schedule,
            "enabled": job.get("enabled"), "job_state": job.get("state"),
            "state": state, "state_text": text,
            "reason": error.splitlines()[0] if error else "",
            "last_run_at": job.get("last_run_at"), "next_run_at": job.get("next_run_at"),
            "failure_streak": job.get("failure_streak"),
        })
    return rows


# ------------------------------------------------------------------ model

class _Model:
    def __init__(self, hub, now: datetime | None) -> None:
        self.hub = pathlib.Path(hub)
        now = now or datetime.now()
        self.now = now if now.tzinfo else now.astimezone()
        self.tz = self.now.tzinfo
        self.today = self.now.date()
        self.notes: list[dict] = []
        self.procs, self.error, self.registry_text = _load_registry(self.hub)
        self.by_id = {p["id"]: p for p in self.procs}
        self.plan = self._plan()
        runs, self.unreadable = _scan_ledger(self.hub, self.today)
        if self.unreadable:
            first = next(iter(self.unreadable.values()))
            self.notes.append({"level": "info", "text": f"{len(self.unreadable)} run record(s) unreadable, e.g. {first}"})
        self.occ: dict[tuple[str, str], list[dict]] = {}
        for run in sorted(runs, key=lambda r: r["started_at"] or r["updated_at"] or ""):
            self.occ.setdefault((run["process_id"], run["date"]), []).append(run)
        self._memo: dict[str, dict] = {}
        self._reasons: dict[str, str] = {}

    def _plan(self) -> dict:
        data, _ = _read_json(self.hub / "logs" / "today-plan.json")
        if isinstance(data, dict) and data.get("date") == self.today.isoformat():
            return data
        self.notes.append({"level": "info", "text": "No plan for today — states come from the run ledger only"})
        return {}

    # -- attempts

    def _window(self, run: dict) -> tuple[datetime | None, datetime]:
        start = _parse_ts(run["started_at"], self.tz)
        end = _parse_ts(run["completed_at"] or run["updated_at"], self.tz) or self.now
        return start, end

    def _log_path(self, pid: str) -> pathlib.Path | None:
        name = PROCESS_LOGS.get(pid)
        return self.hub / "logs" / name if name else None

    def _log_window(self, pid: str, run: dict) -> list[list[str]]:
        path = self._log_path(pid)
        start, end = self._window(run)
        if path is None or start is None:
            return []
        lo, hi = start.replace(microsecond=0), end.replace(microsecond=0)
        out = []
        for ts, lines in _log_entries(path):
            t = _parse_ts(ts, self.tz)
            if t and lo <= t.replace(microsecond=0) <= hi:
                out.append(lines)
        return out

    def _reason(self, run: dict) -> str:
        """One line for a failed attempt: stderr, stdout, then the process log."""
        if run["run_id"] in self._reasons:
            return self._reasons[run["run_id"]]
        folder = pathlib.Path(run["folder"])
        line = _last_line(folder / "stderr") or _last_line(folder / "stdout")
        if not line:
            entries = self._log_window(run["process_id"], run)
            if entries:
                first = entries[0]
                head = _LOG_TS.match(first[0]).group(2)
                line = " ".join([head, *(x.strip() for x in first[1:])])
        reason = _clip(line) if line.strip() else "no reason recorded"
        self._reasons[run["run_id"]] = reason
        return reason

    # -- outcomes

    def _outcome_path(self, proc: dict, day: str) -> pathlib.Path | None:
        pid = proc["id"]
        if pid in MAIL_OUTCOMES:
            return self.hub / "personal" / "mail" / "briefs" / f"{day}-{MAIL_OUTCOMES[pid]}.json"
        if pid in DIGEST_OUTCOMES:
            return self.hub / ".orchestrator" / f"{DIGEST_OUTCOMES[pid]}-{day}.json"
        if pid == "agent-review":
            project = _flag(_argv(proc["run"]), "--project")
            if project:
                y, w, _ = Date.fromisoformat(day).isocalendar()
                return (pathlib.Path(project).expanduser() / "knowledge" / ".orchestrator"
                        / f"agent-review-{y}-W{w:02d}.done")
        return None

    def _success_state(self, proc: dict, day: str, win: dict | None) -> tuple[str, str]:
        gate = _gate(proc["run"])
        if gate and WEEKDAYS[Date.fromisoformat(day).weekday()] not in gate:
            return "not_its_day", ""
        path = self._outcome_path(proc, day)
        if path is None:
            return "ok", ""
        if proc["id"] == "agent-review":
            try:
                done = path.exists()
            except OSError:
                return "unknown", f"unreadable: {path}"
            if done:
                return "ok", ""
            line = _last_line(pathlib.Path(win["folder"]) / "stdout") if win else ""
            return "failed_in_result", _clip(line) if line else "no reason recorded"
        data, err = _read_json(path)
        if err == "missing":
            return "unknown", "exit 0, no result file"
        if err or not isinstance(data, dict):
            return "unknown", f"unreadable: {path}"
        if proc["id"] in MAIL_OUTCOMES:
            available = data.get("available")
            if available is True:
                return "ok", ""
            if available is False:
                errors = data.get("errors") or []
                return "failed_in_result", _clip(str(errors[0])) if errors else "available: false"
            return "unknown", f"unreadable: {path}"
        status = data.get("status")
        if status == "completed":
            return "ok", ""
        if status is None:
            return "unknown", f"unreadable: {path}"
        reason = str(status)
        if data.get("failed_stage"):
            reason += f" ({data['failed_stage']})"
        error = str(data.get("error") or "").strip()
        if error:
            reason += ": " + error.splitlines()[0]
        return "failed_in_result", _clip(reason)

    # -- today

    def _state(self, state: str, reason: str = "", text: str | None = None,
               succeeded: bool = False, success_end: datetime | None = None) -> dict:
        return {"state": state, "state_text": text or STATE_TEXT[state], "reason": reason,
                "succeeded": succeeded, "success_end": success_end}

    def today_state(self, pid: str) -> dict:
        if pid not in self._memo:
            self._memo[pid] = self._evaluate(pid)
        return self._memo[pid]

    def _evaluate(self, pid: str) -> dict:
        proc = self.by_id[pid]
        when = proc["when"]
        if not proc["enabled"]:
            return self._state("disabled")
        if when == "on-demand":
            return self._state("manual")
        cycle = self._cycle(pid)
        if cycle:
            return self._state("unknown", "dependency cycle: " + " → ".join(cycle))
        bound = self.plan.get(pid.replace("-", "_") + "_run_id")
        if bound in self.unreadable:
            return self._state("unknown", f"unreadable: {self.unreadable[bound]}")
        day = self.today.isoformat()
        attempts = self.occ.get((pid, day), [])
        active = [r for r in attempts if r["status"] in ACTIVE]
        if active:
            start = _parse_ts(active[-1]["started_at"], self.tz)
            return self._state("running", text=f"Running since {start:%H:%M}" if start else "Running")
        wins = [r for r in attempts if r["status"] == "succeeded"]
        if wins or self.plan.get(_fired_key(pid)) is True:
            win = wins[-1] if wins else None
            state, reason = self._success_state(proc, day, win)
            end = self._window(win)[1] if win else None
            return self._state(state, reason, succeeded=True, success_end=end)
        if attempts:
            return self._state("failed", self._reason(attempts[-1]))
        if when.startswith("after:"):
            parent = when[len("after:"):]
            p = self.today_state(parent)
            if p["state"] == "unknown":
                return self._state("unknown", f"after {parent}")
            if p["succeeded"]:
                if p["success_end"] is None:
                    return self._state("waiting", f"after {parent}")
                return self._due(p["success_end"], AFTER_GRACE)
            if p["state"] in BLOCKING_STATES:
                return self._state("blocked", f"waiting for {parent}")
            if p["state"] in ("running", "waiting"):
                return self._state("waiting", f"after {parent}")
            return self._state("unknown", f"after {parent}")
        due = self._clock(when)
        if self.now < due:
            return self._state("waiting", f"today ≈{when}")
        return self._due(due)

    def _cycle(self, pid: str) -> list[str] | None:
        """The after: chain that leads from pid back to pid, else None."""
        chain = [pid]
        while True:
            when = self.by_id.get(chain[-1], {}).get("when", "")
            if not when.startswith("after:"):
                return None
            parent = when[len("after:"):]
            if parent == pid:
                return [*chain, pid]
            if parent in chain:  # a cycle upstream; that row reports it
                return None
            chain.append(parent)

    def _clock(self, hm: str) -> datetime:
        h, m = (int(x) for x in hm.split(":"))
        return datetime.combine(self.today, time(h, m), tzinfo=self.tz)

    def _due(self, due: datetime, grace: timedelta = TICK_GRACE) -> dict:
        if self.now - due <= grace:
            return self._state("waiting", "waiting for the next tick")
        return self._state("missed", f"was due at {due:%H:%M}, no launch record")

    # -- rows

    def _next_text(self, proc: dict, t: dict, gate: list[str] | None) -> str:
        when = proc["when"]
        if t["state"] in ("disabled", "manual"):
            return "—"
        if when.startswith("after:"):
            text = f"after {when[len('after:'):]}"
        elif t["succeeded"] or t["state"] == "running":
            text = f"tomorrow ≈{when}"
        elif self.now < self._clock(when):
            text = f"today ≈{when}"
        else:
            text = "at the next tick"
        return f"{text} · {_gate_text(gate)}" if gate else text

    def _history(self, pid: str) -> list[tuple[str, list[dict]]]:
        days = [(day, runs) for (p, day), runs in self.occ.items() if p == pid]
        return sorted(days, reverse=True)

    def occurrence(self, proc: dict, day: str, runs: list[dict]) -> dict:
        starts = [t for t in (_parse_ts(r["started_at"], self.tz) for r in runs) if t]
        ends = [t for t in (_parse_ts(r["completed_at"], self.tz) for r in runs) if t]
        wins = [r for r in runs if r["status"] == "succeeded"]
        if any(r["status"] in ACTIVE for r in runs):
            result, state, reason = "running", "running", ""
        elif wins:
            result = "succeeded"
            state, reason = self._success_state(proc, day, wins[-1])
        else:
            result, state, reason = "failed", "failed", self._reason(runs[-1])
        return {
            "date": day, "attempts": len(runs), "first_start": _iso(min(starts, default=None)),
            "last_end": _iso(max(ends, default=None)), "result": result, "state": state, "reason": reason,
        }

    def row(self, pid: str) -> dict:
        proc = self.by_id[pid]
        when = proc["when"]
        gate = _gate(proc["run"])
        parent = when[len("after:"):] if when.startswith("after:") else None
        if parent:
            schedule = f"after {parent}"
        elif when == "on-demand":
            schedule = "on demand"
        else:
            schedule = when
        if gate:
            schedule += f" · {_gate_text(gate)}"
        t = self.today_state(pid)
        history = self._history(pid)
        runs = [r for _, day_runs in history for r in day_runs]
        last_run = None
        if runs:
            last = max(runs, key=lambda r: r["started_at"] or r["updated_at"] or "")
            if last["status"] in ACTIVE:
                result, reason = "running", ""
            elif last["status"] == "succeeded":
                result, reason = "succeeded", ""
            else:
                result, reason = "failed", self._reason(last)
            last_run = {"date": last["date"], "at": _iso(_parse_ts(last["started_at"], self.tz)),
                        "result": result, "reason": reason}
        last_success = None
        for day, day_runs in history:
            wins = [r for r in day_runs if r["status"] == "succeeded"]
            if wins and self._success_state(proc, day, wins[-1])[0] != "failed_in_result":
                last_success = _iso(self._window(wins[-1])[1])
                break
        return {
            "id": pid, "schedule_text": schedule, "parent": parent, "gate": gate,
            "enabled": proc["enabled"], "state": t["state"], "state_text": t["state_text"],
            "reason": t["reason"], "attempts_today": len(self.occ.get((pid, self.today.isoformat()), [])),
            "last_run": last_run, "last_success_at": last_success,
            "next_run_text": self._next_text(proc, t, gate),
        }

    def registry_ref(self, pid: str) -> str:
        path = self.hub / "personal" / "processes.yaml"
        for n, line in enumerate(self.registry_text.splitlines(), start=1):
            m = re.match(r"^- id:\s*['\"]?([^'\"\s]+)", line)
            if m and m.group(1) == pid:
                return f"{path}:{n}"
        return str(path)


# ------------------------------------------------------------------ public

def build_automations(hub: pathlib.Path, now: datetime | None = None) -> dict:
    """Payload of GET /api/automations."""
    model = _Model(hub, now)
    notes = model.notes
    if model.error:
        notes.insert(0, {"level": "error",
                         "text": f"{model.error} — the scheduler is not running any process right now"})
    processes = [model.row(p["id"]) for p in model.procs] if not model.error else []
    backup = _backup_row()
    other = [*([backup] if backup else []), *_hermes_rows(notes)]
    return {
        "scheduler": _scheduler(), "processes": processes, "other": other,
        "notes": notes, "generated_at": _iso(model.now),
    }


def automation_detail(hub: pathlib.Path, process_id: str, date: str | None = None,
                      now: datetime | None = None) -> dict | None:
    """Payload of GET /api/automations/{id}; None for an unknown id (404).
    A malformed `date` raises ValueError (400)."""
    if date is not None and not _DATE_RE.match(date):
        raise ValueError("date must be YYYY-MM-DD")
    if date is not None:
        Date.fromisoformat(date)
    model = _Model(hub, now)
    if model.error or process_id not in model.by_id:
        return None
    proc = model.by_id[process_id]
    history = model._history(process_id)
    occurrences = [model.occurrence(proc, day, runs) for day, runs in history]
    day = date or (history[0][0] if history else None)
    runs = model.occ.get((process_id, day), []) if day else []
    last = runs[-1] if runs else None
    log_path = model._log_path(process_id)
    outcome_path = model._outcome_path(proc, day) if day else None
    paths = {
        "registry": model.registry_ref(process_id),
        "run_folder": last["folder"] if last else None,
        "state": os.path.join(last["folder"], "state.json") if last else None,
        "stdout": os.path.join(last["folder"], "stdout") if last else None,
        "stderr": os.path.join(last["folder"], "stderr") if last else None,
        "log": str(log_path) if log_path else None,
        "outcome": str(outcome_path) if outcome_path else None,
    }
    attempt = None
    if last:
        folder = pathlib.Path(last["folder"])
        attempt = {
            "run_id": last["run_id"], "date": last["date"], "status": last["status"],
            "returncode": last["returncode"],
            "started_at": _iso(_parse_ts(last["started_at"], model.tz)),
            "completed_at": _iso(_parse_ts(last["completed_at"], model.tz)),
            "stderr": _tail_lines(folder / "stderr"), "stdout": _tail_lines(folder / "stdout"),
            "log_lines": [line for entry in model._log_window(process_id, last) for line in entry][-TAIL_LINES:],
        }
    return {"row": model.row(process_id), "occurrences": occurrences, "date": day,
            "attempt": attempt, "paths": paths}
