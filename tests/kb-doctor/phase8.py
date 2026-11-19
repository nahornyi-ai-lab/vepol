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
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap

# kb-doctor imports sibling bin/ modules (e.g. _kb_codex); when the fixtures
# below exec it via importlib those imports resolve through sys.path, so the
# tree's own bin/ must be importable in every topology (repo, hub, seed).
_BIN_DIR = pathlib.Path(__file__).resolve().parents[2] / "bin"
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))


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
    assert_(_fc_one_p1(proc.stdout), f"P1 finding for 10-day stale marker (got: {proc.stdout[:200]})")
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


def f_report_quality_sections():
    print("report-quality-check: status:done sections — English and legacy Russian headings")
    today = dt.date.today().isoformat()
    front = (
        f"---\nreport_id: alpha-{today}\nslug: alpha\ndate: {today}\n"
        f"cycle: evening\nstatus: done\nrun_id: x\n---\n\n"
    )
    english = (
        "## What was done today\n- a\n\n## What was planned\n- b\n\n"
        "## Delta (plan − actual)\n- closed: 1\n\n"
        "## Candidates (what could be done tomorrow)\n\n## Escalations (upward)\n"
    )
    # Reports written from the older Russian template/prompt must still pass.
    legacy_ru = (
        "## Что сделано сегодня\n- a\n\n## Что было в плане\n- b\n\n"
        "## Дельта (план − факт)\n- closed: 1\n\n"
        "## Candidates (что можно сделать завтра)\n\n## Escalations (наверх)\n"
    )
    for label, body in (("English", english), ("legacy Russian", legacy_ru)):
        sb = setup_sandbox()
        (sb / "alpha" / "knowledge" / "reports" / f"{today}.md").write_text(front + body, encoding="utf-8")
        proc = kbd(sb, "report-quality-check")
        assert_("missing-section" not in proc.stdout,
                f"{label} section headings satisfy the done-report check (got: {proc.stdout[:200]})")
        shutil.rmtree(sb)

    sb = setup_sandbox()
    (sb / "alpha" / "knowledge" / "reports" / f"{today}.md").write_text(
        front + "## Candidates\n\n## Escalations\n", encoding="utf-8",
    )
    proc = kbd(sb, "report-quality-check")
    assert_(proc.stdout.count("missing-section") == 3,
            f"missing done/planned/delta sections are flagged (got: {proc.stdout[:300]})")
    assert_("What was done" in proc.stdout, "missing-section finding names the English section")
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
    import re as _re_p1
    assert_(_re_p1.search(r"P1=[1-9]", proc.stdout) is not None,
            "registry.md leak → P1 finding (P1= alone also matches P1=0 — R1 impl review)")
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


def f_install_health_settings_bypass():
    """Regression guard for C-01 settings bypass keys.

    The live rollout was blocked by `skipDangerousModePermissionPrompt: true`
    appearing in both live and template settings. Pin both unsafe keys in an
    isolated synthetic home/seed pair so future install-health changes cannot
    silently stop detecting them.
    """
    print("install-health settings bypass: unsafe keys → P0; safe keys → clean")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-settings-bypass-"))
    home = sb / "home"
    seed = sb / "seed"
    live = home / ".claude" / "settings.json"
    tmpl = seed / "claude" / "settings.json.template"
    live.parent.mkdir(parents=True)
    tmpl.parent.mkdir(parents=True)
    live.write_text(
        json.dumps({
            "permissions": {"defaultMode": "bypassPermissions"},
            "skipDangerousModePermissionPrompt": True,
        }),
        encoding="utf-8",
    )
    tmpl.write_text(
        json.dumps({"skipDangerousModePermissionPrompt": True}),
        encoding="utf-8",
    )

    findings = mod._ih_check_settings_bypass(home, seed)
    ids = "\n".join(f.id for f in findings)
    assert_("settings-bypass-legacy" in ids, "unsafe settings keys are detected")
    assert_(sum(1 for f in findings if f.severity == "P0") >= 2, "unsafe settings are P0")

    live.write_text(
        json.dumps({
            "permissions": {"defaultMode": "default"},
            "skipDangerousModePermissionPrompt": False,
        }),
        encoding="utf-8",
    )
    tmpl.write_text(json.dumps({"skipDangerousModePermissionPrompt": False}), encoding="utf-8")
    findings = mod._ih_check_settings_bypass(home, seed)
    assert_(not findings, "safe settings produce no bypass findings")
    shutil.rmtree(sb)


def f_install_health_orchestrator_cycle_disabled_state():
    """Regression guard for the scanner-v2 cliff.

    The prod rollout intentionally disables `com.knowledge.orchestrator-cycle`
    until scanner v2 is approved. `install-health` must not force us to restore
    an unsafe scheduled LaunchAgent just to clear P0; it should recognize the
    reviewed disabled-state evidence.
    """
    print("install-health orchestrator-cycle disabled state: reviewed disable → no P0")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test_disabled", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test_disabled", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-orch-disabled-"))
    mod.HUB = sb
    home = sb / "home"
    active_plist = home / "Library" / "LaunchAgents" / "com.knowledge.orchestrator-cycle.plist"
    disabled_dir = home / "Library" / "LaunchAgents.disabled"
    disabled_dir.mkdir(parents=True)
    (disabled_dir / "com.knowledge.orchestrator-cycle.plist.disabled-20260529-203540").write_text(
        "<plist></plist>\n",
        encoding="utf-8",
    )
    (sb / "log.md").write_text(
        "## [2026-05-29] disabled | kb-orchestrator-cycle | verified launchd/cron disabled\n",
        encoding="utf-8",
    )
    manifest = {
        "files": {
            "launchd-orchestrator-cycle": {
                "category": "managed-templated",
                "source_path": "launchd/com.knowledge.orchestrator-cycle.plist.template",
                "install_path": str(active_plist),
                "source_hash": "sha256:" + "0" * 64,
                "installed_hash": "sha256:" + "1" * 64,
            }
        }
    }

    findings = mod._ih_check_entries(manifest, home=home)
    findings.extend(mod._ih_check_launchagents(home, manifest))
    ids = "\n".join(f.id for f in findings)
    assert_("launchagent-disabled" in ids, "disabled state is reported as informational")
    assert_(not any(f.severity == "P0" for f in findings), "reviewed disabled state has no P0")

    manifest["files"]["launchd-orchestrator-cycle"]["installed_hash"] = None
    findings = mod._ih_check_entries(manifest, home=home)
    ids = "\n".join(f.id for f in findings)
    assert_("launchagent-disabled" in ids, "disabled state also tolerates manifest refresh with null installed_hash")
    assert_(not any(f.severity == "P0" for f in findings), "null installed_hash is not P0 for reviewed disabled LaunchAgent")
    shutil.rmtree(sb)


