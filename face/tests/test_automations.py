"""Automations shows the real failure cause and kb-tick's give-up / retry records.

Spec: decisions/scheduler-honest-failure-2026-10-02.md (§A, §D).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from vepol_face import automations  # noqa: E402


def _hub(tmp_path, monkeypatch, processes: str, plan: dict) -> pathlib.Path:
    # The processes validator in this repository, else the installed hub's.
    real = pathlib.Path(__file__).resolve().parents[2] / "bin" / "_kb_processes.py"
    if not real.is_file():
        real = pathlib.Path.home() / "knowledge" / "bin" / "_kb_processes.py"
    if not real.is_file():
        pytest.skip("processes validator not present")
    hub = tmp_path / "knowledge"
    (hub / "bin").mkdir(parents=True)
    shutil.copy(real, hub / "bin" / "_kb_processes.py")
    (hub / "personal").mkdir()
    (hub / "personal" / "processes.yaml").write_text(processes)
    (hub / "logs").mkdir()
    (hub / "logs" / "today-plan.json").write_text(json.dumps(plan))
    monkeypatch.setattr(automations, "launchctl_list", lambda label: (0, '"LastExitStatus" = 0;'))
    monkeypatch.setattr(automations, "LAUNCH_AGENTS", tmp_path / "agents")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    return hub


def _failed_run(hub, n, pid, day, stderr):
    folder = hub / ".orchestrator" / "claude-runs" / f"kbcr-{n:032x}"
    folder.mkdir(parents=True)
    (folder / "stderr").write_text(stderr)
    (folder / "stdout").write_text("")
    (folder / "state.json").write_text(json.dumps({
        "status": "failed", "returncode": 75,
        "started_at": f"{day}T06:15:00+00:00", "completed_at": f"{day}T06:20:00+00:00",
        "updated_at": f"{day}T06:20:00+00:00",
        "metadata": {"caller": "kb-tick", "process_id": pid, "occurrence_date": day},
    }))


def test_digest_outcome_reason_is_the_quota_line_not_the_engine_note(tmp_path, monkeypatch):
    """The 2026-10-01 morning digest: the engine note is printed first, the 429 last;
    the row must name the quota (it named the note for three days)."""
    hub = _hub(tmp_path, monkeypatch,
               "- id: morning-digest\n  enabled: true\n  when: \"06:15\"\n  run: kb-morning-digest\n"
               "  outputs: [telegram]\n",
               {"date": "2026-10-01", "morning_digest_fired": True})
    (hub / ".orchestrator").mkdir()
    (hub / ".orchestrator" / "morning-digest-2026-10-01.json").write_text(json.dumps({
        "status": "failed", "failed_stage": "tts",
        "error": "gemini engine ignores --voice-instruct; model and voice come from Hermes config\n"
                 "TTS generation failed (gemini): Gemini TTS API error (HTTP 429): You exceeded your "
                 "current quota, please check your plan and billing details.\n",
    }))
    now = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    row = automations.build_automations(hub, now=now)["processes"][0]
    assert row["state_text"] == "Failed in result"
    assert "HTTP 429" in row["reason"] and "voice-instruct" not in row["reason"], row["reason"]


def test_missed_day_and_scheduled_retry_from_kb_tick_plan(tmp_path, monkeypatch):
    """kb-tick gave up on one process (attempt cap) and scheduled a retry for another:
    both rows say so instead of a generic 'Failed · retries every 15 min'."""
    day = "2026-10-02"
    hub = _hub(tmp_path, monkeypatch,
               "- id: people-remind\n  enabled: true\n  when: \"08:00\"\n  run: kb-people-remind\n"
               "  outputs: [telegram]\n"
               "- id: calendar-sync\n  enabled: true\n  when: \"07:00\"\n  run: kb-calendar-sync\n"
               "  outputs: [file]\n",
               {"date": day,
                "people_remind_missed": {"reason_code": "quota", "attempts": 4, "at": "2026-10-02T07:10:00Z",
                                         "reason": "You've hit your usage limit. Try again at Oct 3rd, 2026 9:00 AM."},
                "calendar_sync_attempts": 1, "calendar_sync_next_attempt_at": "2026-10-02T10:15:00Z"})
    _failed_run(hub, 1, "people-remind", day, "rc=75\ncodex: rate_limit\n")
    _failed_run(hub, 2, "calendar-sync", day, "rc=75\nclaude: network\n")
    now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))  # 10:00Z
    rows = {r["id"]: r for r in automations.build_automations(hub, now=now)["processes"]}

    missed = rows["people-remind"]
    assert (missed["state"], missed["state_text"]) == ("missed", "Did not run today")
    assert missed["reason"].startswith("[quota] You've hit your usage limit"), missed["reason"]
    assert missed["next_run_text"] == "tomorrow ≈08:00"
    assert rows["calendar-sync"]["state_text"] == "Retry scheduled at 12:15 (attempt 2 of 4)"
