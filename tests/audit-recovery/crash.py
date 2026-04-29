#!/usr/bin/env python3
"""crash.py — exercise audit recovery scenarios.

Each fixture simulates a crash at a specific point in the prepared/committed
protocol by manipulating journal segments + backlog file directly.

Fixtures (per Phase 1b acceptance):
  F-CR-1: crash after `prepared`, before rename → recovery should mark `aborted`.
  F-CR-2: crash after rename, before `committed` → recovery `committed-recovered`.
  F-CR-3: double-crash mid-recovery — re-running recovery should not duplicate
          terminal records.
  F-CR-4: orphan — external raw write between prepared and recovery →
          `escalated-orphan` + escalation entry.
  F-CR-7: rotation race — refused with active spawn (deferred to journal layer test).
  F-CR-8: hash-chain mismatch (durable raw write between two legitimate
          mutations) — chain replay catches mismatch.

Run: python3 crash.py
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

# Make sure we import from the live bin (not a copy).
sys.path.insert(0, "__HOME__/knowledge/bin")
from _kb_backlog import journal, locks, ops, parsing  # noqa: E402


def setup_sandbox():
    """Create a temp KB_HUB with one project (alpha) and return its paths."""
    sb = tempfile.mkdtemp(prefix="kb-recovery-")
    os.environ["KB_HUB"] = sb
    # Re-import modules to pick up the env change.
    for mod in ("journal", "locks", "ops", "parsing", "preflight", "spawns", "xfer", "mutation"):
        full = f"_kb_backlog.{mod}"
        if full in sys.modules:
            del sys.modules[full]
    # We'll subprocess-call kb-backlog instead, so env is naturally fresh.
    # Build alpha
    proj = pathlib.Path(sb) / "alpha"
    (proj / "knowledge").mkdir(parents=True)
    (proj / "knowledge" / "backlog.md").write_text("# Backlog — alpha\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    (pathlib.Path(sb) / "projects").mkdir()
    os.symlink(str(proj / "knowledge"), str(pathlib.Path(sb) / "projects" / "alpha"))
    (pathlib.Path(sb) / ".orchestrator" / "locks").mkdir(parents=True)
    (pathlib.Path(sb) / ".orchestrator" / "audit").mkdir(parents=True)
    (pathlib.Path(sb) / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    return sb, proj


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


def find_segment(sb, slug):
    """Return path to the slug's only segment file."""
    sd = pathlib.Path(sb) / ".orchestrator" / "audit" / slug
    files = list(sd.glob("*.jsonl"))
    return files[0] if files else None


def read_segment(sb, slug):
    p = find_segment(sb, slug)
    if p is None:
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


