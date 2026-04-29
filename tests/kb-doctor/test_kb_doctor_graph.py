"""Acceptance tests for kb-doctor Phase 1.6 — graph-audit mode.

Spec: ~/knowledge/concepts/kb-freshness-loop.md (Phase 1.6 section).

These tests are RED until the `graph-audit` mode is implemented in
~/knowledge/bin/kb-doctor. Synthetic vaults built under tmp_path; isolated
KB_HUB; never touch the live knowledge base.

Pure-Python parser is the production engine; Obsidian CLI subprocess is
exercised only in T18-T21 (validation flag), via a fake CLI script.
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import textwrap
import time


HUB_REPO = pathlib.Path(__file__).resolve().parents[2]
DOCTOR = HUB_REPO / "bin" / "kb-doctor"
TODAY = "2026-04-26"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Make a synthetic vault with the minimum chrome for graph-audit mode.

    graph-audit walks KB_HUB itself; it does not need registry rows or
    project symlinks, so the chrome is just an empty pending-curation.md.
    """
    hub = tmp_path / "hub"
    hub.mkdir(parents=True)
    write(hub / "pending-curation.md", "# Pending curation\n")
    return hub


def run_doctor(hub: pathlib.Path, *args: str, env_overrides: dict | None = None,
               today: str = TODAY) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["KB_HUB"] = str(hub)
    env["KB_DOCTOR_TODAY"] = today
    if env_overrides:
        env.update({k: str(v) for k, v in env_overrides.items()})
    return subprocess.run(
        [str(DOCTOR), "graph-audit", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def graph_findings(hub: pathlib.Path, *args: str,
                   env_overrides: dict | None = None) -> list[dict]:
    result = run_doctor(hub, "--format", "json", *args, env_overrides=env_overrides)
    assert result.returncode in (0, 1, 2), (
        f"unexpected exit {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    payload = json.loads(result.stdout)
    return payload["findings"]


def by_id_prefix(items: list[dict], prefix: str) -> list[dict]:
    return [it for it in items if it["id"].startswith(prefix)]


def by_severity(items: list[dict], severity: str) -> list[dict]:
    return [it for it in items if it["severity"] == severity]


def make_fake_obsidian_cli(tmp_path: pathlib.Path, script_body: str) -> pathlib.Path:
    """Drop a python-based fake CLI at tmp_path/fake-obsidian and chmod +x."""
    path = tmp_path / "fake-obsidian"
    path.write_text("#!/usr/bin/env python3\n" + script_body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def set_mtime_days_ago(path: pathlib.Path, days: int) -> None:
    target = time.time() - days * 86400
    os.utime(path, (target, target))


# ---------------------------------------------------------------------------
# T1-T17 — pure-Python parser behavior
# ---------------------------------------------------------------------------

def test_T01_orphan_basic_three_files(tmp_path):
    """A → B, A → C; C orphan; B has incoming from A. Only one orphan finding."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n\nLinks: [[B]] and [[C]]\n")
    write(hub / "concepts" / "B.md", "# B\n")
    write(hub / "concepts" / "C.md", "# C\n")
    # Make B an orphan so we have 2 orphans (B and A both unreferenced).
    # Wait — A has no incoming, B has incoming from A, C has incoming from A.
    # So actual orphan is A.
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)
    set_mtime_days_ago(hub / "concepts" / "B.md", 30)
    set_mtime_days_ago(hub / "concepts" / "C.md", 30)

    items = graph_findings(hub)
    # A is curated (concepts/) with 0 backlinks → P1 zero-backlinks.
    # B and C have incoming from A → no orphan, but they themselves are also
    # zero-backlinked from anywhere except A. A is a concept though. So B, C
    # have 1 backlink (from A). They get suppressed by curated logic only if
    # zero-backlinks; here they have 1 from a non-index source, so OK.
    zero_backlinks = by_id_prefix(items, "graph-zero-backlinks")
    # Only A should fire as zero-backlinks (others have incoming from A).
    assert len(zero_backlinks) == 1
    assert "A.md" in zero_backlinks[0]["file"]


def test_T02_path_component_excludes_template(tmp_path):
    """Orphan in `_template/foo.md` is not reported."""
    hub = make_vault(tmp_path)
    write(hub / "_template" / "knowledge" / "foo.md", "# template orphan\n")
    set_mtime_days_ago(hub / "_template" / "knowledge" / "foo.md", 30)

    items = graph_findings(hub)
    orphans = by_id_prefix(items, "graph-orphan")
    assert orphans == []


def test_T03_path_component_excludes_project_scoped_daily(tmp_path):
    """Orphan in projects/x/daily/2026-04-26.md is filtered by path-component."""
    hub = make_vault(tmp_path)
    write(hub / "projects" / "x" / "daily" / "2026-04-26.md", "# daily\n")
    set_mtime_days_ago(hub / "projects" / "x" / "daily" / "2026-04-26.md", 30)

    items = graph_findings(hub)
    orphans = by_id_prefix(items, "graph-orphan")
    assert orphans == [], f"expected 0 orphan findings, got {orphans}"


def test_T04_wikilink_alias(tmp_path):
    """[[Target|display]] resolves to target.md."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "Click [[Target|cool name]]\n")
    write(hub / "Target.md", "# target\n")
    set_mtime_days_ago(hub / "A.md", 30)
    set_mtime_days_ago(hub / "Target.md", 30)

    items = graph_findings(hub)
    # Target.md has 1 incoming from A → no orphan finding for Target.
    orphans = [it for it in items if "Target.md" in it["file"] and it["id"].startswith("graph-orphan")]
    assert orphans == []


def test_T05_wikilink_heading(tmp_path):
    """[[Target#section]] resolves to target.md."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "See [[Target#Section]] for more\n")
    write(hub / "Target.md", "# target\n\n## Section\n")
    set_mtime_days_ago(hub / "A.md", 30)
    set_mtime_days_ago(hub / "Target.md", 30)

    items = graph_findings(hub)
    orphans = [it for it in items if "Target.md" in it["file"] and it["id"].startswith("graph-orphan")]
    assert orphans == []


def test_T06_embed_counts_as_link(tmp_path):
    """![[Target]] embed counts as incoming for target."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "Embed: ![[Target]]\n")
    write(hub / "Target.md", "# target\n")
    set_mtime_days_ago(hub / "A.md", 30)
    set_mtime_days_ago(hub / "Target.md", 30)

    items = graph_findings(hub)
    orphans = [it for it in items if "Target.md" in it["file"] and it["id"].startswith("graph-orphan")]
    assert orphans == []


def test_T07_markdown_link_to_md(tmp_path):
    """[text](path/to/file.md) counts as incoming."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "See [doc](./Target.md)\n")
    write(hub / "Target.md", "# target\n")
    set_mtime_days_ago(hub / "A.md", 30)
    set_mtime_days_ago(hub / "Target.md", 30)

    items = graph_findings(hub)
    orphans = [it for it in items if "Target.md" in it["file"] and it["id"].startswith("graph-orphan")]
    assert orphans == []


def test_T08_broken_link(tmp_path):
    """[[NonExistent]] yields P2 graph-broken-link finding."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "Broken: [[NonExistent]]\n")
    set_mtime_days_ago(hub / "A.md", 30)

    items = graph_findings(hub)
    broken = by_id_prefix(items, "graph-broken-link")
    assert len(broken) == 1, f"expected 1 broken-link finding, got {broken}"
    assert broken[0]["severity"] == "P2"


def test_T09_ambiguous_link(tmp_path):
    """Two files with same basename + bare wikilink → ambiguous-link P2."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "Foo.md", "# concepts/foo\n")
    write(hub / "personal" / "Foo.md", "# personal/foo\n")
    write(hub / "A.md", "See [[Foo]]\n")
    set_mtime_days_ago(hub / "concepts" / "Foo.md", 30)
    set_mtime_days_ago(hub / "personal" / "Foo.md", 30)
    set_mtime_days_ago(hub / "A.md", 30)

    items = graph_findings(hub)
    ambig = by_id_prefix(items, "graph-ambiguous-link")
    assert len(ambig) == 1, f"expected 1 ambiguous-link finding, got {ambig}"
    assert ambig[0]["severity"] == "P2"


def test_T10_zero_backlinks_concept(tmp_path):
    """concepts/A.md exists, no one links → P1 graph-zero-backlinks."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n")
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)

    items = graph_findings(hub)
    zb = by_id_prefix(items, "graph-zero-backlinks")
    assert len(zb) == 1
    assert zb[0]["severity"] == "P1"
    assert "concepts/A.md" in zb[0]["file"]


def test_T11_index_only_backlink_is_p2(tmp_path):
    """concepts/A.md linked only from index.md → P2 (not P1)."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n")
    write(hub / "index.md", "# index\n\n- [[A]]\n")
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)
    set_mtime_days_ago(hub / "index.md", 30)

    items = graph_findings(hub)
    zb = by_id_prefix(items, "graph-zero-backlinks")
    assert len(zb) == 1
    assert zb[0]["severity"] == "P2"


def test_T12_dedup_orphan_suppressed_by_zero_backlinks(tmp_path):
    """concepts/A.md zero backlinks → P1 fired, parallel P2 orphan suppressed."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n")
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)

    items = graph_findings(hub)
    a_findings = [it for it in items if "concepts/A.md" in it["file"]]
    kinds = {it["id"].split(":")[0] for it in a_findings}
    # Should have graph-zero-backlinks but NOT graph-orphan for the same file.
    assert "graph-zero-backlinks" in kinds
    assert "graph-orphan" not in kinds


