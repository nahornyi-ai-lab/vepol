#!/usr/bin/env python3
"""Acceptance tests for spec: ~/knowledge/concepts/wave-rollup-to-log.md

Runs the real `kb-orchestrator-cycle retro` against a sandbox 3-level
hierarchy (hub → mid → leaf-a, plus `solo` leaf under hub), with a stub
broker. After each cycle, verifies that:

T1 (happy path) — parent's log.md gets exactly one `cycle | mid | ...`
                  line, hub's log.md gets exactly one `cycle | hub |
                  wave_complete ...` line.
T2 (idempotency) — second cycle with same KB_CYCLE_RUN_ID_OVERRIDE
                   does NOT duplicate the lines.
T3 (parent failed) — when parent's broker returns rc=1, parent's log.md
                     stays empty; hub log still records error=1.
T4 (leaf failed)  — leaf timeout, parent done — parent's line shows
                    rolled_up_children=1 done=0 error=1, hub shows
                    nodes=3 with appropriate error count.
T5 (parent log.md missing) — cycle warns but doesn't crash; hub log
                              still updated.
T6 (escalations count) — parent's report contains 3 lines under
                          `## Escalations` → log line shows
                          `escalations=3`. No section → `escalations=0`.

All tests are RED until kb-orchestrator-cycle implements the rollup
behavior described in the spec.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid


HUB_SRC = pathlib.Path.home() / "knowledge"


# ──────────────────────────────────────────────────────────────────────────
# Sandbox setup
# ──────────────────────────────────────────────────────────────────────────

def setup_sandbox(*, escalation_count_for: dict[str, int] | None = None) -> pathlib.Path:
    """Build a fresh sandbox hub. escalation_count_for[slug] controls how
    many bullets appear under `## Escalations` of that project's report."""
    escalation_count_for = escalation_count_for or {}
    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-wave-rollup-"))
    (sb / "projects").mkdir()
    (sb / "bin").mkdir()
    (sb / "bin" / "templates").mkdir()
    (sb / ".orchestrator" / "circuits").mkdir(parents=True)
    (sb / ".orchestrator" / "runs").mkdir(parents=True)
    (sb / "daily").mkdir()
    (sb / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    (sb / "log.md").write_text("# Hub log\n\n", encoding="utf-8")

    for slug, parent in [("leaf-a", "mid"), ("mid", "hub"), ("solo", "hub")]:
        proj = sb / slug
        (proj / "knowledge").mkdir(parents=True)
        (proj / "knowledge" / "backlog.md").write_text(
            f"# {slug}\n\n## Open\n\n## Done\n", encoding="utf-8"
        )
        (proj / "knowledge" / "log.md").write_text(
            f"# {slug} log\n\n", encoding="utf-8"
        )
        (proj / "knowledge" / "state.md").write_text(
            f"# {slug} state\n", encoding="utf-8"
        )
        os.symlink(str(proj / "knowledge"), str(sb / "projects" / slug))

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
    (sb / "hierarchy.yaml").write_text(hierarchy, encoding="utf-8")

    # Stub broker that fails for slugs listed in env STUB_FAIL_SLUGS
    # (newline- or comma-separated). Otherwise writes a `done` report.
    # Each project's report can have a custom number of `## Escalations`
    # bullets via env STUB_ESCALATIONS_<SLUG_UPPER>=N.
    stub_broker = textwrap.dedent("""\
        #!/usr/bin/env python3
        import sys, os, datetime, pathlib, re
        args = sys.argv[1:]
        cwd = None
        for i, a in enumerate(args):
            if a == "--cwd" and i + 1 < len(args):
                cwd = args[i + 1]
                break
        if cwd is None:
            print("stub broker: no --cwd", file=sys.stderr); sys.exit(1)
        prompt = args[0]
        m = re.search(r'project\\s+\\*\\*([^*]+)\\*\\*', prompt)
        slug = m.group(1) if m else 'unknown'
        m2 = re.search(r'`reports/([0-9-]+)\\.md`', prompt)
        date = m2.group(1) if m2 else datetime.date.today().isoformat()
        m3 = re.search(r'run_id: ([0-9a-f-]+)', prompt)
        run_id = m3.group(1) if m3 else 'stub-run'

        # Fail injection
        fail_list = (os.environ.get("STUB_FAIL_SLUGS", "")
                     .replace(",", "\\n").splitlines())
        fail_list = [s.strip() for s in fail_list if s.strip()]
        if slug in fail_list:
            print(f"stub broker: forced failure for {slug}", file=sys.stderr)
            sys.exit(1)

        # Build escalations section
        n_esc = int(os.environ.get(f"STUB_ESCALATIONS_{slug.upper().replace('-', '_')}", "0"))
        esc_section = "## Escalations\\n"
        for i in range(n_esc):
            esc_section += f"- escalation #{i+1} from {slug}\\n"

        rp = pathlib.Path(cwd) / 'reports' / f'{date}.md'
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            f"---\\nreport_id: {slug}-{date}\\nslug: {slug}\\ndate: {date}\\n"
            f"cycle: evening\\nparent: ?\\nchildren_rolled_up: []\\n"
            f"status: done\\nrun_id: {run_id}\\n---\\n\\n"
            f"## Что сделано сегодня\\n- stub task by stub broker\\n\\n"
            f"## Candidates\\n\\n"
            + esc_section,
            encoding='utf-8',
        )
        print(f"OUTCOME: closed: stub-broker wrote report for {slug}")
    """)
    stub_path = sb / "bin" / "kb-orchestrator-run"
    stub_path.write_text(stub_broker, encoding="utf-8")
    stub_path.chmod(0o755)

    retro_stub = sb / "bin" / "kb-retro"
    retro_stub.write_text("#!/usr/bin/env bash\necho 'stub kb-retro' >&2\n", encoding="utf-8")
    retro_stub.chmod(0o755)

    shutil.copy(HUB_SRC / "bin" / "kb-orchestrator-cycle",
                sb / "bin" / "kb-orchestrator-cycle")
    shutil.copy(HUB_SRC / "bin" / "templates" / "cycle-retro.prompt.md",
                sb / "bin" / "templates" / "cycle-retro.prompt.md")
    return sb


def run_cycle(sb: pathlib.Path, *, run_id_override: str | None = None,
              fail_slugs: str = "", escalations: dict[str, int] | None = None,
              extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "KB_HUB": str(sb), "STUB_FAIL_SLUGS": fail_slugs,
           "KB_TEST_MODE": "1"}
    if run_id_override:
        env["KB_CYCLE_RUN_ID_OVERRIDE"] = run_id_override
    for slug, n in (escalations or {}).items():
        env[f"STUB_ESCALATIONS_{slug.upper().replace('-', '_')}"] = str(n)
    if extra_env:
        env.update(extra_env)
    cli = sb / "bin" / "kb-orchestrator-cycle"
    return subprocess.run(
        [str(cli), "retro", "--skip-registry-check", "--skip-hub-retro",
         "--skip-plan-gen", "--skip-post-cleanup"],
        env=env, capture_output=True, text=True, timeout=120,
    )


def today() -> str:
    import datetime as _dt
    return _dt.date.today().isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Assertion helpers
# ──────────────────────────────────────────────────────────────────────────

def count_cycle_lines(log_path: pathlib.Path, slug: str, run_id: str | None = None) -> int:
    if not log_path.is_file():
        return 0
    txt = log_path.read_text(encoding="utf-8")
    pattern = rf"^## \[\d{{4}}-\d{{2}}-\d{{2}}\] cycle \| {re.escape(slug)} \|"
    if run_id:
        pattern += rf".*run_id={re.escape(run_id)}"
    return len([l for l in txt.splitlines() if re.match(pattern, l)])


def find_cycle_line(log_path: pathlib.Path, slug: str) -> str | None:
    if not log_path.is_file():
        return None
    txt = log_path.read_text(encoding="utf-8")
    for l in txt.splitlines():
        if re.match(rf"^## \[\d{{4}}-\d{{2}}-\d{{2}}\] cycle \| {re.escape(slug)} \|", l):
            return l
    return None


def parse_kv(line: str) -> dict[str, str]:
    """Extract key=value pairs from the line summary section."""
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")


def bad(msg: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  ✗ {msg}", file=sys.stderr)
    if detail:
        print(f"    {detail}", file=sys.stderr)


def t1_happy_path():
    print("T1: happy path — parent + hub log lines appear once each")
    sb = setup_sandbox()
    try:
        proc = run_cycle(sb)
        if proc.returncode != 0:
            bad("T1 cycle exits 0", f"rc={proc.returncode} stderr={proc.stderr[-300:]}")
            return

        mid_log = sb / "mid" / "knowledge" / "log.md"
        hub_log = sb / "log.md"
        leaf_log = sb / "leaf-a" / "knowledge" / "log.md"
        solo_log = sb / "solo" / "knowledge" / "log.md"

        if count_cycle_lines(mid_log, "mid") != 1:
            bad("mid log has exactly 1 cycle line", mid_log.read_text())
        else:
            ok("mid log has exactly 1 cycle line")

        if count_cycle_lines(hub_log, "hub") != 1:
            bad("hub log has exactly 1 cycle line", hub_log.read_text())
        else:
            ok("hub log has exactly 1 cycle line")

        if count_cycle_lines(leaf_log, "leaf-a") != 0:
            bad("leaf log has 0 cycle lines (leaves don't write)", leaf_log.read_text())
        else:
            ok("leaf log has 0 cycle lines")

        if count_cycle_lines(solo_log, "solo") != 0:
            bad("solo log has 0 cycle lines (no children = treat as leaf)", solo_log.read_text())
        else:
            ok("solo log has 0 cycle lines")

        mid_line = find_cycle_line(mid_log, "mid") or ""
        kv = parse_kv(mid_line)
        if kv.get("rolled_up_children") != "1":
            bad("mid: rolled_up_children=1", f"got {kv.get('rolled_up_children')!r}, line={mid_line!r}")
        else:
            ok("mid: rolled_up_children=1")
        if kv.get("done") != "1":
            bad("mid: done=1", f"got {kv.get('done')!r}, line={mid_line!r}")
        else:
            ok("mid: done=1")
        if "run_id" not in kv:
            bad("mid: run_id present", f"line={mid_line!r}")
        else:
            ok("mid: run_id present")

        hub_line = find_cycle_line(hub_log, "hub") or ""
        if "wave_complete" not in hub_line:
            bad("hub: wave_complete keyword", f"line={hub_line!r}")
        else:
            ok("hub: wave_complete keyword")
        hub_kv = parse_kv(hub_line)
        if hub_kv.get("nodes") != "3":
            bad("hub: nodes=3", f"got {hub_kv.get('nodes')!r}, line={hub_line!r}")
        else:
            ok("hub: nodes=3")
        if hub_kv.get("done") != "3":
            bad("hub: done=3", f"got {hub_kv.get('done')!r}, line={hub_line!r}")
        else:
            ok("hub: done=3")
    finally:
        shutil.rmtree(sb)


def t2_idempotency():
    print("T2: idempotency — same cycle_run_id, second run does not duplicate")
    sb = setup_sandbox()
    try:
        rid = str(uuid.uuid4())
        p1 = run_cycle(sb, run_id_override=rid)
        if p1.returncode != 0:
            bad("T2 first cycle exits 0", p1.stderr[-300:])
            return
        p2 = run_cycle(sb, run_id_override=rid)
        if p2.returncode != 0:
            bad("T2 second cycle exits 0", p2.stderr[-300:])
            return

        mid_log = sb / "mid" / "knowledge" / "log.md"
        hub_log = sb / "log.md"
        if count_cycle_lines(mid_log, "mid", rid) != 1:
            bad("mid log: exactly 1 line for run_id after 2 runs",
                f"got {count_cycle_lines(mid_log, 'mid', rid)}")
        else:
            ok("mid log idempotent under same run_id")
        if count_cycle_lines(hub_log, "hub", rid) != 1:
            bad("hub log: exactly 1 line for run_id after 2 runs",
                f"got {count_cycle_lines(hub_log, 'hub', rid)}")
        else:
            ok("hub log idempotent under same run_id")
    finally:
        shutil.rmtree(sb)


def t3_parent_failed():
    print("T3: parent failed — no parent log line, hub records error")
    sb = setup_sandbox()
    try:
        proc = run_cycle(sb, fail_slugs="mid")
        # cycle may rc != 0 if circuit triggers, but should still write hub
        # log entry. We accept any rc but require hub log written.

        mid_log = sb / "mid" / "knowledge" / "log.md"
        hub_log = sb / "log.md"

        if count_cycle_lines(mid_log, "mid") != 0:
            bad("T3 mid log has no cycle line",
                mid_log.read_text() if mid_log.exists() else "<missing>")
        else:
            ok("T3 mid log has no cycle line")

        hub_line = find_cycle_line(hub_log, "hub") or ""
        if not hub_line:
            bad("T3 hub log line still written", hub_log.read_text())
            return
        else:
            ok("T3 hub log line still written")
        kv = parse_kv(hub_line)
        if int(kv.get("error", "0")) < 1:
            bad("T3 hub error count >=1", f"line={hub_line!r}")
        else:
            ok("T3 hub error count reflects mid failure")
    finally:
        shutil.rmtree(sb)


def t4_leaf_failed():
    print("T4: leaf failed — parent records done with error child")
    sb = setup_sandbox()
    try:
        proc = run_cycle(sb, fail_slugs="leaf-a")

        mid_log = sb / "mid" / "knowledge" / "log.md"
        mid_line = find_cycle_line(mid_log, "mid") or ""
        if not mid_line:
            bad("T4 mid log line written", mid_log.read_text() if mid_log.exists() else "<missing>")
            return
        ok("T4 mid log line written")
        kv = parse_kv(mid_line)
        if kv.get("rolled_up_children") != "1":
            bad("T4 mid rolled_up_children=1", f"line={mid_line!r}")
        else:
            ok("T4 mid rolled_up_children=1")
        if int(kv.get("error", "0")) + int(kv.get("timeout", "0")) < 1:
            bad("T4 mid records leaf error/timeout >=1", f"line={mid_line!r}")
        else:
            ok("T4 mid records leaf failure")
    finally:
        shutil.rmtree(sb)


def t5_parent_log_missing():
    print("T5: parent log.md missing — cycle warns but continues; hub log still updated")
    sb = setup_sandbox()
    try:
        # Remove mid's log.md
        (sb / "mid" / "knowledge" / "log.md").unlink()
        proc = run_cycle(sb)

        hub_log = sb / "log.md"
        if count_cycle_lines(hub_log, "hub") != 1:
            bad("T5 hub log written despite missing parent log",
                hub_log.read_text() if hub_log.exists() else "<missing>")
        else:
            ok("T5 hub log written despite missing parent log")
        # Cycle should not have raised hard error
        if proc.returncode not in (0, 3):
            bad("T5 cycle exits 0 or 3 (circuit), not crash",
                f"rc={proc.returncode} stderr={proc.stderr[-300:]}")
        else:
            ok("T5 cycle did not crash on missing parent log")
    finally:
        shutil.rmtree(sb)


def t6_escalations_count():
    print("T6: escalations count — parser counts bullets in ## Escalations section")
    sb = setup_sandbox()
    try:
        proc = run_cycle(sb, escalations={"mid": 3})

        mid_log = sb / "mid" / "knowledge" / "log.md"
        mid_line = find_cycle_line(mid_log, "mid") or ""
        if not mid_line:
            bad("T6 mid log line written", mid_log.read_text())
            return
        ok("T6 mid log line written")
        kv = parse_kv(mid_line)
        if kv.get("escalations") != "3":
            bad("T6 mid escalations=3", f"got {kv.get('escalations')!r}, line={mid_line!r}")
        else:
            ok("T6 mid escalations=3")
    finally:
        shutil.rmtree(sb)


def main() -> int:
    print("=== Wave-rollup-to-log acceptance tests ===\n")
    for fn in (t1_happy_path, t2_idempotency, t3_parent_failed,
               t4_leaf_failed, t5_parent_log_missing, t6_escalations_count):
        try:
            fn()
        except Exception as exc:
            global FAIL
            FAIL += 1
            print(f"  ✗ {fn.__name__} raised {type(exc).__name__}: {exc}", file=sys.stderr)
        print()
    print(f"=== {PASS} pass, {FAIL} fail ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
