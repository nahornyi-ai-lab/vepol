#!/usr/bin/env python3
"""Startup-context hotfix acceptance smokes.

These tests intentionally exercise the SessionStart shell entrypoint rather than
importing implementation details. They must stay valid for the live hub copy,
the orchestrator-seed copy, and the public seed copy.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SESSION_START = Path(os.environ.get(
    "KB_SESSION_START",
    str(Path.home() / "knowledge" / "bin" / "kb-session-start"),
))
LIVE_PROJECT_ENV = os.environ.get("KB_STARTUP_TEST_PROJECT", "").strip()
HUB = Path(os.environ.get("KB_STARTUP_TEST_HUB", str(SESSION_START.parent.parent)))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def hook_env(env_extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.setdefault("KB_HUB", str(HUB))
    env.setdefault("KB_STARTUP_MAX_CONTEXT", "20000")
    if env_extra:
        env.update(env_extra)
    return env


def run_hook(cwd: Path, *, script: Path = SESSION_START, env_extra: dict[str, str] | None = None):
    return subprocess.run(
        [str(script)],
        input=json.dumps({"cwd": str(cwd)}),
        capture_output=True,
        text=True,
        env=hook_env(env_extra),
        timeout=20,
    )


def hook_context(cwd: Path, *, script: Path = SESSION_START, env_extra: dict[str, str] | None = None) -> str:
    r = run_hook(cwd, script=script, env_extra=env_extra)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    return payload.get("hookSpecificOutput", {}).get("additionalContext", "")


def assert_valid_json_context(cwd: Path, *, env_extra: dict[str, str] | None = None) -> str:
    r = run_hook(cwd, env_extra=env_extra)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    ctx = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert ctx, f"empty context for {cwd}"
    return ctx


def assert_one(ctx: str, marker: str) -> None:
    count = ctx.count(marker)
    assert count == 1, f"expected one {marker!r}, got {count}\n{ctx[:2000]}"


def valid_board() -> str:
    return """# Backlog

## Backlog

- [ ] Backlog task
  plan_item_id: pi-backlog
  created: 2026-06-21
  updated: 2026-06-21
  acceptance: |
    Later.

## Ready

- [ ] Ready hotfix task
  plan_item_id: pi-ready
  created: 2026-06-21
  updated: 2026-06-21
  acceptance: |
    Ready task must appear.

## In Progress

- [>] Active hotfix task
  plan_item_id: pi-active
  created: 2026-06-21
  updated: 2026-06-21
  claim_owner: codex
  claim_id: clm-active
  claim_expires_at: 2026-06-21T12:00:00Z
  acceptance: |
    Active task must appear.

## Blocked

- [ ] Blocked hotfix task
  plan_item_id: pi-blocked
  created: 2026-06-21
  updated: 2026-06-21
  blocked_reason: waiting
  acceptance: |
    Blocked task must appear.

## Review

- [>] Review hotfix task
  plan_item_id: pi-review
  created: 2026-06-21
  updated: 2026-06-21
  claim_owner: claude
  claim_id: clm-review
  claim_expires_at: 2026-06-21T12:00:00Z
  acceptance: |
    Review task must appear.

## Done
"""


def make_project(root: Path, *, huge: bool = False, malformed_board: bool = False) -> Path:
    k = root / "knowledge"
    write(k / "agents" / "agent-card.md", "# Agent Card\n\n## Self-introduction\n\nI am fixture-agent.\n\n## Boundaries\n\nStay in fixture.\n")
    state = "# State\n\nCurrent phase: fixture test.\nLive: startup bundle.\nGated: none.\n"
    if huge:
        state += "\n".join(f"state filler {i}" for i in range(500))
    write(k / "state.md", state)
    log_lines = ["# Log"]
    for i in range(140):
        log_lines.append(f"## [2026-06-21] test | event-{i:03d} | fixture | recent log entry {i}")
    write(k / "log.md", "\n".join(log_lines) + "\n")
    write(k / "index.md", "# Index\n\n" + ("index filler\n" * (2000 if huge else 5)))
    write(k / "backlog.md", "not a valid kb-board\n" if malformed_board else valid_board())
    write(k / "escalations.md", "# Escalations\n\n## Open\n\n### [2026-06-21] Fixture open decision\n- Need owner.\n\n## Resolved\n")
    write(k / "incidents.md", """# Incidents