def test_T13_root_zero_outgoing(tmp_path):
    """Whitelisted root concept with no outgoing wikilinks → P1 zero-outgoing."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "root-x.md", "# root-x\n\nText with no [[wikilinks]] at all.\n")
    write(hub / "concepts" / "child.md", "# child\n\nLinks back: [[root-x]]\n")
    set_mtime_days_ago(hub / "concepts" / "root-x.md", 30)
    set_mtime_days_ago(hub / "concepts" / "child.md", 30)

    items = graph_findings(
        hub,
        env_overrides={"KB_DOCTOR_ROOT_CONCEPTS": "concepts/root-x.md"},
    )
    zo = by_id_prefix(items, "graph-zero-outgoing")
    assert len(zo) == 1
    assert zo[0]["severity"] == "P1"
    assert "concepts/root-x.md" in zo[0]["file"]


def test_T14_root_with_outgoing_no_finding(tmp_path):
    """Whitelisted root with at least one [[X]] → no zero-outgoing finding."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "root-x.md", "# root-x\n\nLinks: [[child]]\n")
    write(hub / "concepts" / "child.md", "# child\n\nBack: [[root-x]]\n")
    set_mtime_days_ago(hub / "concepts" / "root-x.md", 30)
    set_mtime_days_ago(hub / "concepts" / "child.md", 30)

    items = graph_findings(
        hub,
        env_overrides={"KB_DOCTOR_ROOT_CONCEPTS": "concepts/root-x.md"},
    )
    zo = by_id_prefix(items, "graph-zero-outgoing")
    assert zo == []


