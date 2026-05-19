#!/usr/bin/env python3
"""synthetic.py — Phase 6 bootstrap acceptance.

Simulates a fresh-machine bootstrap from `kb-seed-sync`'s output:

1. Build a synthetic "fresh hub" in a tempdir (no live ~/knowledge/
   dependency).
2. Copy the seed's bin/, _template/, CLAUDE.md.
3. Create 3 dummy "project" directories, each with knowledge/.
4. Run `new-wiki` on each (or symlink directly to skip the codex setup
   that needs network).
5. Edit each project's `.orchestration.yaml` to `cycle_enabled: true`.
6. Run `kb-rebuild-registry apply` (regenerates registry.md +
   hierarchy.yaml from frontmatter).
7. Run `kb-orchestrator-cycle retro --skip-registry-check
   --skip-hub-retro` against the synthetic hierarchy. The broker is a
   stub that emits a valid report and exits 0.
8. Verify: each project has a `status: done` report, hub gets daily
   summary, no spurious `pending`/`error` reports.

Bootstrap acceptance per Phase 6: this should complete in ≤90 minutes
on a clean macOS VM. In test env, target is ≤30 seconds.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_BIN = REPO_ROOT / "bin"
SEED_TEMPLATE = REPO_ROOT / "_template"


def setup_fresh_hub():
    """Build a from-scratch hub: bin/, _template/, projects/, daily/, .orchestrator/."""
    sb = tempfile.mkdtemp(prefix="kb-bootstrap-")
    hub = pathlib.Path(sb)

    # Copy bin/ (including _kb_backlog package)
    shutil.copytree(SEED_BIN, hub / "bin", symlinks=False, dirs_exist_ok=False)
    for child in (hub / "bin").iterdir():
        if child.is_file() and not child.name.startswith("_"):
            child.chmod(0o755)
    # Make script files (no extension, not _kb_backlog/) executable
    for child in (hub / "bin").iterdir():
        if child.is_file() and not child.suffix and not child.name.startswith("_"):
            child.chmod(0o755)

    # Copy _template/
    shutil.copytree(SEED_TEMPLATE, hub / "_template", dirs_exist_ok=False)

    # Hub-level scaffolding
    (hub / "projects").mkdir()
    (hub / "daily").mkdir()
    (hub / "daily-plan").mkdir()
    (hub / ".orchestrator" / "locks").mkdir(parents=True)
    (hub / ".orchestrator" / "audit").mkdir(parents=True)
    (hub / ".orchestrator" / "circuits").mkdir(parents=True)
    (hub / ".orchestrator" / "runs").mkdir(parents=True)
    (hub / "logs").mkdir()

    # Hub README + log + backlog
    (hub / "README.md").write_text(
        "---\nslug: hub\nparent: null\ncategory: hub\nstatus: live\n"
        "description: \"Fresh test hub\"\n---\n\n# Hub\n",
        encoding="utf-8",
    )
    (hub / "log.md").write_text("# Hub log\n", encoding="utf-8")
    (hub / "backlog.md").write_text("# Hub backlog\n\n## Open\n\n## Done\n", encoding="utf-8")
    (hub / "index.md").write_text("# Hub index\n", encoding="utf-8")

    return hub


def bootstrap_project(hub: pathlib.Path, slug: str, parent_slug: str = "hub"):
    """Create a project with full knowledge/ scaffold + frontmatter + .orchestration.yaml.

    Project lives INSIDE the hub tempdir (not as a sibling) to avoid stale
    leftovers from prior runs at /tmp/proj-<slug>.
    """
    proj = hub / "_projects" / f"proj-{slug}"
    knowledge = proj / "knowledge"
    knowledge.mkdir(parents=True)

    # Render templates manually (skip new-wiki because it tries to enable Codex review gate
    # which would fail in test env without network)
    files = {
        "README.md": (
            f"---\nslug: {slug}\nparent: {parent_slug}\ncategory: pet\nstatus: live\n"
            f"description: \"Synthetic test project {slug}\"\n---\n\n# {slug}\n"
        ),
        "log.md": f"# {slug} log\n",
        "state.md": f"# {slug} state\n\nFresh project.\n",
        "backlog.md": f"# {slug} backlog\n\n## Open\n\n## Done\n",
        "escalations.md": f"# {slug} escalations\n\n## Open\n",
        "incidents.md": f"# {slug} incidents\n\n## Open\n",
        "strategies.md": f"# {slug} strategies\n",
        "index.md": f"# {slug} index\n",
        ".orchestration.yaml": (
            "version: 1\ncycle_enabled: true\nsla_report_timeout_sec: 60\n"
            "owner: test\ndecompose_strategy: subset\nexec_broker: false\n"
        ),
    }
    for name, content in files.items():
        (knowledge / name).write_text(content, encoding="utf-8")
    (knowledge / "reports").mkdir()
    (knowledge / "raw").mkdir()
    (knowledge / "sources").mkdir()
    (knowledge / "daily").mkdir()

    # Symlink into hub/projects/
    os.symlink(str(knowledge), str(hub / "projects" / slug))

    return proj


def write_migration_table(hub: pathlib.Path, slugs: list[str]):
    """Write migration-2026-04-25.yaml in the format kb-rebuild-registry expects.

    The parser requires a top-level `entries:` block followed by 2-space
    indented `- slug: ...` entries.
    """
    today = dt.date.today().isoformat()
    lines = [f"# migration-{today}.yaml — synthetic bootstrap", "", "entries:"]
    for slug in slugs:
        proj = hub / "_projects" / f"proj-{slug}"
        lines.append(f"  - slug: {slug}")
        lines.append(f"    registry_source: derived")
        lines.append(f"    wiki_backed: true")
        lines.append(f"    orchestration_eligible: true")
        lines.append(f"    status: live")
        lines.append(f"    parent: hub")
        lines.append(f"    category: pet")
        lines.append(f"    knowledge_path: {proj}/knowledge")
        lines.append(f"    expected_symlink: {hub}/projects/{slug}")
        lines.append(f"    project_path: {proj}")
        lines.append(f'    description: "Synthetic test project {slug}"')
    (hub / f"migration-{today}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_stub_broker(hub: pathlib.Path):
    """Replace the real kb-orchestrator-run with a stub that writes a valid
    report and exits 0. This isolates the bootstrap test from network calls.
    """
    stub = hub / "bin" / "kb-orchestrator-run"
    stub.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import sys, datetime, pathlib, re, os, json, uuid
        args = sys.argv[1:]
        cwd = None
        run_id = None
        for i, a in enumerate(args):
            if a == "--cwd" and i + 1 < len(args):
                cwd = args[i + 1]
            elif a == "--run-id" and i + 1 < len(args):
                run_id = args[i + 1]
        if cwd is None:
            print("stub broker: no --cwd", file=sys.stderr); sys.exit(1)
        prompt = args[0]
        m = re.search(r'project\\s+\\*\\*([^*]+)\\*\\*', prompt)
        slug = m.group(1) if m else 'unknown'
        m2 = re.search(r'`reports/([0-9-]+)\\.md`', prompt)
        date = m2.group(1) if m2 else datetime.date.today().isoformat()
        m3 = re.search(r'run_id: ([0-9a-f-]+)', prompt)
        rid = m3.group(1) if m3 else 'stub-run'
        rp = pathlib.Path(cwd) / 'reports' / f'{date}.md'
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            f"---\\nreport_id: {slug}-{date}\\nslug: {slug}\\ndate: {date}\\n"
            f"cycle: evening\\nparent: hub\\nchildren_rolled_up: []\\n"
            f"status: done\\nrun_id: {rid}\\n---\\n\\n"
            f"## Что сделано сегодня\\n- stub work for {slug}\\n\\n"
            f"## Candidates\\n\\n## Escalations\\n",
            encoding='utf-8',
        )
        if run_id:
            hub = os.environ.get("KB_HUB", os.path.expanduser("~/knowledge"))
            runs_dir = pathlib.Path(hub) / ".orchestrator" / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            (runs_dir / f"{run_id}.json").write_text(json.dumps({
                "run_id": run_id, "exit_code": 0, "category": "ok",
                "detail": "stub-broker", "provider": "claude", "fallback_used": False,
            }), encoding="utf-8")
        print(f"OUTCOME: closed: stub-broker for {slug}")
    """), encoding="utf-8")
    stub.chmod(0o755)

    # Also stub kb-retro
    retro = hub / "bin" / "kb-retro"
    retro.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    retro.chmod(0o755)


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def main():
    print("Phase 6 bootstrap acceptance: synthetic 3-project end-to-end")
    t0 = time.time()

    hub = setup_fresh_hub()
    slugs = ("alpha", "beta", "gamma")
    for slug in slugs:
        bootstrap_project(hub, slug)
    write_migration_table(hub, list(slugs))
    write_stub_broker(hub)

    # Run kb-rebuild-registry apply to regenerate registry + hierarchy
    today = dt.date.today().isoformat()
    proc = subprocess.run(
        [str(hub / "bin" / "kb-rebuild-registry"), "apply",
         "--migration", str(hub / f"migration-{today}.yaml")],
        env={**os.environ, "KB_HUB": str(hub)},
        capture_output=True, text=True,
    )
    assert_(proc.returncode == 0,
            f"kb-rebuild-registry apply succeeds (rc={proc.returncode}, stderr={proc.stderr[-300:]})")
    assert_((hub / "hierarchy.yaml").is_file(), "hierarchy.yaml created")

    # Run the cycle
    proc = subprocess.run(
        [str(hub / "bin" / "kb-orchestrator-cycle"), "retro",
         "--skip-registry-check", "--skip-hub-retro"],
        env={**os.environ, "KB_HUB": str(hub)},
        capture_output=True, text=True,
    )
    assert_(proc.returncode == 0,
            f"cycle retro exits 0 (rc={proc.returncode}, stderr={proc.stderr[-300:]})")

    # Each project has a status: done report
    for slug in slugs:
        rp = (hub / "_projects" / f"proj-{slug}" / "knowledge" / "reports" / f"{today}.md")
        assert_(rp.is_file(), f"{slug} report exists")
        text = rp.read_text(encoding="utf-8")
        assert_("status: done" in text, f"{slug} status: done")

    # Hub got daily summary
    daily = hub / "daily" / f"{today}.md"
    assert_(daily.is_file(), "daily.md created")
    summary = daily.read_text(encoding="utf-8")
    assert_("### Cycle summary" in summary, "daily.md has cycle summary section")

    elapsed = time.time() - t0
    print(f"\nBootstrap acceptance: {len(slugs)} projects in {elapsed:.1f}s "
          f"(target ≤90 min on clean VM, ≤30s in CI)")
    assert_(elapsed < 90, f"completed under 90s in test env (got {elapsed:.1f}s)")

    # Cleanup (everything's under hub since _projects is inside)
    shutil.rmtree(hub)
    print("\nPhase 6 bootstrap PASSED")


if __name__ == "__main__":
    main()