def f_install_health_optional_feature_opt_out():
    """Fresh install with optional features declined should be health-clean."""
    print("install-health optional opt-out: missing optional features → info, not P0/P1")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test_optional", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test_optional", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-optional-optout-"))
    mod.HUB = sb / "knowledge"
    mod.HUB.mkdir(parents=True)
    (mod.HUB / ".orchestrator").mkdir()
    (mod.HUB / ".orchestrator" / "launchagents.opted-out").write_text("declined\n", encoding="utf-8")
    (mod.HUB / ".orchestrator" / "memory-compiler.opted-out").write_text("declined\n", encoding="utf-8")

    home = sb / "home"
    plist = home / "Library" / "LaunchAgents" / "com.knowledge.tick.plist"
    manifest = {
        "files": {
            "launchd-tick": {
                "category": "managed-templated",
                "source_path": "launchd/com.knowledge.tick.plist.template",
                "install_path": str(plist),
                "source_hash": "sha256:" + "0" * 64,
                "installed_hash": None,
            }
        }
    }

    findings = mod._ih_check_entries(manifest, home=home)
    findings.extend(mod._ih_check_launchagents(home, manifest))
    findings.extend(mod._ih_check_memory_compiler(home))
    ids = "\n".join(f.id for f in findings)
    id_list = [f.id for f in findings]
    assert_("optional-opt-out" in ids, "optional opt-out is reported")
    assert_(len(id_list) == len(set(id_list)), "optional opt-out findings are not duplicated")
    assert_(not any(f.severity in {"P0", "P1"} for f in findings), "optional opt-out has no P0/P1")
    shutil.rmtree(sb)


def f_install_health_codex_optional():
    """Codex is optional at install time; only a configured-then-lost Codex is P1."""
    print("install-health codex optional: never-configured → info; configured-but-missing → P1")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test_codex", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test_codex", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-codex-optional-"))
    home = sb / "home"
    home.mkdir(parents=True)

    # Hermetic: the check consults KB_CODEX_BIN as a "configured" signal, so a
    # host exporting it must not leak into the never-configured scenario. Nor
    # must a Codex installed on this machine: the lookup also searches PATH and
    # the fixed Homebrew locations, so both point at nothing for this case.
    kb_codex = sys.modules["_kb_codex"]   # imported by kb-doctor above
    saved_codex_bin = os.environ.pop("KB_CODEX_BIN", None)
    saved_path = os.environ.get("PATH")
    saved_candidates = kb_codex.SYSTEM_CANDIDATES
    empty_bin = sb / "empty-bin"
    empty_bin.mkdir()
    os.environ["PATH"] = str(empty_bin)
    kb_codex.SYSTEM_CANDIDATES = ()
    try:
        findings = mod._ih_check_codex_currency(home=home)
        ids = "\n".join(f.id for f in findings)
        assert_("codex-optional-absent" in ids, "never-configured Codex is reported as optional-absent")
        assert_(not any(f.severity in {"P0", "P1"} for f in findings),
                "never-configured Codex produces no P0/P1")

        (home / ".codex").mkdir()
        findings = mod._ih_check_codex_currency(home=home)
        ids = "\n".join(f.id for f in findings)
        assert_("codex-missing" in ids, "configured-but-missing Codex is still reported")
        assert_(any(f.severity == "P1" for f in findings), "configured-but-missing Codex stays P1")
    finally:
        kb_codex.SYSTEM_CANDIDATES = saved_candidates
        if saved_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved_path
        if saved_codex_bin is not None:
            os.environ["KB_CODEX_BIN"] = saved_codex_bin
    shutil.rmtree(sb)


def f_install_health_binaries_match_installer():
    """Required binaries = install.sh REQUIRED_TOOLS; the rest are optional.

    A clean Mac that followed the README has git, claude, rg and python3 but
    maybe not gh/uv/jq/node/bun; install-health --strict must not fail on it.
    claude counts where install.sh finds it (shared lookup), not only on PATH.
    """
    print("install-health binaries: installer-required → P1 when missing; gh/uv/jq/node/bun → info")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test_bins", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test_bins", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-ih-bins-"))
    bindir = sb / "bin"
    bindir.mkdir()

    def stub(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)

    required = ("git", "claude", "rg", "python3")
    for name in required:
        stub(bindir / name)

    # Hermetic: KB_CLAUDE_BIN would count as a found claude.
    saved_claude_bin = os.environ.pop("KB_CLAUDE_BIN", None)
    try:
        findings = mod._ih_check_binaries(sb, env_path=str(bindir))
        blocking = [f for f in findings if f.severity in {"P0", "P1"}]
        assert_(not blocking, f"no P0/P1 with only installer-required tools present (got: {[f.id for f in blocking]})")
        optional = {f.file: f for f in findings if f.id.startswith("install-health:optional-binary-missing")}
        assert_(set(optional) == {"gh", "uv", "jq", "node", "bun"},
                f"gh/uv/jq/node/bun reported as optional (got: {sorted(optional)})")
        assert_(all(f.severity == "info" for f in optional.values()), "optional binaries are info, not P1")

        (bindir / "rg").unlink()
        findings = mod._ih_check_binaries(sb, env_path=str(bindir))
        missing = [f for f in findings if f.id.startswith("install-health:binary-missing:") and f.severity == "P1"]
        assert_([f.file for f in missing] == ["rg"], f"a missing installer-required tool stays P1 (got: {[f.id for f in missing]})")
        stub(bindir / "rg")

        # Claude Code's native installer puts claude in ~/.local/bin, which may
        # not be on PATH yet right after install: install.sh accepts it there.
        (bindir / "claude").unlink()
        stub(sb / ".local" / "bin" / "claude")
        findings = mod._ih_check_binaries(sb, env_path=str(bindir))
        assert_(not [f for f in findings if f.severity in {"P0", "P1"}],
                "claude in ~/.local/bin (not on PATH) counts as present")
        (sb / ".local" / "bin" / "claude").unlink()
        if not any(pathlib.Path(p).is_file() for p in ("/opt/homebrew/bin/claude", "/usr/local/bin/claude")):
            findings = mod._ih_check_binaries(sb, env_path=str(bindir))
            missing = [f for f in findings if f.id.startswith("install-health:binary-missing:")]
            assert_([f.file for f in missing] == ["claude"] and missing[0].severity == "P1",
                    f"claude found nowhere stays P1 (got: {[f.id for f in missing]})")
    finally:
        if saved_claude_bin is not None:
            os.environ["KB_CLAUDE_BIN"] = saved_claude_bin
    shutil.rmtree(sb)