def test_T15_mtime_grace(tmp_path):
    """Orphan with mtime 3 days ago is hidden by 7-day grace; 8 days → reported."""
    hub = make_vault(tmp_path)
    fresh = hub / "personal" / "fresh.md"
    stale = hub / "personal" / "stale.md"
    write(fresh, "# fresh\n")
    write(stale, "# stale\n")
    set_mtime_days_ago(fresh, 3)
    set_mtime_days_ago(stale, 8)

    items = graph_findings(hub)
    orphan_files = {it["file"] for it in by_id_prefix(items, "graph-orphan")}
    assert any("stale.md" in f for f in orphan_files), f"stale.md missing from {orphan_files}"
    assert not any("fresh.md" in f for f in orphan_files), f"fresh.md should be in grace window"


def test_T16_write_idempotent(tmp_path):
    """--write goes through shared write_pending(); double run does not duplicate."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n")
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)

    run1 = run_doctor(hub, "--write", "--format", "text")
    assert run1.returncode == 0, run1.stderr
    pc1 = (hub / "pending-curation.md").read_text()
    run2 = run_doctor(hub, "--write", "--format", "text")
    pc2 = (hub / "pending-curation.md").read_text()
    assert pc1 == pc2, "managed block changed on idempotent re-run"


def test_T17_strict_exit_p1(tmp_path):
    """--strict returns 1 on a single P1 finding."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n")
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)

    res = run_doctor(hub, "--strict")
    assert res.returncode == 1, f"expected exit 1, got {res.returncode}\n{res.stdout}\n{res.stderr}"


# ---------------------------------------------------------------------------
# T18-T21 — optional Obsidian CLI cross-validation
# ---------------------------------------------------------------------------

def test_T18_validate_with_obsidian_match(tmp_path):
    """Fake CLI returns same orphans set → no mismatch finding."""
    hub = make_vault(tmp_path)
    write(hub / "personal" / "stale.md", "# stale\n")
    set_mtime_days_ago(hub / "personal" / "stale.md", 30)

    fake = make_fake_obsidian_cli(tmp_path, textwrap.dedent("""
        import sys
        args = [a for a in sys.argv[1:] if not a.startswith("vault=")]
        if args and args[0] == "vault":
            print("name\\tknowledge"); sys.exit(0)
        if args and args[0] == "orphans":
            # mirror what pure-Python found
            print("personal/stale.md")
            sys.exit(0)
        sys.exit(0)
    """))

    items = graph_findings(
        hub, "--validate-with-obsidian",
        env_overrides={"KB_DOCTOR_GRAPH_OBSIDIAN_CLI": str(fake)},
    )
    mismatch = by_id_prefix(items, "graph-audit:obsidian-orphan-mismatch")
    assert mismatch == [], f"expected 0 mismatch findings, got {mismatch}"


