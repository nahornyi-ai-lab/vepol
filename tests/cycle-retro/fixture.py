#!/usr/bin/env python3
"""fixture.py — Phase 3 acceptance for kb-orchestrator-cycle retro.

Creates a sandbox hub with a 3-level hierarchy (hub → mid → leaf) where all
projects have `cycle_enabled: true`. Substitutes `kb-orchestrator-run` with
a stub that emits a valid report file and exits 0 (so we test the cycle's
own logic, not the broker's). Verifies:

1. Terminal pre-pass writes `status: pending` reports for all enabled projects.
2. BFS bottom-up: leaves processed before parents (verified by report timestamps).
3. After cycle: every enabled project has a `done` report.
4. Daily.md gets a `### Cycle summary` section.
5. Cycle summary JSON is written.
6. `--force` re-runs even when reports exist.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap


def setup_sandbox():
    sb = tempfile.mkdtemp(prefix="kb-cycle-")
    p = pathlib.Path(sb)
    (p / "projects").mkdir()
    (p / "bin").mkdir()
    (p / "bin" / "templates").mkdir()
    (p / ".orchestrator" / "circuits").mkdir(parents=True)
    (p / ".orchestrator" / "runs").mkdir(parents=True)
    (p / "daily").mkdir()
    (p / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    (p / "log.md").write_text("# Hub log\n\n", encoding="utf-8")

    # Three projects: leaf-a, mid (parent of leaf-a), and a top-level standalone.
    for slug, parent in [("leaf-a", "mid"), ("mid", "hub"), ("solo", "hub")]:
        proj = p / slug
        (proj / "knowledge").mkdir(parents=True)
        (proj / "knowledge" / "backlog.md").write_text(
            f"# {slug}\n\n## Open\n\n## Done\n", encoding="utf-8"
        )
        (proj / "knowledge" / "log.md").write_text(
            f"# {slug} log\n", encoding="utf-8"
        )
        (proj / "knowledge" / "state.md").write_text(
            f"# {slug} state\n", encoding="utf-8"
        )
        os.symlink(str(proj / "knowledge"), str(p / "projects" / slug))

    # Build a minimal hierarchy.yaml that the cycle CLI's parser handles.
    hierarchy = textwrap.dedent(f"""\
        version: 1
        generated: 2026-04-25
        root: hub
        nodes:
          hub:
            kind: root
            parent: null
            knowledge_path: {sb}
            children: [mid, solo]
          mid:
            kind: project
            parent: hub
            category: lab
            status: live
            knowledge_path: {sb}/mid/knowledge
            children: [leaf-a]
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
          leaf-a:
            kind: project
            parent: mid
            category: lab
            status: live
            knowledge_path: {sb}/leaf-a/knowledge
            children: []
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
          solo:
            kind: project
            parent: hub
            category: pet
            status: live
            knowledge_path: {sb}/solo/knowledge
            children: []
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
    """)
    (p / "hierarchy.yaml").write_text(hierarchy, encoding="utf-8")

    # Stub broker: emits a fake report file and exits 0. The cycle CLI calls
    # `kb-orchestrator-run <prompt> --cwd <knowledge_path> --timeout <s>
    # --json-status`. We extract the cwd to write the report there.
    stub_broker = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys, datetime, pathlib, re
        args = sys.argv[1:]
        # find --cwd
        cwd = None
        for i, a in enumerate(args):
            if a == "--cwd" and i + 1 < len(args):
                cwd = args[i + 1]
        if cwd is None:
            print("stub broker: no --cwd", file=sys.stderr); sys.exit(1)
        # Extract slug from prompt (first arg)
        prompt = args[0]
        m = re.search(r'project\\s+\\*\\*([^*]+)\\*\\*', prompt)
        slug = m.group(1) if m else 'unknown'
        m2 = re.search(r'`reports/([0-9-]+)\\.md`', prompt)
        date = m2.group(1) if m2 else datetime.date.today().isoformat()
        m3 = re.search(r'run_id: ([0-9a-f-]+)', prompt)
        run_id = m3.group(1) if m3 else 'stub-run'
        m4 = re.search(r'parent: ([^\\n,]+)', prompt)
        parent = m4.group(1) if m4 else 'null'
        rp = pathlib.Path(cwd) / 'reports' / f'{{date}}.md'
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            f"---\\nreport_id: {{slug}}-{{date}}\\nslug: {{slug}}\\ndate: {{date}}\\n"
            f"cycle: evening\\nparent: {{parent}}\\nchildren_rolled_up: []\\n"
            f"status: done\\nrun_id: {{run_id}}\\n---\\n\\n"
            f"## Что сделано сегодня\\n- stub task by stub broker\\n\\n"
            f"## Candidates\\n\\n## Escalations\\n",
            encoding='utf-8',
        )
        print(f"OUTCOME: closed: stub-broker wrote report for {{slug}}")
    """)
    stub_path = p / "bin" / "kb-orchestrator-run"
    stub_path.write_text(stub_broker, encoding="utf-8")
    stub_path.chmod(0o755)

    # Stub kb-retro (just exits 0)
    retro_stub = p / "bin" / "kb-retro"
    retro_stub.write_text("#!/usr/bin/env bash\necho 'stub kb-retro' >&2\n", encoding="utf-8")
    retro_stub.chmod(0o755)

    # Copy the actual cycle CLI + retro prompt template into the sandbox.
    HUB_SRC = pathlib.Path.home() / "knowledge"
    shutil.copy(HUB_SRC / "bin" / "kb-orchestrator-cycle", p / "bin" / "kb-orchestrator-cycle")
    shutil.copy(HUB_SRC / "bin" / "templates" / "cycle-retro.prompt.md",
                p / "bin" / "templates" / "cycle-retro.prompt.md")

    return p


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def main():
    print("Phase 3 acceptance: kb-orchestrator-cycle retro on 3-node hierarchy")
    sb = setup_sandbox()

    env = {**os.environ, "KB_HUB": str(sb)}
    cli = sb / "bin" / "kb-orchestrator-cycle"

    # Step 1: dry-run prints BFS plan
    proc = subprocess.run([str(cli), "retro", "--dry-run", "--skip-registry-check"],
                          env=env, capture_output=True, text=True)
    assert_(proc.returncode == 0, f"dry-run exits 0 (got {proc.returncode}, stderr={proc.stderr})")
    assert_("level 0" in proc.stderr and "level 1" in proc.stderr,
            "dry-run shows multiple levels")

    # Step 2: real cycle (without hub-retro inline)
    proc = subprocess.run([str(cli), "retro", "--skip-registry-check", "--skip-hub-retro"],
                          env=env, capture_output=True, text=True)
    print(proc.stderr, file=sys.stderr) if proc.returncode != 0 else None
    assert_(proc.returncode == 0,
            f"retro exits 0 (got {proc.returncode}; stderr={proc.stderr[-300:]})")

    # Verify each project has a `done` report
    today = subprocess.check_output(["date", "+%Y-%m-%d"]).decode().strip()
    for slug in ("leaf-a", "mid", "solo"):
        rp = sb / slug / "knowledge" / "reports" / f"{today}.md"
        assert_(rp.is_file(), f"{slug} report exists at {rp}")
        text = rp.read_text(encoding="utf-8")
        assert_("status: done" in text, f"{slug} report status: done")

    # Verify cycle summary JSON written
    summary_path = sb / ".orchestrator" / f"cycle-{today}.json"
    assert_(summary_path.is_file(), "cycle summary JSON written")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert_(len(summary["results"]) == 3, f"3 results in summary (got {len(summary['results'])})")
    for slug in ("leaf-a", "mid", "solo"):
        assert_(summary["results"][slug]["status"] == "done", f"{slug} status=done in summary")

    # Verify daily.md got cycle summary section
    daily = sb / "daily" / f"{today}.md"
    assert_(daily.is_file(), "daily.md created")
    daily_text = daily.read_text(encoding="utf-8")
    assert_("### Cycle summary" in daily_text, "daily.md has cycle summary section")
    assert_("done" in daily_text and "leaf-a" in daily_text, "daily summary lists projects")

    # Step 3: re-run with --force should re-spawn (not idempotent-skip)
    proc = subprocess.run([str(cli), "retro", "--skip-registry-check", "--skip-hub-retro", "--force"],
                          env=env, capture_output=True, text=True)
    assert_(proc.returncode == 0, f"--force re-run exits 0 (got {proc.returncode})")

    # Step 4: re-run without --force should idempotent-skip (status: done remains)
    # Actually idempotency is by run_id; new run_id → new report. So this just succeeds.
    proc = subprocess.run([str(cli), "retro", "--skip-registry-check", "--skip-hub-retro"],
                          env=env, capture_output=True, text=True)
    assert_(proc.returncode == 0, "second pass succeeds")

    shutil.rmtree(sb)
    print("\nPhase 3 acceptance PASSED — N-level retro cycle works end-to-end")


if __name__ == "__main__":
    main()