def f_install_health_runtime_bypass_flags():
    """Runtime launch flags must not reintroduce bypass mode."""
    print("install-health runtime bypass flags: channel/launchd flag → P0")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test_runtime_bypass", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test_runtime_bypass", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-runtime-bypass-"))
    home = sb / "home"
    seed = sb / "seed"
    mod.HUB = sb / "knowledge"
    (seed / "bin").mkdir(parents=True)
    (mod.HUB / "bin").mkdir(parents=True)
    launch_agents = home / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True)
    (seed / "bin" / "kb-channels-start").write_text(
        "exec claude --channels x --dangerously-skip-permissions\n",
        encoding="utf-8",
    )
    (mod.HUB / "bin" / "kb-channels-start").write_text(
        "exec claude --channels x\n",
        encoding="utf-8",
    )
    (launch_agents / "com.knowledge.channel-telegram.plist").write_text(
        "<string>--dangerously-skip-permissions</string>\n",
        encoding="utf-8",
    )

    findings = mod._ih_check_runtime_bypass_flags(home, seed)
    ids = "\n".join(f.id for f in findings)
    assert_("runtime-bypass-flag" in ids, "runtime bypass flag is detected")
    assert_(sum(1 for f in findings if f.severity == "P0") >= 2, "runtime bypass flags are P0")

    (seed / "bin" / "kb-channels-start").write_text("exec claude --channels x\n", encoding="utf-8")
    (launch_agents / "com.knowledge.channel-telegram.plist").write_text("<plist></plist>\n", encoding="utf-8")
    findings = mod._ih_check_runtime_bypass_flags(home, seed)
    assert_(not findings, "safe runtime launch surfaces produce no bypass findings")
    shutil.rmtree(sb)


def f_install_health_optional_launchagents():
    """Scheduled tasks accepted: only what install.sh installs is expected.

    install.sh installs tick, planner, orchestrator-cycle and people-review-bot.
    The repo also ships channel-telegram and multibot-supervisor templates that
    are set up by hand; kb-bootstrap-manifest marks them optional, and an
    absent optional LaunchAgent is info, not a P0 broken install.
    """
    print("install-health optional LaunchAgents: not installed by install.sh → info, not P0")

    bin_dir = pathlib.Path(__file__).resolve().parents[2] / "bin"
    mods = {}
    for name, fname in (("doctor", "kb-doctor"), ("manifest", "kb-bootstrap-manifest")):
        mod_name = f"kb_{name}_under_test_optional_la"
        loader = importlib.machinery.SourceFileLoader(mod_name, str(bin_dir / fname))
        spec = importlib.util.spec_from_loader(mod_name, loader)
        assert_(spec is not None and spec.loader is not None, f"load {fname} module spec")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    doctor, manifest_mod = mods["doctor"], mods["manifest"]

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-optional-la-"))
    doctor.HUB = sb / "knowledge"
    (doctor.HUB / ".orchestrator").mkdir(parents=True)  # no opt-out marker: tasks accepted
    seed = sb / "seed"
    (seed / "launchd").mkdir(parents=True)
    home = sb / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    installed = ("tick", "planner", "orchestrator-cycle", "people-review-bot")
    for short in installed + ("channel-telegram", "multibot-supervisor"):
        (seed / "launchd" / f"com.knowledge.{short}.plist.template").write_text(
            f"<plist>{short} __HOME__</plist>\n", encoding="utf-8",
        )
    for short in installed:
        (agents / f"com.knowledge.{short}.plist").write_text(f"<plist>{short}</plist>\n", encoding="utf-8")

    manifest = manifest_mod.build_manifest(seed, home)
    files = manifest["files"]
    optional = sorted(k for k, v in files.items() if v.get("optional"))
    assert_(optional == ["launchd-channel-telegram", "launchd-multibot-supervisor"],
            f"manifest marks only the LaunchAgents install.sh does not install as optional (got: {optional})")
    assert_(all(files[f"launchd-{s}"]["installed_hash"] for s in installed),
            "the four installer LaunchAgents are recorded with their hash")

    findings = doctor._ih_check_entries(manifest, home=home)
    blocking = [f.id for f in findings if f.severity in {"P0", "P1"}]
    assert_(not blocking, f"accepted scheduled tasks + absent optional LaunchAgents → no P0/P1 (got: {blocking})")
    info = sorted(f.file for f in findings if f.id.startswith("install-health:optional-not-installed"))
    assert_(len(info) == 2 and all(("channel-telegram" in p or "multibot-supervisor" in p) for p in info),
            f"absent optional LaunchAgents are reported as info (got: {info})")

    # A required (installer) LaunchAgent missing at bootstrap stays P0, with the fix.
    (agents / "com.knowledge.planner.plist").unlink()
    findings = doctor._ih_check_entries(manifest_mod.build_manifest(seed, home), home=home)
    p0 = [f for f in findings if f.severity == "P0"]
    assert_([f.id.split(":")[3] for f in p0] == ["launchd-planner"],
            f"a missing installer LaunchAgent is still P0 (got: {[f.id for f in p0]})")
    assert_("re-run install.sh" in p0[0].message, "the P0 names the fix")
    shutil.rmtree(sb)


def f_install_health_settings_hook_fix_hint():
    """settings-hook-missing must name the fix: kb-claude-hooks --apply."""
    print("install-health settings hooks: missing hook P0 names `kb-claude-hooks --apply`")

    doctor_path = pathlib.Path(__file__).resolve().parents[2] / "bin" / "kb-doctor"
    loader = importlib.machinery.SourceFileLoader("kb_doctor_under_test_hook_hint", str(doctor_path))
    spec = importlib.util.spec_from_loader("kb_doctor_under_test_hook_hint", loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-hook-hint-"))
    home = sb / "home"
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    # A user's own settings.json that predates Vepol: no hooks at all.
    settings.write_text(json.dumps({"model": "opus", "hooks": {"Stop": []}}), encoding="utf-8")
    findings = mod._ih_check_settings(home)
    missing = [f for f in findings if f.id.startswith("install-health:settings-hook-missing")]
    assert_(len(missing) == 3 and all(f.severity == "P0" for f in missing),
            "each of the three missing Vepol hooks is P0")
    assert_(all("~/knowledge/bin/kb-claude-hooks --apply" in f.message for f in missing),
            "each settings-hook-missing finding names `~/knowledge/bin/kb-claude-hooks --apply`")

    settings.write_text(json.dumps({"hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": "~/knowledge/bin/kb-session-start"}]}],
        "SessionEnd": [{"hooks": [{"type": "command", "command": "~/knowledge/bin/kb-session-end"}]}],
        "PreCompact": [{"hooks": [{"type": "command", "command": "~/knowledge/bin/kb-pre-compact"}]}],
    }}), encoding="utf-8")
    assert_(not mod._ih_check_settings(home), "all three hooks present → no finding")
    shutil.rmtree(sb)


_REPO = pathlib.Path(__file__).resolve().parents[2]
_PIP_USER = "python3 -m pip install --user -r "
_PIP_BREW = "python3 -m pip install --break-system-packages -r "


