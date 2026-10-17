"""Today card: the day plan, read through the hub's kb-dayplan.

The app never writes a plan file. It runs `kb-dayplan show --json` (the subprocess pattern of
tasks.py) and passes the answer on; a missing script or an unreadable answer is an error the
page shows as text, never an empty plan.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import subprocess

SHOW_TIMEOUT = 10
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def check_date(value: object) -> str:
    """A calendar date as YYYY-MM-DD, or ValueError."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError("date must look like 2026-10-15")
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError("date must look like 2026-10-15") from None
    return value


def today() -> str:
    """Today in the server's local zone."""
    return dt.date.today().isoformat()


def short_date(value: str) -> str:
    """'2026-10-15' -> 'Oct 15' (fixed English names, whatever the system locale)."""
    day = dt.date.fromisoformat(check_date(value))
    return f"{_MONTHS[day.month - 1]} {day.day}"


def read_plan(hub: pathlib.Path, date: str | None = None) -> dict:
    """The stored plan of `date` (default: today), as kb-dayplan prints it.

    Bad date -> ValueError. Anything wrong with the tool or its answer -> {"error": reason}.
    """
    date = check_date(date) if date else today()
    script = pathlib.Path(hub) / "bin" / "kb-dayplan"
    if not script.is_file():
        return {"error": f"kb-dayplan not found: {script}"}
    try:
        proc = subprocess.run(
            [str(script), "show", "--date", date, "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=SHOW_TIMEOUT, env={**os.environ, "KB_HUB": str(hub)},
        )
    except subprocess.TimeoutExpired:
        return {"error": f"kb-dayplan did not answer within {SHOW_TIMEOUT} s"}
    except OSError as exc:
        return {"error": str(exc)}
    lines = [line.strip() for line in proc.stderr.splitlines() if line.strip()]
    if proc.returncode != 0:
        return {"error": lines[-1] if lines else f"kb-dayplan exited {proc.returncode}"}
    try:
        plan = json.loads(proc.stdout)
    except ValueError:
        plan = None
    if not isinstance(plan, dict) or not isinstance(plan.get("exists"), bool):
        return {"error": "kb-dayplan output is not a day plan"}
    return plan