def test_T19_validate_with_obsidian_diff_over_threshold(tmp_path):
    """Fake CLI returns diff > 5 → 1 P2 mismatch finding."""
    hub = make_vault(tmp_path)
    write(hub / "personal" / "stale.md", "# stale\n")
    set_mtime_days_ago(hub / "personal" / "stale.md", 30)

    fake = make_fake_obsidian_cli(tmp_path, textwrap.dedent("""
        import sys
        args = [a for a in sys.argv[1:] if not a.startswith("vault=")]
        if args and args[0] == "vault":
            print("name\\tknowledge"); sys.exit(0)
        if args and args[0] == "orphans":
            # claim 10 unique orphans → diff > 5
            for i in range(10):
                print(f"phantom/file{i}.md")
            sys.exit(0)
        sys.exit(0)
    """))

    items = graph_findings(
        hub, "--validate-with-obsidian",
        env_overrides={"KB_DOCTOR_GRAPH_OBSIDIAN_CLI": str(fake)},
    )
    mismatch = by_id_prefix(items, "graph-audit:obsidian-orphan-mismatch")
    assert len(mismatch) == 1, f"expected 1 mismatch, got {mismatch}"
    assert mismatch[0]["severity"] == "P2"


def test_T20_cli_unknown_nonzero_is_p2(tmp_path):
    """Fake CLI exits 1 (not the known skip-class) → P2 cli-error finding."""
    hub = make_vault(tmp_path)

    fake = make_fake_obsidian_cli(tmp_path, textwrap.dedent("""
        import sys
        args = [a for a in sys.argv[1:] if not a.startswith("vault=")]
        if args and args[0] == "vault":
            print("name\\tknowledge"); sys.exit(0)
        if args and args[0] == "orphans":
            sys.stderr.write("BOOM something broke\\n")
            sys.exit(1)
        sys.exit(0)
    """))

    items = graph_findings(
        hub, "--validate-with-obsidian",
        env_overrides={"KB_DOCTOR_GRAPH_OBSIDIAN_CLI": str(fake)},
    )
    cli_err = by_id_prefix(items, "graph-audit:cli-error")
    assert len(cli_err) == 1, f"expected 1 cli-error, got {cli_err}"
    assert cli_err[0]["severity"] == "P2"


def test_T21_cli_missing_silent_skip(tmp_path):
    """CLI binary path doesn't exist → silent skip; no findings emitted."""
    hub = make_vault(tmp_path)

    items = graph_findings(
        hub, "--validate-with-obsidian",
        env_overrides={"KB_DOCTOR_GRAPH_OBSIDIAN_CLI": "/nonexistent/obsidian-fake"},
    )
    cli_err = by_id_prefix(items, "graph-audit:cli-error")
    mismatch = by_id_prefix(items, "graph-audit:obsidian-orphan-mismatch")
    assert cli_err == [] and mismatch == [], (
        f"expected silent skip, got cli_err={cli_err} mismatch={mismatch}"
    )


# ---------------------------------------------------------------------------
# T22-T24 — robustness
# ---------------------------------------------------------------------------

def test_T22_run_budget_exceeded(tmp_path):
    """Budget=1s exceeded → P2 budget-exceeded finding, partial flush."""
    hub = make_vault(tmp_path)
    # Create lots of files to slow the parser.
    for i in range(5000):
        write(hub / "personal" / f"f{i:04d}.md", f"# f{i}\n")
        if i % 1000 == 0:
            set_mtime_days_ago(hub / "personal" / f"f{i:04d}.md", 30)

    items = graph_findings(hub, env_overrides={"KB_DOCTOR_GRAPH_RUN_BUDGET_S": "0.0001"})
    budget = by_id_prefix(items, "graph-audit:budget-exceeded")
    assert len(budget) == 1, f"expected 1 budget-exceeded finding, got {budget}"
    assert budget[0]["severity"] == "P2"


def test_T23_json_mode_field(tmp_path):
    """JSON output includes mode='graph-audit'."""
    hub = make_vault(tmp_path)
    res = run_doctor(hub, "--format", "json")
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload.get("mode") == "graph-audit"


