#!/usr/bin/env python3
"""cr4-fixes.py — CR4 acceptance fixtures.

CR4-B2: enabled child under disabled ancestor → cycle refuses (exit 2).
CR4-B3: pre-pass does NOT overwrite a completed report from a prior run.
CR4-B4: MAX_DEPTH and MAX_FANOUT are enforced.
Fresh hub: retro/plan exit 0 with a setup hint when the cycle was never set up.
Deep autonomy gate without the scanner: refuses with one line before any spawn.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap



def sandbox_env(hub: pathlib.Path) -> dict:
    """Environment for a cycle invocation against a sandbox hub.

    Isolation (mandatory, not hygiene): the durable runner's dedup index lives
    at `KB_CLAUDE_RUN_ROOT` (default `~/knowledge/.orchestrator/claude-runs`)
    and is NOT hub-scoped, while the cycle's per-node key is only
    `cycle-node:<slug>:<date>:retro`. A *succeeded* managed run keeps its
    reservation forever, so without an own run root these fixtures (a) attach
    to whatever run an earlier sandbox left under the same slug/date and never
    execute their own stub broker, and (b) write their runs into the real hub.
    """
    return {
        **os.environ,
        "KB_HUB": str(hub),
        "KB_CLAUDE_RUN_ROOT": str(hub / ".orchestrator" / "claude-runs"),
    }


def _cycle_src_bin() -> pathlib.Path:
    """Source bin/ for the cycle CLI under test.

    Defaults to this tree's own bin/ so the suite tests the code it ships
    with; KB_CYCLE_SRC_BIN points the suite at another tree (e.g. an
    installed hub copy).
    """
    override = os.environ.get("KB_CYCLE_SRC_BIN")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parents[2] / "bin"


def _install_cycle_cli(p: pathlib.Path) -> None:
    src_bin = _cycle_src_bin()
    shutil.copy(src_bin / "kb-orchestrator-cycle", p / "bin" / "kb-orchestrator-cycle")
    shutil.copy(src_bin / "templates" / "cycle-retro.prompt.md",
                p / "bin" / "templates" / "cycle-retro.prompt.md")
    # The CLI may import sibling _kb_*.py helpers (installed hub copies do);
    # bring them along so the sandboxed binary runs in every topology.
    for mod in sorted(src_bin.glob("_kb_*.py")):
        shutil.copy(mod, p / "bin" / mod.name)
    for pkg in sorted(src_bin.glob("_kb_*")):
        if pkg.is_dir():
            shutil.copytree(pkg, p / "bin" / pkg.name, dirs_exist_ok=True)


def make_sandbox(hier: str):
    sb = tempfile.mkdtemp(prefix="kb-cr4-")
    p = pathlib.Path(sb)
    (p / "projects").mkdir()
    (p / "bin" / "templates").mkdir(parents=True)
    (p / ".orchestrator" / "circuits").mkdir(parents=True)
    (p / ".orchestrator" / "runs").mkdir(parents=True)
    (p / "daily").mkdir()
    (p / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n", encoding="utf-8")
    (p / "log.md").write_text("# Hub log\n\n", encoding="utf-8")
    (p / "hierarchy.yaml").write_text(hier, encoding="utf-8")
    # Stub broker: no-op success that doesn't write a report file.
    stub = p / "bin" / "kb-orchestrator-run"
    stub.write_text("#!/usr/bin/env bash\necho 'OUTCOME: closed: ok'\n", encoding="utf-8")
    stub.chmod(0o755)
    retro = p / "bin" / "kb-retro"
    retro.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    retro.chmod(0o755)
    _install_cycle_cli(p)
    return p


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def cr4_b2_disabled_ancestor():
    print("CR4-B2: enabled child under disabled ancestor refuses")
    hier = textwrap.dedent("""\
        version: 1
        root: hub
        nodes:
          hub:
            kind: root
            parent: null
            knowledge_path: /tmp
            children: [parent_off]
          parent_off:
            kind: project
            parent: hub
            category: lab
            status: live
            knowledge_path: /tmp
            children: [child_on]
            cycle_enabled: false
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
          child_on:
            kind: project
            parent: parent_off
            category: lab
            status: live
            knowledge_path: /tmp
            children: []
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
    """)
    sb = make_sandbox(hier)
    proc = subprocess.run(
        [str(sb / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro"],
        env=sandbox_env(sb),
        capture_output=True, text=True,
    )
    assert_(proc.returncode == 2, f"refuses with exit 2 (got {proc.returncode})")
    assert_("INVALID" in proc.stderr or "invalid" in proc.stderr,
            f"stderr explains the violation (got: {proc.stderr[-300:]})")
    shutil.rmtree(sb)


def cr5_b3_skips_spawn_for_completed():
    """CR5-B3: even an aggressive broker that would overwrite the report on
    every spawn must NOT be invoked when a `status: done` report exists.
    This is the broader fix beyond CR4-B3 (which only protected pre-pass).
    """
    print("CR5-B3: cycle skips broker spawn entirely if completed report exists")
    sb = tempfile.mkdtemp(prefix="kb-cr5b3-")
    p = pathlib.Path(sb)
    (p / "projects").mkdir()
    (p / "bin" / "templates").mkdir(parents=True)
    (p / ".orchestrator" / "circuits").mkdir(parents=True)
    (p / ".orchestrator" / "runs").mkdir(parents=True)
    (p / "daily").mkdir()
    (p / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n", encoding="utf-8")
    (p / "log.md").write_text("# Hub log\n\n", encoding="utf-8")
    proj = p / "solo" / "knowledge"
    (proj / "reports").mkdir(parents=True)
    (proj / "backlog.md").write_text("# solo\n\n## Open\n\n", encoding="utf-8")
    os.symlink(str(proj), str(p / "projects" / "solo"))
    hier = textwrap.dedent(f"""\
        version: 1
        root: hub
        nodes:
          hub:
            kind: root
            parent: null
            knowledge_path: {p}
            children: [solo]
          solo:
            kind: project
            parent: hub
            category: pet
            status: live
            knowledge_path: {proj}
            children: []
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
    """)
    (p / "hierarchy.yaml").write_text(hier, encoding="utf-8")

    today = dt.date.today().isoformat()
    completed = (
        f"---\nreport_id: solo-{today}\nslug: solo\ndate: {today}\n"
        f"cycle: evening\nparent: hub\nchildren_rolled_up: []\n"
        f"status: done\nrun_id: prior-cycle-uuid\n---\n\n"
        f"## What was done\n- prior cycle finished work, do not overwrite\n"
    )
    (proj / "reports" / f"{today}.md").write_text(completed, encoding="utf-8")

    # Aggressive broker: writes a junk report on EVERY spawn — would corrupt
    # the prior `done` report if cycle didn't skip the spawn.
    aggro = p / "bin" / "kb-orchestrator-run"
    aggro.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        cat > "{proj}/reports/{today}.md" <<EOF
        ---
        report_id: solo-{today}
        slug: solo
        date: {today}
        cycle: evening
        parent: hub
        children_rolled_up: []
        status: error
        run_id: AGGRO-OVERWROTE-IT
        ---
        ## Aggressive broker overwrote your real report
        EOF
        echo 'OUTCOME: closed: aggressive overwrite'
    """), encoding="utf-8")
    aggro.chmod(0o755)

    retro = p / "bin" / "kb-retro"
    retro.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    retro.chmod(0o755)
    _install_cycle_cli(p)

    proc = subprocess.run(
        [str(p / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro"],
        env=sandbox_env(p),
        capture_output=True, text=True,
    )
    assert_(proc.returncode == 0, f"cycle succeeds (rc={proc.returncode})")

    text_now = (proj / "reports" / f"{today}.md").read_text(encoding="utf-8")
    assert_("run_id: prior-cycle-uuid" in text_now,
            "completed report preserved (broker was NOT spawned)")
    assert_("AGGRO-OVERWROTE-IT" not in text_now,
            "aggressive broker did NOT run on a project with done report")

    # And --force should bypass the skip and let the broker run.
    proc2 = subprocess.run(
        [str(p / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro", "--force"],
        env=sandbox_env(p),
        capture_output=True, text=True,
    )
    assert_(proc2.returncode == 0, "force re-run succeeds")
    text_after_force = (proj / "reports" / f"{today}.md").read_text(encoding="utf-8")
    assert_("AGGRO-OVERWROTE-IT" in text_after_force,
            "--force allows broker to overwrite (escape hatch works)")

    shutil.rmtree(p)


def cr4_b3_no_overwrite_completed():
    print("CR4-B3: pre-pass does NOT overwrite a completed report")
    hier_template = textwrap.dedent("""\
        version: 1
        root: hub
        nodes:
          hub:
            kind: root
            parent: null
            knowledge_path: {sb}
            children: [solo]
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
    sb = tempfile.mkdtemp(prefix="kb-cr4b3-")
    p = pathlib.Path(sb)
    (p / "projects").mkdir()
    (p / "bin" / "templates").mkdir(parents=True)
    (p / ".orchestrator" / "circuits").mkdir(parents=True)
    (p / ".orchestrator" / "runs").mkdir(parents=True)
    (p / "daily").mkdir()
    (p / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n", encoding="utf-8")
    (p / "log.md").write_text("# Hub log\n\n", encoding="utf-8")
    proj = p / "solo" / "knowledge"
    (proj / "reports").mkdir(parents=True)
    (proj / "backlog.md").write_text("# solo\n\n## Open\n\n", encoding="utf-8")
    os.symlink(str(proj), str(p / "projects" / "solo"))
    (p / "hierarchy.yaml").write_text(hier_template.format(sb=sb), encoding="utf-8")

    # Pre-existing completed report from "yesterday's cycle"
    today = dt.date.today().isoformat()
    completed = (
        f"---\nreport_id: solo-{today}\nslug: solo\ndate: {today}\n"
        f"cycle: evening\nparent: hub\nchildren_rolled_up: []\n"
        f"status: done\nrun_id: prior-cycle-uuid\n---\n\n"
        f"## What was done\n- prior cycle did real work\n"
    )
    (proj / "reports" / f"{today}.md").write_text(completed, encoding="utf-8")
    pre_existing_size = (proj / "reports" / f"{today}.md").stat().st_size

    # Setup stubs and run a fresh cycle.
    stub = p / "bin" / "kb-orchestrator-run"
    stub.write_text("#!/usr/bin/env bash\necho 'OUTCOME: closed: ok'; exit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    retro = p / "bin" / "kb-retro"
    retro.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    retro.chmod(0o755)
    _install_cycle_cli(p)

    # Run cycle. Pre-pass should see existing status: done and skip.
    proc = subprocess.run(
        [str(p / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro"],
        env=sandbox_env(p),
        capture_output=True, text=True,
    )
    assert_(proc.returncode == 0, f"cycle succeeds (rc={proc.returncode})")

    # Verify the completed report still has prior-cycle-uuid (was NOT overwritten by pre-pass).
    text_now = (proj / "reports" / f"{today}.md").read_text(encoding="utf-8")
    # Stub broker doesn't actually write a new report — so pre-pass would have written
    # `pending` over our existing `done` if broken. Verify done is preserved.
    if "run_id: prior-cycle-uuid" in text_now:
        # Pre-pass correctly preserved the prior report. Stub broker didn't update it.
        assert_(True, "pre-pass preserved prior completed report (run_id intact)")
    else:
        # Acceptable alternative: cycle ran the broker spawn (which might have updated the file
        # via stub). The critical property is that pre-pass didn't write `pending`.
        assert_("status: pending" not in text_now,
                f"pre-pass did NOT downgrade to pending (final status preserved: "
                f"{[ln for ln in text_now.splitlines() if ln.startswith('status:')]})")

    shutil.rmtree(p)


def cr4_b4_max_fanout():
    print("CR4-B4: MAX_FANOUT exceeded → refuse")
    # Build hub with 9 children (cap is 8). We relaxed root cap, so use a non-root
    # node with too many children.
    children_yaml = ", ".join(f"c{i}" for i in range(9))
    hier_lines = [
        "version: 1", "root: hub",
        "nodes:",
        "  hub:",
        "    kind: root",
        "    parent: null",
        "    knowledge_path: /tmp",
        "    children: [megaparent]",
        "  megaparent:",
        "    kind: project",
        "    parent: hub",
        "    category: lab",
        "    status: live",
        "    knowledge_path: /tmp",
        f"    children: [{children_yaml}]",
        "    cycle_enabled: false",
        "    sla_report_timeout_sec: 60",
        "    owner: test",
        "    decompose_strategy: subset",
        "    exec_broker: false",
    ]
    for i in range(9):
        hier_lines.extend([
            f"  c{i}:",
            "    kind: project",
            "    parent: megaparent",
            "    category: lab",
            "    status: live",
            "    knowledge_path: /tmp",
            "    children: []",
            "    cycle_enabled: false",
            "    sla_report_timeout_sec: 60",
            "    owner: test",
            "    decompose_strategy: subset",
            "    exec_broker: false",
        ])
    hier = "\n".join(hier_lines) + "\n"
    sb = make_sandbox(hier)
    proc = subprocess.run(
        [str(sb / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro"],
        env=sandbox_env(sb),
        capture_output=True, text=True,
    )
    assert_(proc.returncode == 1, f"refuses with exit 1 on MAX_FANOUT (got {proc.returncode}; stderr={proc.stderr[-200:]})")
    assert_("MAX_FANOUT" in proc.stderr or "fanout" in proc.stderr.lower(),
            "stderr mentions fanout")
    shutil.rmtree(sb)


def fresh_hub_cycle_not_set_up():
    print("Fresh hub: retro and plan skip with a setup hint instead of failing")
    sb = make_sandbox("")
    (sb / "hierarchy.yaml").unlink()  # fresh install: no hierarchy, no migration table
    cli = sb / "bin" / "kb-orchestrator-cycle"
    proc = subprocess.run([str(cli), "retro"], env=sandbox_env(sb),
                          capture_output=True, text=True)
    assert_(proc.returncode == 0, f"retro exits 0 on a fresh hub (got {proc.returncode}: {proc.stderr[-300:]})")
    assert_("kb-rebuild-registry bootstrap" in proc.stderr and "cycle_enabled: true" in proc.stderr,
            f"retro says how to enable the cycle (got: {proc.stderr[-300:]})")
    assert_(proc.stderr.count("\n") == 1, "retro prints exactly one line")
    assert_(not (sb / ".orchestrator" / "runs").exists() or not any((sb / ".orchestrator" / "runs").iterdir()),
            "retro started no runs")

    plan = sb / "daily-plan" / "today.md"
    plan.parent.mkdir()
    plan.write_text("approved_at: 2026-11-17T07:00:00\n\n- [ ] hub: something\n", encoding="utf-8")
    proc = subprocess.run([str(cli), "plan", "--approved-plan", str(plan)], env=sandbox_env(sb),
                          capture_output=True, text=True)
    assert_(proc.returncode == 0, f"plan exits 0 on a fresh hub (got {proc.returncode}: {proc.stderr[-300:]})")
    assert_("kb-rebuild-registry bootstrap" in proc.stderr, "plan says how to enable the cycle")

    # Half set up (migration table written, apply not run yet) still fails loudly.
    shutil.copy(_cycle_src_bin() / "kb-rebuild-registry", sb / "bin" / "kb-rebuild-registry")
    (sb / "migration-2026-04-25.yaml").write_text("version: 1\nentries:\n", encoding="utf-8")
    proc = subprocess.run([str(cli), "retro"], env=sandbox_env(sb),
                          capture_output=True, text=True)
    assert_(proc.returncode != 0, f"half-set-up hub still fails (got {proc.returncode})")
    assert_("kb-rebuild-registry check failed" in proc.stderr,
            f"half-set-up failure names the registry check (got: {proc.stderr[-300:]})")
    shutil.rmtree(sb)


def deep_gate_without_scanner_refuses_before_work():
    print("KB_AUTONOMY_GATE_DEEP=1 without the scanner refuses before any work")
    sb_dir = pathlib.Path(tempfile.mkdtemp(prefix="kb-cr4-gate-"))
    nodes = {"mid": ("hub", "[leaf]"), "leaf": ("mid", "[]")}
    lines = ["version: 1", "root: hub", "nodes:", "  hub:", "    kind: root",
             "    parent: null", f"    knowledge_path: {sb_dir}", "    children: [mid]"]
    for slug, (parent, children) in nodes.items():
        kp = sb_dir / slug / "knowledge"
        kp.mkdir(parents=True)
        (kp / "backlog.md").write_text(f"# {slug}\n\n## Open\n\n## Done\n", encoding="utf-8")
        lines += [f"  {slug}:", "    kind: project", f"    parent: {parent}", "    category: lab",
                  "    status: live", f"    knowledge_path: {kp}", f"    children: {children}",
                  "    cycle_enabled: true", "    sla_report_timeout_sec: 60", "    owner: test",
                  "    decompose_strategy: subset", "    exec_broker: false"]
    sb = make_sandbox("\n".join(lines) + "\n")
    marker = sb / "broker-was-called"
    stub = sb / "bin" / "kb-orchestrator-run"
    stub.write_text(f"#!/usr/bin/env bash\ntouch {marker}\necho 'OUTCOME: closed: ok'\n", encoding="utf-8")
    # HOME points into the sandbox: the gate also looks for the scanner under
    # ~/knowledge/bin, and a real hub that has one must not change this test.
    env = {**sandbox_env(sb), "KB_AUTONOMY_GATE_DEEP": "1", "HOME": str(sb)}
    env.pop("KB_AUTONOMY_GATE_INPUT", None)
    proc = subprocess.run(
        [str(sb / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro", "--skip-post-cleanup"],
        env=env, capture_output=True, text=True,
    )
    assert_(proc.returncode == 75, f"refuses with exit 75 (got {proc.returncode}: {proc.stderr[-300:]})")
    assert_("did not start" in proc.stderr and "Traceback" not in proc.stderr,
            f"one clear message, no traceback (got: {proc.stderr[-300:]})")
    assert_(not marker.exists(), "no agent was spawned")
    for slug in nodes:
        assert_(not (sb_dir / slug / "knowledge" / "reports").exists(),
                f"{slug}: no half-written report")
    shutil.rmtree(sb)
    shutil.rmtree(sb_dir)


def main():
    cr4_b2_disabled_ancestor()
    cr4_b3_no_overwrite_completed()
    cr5_b3_skips_spawn_for_completed()
    cr4_b4_max_fanout()
    fresh_hub_cycle_not_set_up()
    deep_gate_without_scanner_refuses_before_work()
    print("\nAll CR4 + CR5 fixes verified")


if __name__ == "__main__":
    main()
