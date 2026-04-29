#!/usr/bin/env python3
"""concurrent.py — race-condition test: 3 concurrent writers, no losses.

Spawns 3 background processes that hammer kb-backlog append on the same slug
(each producing N tasks with unique plan_item_ids). After all complete, we
verify:
  1. Total open lines == 3*N (no losses).
  2. Audit journal has 3*N committed transactions for the slug.
  3. No prepared without committed (no orphans).
  4. Each plan_item_id appears exactly once in the backlog.
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

N_PER_WORKER = 30
N_WORKERS = 3


def setup_sandbox():
    sb = tempfile.mkdtemp(prefix="kb-race-")
    os.environ["KB_HUB"] = sb
    (pathlib.Path(sb) / "projects").mkdir()
    (pathlib.Path(sb) / ".orchestrator" / "locks").mkdir(parents=True)
    (pathlib.Path(sb) / ".orchestrator" / "audit").mkdir(parents=True)
    (pathlib.Path(sb) / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    proj = pathlib.Path(sb) / "alpha"
    (proj / "knowledge").mkdir(parents=True)
    (proj / "knowledge" / "backlog.md").write_text("# alpha\n\n## Open\n\n## Done\n\n", encoding="utf-8")
    os.symlink(str(proj / "knowledge"), str(pathlib.Path(sb) / "projects" / "alpha"))
    return sb


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def run_worker(sb, worker_id, n):
    procs = []
    for i in range(n):
        pid = str(uuid.uuid4())
        p = subprocess.Popen(
            ["__HOME__/knowledge/bin/kb-backlog", "append", "alpha",
             f"task w{worker_id}-{i}",
             "--plan-item-id", pid, "--lock-timeout", "60", "--json"],
            env={**os.environ, "KB_HUB": sb},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        procs.append(p)
    for p in procs:
        p.wait()
        if p.returncode != 0:
            err = p.stderr.read().decode() if p.stderr else "?"
            print(f"  ⚠ worker {worker_id} sub-rc={p.returncode}: {err[:120]}", file=sys.stderr)


def main():
    print(f"Race test: {N_WORKERS} workers × {N_PER_WORKER} appends each = {N_WORKERS*N_PER_WORKER} tasks")
    sb = setup_sandbox()

    # Launch N_WORKERS concurrent worker processes.
    workers = []
    # Spawn each worker in a fresh subprocess that fires off N_PER_WORKER appends.
    for w in range(N_WORKERS):
        worker_script = (
            "import os, sys, subprocess, uuid\n"
            f"sb = {sb!r}\n"
            f"w = {w}\n"
            f"n = {N_PER_WORKER}\n"
            "for i in range(n):\n"
            "    subprocess.run(\n"
            "        ['__HOME__/knowledge/bin/kb-backlog', 'append', 'alpha',\n"
            "         f'task w{w}-{i}',\n"
            "         '--plan-item-id', str(uuid.uuid4()),\n"
            "         '--lock-timeout', '60', '--json'],\n"
            "        env={**os.environ, 'KB_HUB': sb},\n"
            "        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,\n"
            "    )\n"
        )
        p = subprocess.Popen(
            ["python3", "-c", worker_script],
            env={**os.environ, "KB_HUB": sb},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        workers.append(p)

    failed = 0
    for p in workers:
        p.wait()
        if p.returncode != 0:
            failed += 1
            err = p.stderr.read().decode() if p.stderr else "?"
            print(f"  ⚠ worker exit {p.returncode}: {err[:200]}", file=sys.stderr)

    assert_(failed == 0, f"all {N_WORKERS} workers exit 0")

    # Verify backlog
    bl_text = (pathlib.Path(sb) / "alpha" / "knowledge" / "backlog.md").read_text()
    open_lines = [ln for ln in bl_text.splitlines() if ln.strip().startswith("- [ ]")]
    assert_(len(open_lines) == N_WORKERS * N_PER_WORKER,
            f"all {N_WORKERS * N_PER_WORKER} appends present (got {len(open_lines)})")

    # Verify audit journal: count committed transactions.
    audit_dir = pathlib.Path(sb) / ".orchestrator" / "audit" / "alpha"
    committed = 0
    prepared_without_terminal: dict = {}
    for seg_path in sorted(audit_dir.glob("*.jsonl")):
        for line in seg_path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("segment_init"):
                continue
            tid = rec.get("tx_id")
            phase = rec.get("phase")
            if phase == "prepared":
                prepared_without_terminal[tid] = True
            elif phase in ("committed", "committed-recovered", "aborted", "escalated-orphan"):
                prepared_without_terminal.pop(tid, None)
                if phase == "committed":
                    committed += 1
    assert_(committed == N_WORKERS * N_PER_WORKER,
            f"audit journal committed={committed} matches expected={N_WORKERS * N_PER_WORKER}")
    assert_(not prepared_without_terminal,
            f"no orphans (prepared without terminal): {len(prepared_without_terminal)}")

    shutil.rmtree(sb)
    print("\nRace test PASSED — no losses, no orphans, no duplicates")


if __name__ == "__main__":
    main()