def test_T24_symlink_loop_protection(tmp_path):
    """Cycle through projects/<slug> symlink — walk completes, no hang."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "A.md", "# A\n")
    set_mtime_days_ago(hub / "concepts" / "A.md", 30)
    # Create a self-referential symlink: hub/projects/loop -> hub/projects
    (hub / "projects").mkdir(exist_ok=True)
    (hub / "projects" / "loop").symlink_to(hub / "projects")

    res = run_doctor(hub)
    # Just must finish in reasonable time.
    assert res.returncode in (0, 1, 2), f"hung or crashed: {res.returncode} stderr={res.stderr}"


# ---------------------------------------------------------------------------
# T25-T30 — round-2 spec clarifications
# ---------------------------------------------------------------------------

def test_T25_source_relative_md_link(tmp_path):
    """personal/A.md has [note](../concepts/B.md) → counts as incoming for concepts/B.md."""
    hub = make_vault(tmp_path)
    write(hub / "personal" / "A.md", "See [doc](../concepts/B.md)\n")
    write(hub / "concepts" / "B.md", "# B\n")
    set_mtime_days_ago(hub / "personal" / "A.md", 30)
    set_mtime_days_ago(hub / "concepts" / "B.md", 30)

    items = graph_findings(hub)
    # B is a curated concept; with 1 incoming from non-index → no zero-backlinks.
    zb = [it for it in items if "concepts/B.md" in it["file"] and it["id"].startswith("graph-zero-backlinks")]
    assert zb == [], f"B.md should have incoming from A via relative md-link, got {zb}"


def test_T26_case_insensitive_wikilink(tmp_path):
    """[[Target]] resolves both target.md and Target.md (Obsidian default)."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "See [[target]]\n")
    write(hub / "Target.md", "# Target\n")
    set_mtime_days_ago(hub / "A.md", 30)
    set_mtime_days_ago(hub / "Target.md", 30)

    items = graph_findings(hub)
    broken = by_id_prefix(items, "graph-broken-link")
    assert broken == [], f"case-insensitive resolution should find Target.md from [[target]], got {broken}"


def test_T27_broken_link_dedup_one_per_source(tmp_path):
    """Same broken target referenced 3x in one file → 1 finding."""
    hub = make_vault(tmp_path)
    write(hub / "A.md", "[[Missing]] and [[Missing]] and [[Missing]] again\n")
    set_mtime_days_ago(hub / "A.md", 30)

    items = graph_findings(hub)
    broken = by_id_prefix(items, "graph-broken-link")
    assert len(broken) == 1, f"expected 1 dedup'd broken-link, got {broken}"


def test_T28_obsidian_directory_excluded(tmp_path):
    """orphan-like file under .obsidian/plugins/foo/notes.md — 0 findings."""
    hub = make_vault(tmp_path)
    write(hub / ".obsidian" / "plugins" / "foo" / "notes.md", "# plugin notes\n")
    set_mtime_days_ago(hub / ".obsidian" / "plugins" / "foo" / "notes.md", 30)

    items = graph_findings(hub)
    orphan_hits = [it for it in items if ".obsidian" in it["file"]]
    assert orphan_hits == [], f"expected 0 findings under .obsidian/, got {orphan_hits}"


def test_T29_edge_invariant_broken_does_not_suppress_zero_outgoing(tmp_path):
    """Whitelisted root contains only [[NonExistent]] → zero-outgoing P1 + broken-link P2 both fire."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "root-x.md", "# root\n\n[[NonExistent]]\n")
    set_mtime_days_ago(hub / "concepts" / "root-x.md", 30)

    items = graph_findings(
        hub,
        env_overrides={"KB_DOCTOR_ROOT_CONCEPTS": "concepts/root-x.md"},
    )
    zo = by_id_prefix(items, "graph-zero-outgoing")
    broken = by_id_prefix(items, "graph-broken-link")
    assert len(zo) == 1, f"expected zero-outgoing finding, got {zo}"
    assert len(broken) == 1, f"expected broken-link finding, got {broken}"


def test_T30_external_md_link_not_counted(tmp_path):
    """[x](https://example.com/foo.md) is NOT counted as a graph edge."""
    hub = make_vault(tmp_path)
    write(hub / "concepts" / "B.md", "# B\n")
    write(hub / "A.md", "See [x](https://example.com/B.md)\n")
    set_mtime_days_ago(hub / "concepts" / "B.md", 30)
    set_mtime_days_ago(hub / "A.md", 30)

    items = graph_findings(hub)
    # B should still be flagged as zero-backlinks since the external link
    # doesn't count.
    zb = [it for it in items if "concepts/B.md" in it["file"] and it["id"].startswith("graph-zero-backlinks")]
    assert len(zb) == 1, f"expected zero-backlinks for B.md (external link should not count), got {zb}"
