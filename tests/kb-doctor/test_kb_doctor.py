"""Acceptance tests for kb-doctor Phase 1.

Spec: ~/knowledge/concepts/kb-freshness-loop.md

These tests are RED until ~/knowledge/bin/kb-doctor is implemented. Fixtures use
an isolated KB_HUB and never touch the live knowledge base.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess


HUB = pathlib.Path(__file__).resolve().parents[2]
DOCTOR = HUB / "bin" / "kb-doctor"
TODAY = "2026-04-23"


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def registry(rows: list[tuple[str, str, pathlib.Path]]) -> str:
    body = [
        "# Registry",
        "",
        "| slug | статус | путь | описание |",
        "|---|---|---|---|",
    ]
    for slug, status, path in rows:
        body.append(f"| {slug} | {status} | `{path}` | test |")
    return "\n".join(body)


def create_project(
    root: pathlib.Path,
    hub: pathlib.Path,
    slug: str,
    status: str = "live",
    *,
    state: str | None = None,
    log: str | None = None,
    backlog: str | None = None,
    incidents: str | None = None,
    missing: list[str] | None = None,
) -> pathlib.Path:
    project = root / slug
    knowledge = project / "knowledge"
    knowledge.mkdir(parents=True)
    missing = missing or []
    files = {
        "README.md": f"# {slug}\n",
        "index.md": "# index\n",
        "state.md": state or f"# {slug} — текущее состояние\n\n## Одной строкой\n\nActive.\n\n## Последнее обновление\n\n{TODAY}\n",
        "log.md": log or f"# log\n\n## [{TODAY}] init | {slug} | test\n",
        "backlog.md": backlog or "# Backlog\n\n## Open\n\n## In progress\n\n## Done\n",
        "escalations.md": "# Escalations\n\n## Open\n\n## Resolved\n",
        "incidents.md": incidents or "# Incidents\n\n## Ongoing\n\n## Resolved\n",
    }
    for name, content in files.items():
        if name not in missing:
            write(knowledge / name, content)
    link = hub / "projects" / slug
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(knowledge)
    return project


def make_hub(tmp_path: pathlib.Path, rows: list[tuple[str, str, pathlib.Path]]) -> pathlib.Path:
    hub = tmp_path / "hub"
    hub.mkdir(parents=True)
    (hub / "projects").mkdir()
    write(hub / "registry.md", registry(rows))
    write(hub / "pending-curation.md", "# Pending curation\n")
    return hub


def run_doctor(hub: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["KB_HUB"] = str(hub)
    env["KB_DOCTOR_TODAY"] = TODAY
    return subprocess.run(
        [str(DOCTOR), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def findings(hub: pathlib.Path, *args: str) -> list[dict]:
    result = run_doctor(hub, "--format", "json", *args)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["findings"]


def severities(items: list[dict]) -> set[str]:
    return {item["severity"] for item in items}


def test_missing_symlink_is_p0(tmp_path):
    project_path = tmp_path / "projects-root" / "missing"
    hub = make_hub(tmp_path, [("missing", "live", project_path)])

    items = findings(hub)

    assert any(item["id"].startswith("registry-missing-symlink:missing") for item in items)
    assert "P0" in severities(items)


def test_missing_core_file_is_p0(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(root, hub, "app", missing=["incidents.md"])

    items = findings(hub)

    assert any(item["id"].startswith("missing-core:app:incidents.md") for item in items)
    assert "P0" in severities(items)


def test_coordination_core_file_missing_required_headings_is_p1(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        backlog="# Backlog\n\n- [ ] Task without expected sections\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("core-structure:app:backlog.md") for item in items)
    assert "P1" in severities(items)


def test_state_stale_uses_internal_dates(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        state="# app — текущее состояние\n\n## Последнее обновление\n\n2026-04-10\n",
        log="# log\n\n## [2026-04-20] update | app | newer activity\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("state-stale:app") for item in items)
    assert "P1" in severities(items)


def test_state_freshness_uses_iso_datetimes(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        state="# app — текущее состояние\n\nlast_updated: 2026-04-10T09:30:00+02:00\n",
        log="# log\n\n## [2026-04-20 08:00] update | app | activity\n",
    )

    items = findings(hub)

    assert any(
        item["id"].startswith("state-stale:app") and "state_date=2026-04-10" in item["evidence"]
        for item in items
    )


def test_log_body_future_dates_do_not_drive_activity_date(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "seeded", root / "app")])
    create_project(
        root,
        hub,
        "app",
        status="seeded",
        state="# app — текущее состояние\n\n## Последнее обновление\n\n2026-04-10\n",
        log="# log\n\n## [2026-04-20] update | app | real activity\nMention future maintenance window 2027-05-18 in body.\n",
    )

    items = findings(hub)

    assert not any("2027-05-18" in item["evidence"] for item in items)
    assert any(item["id"].startswith("state-stale:app") and "log_date=2026-04-20" in item["evidence"] for item in items)


def test_seeded_skeleton_without_activity_is_info(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("seed", "seeded", root / "seed")])
    create_project(
        root,
        hub,
        "seed",
        status="seeded",
        state="# seed — текущее состояние\n\n## Одной строкой\n\n_(что это и в каком состоянии — буквально одно предложение)_\n\n## Последнее обновление\n\n2026-04-19\n",
        log="# log\n",
    )

    items = findings(hub, "--verbose")

    assert any(item["id"].startswith("seeded-skeleton:seed") and item["severity"] == "info" for item in items)
    assert "P0" not in severities(items)
    assert "P1" not in severities(items)


def test_live_skeleton_state_is_p1(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("liveapp", "live", root / "liveapp")])
    create_project(
        root,
        hub,
        "liveapp",
        state="# liveapp — текущее состояние\n\n## Одной строкой\n\n_(что это и в каком состоянии — буквально одно предложение)_\n\n## Последнее обновление\n\n2026-04-19\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("live-state-skeleton:liveapp") for item in items)
    assert "P1" in severities(items)


def test_open_incident_older_than_threshold_is_p1(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        incidents="# Incidents\n\n## Ongoing\n\n### [2026-04-10] old breakage\n- Симптомы: broken\n\n## Resolved\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("incident-old:app") for item in items)
    assert "P1" in severities(items)


def test_backlog_due_in_past_is_p0(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        backlog="# Backlog\n\n## Open\n\n- [ ] Ship thing — opened 2026-04-10 — due: 2026-04-20 — context: test\n\n## In progress\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("backlog-due-past:app") for item in items)
    assert "P0" in severities(items)


def test_backlog_due_iso_datetime_in_past_is_p0(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        backlog="# Backlog\n\n## Open\n\n- [ ] Ship thing — opened 2026-04-10 — due: 2026-04-20T09:30:00+02:00 — context: test\n\n## In progress\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("backlog-due-past:app") for item in items)
    assert "P0" in severities(items)


def test_in_progress_stale_is_p1(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        backlog="# Backlog\n\n## Open\n\n## In progress\n\n- [>] Finish thing — opened 2026-04-10 — picked 2026-04-20 by agent\n",
    )

    items = findings(hub)

    assert any(item["id"].startswith("backlog-in-progress-stale:app") for item in items)
    assert "P1" in severities(items)


def test_write_managed_block_is_idempotent_and_respects_resolved_ids(tmp_path):
    root = tmp_path / "projects-root"
    hub = make_hub(tmp_path, [("app", "live", root / "app")])
    create_project(
        root,
        hub,
        "app",
        backlog="# Backlog\n\n## Open\n\n- [ ] Ship thing — opened 2026-04-10 — due: 2026-04-20 — context: test\n\n## In progress\n\n## Done\n",
    )

    first = run_doctor(hub, "--write")
    assert first.returncode == 0, first.stderr
    pending = hub / "pending-curation.md"
    text1 = pending.read_text()
    assert "<!-- managed by kb-doctor" in text1
    assert text1.count("doctor-id:") == 1

    second = run_doctor(hub, "--write")
    assert second.returncode == 0, second.stderr
    text2 = pending.read_text()
    assert text2.count("doctor-id:") == 1

    resolved = text2.replace("- [ ]", "- [x]")
    pending.write_text(resolved, encoding="utf-8")
    third = run_doctor(hub, "--write")
    assert third.returncode == 0, third.stderr
    text3 = pending.read_text()
    assert "- [ ]" not in text3


def test_strict_exit_codes(tmp_path):
    root = tmp_path / "projects-root"
    hub_p0 = make_hub(tmp_path / "p0", [("missing", "live", root / "missing")])
    p0 = run_doctor(hub_p0, "--strict")
    assert p0.returncode == 2

    hub_p1 = make_hub(tmp_path / "p1", [("app", "live", root / "app")])
    create_project(
        root,
        hub_p1,
        "app",
        incidents="# Incidents\n\n## Ongoing\n\n### [2026-04-10] old breakage\n\n## Resolved\n",
    )
    p1 = run_doctor(hub_p1, "--strict")
    assert p1.returncode == 1