def _load_doctor(name):
    loader = importlib.machinery.SourceFileLoader(name, str(_REPO / "bin" / "kb-doctor"))
    spec = importlib.util.spec_from_loader(name, loader)
    assert_(spec is not None and spec.loader is not None, "load kb-doctor module spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _module_dir(root, blocked=(), present=()):
    """A PYTHONPATH dir: `blocked` modules import like missing ones, `present` are empty stubs."""
    root.mkdir(parents=True, exist_ok=True)
    for name in blocked:
        (root / f"{name}.py").write_text(
            f"raise ModuleNotFoundError(\"No module named '{name}'\", name={name!r})\n",
            encoding="utf-8")
    for name in present:
        (root / f"{name}.py").write_text("", encoding="utf-8")
    return root


def _python3_on(bindir, pythonpath):
    """bindir/python3: this interpreter with PYTHONPATH pinned (hermetic packages)."""
    bindir.mkdir(parents=True, exist_ok=True)
    wrapper = bindir / "python3"
    wrapper.write_text(f"#!/bin/sh\nPYTHONPATH='{pythonpath}' exec '{sys.executable}' \"$@\"\n",
                       encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def f_install_health_python_packages():
    """requirements.txt packages missing for the PATH python3 → P1 naming the pip command."""
    print("install-health python packages: missing for PATH python3 → P1 with the install command")
    mod = _load_doctor("kb_doctor_under_test_pypkgs")
    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-ih-pypkgs-"))
    req = str(_REPO / "requirements.txt")

    _python3_on(sb / "none", _module_dir(sb / "mods-none",
                                         blocked=("frontmatter", "click", "yaml", "jellyfish")))
    findings = mod._ih_check_python_packages(env_path=str(sb / "none"))
    assert_(len(findings) == 1 and findings[0].severity == "P1"
            and findings[0].id.startswith("install-health:python-packages-missing:"),
            f"all four missing → one P1 python-packages-missing (got: {[f.id for f in findings]})")
    msg = findings[0].message
    assert_(all(p in msg for p in ("python-frontmatter", "click", "PyYAML", "jellyfish")),
            "the P1 names the pip package names")
    assert_(_PIP_USER + req in msg and _PIP_BREW + req in msg,
            f"the P1 names the --user and --break-system-packages commands (got: {msg})")

    _python3_on(sb / "some", _module_dir(sb / "mods-some", blocked=("jellyfish",),
                                         present=("frontmatter", "click", "yaml")))
    findings = mod._ih_check_python_packages(env_path=str(sb / "some"))
    assert_(len(findings) == 1 and "missing=jellyfish" in findings[0].evidence,
            f"only the missing package is listed (got: {[f.evidence for f in findings]})")

    _python3_on(sb / "all", _module_dir(sb / "mods-all",
                                        present=("frontmatter", "click", "yaml", "jellyfish")))
    assert_(mod._ih_check_python_packages(env_path=str(sb / "all")) == [],
            "all four importable → no finding")
    # A relative PATH entry: the python3 it names is the one checked, not a false P1.
    saved_cwd = os.getcwd()
    os.chdir(sb)
    try:
        findings = mod._ih_check_python_packages(env_path="all")
    finally:
        os.chdir(saved_cwd)
    assert_(findings == [], f"relative PATH entry → python3 found and checked (got: {[f.id for f in findings]})")

    (sb / "nopy").mkdir()
    assert_(mod._ih_check_python_packages(env_path=str(sb / "nopy")) == [],
            "no python3 on PATH → no extra finding (binary-missing covers it)")

    broken = sb / "broken"
    broken.mkdir()
    (broken / "python3").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (broken / "python3").chmod(0o755)
    findings = mod._ih_check_python_packages(env_path=str(broken))
    assert_([f.severity for f in findings] == ["P1"]
            and findings[0].id.startswith("install-health:python-packages-unchecked:"),
            "a python3 that cannot run the check → P1 python-packages-unchecked")

    import inspect
    assert_("_ih_check_python_packages()" in inspect.getsource(mod.install_health_check),
            "install_health_check() runs the package check")
    shutil.rmtree(sb)


def f_install_health_corelocation_info():
    """CoreLocationCLI is optional (planner sun times only) → info with the brew command."""
    print("install-health CoreLocationCLI: missing → info naming `brew install --cask corelocationcli`")
    mod = _load_doctor("kb_doctor_under_test_corelocation")
    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-ih-coreloc-"))
    real_is_file = pathlib.Path.is_file
    pathlib.Path.is_file = lambda self: False if self.name == "CoreLocationCLI" else real_is_file(self)
    try:
        findings = mod._ih_check_binaries(sb, env_path=str(sb))
    finally:
        pathlib.Path.is_file = real_is_file
    cl = [f for f in findings if f.id.startswith("install-health:binary-missing-corelocationcli")]
    assert_(len(cl) == 1 and cl[0].severity == "info", "CoreLocationCLI missing is info, not P2")
    assert_("brew install --cask corelocationcli" in cl[0].message, "the info names the install command")
    assert_("KB_FALLBACK_LAT" in cl[0].message, "the info names the fallback that works without it")
    shutil.rmtree(sb)


def f_mcp_check_shared_claude_lookup():
    """mcp-check finds claude where calendar reads do (_kb_mcp.runner._find_claude)."""
    print("mcp-check: claude in ~/.local/bin or $KB_CLAUDE_BIN (not on PATH) is found")
    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-mcp-lookup-"))
    home = sb / "home"
    log = sb / "claude-calls.log"
    stub = home / ".local" / "bin" / "claude"
    stub.parent.mkdir(parents=True)
    # Offline stub: logs its argv and fails, so no probe or canary goes anywhere.
    stub.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\necho stub-claude >&2\nexit 3\n",
                    encoding="utf-8")
    stub.chmod(0o755)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "KB_HUB": str(sb / "knowledge"),
           "LANG": "en_US.UTF-8"}

    def run(extra=None):
        proc = subprocess.run([sys.executable, str(_REPO / "bin" / "kb-doctor"), "mcp-check",
                               "--format", "json"], env={**env, **(extra or {})},
                              capture_output=True, text=True, timeout=60)
        assert_(proc.returncode == 0, f"mcp-check runs (stderr: {proc.stderr[-300:]})")
        return json.loads(proc.stdout)["findings"]

    found = run()
    assert_(not any(f["id"].startswith("mcp-check:host-missing") for f in found),
            "claude only in ~/.local/bin → no host-missing P0")
    assert_([f["file"] for f in found if f["id"].startswith("mcp-check:host-rc")] == [str(stub)],
            f"the probe ran ~/.local/bin/claude (got: {found})")
    assert_(log.read_text(encoding="utf-8").startswith("-p "), "the prompt follows -p")

    other = sb / "elsewhere" / "claude"
    other.parent.mkdir()
    shutil.copy2(stub, other)
    found = run({"KB_CLAUDE_BIN": str(other)})
    assert_([f["file"] for f in found if f["id"].startswith("mcp-check:host-rc")] == [str(other)],
            "$KB_CLAUDE_BIN wins over ~/.local/bin")

    stub.unlink()
    if not any(pathlib.Path(p).is_file() for p in ("/opt/homebrew/bin/claude", "/usr/local/bin/claude")):
        found = run()
        missing = [f for f in found if f["id"].startswith("mcp-check:host-missing")]
        assert_(len(missing) == 1 and missing[0]["severity"] == "P0"
                and "~/.local/bin" in missing[0]["message"],
                "claude found nowhere → P0 host-missing naming where it looked")
    shutil.rmtree(sb)


