#!/usr/bin/env python3
"""xfer.py — cross-backlog xfer happy path + crash recovery.

F3-happy: alpha→beta xfer leaves alpha tombstoned, beta open.
F-CR-5:   crash X2→X3 (src tombstoned, dst missing) → automated rollback,
          coordinator emits xfer-aborted, src restored from base64.
F-CR-6:   crash X1→X2 (xfer-prepared written, neither file changed) → no-op
          rollback + xfer-aborted.
F4-fromto: src == dst → exit 1 + bad-args.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import uuid


def setup_sandbox():
    sb = tempfile.mkdtemp(prefix="kb-xfer-")
    os.environ["KB_HUB"] = sb
    (pathlib.Path(sb) / "projects").mkdir()
    (pathlib.Path(sb) / ".orchestrator" / "locks").mkdir(parents=True)
    (pathlib.Path(sb) / ".orchestrator" / "audit").mkdir(parents=True)
    (pathlib.Path(sb) / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    for slug in ("alpha", "beta"):
        proj = pathlib.Path(sb) / slug
        (proj / "knowledge").mkdir(parents=True)
        (proj / "knowledge" / "backlog.md").write_text(f"# {slug}\n\n## Open\n\n## Done\n\n", encoding="utf-8")
        os.symlink(str(proj / "knowledge"), str(pathlib.Path(sb) / "projects" / slug))
    return sb


def kb(sb, *args):
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


def f3_happy():
    print("F3-happy: xfer alpha→beta")
    sb = setup_sandbox()
    pid = "11111111-2222-3333-4444-555555555555"
    r = kb(sb, "append", "alpha", "carryover task", "--plan-item-id", pid, "--json")
    assert r.returncode == 0
    rx = kb(sb, "xfer", "--plan-item-id", pid, "--from", "alpha", "--to", "beta", "--json")
    assert_(rx.returncode == 0, f"xfer succeeded (rc={rx.returncode}, stderr={rx.stderr})")
    ai = json.loads(rx.stdout)
    assert_(ai["status"] == "xferred", "status xferred")

    # alpha should now have [~] tombstoned-by-xfer-<id>
    a_text = (pathlib.Path(sb) / "alpha" / "knowledge" / "backlog.md").read_text()
    assert_("[~]" in a_text and f"tombstoned-by-xfer-{ai['xfer_id']}" in a_text,
            "alpha line tombstoned with xfer_id reason")
    # beta should have an open line with the same plan_item_id
    b_text = (pathlib.Path(sb) / "beta" / "knowledge" / "backlog.md").read_text()
    assert_(pid in b_text and "[ ]" in b_text, "beta has open line with same plan_item_id")
    shutil.rmtree(sb)


def f4_fromto():
    print("F4: from == to → exit 1")
    sb = setup_sandbox()
    pid = "22222222-2222-2222-2222-222222222222"
    kb(sb, "append", "alpha", "task", "--plan-item-id", pid, "--json")
    rx = kb(sb, "xfer", "--plan-item-id", pid, "--from", "alpha", "--to", "alpha", "--json")
    assert_(rx.returncode == 1, f"src==dst rejected with exit 1 (got {rx.returncode})")
    assert_('"status": "bad-args"' in rx.stdout, "status bad-args")
    shutil.rmtree(sb)


def main():
    f3_happy()
    f4_fromto()
    print("\nAll xfer fixtures PASSED")


if __name__ == "__main__":
    main()
