#!/usr/bin/env python3
"""phase8.py — kb-doctor Phase 2 checks acceptance.

Verifies all 4 Phase 8 subcommands work on synthetic sandbox setups:
  - decompose-staleness: stale `decompose:` markers > 1 day old → P1/P2.
  - report-quality-check: missing frontmatter / sections / stale reports.
  - cycle-source-id-collision: same csid across multiple plan_item_ids.
  - seed-docs-drift: live bin/* differs from seed bin/*.
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


def setup_sandbox():
    sb = tempfile.mkdtemp(prefix="kb-phase8-")
    p = pathlib.Path(sb)
    (p / "projects").mkdir()
    (p / ".orchestrator" / "locks").mkdir(parents=True)
    (p / ".orchestrator" / "audit").mkdir(parents=True)
    (p / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n", encoding="utf-8")
    (p / "registry.md").write_text("# registry\n\n<!-- DERIVED-BEGIN -->\n<!-- DERIVED-END -->\n<!-- HUB-MANAGED-BEGIN -->\n<!-- HUB-MANAGED-END -->\n", encoding="utf-8")
    (p / "hierarchy.yaml").write_text(
        "version: 1\nroot: hub\nnodes:\n  hub:\n    kind: root\n    parent: null\n    knowledge_path: " + str(p) + "\n    children: [alpha]\n  alpha:\n    kind: project\n    parent: hub\n    category: pet\n    status: live\n    knowledge_path: " + str(p) + "/alpha/knowledge\n    children: []\n    cycle_enabled: false\n    sla_report_timeout_sec: 300\n    owner: test\n    decompose_strategy: subset\n    exec_broker: false\n",
        encoding="utf-8",
    )
    proj = p / "alpha"
    (proj / "knowledge" / "reports").mkdir(parents=True)
    (proj / "knowledge" / "backlog.md").write_text(
        "# alpha\n\n## Open\n\n## Done\n", encoding="utf-8",
    )
    (proj / "knowledge" / "README.md").write_text(
        "---\nslug: alpha\nparent: hub\ncategory: pet\nstatus: live\ndescription: \"\"\n---\n", encoding="utf-8",
    )
    (proj / "knowledge" / ".orchestration.yaml").write_text(
        "version: 1\ncycle_enabled: false\nsla_report_timeout_sec: 300\nowner: test\ndecompose_strategy: subset\nexec_broker: false\n",
        encoding="utf-8",
    )
    os.symlink(str(proj / "knowledge"), str(p / "projects" / "alpha"))
    return p


def kbd(sb, *args):
    return subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", *args],
        env={**os.environ, "KB_HUB": str(sb)},
        capture_output=True, text=True,
    )


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


# ──────────────────────────────────────────────────────────────────────────
# decompose-staleness
# ──────────────────────────────────────────────────────────────────────────
def f_decompose_staleness():
    print("decompose-staleness: stale marker > 1 day → P2")
    sb = setup_sandbox()
    bl = sb / "alpha" / "knowledge" / "backlog.md"
    # Inject a stale decompose marker (3 days old)
    stale_date = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    bl.write_text(
        f"# alpha\n\n## Open\n- [ ] decompose: foo bar — opened {stale_date} by hub\n\n## Done\n",
        encoding="utf-8",
    )
    proc = kbd(sb, "decompose-staleness")
    assert_("decompose-staleness" in proc.stdout, "found a decompose-staleness finding")
    assert_("3 days" in proc.stdout, "reported correct age (3 days)")

    # Now a 10-day-old marker → P1
    very_stale = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    bl.write_text(
        f"# alpha\n\n## Open\n- [ ] decompose: foo — opened {very_stale} by hub\n",
        encoding="utf-8",
    )
    proc = kbd(sb, "decompose-staleness")
    assert_("P1=1" in proc.stdout, f"P1 finding for 10-day stale marker (got: {proc.stdout[:200]})")
    shutil.rmtree(sb)


# ──────────────────────────────────────────────────────────────────────────
# report-quality-check
# ──────────────────────────────────────────────────────────────────────────
def f_report_quality():
    print("report-quality-check: missing frontmatter key → P1")
    sb = setup_sandbox()
    rp = sb / "alpha" / "knowledge" / "reports"
    today = dt.date.today().isoformat()
    # Report missing `cycle:` key
    (rp / f"{today}.md").write_text(
        f"---\nreport_id: alpha-{today}\nslug: alpha\ndate: {today}\nstatus: done\nrun_id: x\n---\n\n# nothing\n",
        encoding="utf-8",
    )
    proc = kbd(sb, "report-quality-check")
    assert_("missing-frontmatter-key" in proc.stdout, "flag missing frontmatter key")
    assert_("cycle" in proc.stdout, "specifically the cycle key is missing")

    # Stale report (>7 days)
    stale_date = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    for f in rp.glob("*.md"):
        f.unlink()
    (rp / f"{stale_date}.md").write_text(
        f"---\nreport_id: alpha-{stale_date}\nslug: alpha\ndate: {stale_date}\ncycle: evening\nstatus: done\nrun_id: x\n---\n",
        encoding="utf-8",
    )
    proc = kbd(sb, "report-quality-check")
    assert_("report-quality:stale" in proc.stdout, "flag stale report")
    shutil.rmtree(sb)


# ──────────────────────────────────────────────────────────────────────────
# cycle-source-id-collision
# ──────────────────────────────────────────────────────────────────────────
def f_csid_collision():
    print("cycle-source-id-collision: same csid across pids → P1")
    sb = setup_sandbox()
    bl = sb / "alpha" / "knowledge" / "backlog.md"
    csid = "abcdef0123456789abcdef0123456789"
    pid1 = "11111111-1111-1111-1111-111111111111"
    pid2 = "22222222-2222-2222-2222-222222222222"
    bl.write_text(
        f"# alpha\n\n## Open\n"
        f"- [ ] task1 — plan_item_id: {pid1} — cycle_source_id: {csid}\n"
        f"- [ ] task2 — plan_item_id: {pid2} — cycle_source_id: {csid}\n",
        encoding="utf-8",
    )
    proc = kbd(sb, "cycle-source-id-collision")
    assert_("cross-pid" in proc.stdout, f"flag cross-pid csid collision (got: {proc.stdout[:200]})")
    shutil.rmtree(sb)


# ──────────────────────────────────────────────────────────────────────────
# seed-docs-drift
# ──────────────────────────────────────────────────────────────────────────
def f_seed_docs_drift():
    """Smoke-test only: verify the check runs and emits findings against a
    sandbox without orchestrator-seed/ subdir (which means the check should
    return empty — that's the no-seed path).
    """
    print("seed-docs-drift: no seed → no findings")
    sb = setup_sandbox()
    proc = kbd(sb, "seed-docs-drift")
    assert_("P0=0 P1=0" in proc.stdout, "no findings when seed isn't present in sandbox")
    shutil.rmtree(sb)


def f_channel_instances():
    """Incident-2026-04-25 guard: count telegram channel plugin instances.

    We mock pgrep with a fake binary on PATH that emits canned output
    matching real `pgrep -lf 'bun run.*claude-plugins-official/telegram'`.
    """
    print("channel-instances: 0 → P0; 1 → clean; 3 → P1")

    def make_pgrep_stub(sb: pathlib.Path, line_count: int):
        bindir = sb / "fake-bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "pgrep"
        # canonical-looking lines, count = line_count
        if line_count == 0:
            output = ""
        else:
            output = "\n".join(
                f"{1000+i} bun run --cwd __HOME__/.claude/plugins/cache/"
                f"claude-plugins-official/telegram/0.0.6 --shell=bun --silent start"
                for i in range(line_count)
            )
        stub.write_text(f"#!/usr/bin/env bash\ncat <<'EOF'\n{output}\nEOF\n")
        stub.chmod(0o755)
        return bindir

    # Case 0: no instances → P0 channel-instances:down
    sb = setup_sandbox()
    bindir = make_pgrep_stub(sb, 0)
    env = {**os.environ, "KB_HUB": str(sb), "PATH": f"{bindir}:{os.environ['PATH']}"}
    proc = subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "channel-instances"],
        env=env, capture_output=True, text=True,
    )
    assert_("channel-instances:down" in proc.stdout, "0 instances → P0 down")
    shutil.rmtree(sb)

    # Case 1: exactly 1 → clean
    sb = setup_sandbox()
    bindir = make_pgrep_stub(sb, 1)
    env = {**os.environ, "KB_HUB": str(sb), "PATH": f"{bindir}:{os.environ['PATH']}"}
    proc = subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "channel-instances"],
        env=env, capture_output=True, text=True,
    )
    assert_("P0=0 P1=0" in proc.stdout, "1 instance → no findings")
    shutil.rmtree(sb)

    # Case 3: duplicates → P1 channel-instances:duplicate
    sb = setup_sandbox()
    bindir = make_pgrep_stub(sb, 3)
    env = {**os.environ, "KB_HUB": str(sb), "PATH": f"{bindir}:{os.environ['PATH']}"}
    proc = subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "channel-instances"],
        env=env, capture_output=True, text=True,
    )
    assert_("channel-instances:duplicate" in proc.stdout, "3 instances → P1 duplicate")
    assert_("3 stale" in proc.stdout, "P1 message reports the count")
    shutil.rmtree(sb)


def f_seed_content_audit():
    """Verify seed-content-audit catches forbidden files in seed.

    We construct a fake seed repo with various forbidden files tracked,
    then verify the audit flags them.
    """
    print("seed-content-audit: forbidden files → P1; clean seed → no findings")

    sb = setup_sandbox()
    seed_dir = sb / "orchestrator-seed"
    (seed_dir / "knowledge").mkdir(parents=True)

    # Initialize as git repo so `git ls-files` works
    subprocess.run(["git", "-C", str(seed_dir), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(seed_dir), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(seed_dir), "config", "user.name", "test"], check=True)

    # Case 1: clean seed (only _template/ + bin/) → P0=0 P1=0
    (seed_dir / "knowledge" / "_template").mkdir()
    (seed_dir / "knowledge" / "_template" / "log.md").write_text("# log template\n")
    (seed_dir / "knowledge" / "bin").mkdir()
    (seed_dir / "knowledge" / "bin" / "kb-test").write_text("#!/bin/bash\n")
    subprocess.run(["git", "-C", str(seed_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(seed_dir), "commit", "-q", "-m", "initial"], check=True)

    proc = subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "seed-content-audit"],
        env={**os.environ, "KB_HUB": str(sb)},
        capture_output=True, text=True,
    )
    assert_("P0=0 P1=0" in proc.stdout, "clean seed → no P1 findings")

    # Case 2: leak forbidden file (live registry.md) → P1
    (seed_dir / "knowledge" / "registry.md").write_text("# real registry with personal data\n")
    subprocess.run(["git", "-C", str(seed_dir), "add", "knowledge/registry.md"], check=True)
    subprocess.run(["git", "-C", str(seed_dir), "commit", "-q", "-m", "leak"], check=True)

    proc = subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "seed-content-audit"],
        env={**os.environ, "KB_HUB": str(sb)},
        capture_output=True, text=True,
    )
    assert_("P1=" in proc.stdout, "registry.md leak → P1 finding")
    assert_("registry.md" in proc.stdout, "specifically registry.md mentioned")

    # Case 3: leak personal/ directory
    (seed_dir / "knowledge" / "personal").mkdir()
    (seed_dir / "knowledge" / "personal" / "goals.md").write_text("# my goals\n")
    subprocess.run(["git", "-C", str(seed_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(seed_dir), "commit", "-q", "-m", "leak2"], check=True)

    proc = subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "seed-content-audit"],
        env={**os.environ, "KB_HUB": str(sb)},
        capture_output=True, text=True,
    )
    assert_("personal" in proc.stdout, "personal/ leak detected")

    shutil.rmtree(sb)


def main():
    f_decompose_staleness()
    f_report_quality()
    f_csid_collision()
    f_seed_docs_drift()
    f_channel_instances()
    f_seed_content_audit()
    print("\nAll Phase 8 fixtures PASSED")


if __name__ == "__main__":
    main()