def f_cli_missing_python_package_message():
    """kb-idea and kb-contact print the pip command, not a traceback, when a package is missing."""
    print("kb-idea / kb-contact: missing requirements.txt package → one line with the pip command")
    sb = pathlib.Path(tempfile.mkdtemp(prefix="kb-cli-pypkgs-"))
    req = str(_REPO / "requirements.txt")
    base = {**os.environ, "HOME": str(sb), "KB_HUB": str(sb / "knowledge")}

    def run(script, args, blocked):
        mods = _module_dir(sb / ("mods-" + "-".join(blocked)), blocked=blocked)
        return subprocess.run([sys.executable, str(_REPO / "bin" / script), *args],
                              env={**base, "PYTHONPATH": str(mods)},
                              capture_output=True, text=True, timeout=60)

    cases = (
        ("kb-idea", ["capture", "My first Vepol idea"], ("frontmatter",), "python-frontmatter"),
        ("kb-contact", ["add", "Jane Doe"], ("click",), "click"),
        ("kb-contact", ["add", "Jane Doe"], ("yaml",), "PyYAML"),
        # jellyfish is imported only when fuzzy name matching runs.
        ("kb-contact", ["context", "Nobody Known"], ("jellyfish",), "jellyfish"),
    )
    for script, args, blocked, package in cases:
        proc = run(script, args, blocked)
        err = proc.stderr.strip()
        assert_(proc.returncode == 1 and "Traceback" not in proc.stderr and len(err.splitlines()) == 1,
                f"{script} {args[0]} without {package}: exit 1, one line, no traceback (got: {proc.stderr[-400:]!r})")
        assert_(err.startswith(f"{script}: Python package {package} is missing for ")
                and _PIP_USER + req in err and _PIP_BREW + req in err,
                f"{script} names the missing package and the install command")
    shutil.rmtree(sb)



# ──────────────────────────────────────────────────────────────────────────
# seed-content-audit fail-closed (spec seed-content-audit-failclosed-2026-08-14,
# contract 3e4769f8…): the audit must never report clean when it cannot
# enumerate the seed's tracked files. AC numbering below follows the spec.
# ──────────────────────────────────────────────────────────────────────────

def _fc_git(*args, cwd, env=None):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, env=env)


def _fc_seed_repo(sb, files, git=True):
    """Build orchestrator-seed with the given {relpath: content} files."""
    seed = sb / "orchestrator-seed"
    for rel, content in files.items():
        f = seed / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    if git:
        _fc_git("init", "-q", cwd=seed)
        _fc_git("config", "user.email", "t@example.com", cwd=seed)
        _fc_git("config", "user.name", "t", cwd=seed)
        _fc_git("add", "-A", cwd=seed)
        _fc_git("commit", "-q", "-m", "x", cwd=seed)
    return seed


def _fc_one_p1(out):
    """Exactly one P1: 'P1=1' as a substring also matches 'P1=10' — the R3
    implementation reviewer shipped a [finding]*10 mutant through the suite."""
    import re as _re
    return _re.search(r"P1=1\b", out) is not None


def _fc_audit(sb, env_extra=None, path=None):
    env = {**os.environ, "KB_HUB": str(sb)}
    if env_extra:
        env.update(env_extra)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["__HOME__/knowledge/bin/kb-doctor", "seed-content-audit"],
        env=env, capture_output=True, text=True,
    )


def _fc_clean_bindir(sb):
    """A PATH dir with the interpreter and coreutils the CLI needs, no git."""
    bindir = sb / "fc-bin"
    bindir.mkdir(exist_ok=True)
    import sys as _sys
    for name, target in (
        ("python3", _sys.executable),
        ("sh", "/bin/sh"),
        ("env", "/usr/bin/env"),
        ("sleep", "/bin/sleep"),
    ):
        link = bindir / name
        if not link.exists():
            link.symlink_to(target)
    return bindir


def f_audit_fc_nongit_and_sync_contract():
    print("audit-fc AC1+AC6: standalone non-git seed → P1 no-git; sync grep contract")
    sb = setup_sandbox()
    _fc_seed_repo(sb, {"knowledge/registry.md": "real registry\n"}, git=False)
    proc = _fc_audit(sb)
    assert_("seed-content-audit:no-git" in proc.stdout,
            f"AC1: no-git finding on a non-git seed (got: {proc.stdout[:200]})")
    assert_(_fc_one_p1(proc.stdout), "AC1: exactly one P1")
    assert_("128" in proc.stdout, "AC1: finding carries the git rc")
    assert_("fatal" in proc.stdout, "AC1: finding carries the first stderr line")
    import re
    assert_(re.search(r"P1=[1-9]", proc.stdout) is not None,
            "AC6: output satisfies the exact kb-seed-sync grep regex")
    sync_path = pathlib.Path("__HOME__/knowledge/bin/kb-seed-sync")
    if sync_path.exists():  # hub tool; not shipped in the public product tree
        assert_("could not verify the seed" in sync_path.read_text(encoding="utf-8"),
                "AC6: kb-seed-sync die-message covers the cannot-verify case")
    else:
        print("  - AC6 message check skipped: kb-seed-sync is a hub tool, absent in this tree")
    shutil.rmtree(sb)


def f_audit_fc_nested_parent_repo():
    print("audit-fc AC2: non-git seed nested in a parent repo → P1 no-git naming the foreign toplevel")
    sb = setup_sandbox()
    _fc_git("init", "-q", cwd=sb)
    _fc_git("config", "user.email", "t@example.com", cwd=sb)
    _fc_git("config", "user.name", "t", cwd=sb)
    (sb / "anchor.txt").write_text("x\n", encoding="utf-8")
    _fc_git("add", "anchor.txt", cwd=sb)
    _fc_git("commit", "-q", "-m", "parent", cwd=sb)
    _fc_seed_repo(sb, {"knowledge/personal/goals.md": "secret\n"}, git=False)
    proc = _fc_audit(sb)
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC2: no-git finding at P1 when git resolves the PARENT repo (got: {proc.stdout[:200]})")
    assert_(str(pathlib.Path(str(sb)).resolve()) in proc.stdout,
            "AC2: the foreign toplevel path appears in the finding")
    shutil.rmtree(sb)


