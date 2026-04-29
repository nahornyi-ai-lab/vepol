#!/usr/bin/env python3
"""crash.py — xfer crash recovery fixtures (F-CR-5, F-CR-6).

F-CR-5: crash X2→X3 (src tombstoned, dst missing).
        Recovery acquires full lock stack, sees src_hash == src_after,
        dst_hash == dst_before, performs whole-file rollback from
        src_before_bytes_b64, writes xfer-aborted.

F-CR-6: crash X1→X2 (xfer-prepared written, neither file changed).
        Recovery sees src_hash == src_before, dst_hash == dst_before,
        writes xfer-aborted (no work to undo).

We simulate crashes by manipulating the _xfer.jsonl segment + slug audit
journals + backlog files directly, then triggering recovery via the next
mutation on the affected slug (which runs `_resolve_dangling_xfers_for_slug`).
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

sys.path.insert(0, "__HOME__/knowledge/bin")
from _kb_backlog import journal  # noqa: E402


def setup_sandbox():
    sb = tempfile.mkdtemp(prefix="kb-xcrash-")
    os.environ["KB_HUB"] = sb
    (pathlib.Path(sb) / "projects").mkdir()
    (pathlib.Path(sb) / ".orchestrator" / "locks").mkdir(parents=True)
    (pathlib.Path(sb) / ".orchestrator" / "audit").mkdir(parents=True)
    (pathlib.Path(sb) / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    for slug in ("alpha", "beta"):
        proj = pathlib.Path(sb) / slug
        (proj / "knowledge").mkdir(parents=True)
        (proj / "knowledge" / "backlog.md").write_text(
            f"# {slug}\n\n## Open\n\n- [ ] existing task — opened 2026-04-25 by self\n\n## Done\n\n",
            encoding="utf-8",
        )
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


def write_xfer_segment(sb, records):
    """Write records into _xfer journal."""
    sd = pathlib.Path(sb) / ".orchestrator" / "audit" / "_xfer"
    sd.mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    p = sd / f"{sid}.jsonl"
    init = {"segment_init": True, "segment_id": sid, "prev_segment_id": None,
            "started_at": "2026-04-25T00:00:00+00:00"}
    with open(p, "w") as f:
        f.write(json.dumps(init) + "\n")
        for r in records:
            f.write(json.dumps(r) + "\n")
    pointer = pathlib.Path(sb) / ".orchestrator" / "audit" / "_xfer-current.txt"
    pointer.write_text(sid)


def read_xfer_records(sb):
    out = []
    sd = pathlib.Path(sb) / ".orchestrator" / "audit" / "_xfer"
    for p in sorted(sd.glob("*.jsonl")):
        for line in p.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if not rec.get("segment_init"):
                    out.append(rec)
    return out


import base64


def _b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def f_cr_6():
    """X1→X2 crash: xfer-prepared written, no file changes."""
    print("F-CR-6: crash X1→X2 (no work persisted) → xfer-aborted")
    sb = setup_sandbox()
    src = pathlib.Path(sb) / "alpha" / "knowledge" / "backlog.md"
    dst = pathlib.Path(sb) / "beta" / "knowledge" / "backlog.md"
    src_before = src.read_text(encoding="utf-8")
    dst_before = dst.read_text(encoding="utf-8")
    src_after = src_before  # placeholder — won't be applied since X2 didn't run

    xfer_id = str(uuid.uuid4())
    write_xfer_segment(sb, [
        {
            "xfer_id": xfer_id, "phase": "xfer-prepared",
            "plan_item_id": "00000000-0000-0000-0000-000000000000",
            "src_slug": "alpha", "dst_slug": "beta",
            "src_before_hash": journal.sha256_text(src_before),
            "src_after_hash": journal.sha256_text(src_before + "tombstone-marker"),
            "dst_before_hash": journal.sha256_text(dst_before),
            "dst_after_hash": journal.sha256_text(dst_before + "appended"),
            "src_before_bytes_b64": _b64(src_before),
            "src_line_b64": _b64("- [ ] existing task — opened 2026-04-25 by self"),
            "src_after_line_b64": _b64("- [~] tombstone"),
            "dst_line_b64": _b64("- [ ] new task"),
            "src_lineno": 4,
            "ts": "2026-04-25T00:00:00+00:00",
        },
    ])

    # Trigger recovery via any mutation on alpha.
    r = kb(sb, "append", "alpha", "trigger recovery", "--json")
    assert_(r.returncode == 0, f"append on alpha succeeded after dangling xfer (rc={r.returncode}, stderr={r.stderr})")

    # Verify xfer terminal == xfer-aborted with reason "no work persisted"
    recs = read_xfer_records(sb)
    terminals = [r for r in recs if r.get("xfer_id") == xfer_id and r.get("phase") in
                 ("xfer-committed", "xfer-committed-recovered", "xfer-aborted", "xfer-escalated-orphan")]
    assert_(len(terminals) == 1, f"exactly one xfer terminal (got {len(terminals)})")
    assert_(terminals[0]["phase"] == "xfer-aborted", f"phase=xfer-aborted (got {terminals[0]['phase']})")
    shutil.rmtree(sb)


def f_cr_5():
    """X2→X3 crash: src tombstoned, dst missing → whole-file rollback."""
    print("F-CR-5: crash X2→X3 → whole-file rollback + xfer-aborted")
    sb = setup_sandbox()
    src = pathlib.Path(sb) / "alpha" / "knowledge" / "backlog.md"
    dst = pathlib.Path(sb) / "beta" / "knowledge" / "backlog.md"

    src_before = src.read_text(encoding="utf-8")
    dst_before = dst.read_text(encoding="utf-8")
    # Simulate src already tombstoned (X2 committed).
    src_after_line_text = "- [~] existing task — opened 2026-04-25 by self — tombstoned-by-xfer-XXX: 2026-04-25"
    src_after_text = src_before.replace(
        "- [ ] existing task — opened 2026-04-25 by self",
        src_after_line_text,
    )
    src.write_text(src_after_text, encoding="utf-8")

    xfer_id = str(uuid.uuid4())
    src_after_line_real = src_after_line_text.replace("XXX", xfer_id)
    src_after_text = src_before.replace(
        "- [ ] existing task — opened 2026-04-25 by self",
        src_after_line_real,
    )
    src.write_text(src_after_text, encoding="utf-8")

    # Need to also have a per-slug audit segment with X2 prepared+committed
    # entries so per-file recovery doesn't think alpha's transaction is dangling.
    # Easiest: do the per-file mutation through kb-backlog tombstone, then
    # add the X1 xfer-prepared coordinator entry (with X4 missing). The
    # test mimics "everything completed except X3+X4".

    # Reset src to before, do a real tombstone via kb-backlog, then reset
    # the visible state so we can simulate proper "X2 committed + X3 missing".
    # Actually simpler: just write the X1 entry pointing to a state where
    # src is in src_after (by manual write above), and run recovery.
    # The per-file segment for alpha doesn't have the X2 transaction, but
    # journal.recover_pending only cares about prepared without terminals,
    # not "which transactions exist". The coordinator recovery only
    # verifies hashes against the file content. So we can skip alpha's
    # per-file journal entries.

    write_xfer_segment(sb, [
        {
            "xfer_id": xfer_id, "phase": "xfer-prepared",
            "plan_item_id": "00000000-0000-0000-0000-000000000000",
            "src_slug": "alpha", "dst_slug": "beta",
            "src_before_hash": journal.sha256_text(src_before),
            "src_after_hash": journal.sha256_text(src_after_text),
            "dst_before_hash": journal.sha256_text(dst_before),
            "dst_after_hash": journal.sha256_text(dst_before + "appended"),
            "src_before_bytes_b64": _b64(src_before),
            "src_line_b64": _b64("- [ ] existing task — opened 2026-04-25 by self"),
            "src_after_line_b64": _b64(src_after_line_real),
            "dst_line_b64": _b64("- [ ] new task"),
            "src_lineno": 4,
            "ts": "2026-04-25T00:00:00+00:00",
        },
    ])

    # Trigger recovery via mutation on alpha.
    r = kb(sb, "append", "alpha", "trigger recovery", "--json")
    assert_(r.returncode == 0, f"alpha append succeeded after recovery (rc={r.returncode}, stderr={r.stderr})")

    # Verify terminal == xfer-aborted with rollback reason
    recs = read_xfer_records(sb)
    terminals = [r for r in recs if r.get("xfer_id") == xfer_id and r.get("phase") in
                 ("xfer-committed", "xfer-committed-recovered", "xfer-aborted", "xfer-escalated-orphan")]
    assert_(len(terminals) == 1, f"one terminal (got {len(terminals)})")
    assert_(terminals[0]["phase"] == "xfer-aborted", f"xfer-aborted (got {terminals[0]['phase']})")
    assert_("rolled back" in terminals[0].get("reason", ""), "rollback reason recorded")

    # Verify src is restored (the fresh append after rollback may have added
    # one new line, but the original `[ ] existing task` line should be back
    # since rollback restored src_before, then the trigger append added one
    # new task to that restored state).
    src_text_now = src.read_text(encoding="utf-8")
    assert_("- [ ] existing task — opened 2026-04-25 by self" in src_text_now,
            "original src line restored")
    assert_("[~]" not in src_text_now or "tombstoned-by-xfer" not in src_text_now,
            "tombstone marker removed")
    shutil.rmtree(sb)


def main():
    f_cr_6()
    f_cr_5()
    print("\nAll xfer crash fixtures PASSED")


if __name__ == "__main__":
    main()
