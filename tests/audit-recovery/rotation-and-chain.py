#!/usr/bin/env python3
"""rotation-and-chain.py — F-CR-7 (rotation race) + F-CR-8 (chain replay).

We isolate KB_HUB into subprocess workers so module imports always see the
correct sandbox path (Python caches the package's submodule attribute even
after popping sys.modules).
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
    sb = tempfile.mkdtemp(prefix="kb-rotchain-")
    (pathlib.Path(sb) / "projects").mkdir()
    (pathlib.Path(sb) / ".orchestrator" / "locks").mkdir(parents=True)
    (pathlib.Path(sb) / ".orchestrator" / "audit").mkdir(parents=True)
    (pathlib.Path(sb) / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    proj = pathlib.Path(sb) / "alpha"
    (proj / "knowledge").mkdir(parents=True)
    (proj / "knowledge" / "backlog.md").write_text("# alpha\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    os.symlink(str(proj / "knowledge"), str(pathlib.Path(sb) / "projects" / "alpha"))
    return sb


def run_in_sandbox(sb: str, code: str) -> tuple[int, str, str]:
    """Run `code` in a fresh subprocess with KB_HUB=sb."""
    proc = subprocess.run(
        ["python3", "-c", code],
        env={**os.environ, "KB_HUB": sb},
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def f_cr_7():
    """Rotation refuses with active spawn on current segment."""
    print("F-CR-7: rotation race — refuses with active spawn")
    sb = setup_sandbox()
    # Bootstrap a segment via real CLI call
    subprocess.run(
        ["__HOME__/knowledge/bin/kb-backlog", "append", "alpha", "seed", "--json"],
        env={**os.environ, "KB_HUB": sb}, capture_output=True, check=True,
    )

    # Run the rotation test in a fresh subprocess with correct KB_HUB.
    code = textwrap.dedent(f"""
        import sys, os, json
        sys.path.insert(0, '__HOME__/knowledge/bin')
        os.environ['KB_HUB'] = {sb!r}
        from _kb_backlog import journal as J, spawns as SP

        sid = J._read_current_segment_id('alpha')
        SP.register(spawn_id='test', pid=99999, slug='alpha',
                    segment_id=sid, offset=0, started_at='2026-04-25T00:00:00+00:00')

        J.ROTATION_SIZE_BYTES = 1
        try:
            J.rotate_if_needed('alpha', SP.has_active_on_segment)
            print(json.dumps({{'with_spawn': 'no-error'}}))
        except RuntimeError as e:
            print(json.dumps({{'with_spawn': 'refused', 'msg': str(e)}}))

        SP.unregister('test')
        new = J.rotate_if_needed('alpha', SP.has_active_on_segment)
        init = J._read_segment_init('alpha', new) if new else None
        print(json.dumps({{'after_unreg': new, 'old_sid': sid,
                          'prev_id': init['prev_segment_id'] if init else None}}))
    """)
    rc, out, err = run_in_sandbox(sb, code)
    assert rc == 0, f"subprocess failed: {err}"
    lines = [json.loads(ln) for ln in out.strip().splitlines() if ln.strip()]
    with_spawn = lines[0]
    after_unreg = lines[1]
    assert_(with_spawn["with_spawn"] == "refused",
            f"rotation refused while active spawn present (got: {with_spawn})")
    assert_(after_unreg["after_unreg"] is not None and after_unreg["after_unreg"] != after_unreg["old_sid"],
            "rotation succeeded after spawn unregistered")
    assert_(after_unreg["prev_id"] == after_unreg["old_sid"],
            "new segment chains back via prev_segment_id")
    shutil.rmtree(sb)


def f_cr_8():
    """Chain replay catches A → raw-X → B."""
    print("F-CR-8: chain replay catches A → raw-X → B sequence")
    sb = setup_sandbox()
    # Step 1: append A via real CLI
    subprocess.run(
        ["__HOME__/knowledge/bin/kb-backlog", "append", "alpha", "task A", "--json"],
        env={**os.environ, "KB_HUB": sb}, capture_output=True, check=True,
    )

    # Step 2: raw-write X (bypass kb-backlog)
    bl = pathlib.Path(sb) / "alpha" / "knowledge" / "backlog.md"
    text_after_a = bl.read_text(encoding="utf-8")
    bl.write_text(text_after_a + "- [ ] RAW X — durable unauthorized\n", encoding="utf-8")

    # Step 3: append B via real CLI (this records before_hash = hash_X != hash_A)
    subprocess.run(
        ["__HOME__/knowledge/bin/kb-backlog", "append", "alpha", "task B", "--json"],
        env={**os.environ, "KB_HUB": sb}, capture_output=True, check=True,
    )

    # Step 4: replay chain in subprocess from start of segment.
    code = textwrap.dedent(f"""
        import sys, os, json, pathlib
        sys.path.insert(0, '__HOME__/knowledge/bin')
        os.environ['KB_HUB'] = {sb!r}
        from _kb_backlog import journal as J

        # Compute initial empty-file hash by simulating: actually we want the
        # hash BEFORE any append. The seed file is "# alpha\\n\\n## Open\\n\\n## Done\\n\\n".
        seed = "# alpha\\n\\n## Open\\n\\n## Done\\n\\n"
        file_hash_before = J.sha256_text(seed)
        bl = pathlib.Path({sb!r}) / 'alpha' / 'knowledge' / 'backlog.md'
        file_hash_after = J.sha256_text(bl.read_text(encoding='utf-8'))
        sid = J._read_current_segment_id('alpha')

        # Load replay_chain from kb-execute-next
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader('exec_next', '__HOME__/knowledge/bin/kb-execute-next')
        spec = importlib.util.spec_from_loader('exec_next', loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)

        ok, diag = mod.replay_chain('alpha', file_hash_before, file_hash_after, sid, 0)
        print(json.dumps({{'ok': ok, 'diag': diag}}))
    """)
    rc, out, err = run_in_sandbox(sb, code)
    assert rc == 0, f"subprocess failed: {err}"
    result = json.loads(out.strip())
    assert_(not result["ok"], f"chain replay detected break (diag={result['diag']})")
    assert_("chain break" in result["diag"] or "final chain mismatch" in result["diag"],
            f"diagnostic mentions break (got: {result['diag']})")
    shutil.rmtree(sb)


def main():
    f_cr_7()
    f_cr_8()
    print("\nF-CR-7 + F-CR-8 PASSED")


if __name__ == "__main__":
    main()