def f_audit_fc_unicode_filename():
    print("audit-fc AC3: tracked non-ASCII forbidden filename is not hidden by C-quoting")
    sb = setup_sandbox()
    _fc_seed_repo(sb, {"knowledge/personal/\u00e9.md": "secret\n"})
    proc = _fc_audit(sb)
    assert_("seed-content-audit:forbidden-tracked" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC3: forbidden-tracked fires at P1 for personal/é.md (got: {proc.stdout[:200]})")
    shutil.rmtree(sb)


def f_audit_fc_oserror_family():
    print("audit-fc AC4: git launch OSError (EACCES, ENOEXEC) → P1 no-git, no traceback")
    sb = setup_sandbox()
    _fc_seed_repo(sb, {"knowledge/registry.md": "x\n"})
    bindir = _fc_clean_bindir(sb)
    # (a) EACCES: the only git on PATH is mode-000
    stubdir_a = sb / "fc-stub-a"; stubdir_a.mkdir()
    stub = stubdir_a / "git"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o000)
    proc = _fc_audit(sb, path=f"{stubdir_a}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC4a: EACCES → P1 no-git (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("Traceback" not in proc.stderr, "AC4a: no traceback")
    # (b) ENOEXEC: executable binary garbage
    stubdir_b = sb / "fc-stub-b"; stubdir_b.mkdir()
    garbage = stubdir_b / "git"
    garbage.write_bytes(b"\x00\x01\x02 not an executable format")
    garbage.chmod(0o755)
    proc = _fc_audit(sb, path=f"{stubdir_b}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC4b: ENOEXEC → P1 no-git (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("Traceback" not in proc.stderr, "AC4b: no traceback")
    # (c) ELOOP: a self-referencing git symlink — the R1 implementation
    # reviewer proved an errno-conditional handler passes every other leg.
    stubdir_c = sb / "fc-stub-c"; stubdir_c.mkdir()
    (stubdir_c / "git").symlink_to(stubdir_c / "git")
    proc = _fc_audit(sb, path=f"{stubdir_c}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC4c: ELOOP → P1 no-git (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("Traceback" not in proc.stderr, "AC4c: no traceback")
    shutil.rmtree(sb)


def f_audit_fc_root_fails_before_enumeration():
    print("audit-fc Decision-1 ordering: failed root proof answers fast, never launches ls-files")
    import time
    sb = setup_sandbox()
    _fc_seed_repo(sb, {"knowledge/registry.md": "x\n"}, git=False)
    bindir = _fc_clean_bindir(sb)
    py = str(bindir / "python3")
    d = sb / "fc-rootfail"; d.mkdir()
    (d / "git").write_text(
        "#!" + py + "\n"
        "import os, sys\n"
        "if 'rev-parse' in sys.argv:\n"
        "    sys.stderr.write('fatal-root-first\\n'); sys.exit(128)\n"
        "os.execv('/bin/sleep', ['sleep', '15'])\n", encoding="utf-8")
    (d / "git").chmod(0o755)
    t0 = time.monotonic()
    proc = _fc_audit(sb, path=f"{d}:{bindir}")
    elapsed = time.monotonic() - t0
    assert_("seed-content-audit:no-git" in proc.stdout and "128" in proc.stdout
            and "fatal-root-first" in proc.stdout,
            f"root failure reported with ITS rc and stderr (got: {proc.stdout[:200]})")
    assert_("timed out" not in proc.stdout, "no timeout diagnostic — ls-files never ran")
    assert_(elapsed < 8, f"answers fast ({elapsed:.1f}s) — the hung ls-files was never launched")
    # Same contract for the FOREIGN-ROOT branch: rc 0 with a wrong toplevel
    # must also answer before enumeration (R2 impl review: moving only this
    # check after ls-files passed every other leg).
    d2 = sb / "fc-foreignroot"; d2.mkdir()
    (d2 / "git").write_text(
        "#!" + py + "\n"
        "import os, sys\n"
        "if 'rev-parse' in sys.argv:\n"
        "    print('/'); sys.exit(0)\n"
        "os.execv('/bin/sleep', ['sleep', '15'])\n", encoding="utf-8")
    (d2 / "git").chmod(0o755)
    t0 = time.monotonic()
    proc = _fc_audit(sb, path=f"{d2}:{bindir}")
    elapsed = time.monotonic() - t0
    assert_("not the repository root" in proc.stdout and _fc_one_p1(proc.stdout),
            f"foreign root reported with its diagnostic (got: {proc.stdout[:200]})")
    assert_("timed out" not in proc.stdout and elapsed < 8,
            f"foreign root answers fast ({elapsed:.1f}s) — ls-files never launched")
    shutil.rmtree(sb)


def f_audit_fc_quiet_cases():
    print("audit-fc AC5 quiet legs: absent seed dir and empty proven repo stay silent")
    sb = setup_sandbox()  # no orchestrator-seed at all
    proc = _fc_audit(sb)
    assert_("P0=0 P1=0 P2=0 info=0" in proc.stdout and "No visible findings" in proc.stdout,
            f"absent seed dir → COMPLETELY silent (got: {proc.stdout[:200]})")
    shutil.rmtree(sb)
    sb = setup_sandbox()
    seed = sb / "orchestrator-seed"; seed.mkdir()
    _fc_git("init", "-q", cwd=seed)
    proc = _fc_audit(sb)
    assert_("P0=0 P1=0 P2=0 info=0" in proc.stdout and "No visible findings" in proc.stdout,
            f"empty root-proven repo → COMPLETELY silent (got: {proc.stdout[:200]})")
    shutil.rmtree(sb)


def f_audit_fc_env_sanitization():
    print("audit-fc AC8: GIT_* poisons are stripped; full caller env otherwise preserved")
    import json as _json, uuid
    sb = setup_sandbox()
    seed = _fc_seed_repo(sb, {"knowledge/registry.md": "x\n"})
    # foreign empty repo for the GIT_DIR poison
    foreign = sb / "fc-foreign"; foreign.mkdir()
    _fc_git("init", "-q", cwd=foreign)
    empty_index = sb / "fc-empty-index"
    poison_base = {
        "GIT_INDEX_FILE": str(empty_index),
        "GIT_DIR": str(foreign / ".git"),
        "GIT_WORK_TREE": str(seed),
        "GIT_CONFIG_COUNT": "bogus",
        f"GIT_{uuid.uuid4().hex[:12].upper()}": "bogus",
    }
    # (a) index poison alone, (b) dir/worktree poison alone — direct legs
    proc = _fc_audit(sb, env_extra={"GIT_INDEX_FILE": str(empty_index)})
    assert_("seed-content-audit:forbidden-tracked" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC8a: forbidden-tracked fires at P1 despite GIT_INDEX_FILE poison (got: {proc.stdout[:200]})")
    proc = _fc_audit(sb, env_extra={"GIT_DIR": str(foreign / ".git"), "GIT_WORK_TREE": str(seed)})
    assert_("seed-content-audit:forbidden-tracked" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC8b: forbidden-tracked fires at P1 despite GIT_DIR/GIT_WORK_TREE poison (got: {proc.stdout[:200]})")
    # (c) recording stub: full-set equality of received env vs filtered caller env
    recdir = sb / "fc-rec"; recdir.mkdir()
    rec_log = recdir / "envs.jsonl"
    stub = recdir / "git"
    stub.write_text(
        "#!" + str(_fc_clean_bindir(sb) / "python3") + "\n"
        "import json, os, subprocess, sys\n"
        f"open({str(rec_log)!r}, 'a').write(json.dumps(dict(os.environ)) + chr(10))\n"
        "r = subprocess.run(['/usr/bin/git', *sys.argv[1:]], capture_output=True)\n"
        "sys.stdout.buffer.write(r.stdout); sys.stderr.buffer.write(r.stderr)\n"
        "sys.exit(r.returncode)\n",
        encoding="utf-8")
    stub.chmod(0o755)
    sentinel_name = f"KB_AUDIT_SENTINEL_{uuid.uuid4().hex[:12]}"
    sentinel_value = uuid.uuid4().hex
    caller_env = {**os.environ, "KB_HUB": str(sb), **poison_base,
                  sentinel_name: sentinel_value,
                  "PATH": f"{recdir}:{os.environ['PATH']}"}
    # Explicit interpreter: the /usr/bin/env→Apple-trampoline path mutates
    # MANPATH between our launch and kb-doctor's os.environ, which would break
    # the exact-equality baseline through no fault of the audited code.
    import sys as _sys
    proc = subprocess.run(
        [_sys.executable, "__HOME__/knowledge/bin/kb-doctor", "seed-content-audit"],
        env=caller_env, capture_output=True, text=True,
    )
    assert_("seed-content-audit:forbidden-tracked" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC8c: audit still finds the tracked forbidden file at P1 (got: {proc.stdout[:200]})")
    recorded = [_json.loads(line) for line in rec_log.read_text(encoding="utf-8").splitlines()]
    assert_(len(recorded) == 2, f"AC8c: exactly two git invocations recorded (got {len(recorded)})")
    expected = {k: v for k, v in caller_env.items() if not k.startswith("GIT_")}
    for i, got in enumerate(recorded):
        assert_(got == expected,
                f"AC8c: call {i + 1} received EXACTLY the caller env filtered by GIT_ prefix "
                f"(missing: {sorted(set(expected) - set(got))[:5]}, "
                f"extra: {sorted(set(got) - set(expected))[:5]})")
    shutil.rmtree(sb)


def f_audit_fc_decode_replace():
    print("audit-fc AC9+AC10: invalid UTF-8 stderr on either call → P1 with U+FFFD first line")
    sb = setup_sandbox()
    seed = _fc_seed_repo(sb, {"knowledge/registry.md": "x\n"})
    bindir = _fc_clean_bindir(sb)
    py = str(bindir / "python3")
    # AC9: first call (rev-parse) fails with invalid UTF-8 stderr
    d9 = sb / "fc-ac9"; d9.mkdir()
    (d9 / "git").write_text(
        "#!" + py + "\n"
        "import sys\n"
        "sys.stderr.buffer.write(b'first-\\xff-line\\nsecond-line\\n')\n"
        "sys.exit(128)\n", encoding="utf-8")
    (d9 / "git").chmod(0o755)
    proc = _fc_audit(sb, path=f"{d9}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout)
            and "128" in proc.stdout,
            f"AC9: first-call decode failure → P1 no-git with the rc (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("first-\ufffd-line" in proc.stdout,
            "AC9: evidence carries the U+FFFD-decoded first stderr line")
    assert_("second-line" not in proc.stdout, "AC9: second stderr line excluded")
    assert_("Traceback" not in proc.stderr, "AC9: no traceback")
    # AC10: rev-parse OK (correct root), ls-files fails with invalid UTF-8
    d10 = sb / "fc-ac10"; d10.mkdir()
    (d10 / "git").write_text(
        "#!" + py + "\n"
        "import sys\n"
        "if 'rev-parse' in sys.argv:\n"
        f"    print({str(seed)!r}); sys.exit(0)\n"
        "sys.stderr.buffer.write(b'first-\\xff-line\\nsecond-line\\n')\n"
        "sys.exit(128)\n", encoding="utf-8")
    (d10 / "git").chmod(0o755)
    proc = _fc_audit(sb, path=f"{d10}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout)
            and "128" in proc.stdout,
            f"AC10: second-call rc 128 → P1 no-git with the rc (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("first-\ufffd-line" in proc.stdout,
            "AC10: evidence carries the U+FFFD-decoded first stderr line")
    assert_("second-line" not in proc.stdout, "AC10: second stderr line excluded")
    assert_("Traceback" not in proc.stderr, "AC10: no traceback")
    shutil.rmtree(sb)


def f_audit_fc_newline_filename():
    print("audit-fc AC11: tracked filename with embedded newline still matches forbidden glob")
    sb = setup_sandbox()
    _fc_seed_repo(sb, {"knowledge/migration-secret\n.yaml": "x\n"})
    proc = _fc_audit(sb)
    assert_("seed-content-audit:forbidden-tracked" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC11: newline filename detected at P1 via NUL split (got: {proc.stdout[:200]})")
    shutil.rmtree(sb)


def f_audit_fc_symlinked_hub():
    print("audit-fc AC12: healthy seed reached through a symlinked hub path → no false no-git")
    sb = setup_sandbox()
    _fc_seed_repo(sb, {"knowledge/registry.md": "x\n"})
    alias = pathlib.Path(str(sb) + "-alias")
    if alias.exists() or alias.is_symlink():
        alias.unlink()
    alias.symlink_to(sb)
    proc = _fc_audit(alias)
    assert_("seed-content-audit:forbidden-tracked" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC12: forbidden-tracked fires at P1 through the symlinked path (got: {proc.stdout[:200]})")
    assert_("seed-content-audit:no-git" not in proc.stdout,
            "AC12: no spurious no-git on a symlinked but healthy seed")
    alias.unlink()
    shutil.rmtree(sb)


def f_audit_fc_timeouts():
    print("audit-fc AC13+AC15: a hung git on either call times out into P1 no-git (~20s)")
    sb = setup_sandbox()
    seed = _fc_seed_repo(sb, {"knowledge/registry.md": "x\n"})
    bindir = _fc_clean_bindir(sb)
    py = str(bindir / "python3")
    # AC13: rev-parse hangs (exec /bin/sleep so the timeout kills the child itself)
    d13 = sb / "fc-ac13"; d13.mkdir()
    (d13 / "git").write_text(
        "#!" + py + "\nimport os\nos.execv('/bin/sleep', ['sleep', '15'])\n",
        encoding="utf-8")
    (d13 / "git").chmod(0o755)
    proc = _fc_audit(sb, path=f"{d13}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC13: first-call timeout → P1 no-git (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("timed out" in proc.stdout, "AC13: evidence names the timeout")
    assert_("Traceback" not in proc.stderr, "AC13: no traceback")
    # AC15: rev-parse delegates to real git, ls-files hangs
    d15 = sb / "fc-ac15"; d15.mkdir()
    (d15 / "git").write_text(
        "#!" + py + "\n"
        "import os, subprocess, sys\n"
        "if 'rev-parse' in sys.argv:\n"
        "    r = subprocess.run(['/usr/bin/git', *sys.argv[1:]], capture_output=True)\n"
        "    sys.stdout.buffer.write(r.stdout); sys.stderr.buffer.write(r.stderr)\n"
        "    sys.exit(r.returncode)\n"
        "os.execv('/bin/sleep', ['sleep', '15'])\n", encoding="utf-8")
    (d15 / "git").chmod(0o755)
    proc = _fc_audit(sb, path=f"{d15}:{bindir}")
    assert_("seed-content-audit:no-git" in proc.stdout and _fc_one_p1(proc.stdout),
            f"AC15: second-call timeout → P1 no-git (got: {(proc.stdout + proc.stderr)[:200]})")
    assert_("Traceback" not in proc.stderr, "AC15: no traceback")
    shutil.rmtree(sb)


def f_audit_fc_source_contract():
    print("audit-fc AC14: AST pin — one try over both git calls, literal except, single-return handler, timeout=10")
    import ast
    src_path = pathlib.Path("__HOME__/knowledge/bin/kb-doctor").resolve()
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "seed_content_audit_check"), None)
    assert_(fn is not None, "AC14: seed_content_audit_check exists")

    def is_sp_run(call):
        return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "run" and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "_sp")

    git_try = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Try):
            runs = [c for stmt in node.body for c in ast.walk(stmt) if is_sp_run(c)]
            if len(runs) == 2:
                git_try = (node, runs)
    assert_(git_try is not None, "AC14i: a single try spans exactly the two git invocations")
    node, runs = git_try
    for i, call in enumerate(runs):
        tkw = next((k for k in call.keywords if k.arg == "timeout"), None)
        assert_(tkw is not None and isinstance(tkw.value, ast.Constant) and tkw.value.value == 10,
                f"AC14iv: call {i + 1} carries the literal timeout=10")
        ekw = next((k for k in call.keywords if k.arg == "errors"), None)
        assert_(ekw is not None and isinstance(ekw.value, ast.Constant) and ekw.value.value == "replace",
                f"AC14: call {i + 1} decodes with errors='replace'")
    assert_(len(node.handlers) == 1, "AC14ii: exactly one except handler")
    h = node.handlers[0]
    ok_header = (isinstance(h.type, ast.Tuple) and len(h.type.elts) == 2
                 and isinstance(h.type.elts[0], ast.Attribute)
                 and h.type.elts[0].attr == "SubprocessError"
                 and isinstance(h.type.elts[0].value, ast.Name)
                 and h.type.elts[0].value.id == "_sp"
                 and isinstance(h.type.elts[1], ast.Name)
                 and h.type.elts[1].id == "OSError")
    assert_(ok_header, "AC14ii: handler header is literally except (_sp.SubprocessError, OSError)")
    assert_(len(h.body) == 1 and isinstance(h.body[0], ast.Return),
            "AC14iii: handler body is a single return statement")
    ret_val = h.body[0].value
    assert_(isinstance(ret_val, ast.Call) and isinstance(ret_val.func, ast.Name)
            and ret_val.func.id == "_no_git",
            "AC14iii: the return value is a DIRECT _no_git(...) call — a conditional "
            "expression (x if c else _no_git(...)) is a fail-open in disguise")
    helper = next((n for n in ast.walk(fn)
                   if isinstance(n, ast.FunctionDef) and n.name == "_no_git"), None)
    assert_(helper is not None, "AC14iii: the _no_git helper exists in the function")
    assert_(len(helper.body) == 1 and isinstance(helper.body[0], ast.Return),
            "AC14iii: _no_git's body is exactly one return statement — no room for "
            "if/match/try or any other branching construct (R2 impl review: an "
            "ast.Match returning [] for BlockingIOError slipped the If/IfExp-only check)")
    _branchy = (ast.IfExp, ast.BoolOp) + ((ast.Match,) if hasattr(ast, "Match") else ())
    assert_(not any(isinstance(n, _branchy) for n in ast.walk(helper)),
            "AC14iii: no expression-level branching anywhere in _no_git — the R3 "
            "reviewer shipped `return [] if 'FileNotFoundError' in detail else [finding(...)]` "
            "through the statement-count pin")
    hret = helper.body[0].value
    assert_(isinstance(hret, ast.List) and len(hret.elts) == 1
            and isinstance(hret.elts[0], ast.Call)
            and isinstance(hret.elts[0].func, ast.Name) and hret.elts[0].func.id == "finding",
            "AC14iii: _no_git returns a literal one-element list of a direct finding(...) call")
    fid = hret.elts[0].args[0] if hret.elts[0].args else None
    assert_(isinstance(fid, ast.Constant) and fid.value == "seed-content-audit:no-git",
            "AC14iii: the finding id argument is the literal seed-content-audit:no-git — "
            "R4 impl review spoofed the id by moving the string into the message text, "
            "which every stdout grep in the suite happily matched")
    sev = hret.elts[0].args[3] if len(hret.elts[0].args) > 3 else None
    assert_(isinstance(sev, ast.Constant) and sev.value == "P1",
            "AC14iii: the severity argument is the literal string P1 — not computed")
    hseg = ast.get_source_segment(src, helper) or ""
    assert_("seed-content-audit:no-git" in hseg and '"P1"' in hseg,
            "AC14iii: _no_git builds the P1 seed-content-audit:no-git finding")


def main():
    f_decompose_staleness()
    f_report_quality()
    f_report_quality_sections()
    f_csid_collision()
    f_seed_docs_drift()
    f_channel_instances()
    f_seed_content_audit()
    f_install_health_settings_bypass()
    f_install_health_orchestrator_cycle_disabled_state()
    f_install_health_optional_feature_opt_out()
    f_install_health_codex_optional()
    f_install_health_binaries_match_installer()
    f_install_health_runtime_bypass_flags()
    f_install_health_optional_launchagents()
    f_install_health_settings_hook_fix_hint()
    f_install_health_python_packages()
    f_install_health_corelocation_info()
    f_mcp_check_shared_claude_lookup()
    f_cli_missing_python_package_message()
    f_audit_fc_nongit_and_sync_contract()
    f_audit_fc_nested_parent_repo()
    f_audit_fc_unicode_filename()
    f_audit_fc_oserror_family()
    f_audit_fc_env_sanitization()
    f_audit_fc_decode_replace()
    f_audit_fc_newline_filename()
    f_audit_fc_symlinked_hub()
    f_audit_fc_timeouts()
    f_audit_fc_source_contract()
    f_audit_fc_root_fails_before_enumeration()
    f_audit_fc_quiet_cases()
    print("\nAll Phase 8 fixtures PASSED")


if __name__ == "__main__":
    main()