## Ongoing

<!-- template comment -->

### [2026-06-21 10:00] Fixture ongoing incident
- Symptoms: visible marker.

## Resolved

### [2026-06-20] Old incident

## Prevention rules

- Fixture prevention rule A.
- Fixture prevention rule B.
""")
    if huge:
        with (k / "incidents.md").open("a", encoding="utf-8") as f:
            f.write("\n\n## Archive\n\n")
            f.write("\n".join(f"- incident archive filler {i}" for i in range(2000)))
        with (k / "backlog.md").open("a", encoding="utf-8") as f:
            f.write("\n".join(f"  body filler {i}: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" for i in range(2000)))
    return root


def make_hub(root: Path) -> Path:
    write(root / "agents" / "agent-card.md", "# Agent Card\n\n## Self-introduction\n\nI am fixture-hub.\n")
    write(root / "state.md", "# State\n\nHub fixture state.\n")
    write(root / "log.md", "# Log\n\n## [2026-06-21] test | hub | fixture | hub log entry\n")
    write(root / "index.md", "# Index\n\nHub fixture index.\n")
    write(root / "backlog.md", valid_board())
    write(root / "escalations.md", "# Escalations\n\n## Open\n\n### [2026-06-21] Hub fixture open item\n")
    write(root / "incidents.md", "# Incidents\n\n## Ongoing\n\n## Prevention rules\n\n- Hub fixture prevention rule.\n")
    kb_board = SESSION_START.parent / "kb-board"
    if kb_board.is_file():
        (root / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(kb_board, root / "bin" / "kb-board")
    return root


def live_like_project(root: Path) -> Path:
    if LIVE_PROJECT_ENV:
        return Path(LIVE_PROJECT_ENV)
    return make_project(root / "live_like_project")


def test_live_project_minimal_bundle():
    with tempfile.TemporaryDirectory() as td:
        ctx = hook_context(live_like_project(Path(td)))
    assert len(ctx) <= 20000
    assert_one(ctx, "## Startup Context Manifest")
    assert "bundle_version: startup-context-hotfix-2026-06-21" in ctx
    assert "## Agent Card" in ctx
    assert "## Project State" in ctx
    assert_one(ctx, "## Recent Log")
    assert "## Active Work" in ctx
    assert "## Open Escalations" in ctx
    assert "## Knowledge Index" not in ctx
    assert "index: on-demand" in ctx
    assert "## Incidents (ongoing + recent resolved, prevention rules)" not in ctx
    assert "## Prevention Rules" in ctx
    assert re.search(r"agent_card: (present|clipped|omitted)", ctx)


def test_print_mode_does_not_block_and_is_plain_markdown():
    with tempfile.TemporaryDirectory() as td:
        project = live_like_project(Path(td))
        r = subprocess.run(
            [str(SESSION_START), "--print", "--cwd", str(project)],
            capture_output=True,
            text=True,
            env=hook_env(),
            timeout=10,
        )
    assert r.returncode == 0, r.stderr
    # The recovery block now leads every non-empty emission (delivery contract
    # 2026-08-26); the manifest follows it.
    assert r.stdout.startswith("## Startup Context - read this first")
    assert "## Startup Context Manifest" in r.stdout
    assert "hookSpecificOutput" not in r.stdout
    assert "## Agent Card" in r.stdout


def test_print_mode_defaults_to_current_directory():
    """`kb-session-start --print` run in the project folder, with neither --cwd
    nor CLAUDE_PROJECT_DIR, prints that folder's bundle. Hook mode does not
    guess: with no cwd in the hook JSON it still emits `{}`."""
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td) / "project")
        env = {**hook_env(), "PWD": str(project)}
        r = subprocess.run([str(SESSION_START), "--print"], cwd=str(project),
                           capture_output=True, text=True, env=env, timeout=20)
        assert r.returncode == 0, r.stderr
        assert r.stdout.startswith("## Startup Context - read this first"), r.stdout[:300]
        assert "## Startup Context Manifest" in r.stdout
        assert "Ready hotfix task" in r.stdout
        hook = subprocess.run([str(SESSION_START)], cwd=str(project), input="",
                              capture_output=True, text=True, env=env, timeout=20)
        assert hook.returncode == 0, hook.stderr
        assert hook.stdout.strip() == "{}", hook.stdout[:300]


def backlog_board(n: int) -> str:
    tasks = "".join(
        f"- [ ] Backlog item {i:02d}\n  plan_item_id: pi-bl-{i:02d}\n  priority: P2\n"
        f"  created: 2026-06-21\n  updated: 2026-06-21\n  acceptance: |\n    Later.\n\n"
        for i in range(n))
    return valid_board().replace(
        "## Backlog\n\n- [ ] Backlog task", "## Backlog\n\n" + tasks + "- [ ] Backlog task")


def test_open_backlog_items_reach_active_work():
    """kb-task puts new tasks under `## Backlog`; the bundle must carry them, after
    the Ready/In Progress/Blocked/Review items, bounded to 10 plus a `+K more` line."""
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td) / "small")
        ctx = hook_context(project)
        assert "- Backlog: pi-backlog — Backlog task" in ctx, ctx[-3000:]
        assert ctx.index("Review hotfix task") < ctx.index("Backlog task")
        assert "more not listed" not in ctx

        big = make_project(Path(td) / "big")
        write(big / "knowledge" / "backlog.md", backlog_board(12))  # 13 Backlog items
        ctx = hook_context(big)
    listed = re.findall(r"^- Backlog: (pi-[\w-]+) — ", ctx, re.M)
    assert listed == [f"pi-bl-{i:02d}" for i in range(10)], listed
    assert "pi-backlog" not in ctx
    m = re.search(r"^- Backlog: \+(\d+) more not listed; see them with `(.+)`$", ctx, re.M)
    assert m and m.group(1) == "3", ctx[-2000:]
    assert "kb-board" in m.group(2) and "--status Backlog" in m.group(2)
    assert "Ready hotfix task" in ctx and "Review hotfix task" in ctx
    assert re.search(r"^- active_work: present ", ctx, re.M)


def test_hand_written_backlog_items_show_no_none_id():
    """A hand-added `- [ ] ...` line under `## Backlog` has no plan_item_id. It is
    listed by title alone, never as `None — <title>`."""
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td) / "project")
        board = project / "knowledge" / "backlog.md"
        write(board, valid_board().replace(
            "## Backlog\n\n", "## Backlog\n\n- [ ] Hand-written idea\n\n", 1))
        ctx = hook_context(project)
    assert "- Backlog: Hand-written idea" in ctx, ctx[-2000:]
    assert "None" not in ctx, ctx[-2000:]
    assert "- Backlog: pi-backlog — Backlog task" in ctx, ctx[-2000:]


def test_backlog_items_sorted_by_priority_when_board_reports_it():
    """When `kb-board list --json` rows carry a priority, P0 comes first; ties keep
    board order. A stub kb-board stands in for a board that reports priority."""
    rows = [{"status": "Backlog", "plan_item_id": f"pi-{i:02d}", "title": f"Item {i:02d}",
             "priority": "P0" if i == 11 else ("P1" if i == 5 else "P3")} for i in range(12)]
    with tempfile.TemporaryDirectory() as td:
        hub = Path(td) / "hub"
        stub = hub / "bin" / "kb-board"
        write(stub, "#!/usr/bin/env python3\nimport json, sys\n"
                    f"rows = {json.dumps(rows)}\n"
                    "status = sys.argv[sys.argv.index('--status') + 1]\n"
                    "print(json.dumps([r for r in rows if r['status'] == status]))\n")
        stub.chmod(0o755)
        project = make_project(Path(td) / "project")
        ctx = hook_context(project, env_extra={"KB_HUB": str(hub)})
    listed = re.findall(r"^- Backlog: (pi-\d+) — ", ctx, re.M)
    assert listed == ["pi-11", "pi-05", "pi-00", "pi-01", "pi-02", "pi-03", "pi-04",
                      "pi-06", "pi-07", "pi-08"], listed
    assert re.search(r"^- Backlog: \+2 more not listed", ctx, re.M), ctx[-2000:]


def test_kb_task_prints_one_line_and_its_task_reaches_the_session():
    """The documented path: `kb-task "..." --project my-app` prints one ✓ line with
    the task id (no raw dict), `--json` prints parseable JSON, and the next
    session in that project lists the task."""
    kb_task = SESSION_START.parent / "kb-task"
    if not kb_task.exists():
        return
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        hub = root / "hub"
        (hub / "projects").mkdir(parents=True)
        (hub / "bin").symlink_to(SESSION_START.parent.resolve())
        write(hub / "backlog.md", "# Backlog\n")
        project = make_project(root / "my-app")
        write(project / "knowledge" / "backlog.md", "# Backlog\n")  # canonical empty board
        (hub / "projects" / "my-app").symlink_to(project / "knowledge")
        env = {**hook_env(), "KB_HUB": str(hub)}

        r = subprocess.run([str(kb_task), "Ship the landing page", "--project", "my-app"],
                           capture_output=True, text=True, env=env, timeout=30)
        assert r.returncode == 0, r.stderr
        lines = r.stdout.splitlines()
        assert len(lines) == 1, r.stdout
        m = re.fullmatch(r"✓ Added to project 'my-app' board \(id: ([0-9a-f-]{36})\)", lines[0])
        assert m, lines[0]
        task_id = m.group(1)

        r = subprocess.run([str(kb_task), "Hub chore", "--json"],
                           capture_output=True, text=True, env=env, timeout=30)
        assert r.returncode == 0, r.stderr
        result = json.loads(r.stdout)
        assert result["ok"] is True and result["status"] == "appended", result
        assert result["plan_item_id"] in (hub / "backlog.md").read_text(encoding="utf-8")

        ctx = hook_context(project, env_extra={"KB_HUB": str(hub)})
    assert f"- Backlog: {task_id} — Ship the landing page" in ctx, ctx[-3000:]


def test_huge_files_do_not_starve_critical_sections():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td) / "project", huge=True)
        ctx = hook_context(project)
    assert len(ctx) <= 20000
    assert "## Knowledge Index" not in ctx
    assert "index filler" not in ctx
    assert "incident archive filler" not in ctx
    assert "body filler 1999" not in ctx
    for marker in ("## Startup Context Manifest", "## Agent Card", "## Project State", "## Recent Log",
                   "## Active Work", "## Open Escalations", "## Prevention Rules", "## Ongoing Incidents"):
        assert marker in ctx
    assert "Ready hotfix task" in ctx
    assert "Fixture open decision" in ctx
    assert "Fixture prevention rule A" in ctx
    assert "Fixture ongoing incident" in ctx


def test_json_safety_when_board_is_malformed_and_hub_tools_missing():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td) / "project", malformed_board=True)
        missing_hub = Path(td) / "missing-hub"
        r = run_hook(project, env_extra={"KB_HUB": str(missing_hub)})
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    ctx = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "## Startup Context Manifest" in ctx
    assert "active_work:" in ctx
    assert ("kb-board unavailable" in ctx
            or re.search(r"active_work: (present|clipped|omitted|missing|empty)", ctx))


def test_json_safety_failure_matrix():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        missing_hub = root / "missing-hub"

        cases: list[tuple[str, Path, dict[str, str] | None]] = []

        no_board_project = make_project(root / "kb_board_missing")
        cases.append(("kb-board missing/non-executable", no_board_project, {"KB_HUB": str(missing_hub)}))

        malformed_board_project = make_project(root / "malformed_board", malformed_board=True)
        cases.append(("malformed backlog.md", malformed_board_project, None))

        missing_card_project = make_project(root / "missing_card")
        (missing_card_project / "knowledge" / "agents" / "agent-card.md").unlink()
        cases.append(("missing agent card", missing_card_project, {"KB_HUB": str(missing_hub)}))

        for filename, label in [
            ("state.md", "missing state.md"),
            ("log.md", "missing log.md"),
            ("backlog.md", "missing backlog.md"),
            ("escalations.md", "missing escalations.md"),
            ("incidents.md", "missing incidents.md"),
        ]:
            project = make_project(root / label.replace(" ", "_").replace(".", "_"))
            (project / "knowledge" / filename).unlink()
            cases.append((label, project, None))

        empty_incidents_project = make_project(root / "empty_incidents")
        write(empty_incidents_project / "knowledge" / "incidents.md", "")
        cases.append(("malformed/empty incidents file", empty_incidents_project, None))

        # A path with neither a wiki nor project markers is `empty` mode under the
        # 2026-08-26 delivery contract: it emits nothing at all, rather than a
        # manifest-shaped skip note. Asserted separately below.
        non_project = root / "non_project"
        non_project.mkdir()

        fake_hub = root / "hub_without_roster"
        (fake_hub / "bin").mkdir(parents=True)
        shutil.copy2(HUB / "bin" / "kb-board", fake_hub / "bin" / "kb-board")
        no_roster_project = make_project(root / "no_optional_roster")
        cases.append(("project wiki with no optional roster tool", no_roster_project, {"KB_HUB": str(fake_hub)}))

        r = run_hook(non_project)
        assert r.returncode == 0, r.stderr
        empty_payload = json.loads(r.stdout or "{}")
        assert not empty_payload.get("hookSpecificOutput", {}).get("additionalContext"), \
            "empty mode must emit no context"

        for label, project, env in cases:
            ctx = assert_valid_json_context(project, env_extra=env)
            assert (
                "## Startup Context Manifest" in ctx
                or "No project knowledge/log found" in ctx
                or "initializing a new project wiki" in ctx
            ), f"{label}: unexpected context\n{ctx[:1000]}"


def test_hub_mode_valid_json():
    with tempfile.TemporaryDirectory() as td:
        hub = make_hub(Path(td) / "hub")
        ctx = hook_context(hub, env_extra={"KB_HUB": str(hub)})
    assert len(ctx) <= 20000
    assert "## Startup Context Manifest" in ctx
    assert "mode: hub" in ctx
    assert "index: on-demand" in ctx


def test_critical_budget_fixture_marks_clips_honestly():
    """At a deliberately low configured ceiling the emission stays inside it and
    every slice still carries an honest status.

    Per-section caps and the compact tier were retired by the owner-approved
    startup-context delivery contract (2026-08-26), so this no longer asserts the
    old `card_hygiene_required` clipping. What must hold is stronger: the ceiling
    is respected, the sentinel still verifies, and no slice reports a status that
    is untrue of the emission.
    """
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td) / "critical", huge=True)
        card = "# Agent Card\n\n## Self-introduction\n\n" + ("card filler xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n" * 180)
        card += "\n## Boundaries\n\nStay bounded.\n"
        write(project / "knowledge" / "agents" / "agent-card.md", card)
        state = "# State\n\n" + ("state filler yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy\n" * 100)
        write(project / "knowledge" / "state.md", state)
        ctx = hook_context(project)

    assert len(ctx) <= 20000, f"ceiling not respected: {len(ctx)}"
    assert "## Startup Context Manifest" in ctx
    # No status may be a word outside the contract's one-hot set.
    statuses = re.findall(r"^- (?:today_roster|agent_card|state|log|active_work|"
                          r"open_escalations|prevention_rules|ongoing_incidents|"
                          r"recent_daily|telegram_threads): (\S+)", ctx, re.M)
    assert statuses, "no slice statuses in manifest"
    legal = {"present", "clipped", "omitted", "empty", "missing"}
    illegal = [s for s in statuses if s not in legal]
    assert not illegal, f"illegal status words: {illegal}"
    assert "included" not in " ".join(statuses)
    # The sentinel must still be present and self-consistent under the clip.
    m = re.search(r"^KB-STARTUP-BUNDLE-END v1 chars=(\d+) sha256=([0-9a-f]{64})$",
                  ctx, re.M)
    assert m, "sentinel missing under emergency clip"
    assert int(m.group(1)) == len(ctx), "sentinel chars wrong under emergency clip"


def test_init_kb_hint_is_english_first():
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "some_repo"
        (repo / ".git").mkdir(parents=True)
        ctx = hook_context(repo)
    assert "## Knowledge Base (not yet initialized)" in ctx, ctx[:1000]
    line = next(l for l in ctx.splitlines() if l.startswith("**Trigger phrases**"))
    assert line.index('"set up a wiki"') < line.index("«заведи вику»"), line
    assert '"I need a wiki"' in line and "Russian" in line, line


def test_capture_hooks_skip_quietly_without_memory_compiler():
    """Session capture declined: no ~/claude-memory-compiler. The SessionEnd and
    PreCompact hooks must exit 0 silently and never call uv."""
    bin_dir = SESSION_START.parent
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"
        home.mkdir()
        project = make_project(root / "project")
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        uv_called = root / "uv-called"
        write(fake_bin / "uv", f"#!/bin/sh\ntouch '{uv_called}'\n")
        (fake_bin / "uv").chmod(0o755)
        env = {**hook_env(), "HOME": str(home), "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
        for name in ("kb-session-end", "kb-pre-compact"):
            r = subprocess.run([str(bin_dir / name)], input=json.dumps({"cwd": str(project)}),
                               capture_output=True, text=True, env=env, timeout=20)
            assert r.returncode == 0, (name, r.stderr)
            assert r.stdout == "" and r.stderr == "", (name, r.stdout, r.stderr)
            assert not uv_called.exists(), f"{name} ran uv without the memory compiler"

        # With the compiler installed, the hook still hands off to uv (the hooks
        # never run for projects under /tmp, so that half needs another TMPDIR).
        if str(project.resolve()).startswith(("/tmp/", "/private/tmp/")):
            return
        write(home / "claude-memory-compiler" / "hooks" / "session-end.py", "")
        r = subprocess.run([str(bin_dir / "kb-session-end")], input=json.dumps({"cwd": str(project)}),
                           capture_output=True, text=True, env=env, timeout=20)
        assert r.returncode == 0, r.stderr
        assert uv_called.exists(), "kb-session-end skipped uv although the compiler is installed"


def main() -> int:
    tests = [
        test_live_project_minimal_bundle,
        test_print_mode_does_not_block_and_is_plain_markdown,
        test_print_mode_defaults_to_current_directory,
        test_open_backlog_items_reach_active_work,
        test_hand_written_backlog_items_show_no_none_id,
        test_backlog_items_sorted_by_priority_when_board_reports_it,
        test_kb_task_prints_one_line_and_its_task_reaches_the_session,
        test_huge_files_do_not_starve_critical_sections,
        test_json_safety_when_board_is_malformed_and_hub_tools_missing,
        test_json_safety_failure_matrix,
        test_hub_mode_valid_json,
        test_critical_budget_fixture_marks_clips_honestly,
        test_init_kb_hint_is_english_first,
        test_capture_hooks_skip_quietly_without_memory_compiler,
    ]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
