#!/usr/bin/env python3
"""corruption.py — preflight corruption fixtures (CR11-B1).

F-PC-1: per-file tx_id with 2 terminals → all mutations on slug refused.
F-PC-2: xfer xfer_id with 2 terminals → mutations on src/dst refused.
F-PC-3: detector sees duplicate terminal in spawn window → revert + escalation.
        (Detector runs in kb-execute-next, tested separately.)
F-PC-4: unrelated corrupted xfer (slug Z) does NOT block mutations on slug Y.
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
import uuid


def setup_sandbox(slugs=("alpha", "beta")):
    sb = tempfile.mkdtemp(prefix="kb-preflight-")
    os.environ["KB_HUB"] = sb
    (pathlib.Path(sb) / "projects").mkdir()
    (pathlib.Path(sb) / ".orchestrator" / "locks").mkdir(parents=True)
    (pathlib.Path(sb) / ".orchestrator" / "audit").mkdir(parents=True)
    (pathlib.Path(sb) / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    for slug in slugs:
        proj = pathlib.Path(sb) / slug
        (proj / "knowledge").mkdir(parents=True)
        (proj / "knowledge" / "backlog.md").write_text(f"# {slug}\n\n## Open\n\n## Done\n\n", encoding="utf-8")
        os.symlink(str(proj / "knowledge"), str(pathlib.Path(sb) / "projects" / slug))
    return sb


def kb_backlog(sb, *args):
    env = {**os.environ, "KB_HUB": sb}
    return subprocess.run(
        ["__HOME__/knowledge/bin/kb-backlog", *args],
        env=env, capture_output=True, text=True,
    )


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def write_segment(sb, slug, records):
    """Write records (list of dicts) into slug's audit segment.

    First record is segment_init (created automatically). Caller passes only
    body records.
    """
    sd = pathlib.Path(sb) / ".orchestrator" / "audit" / slug
    sd.mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    p = sd / f"{sid}.jsonl"
    init = {"segment_init": True, "segment_id": sid, "prev_segment_id": None,
            "started_at": "2026-04-25T00:00:00+00:00"}
    with open(p, "w") as f:
        f.write(json.dumps(init) + "\n")
        for r in records:
            f.write(json.dumps(r) + "\n")
    # Set current pointer.
    pointer = pathlib.Path(sb) / ".orchestrator" / "audit" / (
        f"{slug}-current.txt" if slug != "_xfer" else "_xfer-current.txt"
    )
    pointer.write_text(sid)


# ──────────────────────────────────────────────────────────────────────────

def f_pc_1():
    """Per-file tx_id with 2 terminals → mutation refused."""
    print("F-PC-1: per-file duplicate terminal blocks mutations")
    sb = setup_sandbox()
    bad_tx = str(uuid.uuid4())
    write_segment(sb, "alpha", [
        {"tx_id": bad_tx, "phase": "prepared", "op": "append", "actor": "x",
         "line": None, "before_hash": "a", "after_hash": "b",
         "before_line_hashes": [], "after_line_hashes": [], "ts": "t"},
        {"tx_id": bad_tx, "phase": "committed", "ts": "t"},
        {"tx_id": bad_tx, "phase": "committed", "ts": "t"},  # DUPLICATE
    ])
    r = kb_backlog(sb, "append", "alpha", "Should fail")
    assert_(r.returncode == 3, f"append refused with exit 3 (got {r.returncode})")
    assert_("journal corruption" in r.stderr, "stderr mentions corruption")
    # But hub is unaffected.
    r2 = kb_backlog(sb, "append", "hub", "Should succeed", "--json")
    assert_(r2.returncode == 0, "hub mutation still works")
    shutil.rmtree(sb)


def f_pc_2():
    """Xfer with 2 terminals → mutations on src/dst refused."""
    print("F-PC-2: corrupted xfer blocks src/dst mutations")
    sb = setup_sandbox(slugs=("alpha", "beta", "gamma"))
    bad_xfer = str(uuid.uuid4())
    write_segment(sb, "_xfer", [
        {"xfer_id": bad_xfer, "phase": "xfer-prepared",
         "src_slug": "alpha", "dst_slug": "beta",
         "plan_item_id": "p", "src_before_hash": "a",
         "src_after_hash": "b", "dst_before_hash": "c", "dst_after_hash": "d",
         "ts": "t"},
        {"xfer_id": bad_xfer, "phase": "xfer-committed", "ts": "t"},
        {"xfer_id": bad_xfer, "phase": "xfer-aborted", "ts": "t"},  # DUP
    ])
    r1 = kb_backlog(sb, "append", "alpha", "blocked")
    assert_(r1.returncode == 3, f"alpha mutation refused (got {r1.returncode})")
    r2 = kb_backlog(sb, "append", "beta", "blocked")
    assert_(r2.returncode == 3, f"beta mutation refused (got {r2.returncode})")
    # gamma is unrelated → should succeed.
    r3 = kb_backlog(sb, "append", "gamma", "should succeed")
    assert_(r3.returncode == 0, f"gamma mutation succeeds (got {r3.returncode}, stderr: {r3.stderr})")
    shutil.rmtree(sb)


def f_pc_3():
    """Detector sees duplicate terminal in spawn window → revert + escalation.

    We construct a journal where a single tx_id has two committed terminals
    in the spawn window, and verify that `replay_chain` returns False with
    a `duplicate-terminal` diagnostic.
    """
    print("F-PC-3: detector duplicate terminal → refused")
    sb = setup_sandbox()
    bad_tx = str(uuid.uuid4())
    write_segment(sb, "alpha", [
        {"tx_id": bad_tx, "phase": "prepared", "op": "append", "actor": "x",
         "line": None, "before_hash": "a", "after_hash": "b",
         "before_line_hashes": [], "after_line_hashes": [], "ts": "t"},
        {"tx_id": bad_tx, "phase": "committed", "ts": "t"},
        {"tx_id": bad_tx, "phase": "committed", "ts": "t"},  # DUPLICATE
    ])

    # Load replay_chain and call directly with full segment range.
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        "exec_next", "__HOME__/knowledge/bin/kb-execute-next"
    )
    spec = importlib.util.spec_from_loader("exec_next", loader)
    # Run in subprocess to pick up KB_HUB.
    code = textwrap.dedent(f"""
        import sys, os, json
        sys.path.insert(0, '__HOME__/knowledge/bin')
        os.environ['KB_HUB'] = {sb!r}
        from _kb_backlog import journal as J
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader('exec_next', '__HOME__/knowledge/bin/kb-execute-next')
        spec = importlib.util.spec_from_loader('exec_next', loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        sid = J._read_current_segment_id('alpha')
        ok, diag = mod.replay_chain('alpha', 'a', 'b', sid, 0)
        print(json.dumps({{'ok': ok, 'diag': diag}}))
    """)
    proc = subprocess.run(
        ["python3", "-c", code],
        env={**os.environ, "KB_HUB": sb}, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"  ✘ subprocess failed: {proc.stderr}", file=sys.stderr)
        sys.exit(1)
    result = json.loads(proc.stdout.strip())
    assert_(not result["ok"], f"duplicate terminal detected (got ok={result['ok']})")
    assert_("duplicate-terminal" in result["diag"],
            f"diagnostic mentions duplicate-terminal (got: {result['diag']})")
    shutil.rmtree(sb)


def f_pc_4():
    """Unrelated xfer corruption does NOT block mutations on different slug."""
    print("F-PC-4: unrelated corruption does not block other slugs")
    sb = setup_sandbox(slugs=("alpha", "beta", "gamma", "delta"))
    bad_xfer = str(uuid.uuid4())
    # Corrupted xfer between gamma & delta only.
    write_segment(sb, "_xfer", [
        {"xfer_id": bad_xfer, "phase": "xfer-prepared",
         "src_slug": "gamma", "dst_slug": "delta",
         "plan_item_id": "p", "src_before_hash": "a",
         "src_after_hash": "b", "dst_before_hash": "c", "dst_after_hash": "d",
         "ts": "t"},
        {"xfer_id": bad_xfer, "phase": "xfer-committed", "ts": "t"},
        {"xfer_id": bad_xfer, "phase": "xfer-aborted", "ts": "t"},
    ])
    # alpha + beta should be unaffected.
    r1 = kb_backlog(sb, "append", "alpha", "should succeed")
    assert_(r1.returncode == 0, f"alpha unaffected (got {r1.returncode})")
    r2 = kb_backlog(sb, "append", "beta", "should succeed")
    assert_(r2.returncode == 0, f"beta unaffected (got {r2.returncode})")
    # gamma + delta blocked.
    r3 = kb_backlog(sb, "append", "gamma", "blocked")
    assert_(r3.returncode == 3, f"gamma blocked (got {r3.returncode})")
    shutil.rmtree(sb)


def main():
    f_pc_1()
    f_pc_2()
    f_pc_3()
    f_pc_4()
    print("\nAll preflight-corruption fixtures PASSED")


if __name__ == "__main__":
    main()