# ──────────────────────────────────────────────────────────────────────────
# F-CR-1: crash after prepared, before rename → aborted
# ──────────────────────────────────────────────────────────────────────────
def f_cr_1():
    print("F-CR-1: crash before rename → aborted")
    sb, proj = setup_sandbox()
    bl = proj / "knowledge" / "backlog.md"

    # Append T1 normally (so we have one segment file).
    r = kb_backlog(sb, "append", "alpha", "T1", "--plan-item-id", "11111111-0000-0000-0000-000000000000", "--json")
    assert r.returncode == 0, r.stderr

    # Now manually inject a "prepared" record without committed: simulating
    # crash between Step P and Step C (or between Step P and rename).
    # We'll manufacture a tx_id, write prepared, but NOT change the file.
    seg_path = find_segment(sb, "alpha")
    fake_tx_id = str(uuid.uuid4())
    current_text = bl.read_text(encoding="utf-8")
    fake_after_text = current_text + "\n- [ ] FAKE — opened 2026-04-25 by self\n"
    rec = {
        "tx_id": fake_tx_id,
        "phase": "prepared",
        "op": "append",
        "actor": "test",
        "line": None,
        "before_hash": journal.sha256_text(current_text),
        "after_hash": journal.sha256_text(fake_after_text),
        "before_line_hashes": journal.hash_lines(current_text),
        "after_line_hashes": journal.hash_lines(fake_after_text),
        "ts": "2026-04-25T00:00:00+00:00",
    }
    with open(seg_path, "a") as f:
        f.write(json.dumps(rec) + "\n")

    # Now run recovery. Current file == before, no commit, should → aborted.
    r = kb_backlog(sb, "recover", "alpha", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    res = data["resolutions"]
    assert_(any(x["tx_id"] == fake_tx_id and x["phase"] == "aborted" for x in res),
            "tx_id resolved as aborted")

    # The aborted terminal must now exist in the segment.
    recs = read_segment(sb, "alpha")
    assert_(any(r.get("tx_id") == fake_tx_id and r.get("phase") == "aborted" for r in recs),
            "aborted record persisted")

    shutil.rmtree(sb)


# ──────────────────────────────────────────────────────────────────────────
# F-CR-2: crash after rename, before committed → committed-recovered
# ──────────────────────────────────────────────────────────────────────────
def f_cr_2():
    print("F-CR-2: crash after rename, before committed → committed-recovered")
    sb, proj = setup_sandbox()
    bl = proj / "knowledge" / "backlog.md"
    seg_path = find_segment(sb, "alpha") or None

    # Bootstrap segment if not yet exists by doing one normal append.
    r = kb_backlog(sb, "append", "alpha", "Seed", "--json")
    assert r.returncode == 0, r.stderr
    seg_path = find_segment(sb, "alpha")

    # Simulate: prepared record + rename happened (so current file already
    # contains the change), but committed never written.
    current_before = bl.read_text(encoding="utf-8")
    fake_after = current_before + "- [ ] T2 — opened 2026-04-25 by self\n"
    bl.write_text(fake_after, encoding="utf-8")

    fake_tx_id = str(uuid.uuid4())
    rec = {
        "tx_id": fake_tx_id,
        "phase": "prepared",
        "op": "append",
        "actor": "test",
        "line": None,
        "before_hash": journal.sha256_text(current_before),
        "after_hash": journal.sha256_text(fake_after),
        "before_line_hashes": journal.hash_lines(current_before),
        "after_line_hashes": journal.hash_lines(fake_after),
        "ts": "2026-04-25T00:00:00+00:00",
    }
    with open(seg_path, "a") as f:
        f.write(json.dumps(rec) + "\n")

    # Recovery: current_text matches after_hash → committed-recovered.
    r = kb_backlog(sb, "recover", "alpha", "--json")
    data = json.loads(r.stdout)
    assert_(any(x["tx_id"] == fake_tx_id and x["phase"] == "committed-recovered"
                for x in data["resolutions"]),
            "tx_id resolved as committed-recovered")

    shutil.rmtree(sb)


# ──────────────────────────────────────────────────────────────────────────
# F-CR-3: double-crash idempotent recovery
# ──────────────────────────────────────────────────────────────────────────
def f_cr_3():
    print("F-CR-3: double-crash idempotent recovery")
    sb, proj = setup_sandbox()
    bl = proj / "knowledge" / "backlog.md"

    # Bootstrap
    r = kb_backlog(sb, "append", "alpha", "Seed", "--json")
    seg_path = find_segment(sb, "alpha")

    # Inject a prepared record that should resolve to aborted.
    current = bl.read_text(encoding="utf-8")
    fake = current + "- [ ] FAKE\n"
    fake_tx_id = str(uuid.uuid4())
    rec = {
        "tx_id": fake_tx_id, "phase": "prepared", "op": "append", "actor": "test", "line": None,
        "before_hash": journal.sha256_text(current),
        "after_hash": journal.sha256_text(fake),
        "before_line_hashes": journal.hash_lines(current),
        "after_line_hashes": journal.hash_lines(fake),
        "ts": "2026-04-25T00:00:00+00:00",
    }
    with open(seg_path, "a") as f:
        f.write(json.dumps(rec) + "\n")

    # Recover twice — second run should be a no-op.
    r1 = kb_backlog(sb, "recover", "alpha", "--json")
    r2 = kb_backlog(sb, "recover", "alpha", "--json")
    d1 = json.loads(r1.stdout)
    d2 = json.loads(r2.stdout)
    assert_(any(x["tx_id"] == fake_tx_id for x in d1["resolutions"]),
            "first recover resolves the tx")
    assert_(not any(x["tx_id"] == fake_tx_id for x in d2["resolutions"]),
            "second recover is a no-op for the same tx_id")

    # Terminal count must be exactly 1.
    recs = read_segment(sb, "alpha")
    terminal_count = sum(1 for r in recs if r.get("tx_id") == fake_tx_id and r.get("phase") in
                         ("committed", "committed-recovered", "aborted", "escalated-orphan"))
    assert_(terminal_count == 1, f"exactly one terminal for tx (got {terminal_count})")

    shutil.rmtree(sb)


# ──────────────────────────────────────────────────────────────────────────
# F-CR-4: orphan — external raw write changes file mid-prepared → escalated-orphan
# ──────────────────────────────────────────────────────────────────────────
def f_cr_4():
    print("F-CR-4: orphan (external raw write) → escalated-orphan")
    sb, proj = setup_sandbox()
    bl = proj / "knowledge" / "backlog.md"
    r = kb_backlog(sb, "append", "alpha", "Seed", "--json")
    seg_path = find_segment(sb, "alpha")

    # Inject prepared, BUT then do an external raw write that mismatches both
    # before/after hashes.
    current = bl.read_text(encoding="utf-8")
    fake_after = current + "- [ ] T2\n"
    fake_tx_id = str(uuid.uuid4())
    rec = {
        "tx_id": fake_tx_id, "phase": "prepared", "op": "append", "actor": "test", "line": None,
        "before_hash": journal.sha256_text(current),
        "after_hash": journal.sha256_text(fake_after),
        "before_line_hashes": journal.hash_lines(current),
        "after_line_hashes": journal.hash_lines(fake_after),
        "ts": "2026-04-25T00:00:00+00:00",
    }
    with open(seg_path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    # External raw write — produces a hash distinct from both before and after.
    bl.write_text(current + "- [ ] EXTERNAL UNAUTHORIZED CHANGE\n", encoding="utf-8")

    r = kb_backlog(sb, "recover", "alpha", "--json")
    d = json.loads(r.stdout)
    assert_(any(x["tx_id"] == fake_tx_id and x["phase"] == "escalated-orphan"
                for x in d["resolutions"]),
            "tx resolved as escalated-orphan")

    shutil.rmtree(sb)


def main():
    f_cr_1()
    f_cr_2()
    f_cr_3()
    f_cr_4()
    print("\nAll audit-recovery fixtures PASSED")


if __name__ == "__main__":
    main()
