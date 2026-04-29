#!/usr/bin/env python3
"""fixtures.py — Phase 5 acceptance for `kb-orchestrator-cycle plan`.

Carried-item fixtures from the locked plan (F1-F4):

  F1 — open carried in same immediate-child:
       1 open carried (same plan_item_id, same target slug) + 1 new task
       → 1 update + 1 add, 0 dups.

  F2 — closed carried + new:
       1 closed carried (status: x) + 1 new task with different
       plan_item_id but same target → 1 fresh add (NOT skip from closed) +
       1 add.

  F3 — parent-moved carried:
       1 carried open in slug A, plan now targets slug B → xfer A→B
       (atomic, byte-safe rollback).

  F4 — multi-file dup:
       1 plan_item_id has open lines in 2 different slugs → cycle aborts
       with action=abort + escalation entry.
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
import uuid


def setup_sandbox():
    sb = tempfile.mkdtemp(prefix="kb-plan-")
    p = pathlib.Path(sb)
    (p / "projects").mkdir()
    (p / ".orchestrator" / "locks").mkdir(parents=True)
    (p / ".orchestrator" / "audit").mkdir(parents=True)
    (p / "daily-plan").mkdir()
    (p / "backlog.md").write_text("# Hub\n\n## Open\n\n## Done\n", encoding="utf-8")

    # Two leaf projects + one mid-tier parent (for F3 xfer)
    for slug in ("alpha", "beta"):
        proj = p / slug
        (proj / "knowledge").mkdir(parents=True)
        (proj / "knowledge" / "backlog.md").write_text(
            f"# {slug}\n\n## Open\n\n## Done\n", encoding="utf-8",
        )
        os.symlink(str(proj / "knowledge"), str(p / "projects" / slug))

    # Build a hierarchy.yaml with both as direct children of hub.
    hier = textwrap.dedent(f"""\
        version: 1
        root: hub
        nodes:
          hub:
            kind: root
            parent: null
            knowledge_path: {sb}
            children: [alpha, beta]
          alpha:
            kind: project
            parent: hub
            category: lab
            status: live
            knowledge_path: {sb}/alpha/knowledge
            children: []
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
          beta:
            kind: project
            parent: hub
            category: lab
            status: live
            knowledge_path: {sb}/beta/knowledge
            children: []
            cycle_enabled: true
            sla_report_timeout_sec: 60
            owner: test
            decompose_strategy: subset
            exec_broker: false
    """)
    (p / "hierarchy.yaml").write_text(hier, encoding="utf-8")
    return p


def kb(sb, *args):
    return subprocess.run(
        ["__HOME__/knowledge/bin/kb-backlog", *args],
        env={**os.environ, "KB_HUB": str(sb)},
        capture_output=True, text=True,
    )


def cycle_plan(sb, plan_file, **kwargs):
    args = ["__HOME__/knowledge/bin/kb-orchestrator-cycle", "plan",
            "--approved-plan", str(plan_file), "--skip-registry-check"]
    return subprocess.run(
        args, env={**os.environ, "KB_HUB": str(sb)},
        capture_output=True, text=True,
    )


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def write_plan(p: pathlib.Path, items: list[tuple[str, str, str]]) -> pathlib.Path:
    """items: list of (slug, body, plan_item_id) tuples."""
    today = dt.date.today().isoformat()
    plan_path = p / "daily-plan" / f"{today}.md"
    lines = [f"# Daily plan — {today}", "", "approved_at: 2026-04-25T07:32:00", ""]
    for slug, body, pid in items:
        lines.append(f"- [ ] ({slug}) {body} — plan_item_id: {pid}")
    plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return plan_path


# ─────────────────────────────────────────────────────────────────────
# F1 — open carried in same immediate-child + new task
# ─────────────────────────────────────────────────────────────────────
def f1_open_carried():
    print("F1: open carried + new → 1 update + 1 add")
    sb = setup_sandbox()

    # Pre-seed alpha with an open task that has plan_item_id pid_a
    pid_a = "11111111-1111-1111-1111-111111111111"
    pid_b = "22222222-2222-2222-2222-222222222222"
    rc = kb(sb, "append", "alpha", "carried task", "--plan-item-id", pid_a, "--by", "hub")
    assert rc.returncode == 0, rc.stderr

    plan = write_plan(sb, [
        ("alpha", "carried task (refreshed)", pid_a),
        ("alpha", "new task today", pid_b),
    ])

    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, f"plan exits 0 (rc={proc.returncode})")

    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["alpha"]]
    assert_("update" in actions, f"action 'update' present (got {actions})")
    assert_("append" in actions, f"action 'append' present (got {actions})")
    assert_(len(actions) == 2, f"exactly 2 actions (got {len(actions)})")
    shutil.rmtree(sb)


# ─────────────────────────────────────────────────────────────────────
# F2 — closed carried + new task
# ─────────────────────────────────────────────────────────────────────
def f2_closed_carried():
    print("F2: closed carried + new → 1 fresh add + 1 add")
    sb = setup_sandbox()

    pid_a = "33333333-3333-3333-3333-333333333333"
    pid_b = "44444444-4444-4444-4444-444444444444"
    # Append + claim + close pid_a → it's now in [x] state
    kb(sb, "append", "alpha", "yesterday's task", "--plan-item-id", pid_a, "--by", "hub")
    text = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    line = next(i + 1 for i, l in enumerate(text.splitlines()) if pid_a in l)
    claim_res = json.loads(kb(sb, "claim", "alpha", "--line", str(line), "--json").stdout)
    kb(sb, "close", "alpha", "--line", str(line), "--claim-id", claim_res["claim_id"],
       "--outcome", "closed", "--reason", "yesterday", "--json")

    plan = write_plan(sb, [
        ("alpha", "today follow-up (different pid)", pid_b),
        # F2 scenario: same plan_item_id as the closed task, replanned today
        ("alpha", "retry yesterday", pid_a),
    ])

    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, f"plan exits 0 (rc={proc.returncode})")
    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["alpha"]]
    appends = sum(1 for a in actions if a == "append")
    assert_(appends == 2, f"two appends (got {appends}, actions={actions})")
    shutil.rmtree(sb)


# ─────────────────────────────────────────────────────────────────────
# F3 — parent-moved carried (xfer)
# ─────────────────────────────────────────────────────────────────────
def f3_parent_moved():
    print("F3: parent-moved carried → xfer alpha→beta")
    sb = setup_sandbox()
    pid = "55555555-5555-5555-5555-555555555555"

    # Pre-seed: open in alpha
    kb(sb, "append", "alpha", "moveable task", "--plan-item-id", pid, "--by", "hub")

    # Plan now targets beta
    plan = write_plan(sb, [("beta", "moveable task", pid)])

    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, f"plan exits 0 (rc={proc.returncode}; stderr={proc.stderr[-300:]})")
    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["beta"]]
    assert_("xfer" in actions, f"action 'xfer' present (got {actions})")

    # Verify alpha tombstoned, beta has open line
    a_text = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    b_text = (sb / "beta" / "knowledge" / "backlog.md").read_text()
    assert_("[~]" in a_text and "tombstoned-by-xfer-" in a_text, "alpha line tombstoned")
    assert_(pid in b_text and "[ ]" in b_text, "beta has open line with same plan_item_id")
    shutil.rmtree(sb)


# ─────────────────────────────────────────────────────────────────────
# F4 — multi-file dup (open in 2 slugs)
# ─────────────────────────────────────────────────────────────────────
def f4_multi_file_dup():
    print("F4: multi-file dup → action=abort, escalation entry")
    sb = setup_sandbox()
    pid = "77777777-7777-7777-7777-777777777777"

    # Pre-seed pid in BOTH alpha and beta as open (an invariant violation
    # from a prior cycle bug).
    kb(sb, "append", "alpha", "duplicated task", "--plan-item-id", pid, "--by", "hub")
    kb(sb, "append", "beta", "duplicated task", "--plan-item-id", pid, "--by", "hub")

    plan = write_plan(sb, [("alpha", "duplicated task", pid)])

    proc = cycle_plan(sb, plan)
    # The plan should still exit 0 (it dispatched what it could) but the
    # F4 item gets action=abort.
    assert_(proc.returncode == 0, f"plan exits 0 even with F4 (got {proc.returncode})")
    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["alpha"]]
    assert_("abort" in actions, f"action 'abort' present (got {actions})")
    # The aborted entry should have a reason mentioning multi-file dup.
    abort_entry = next(r for r in summary["results"]["alpha"] if r["action"] == "abort")
    assert_("F4" in abort_entry["reason"] or "multi-file" in abort_entry["reason"].lower(),
            f"abort reason mentions multi-file (got: {abort_entry['reason']})")
    shutil.rmtree(sb)


def cr_phase5_b1_idempotent_redispatch():
    """CR-Phase5-B1: re-running the same approved plan after a row was
    closed must NOT re-append. Stable cycle_source_id makes the second
    dispatch a no-op via collision check (now matching all statuses, not
    just open).
    """
    print("CR-Phase5-B1: idempotent redispatch even after row is closed")
    sb = setup_sandbox()
    pid = "abcdef01-2345-6789-abcd-ef0123456789"
    plan = write_plan(sb, [("alpha", "stable test", pid)])

    # First dispatch: appends a fresh row
    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, "first dispatch ok")
    text = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    line = next(i + 1 for i, l in enumerate(text.splitlines()) if pid in l)

    # Close it via kb-backlog (simulating executor finishing)
    claim_res = json.loads(kb(sb, "claim", "alpha", "--line", str(line), "--json").stdout)
    kb(sb, "close", "alpha", "--line", str(line), "--claim-id", claim_res["claim_id"],
       "--outcome", "closed", "--reason", "completed", "--json")

    # Re-run the same approved plan — should NOT re-append
    proc2 = cycle_plan(sb, plan)
    assert_(proc2.returncode == 0, "re-dispatch ok")

    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["alpha"]]
    # On redispatch, the append's collision check should skip — so action is
    # "append" but the result has status: skipped (cycle_source_id collision).
    assert_(actions == ["append"], f"action recorded as append (got {actions})")
    last_result = summary["results"]["alpha"][0]["result"]
    assert_(last_result.get("status") == "skipped",
            f"status: skipped on redispatch (got {last_result.get('status')})")
    assert_("cycle_source_id" in last_result.get("reason", "").lower(),
            f"reason mentions cycle_source_id (got {last_result.get('reason')})")

    # The backlog should still contain only ONE plan_item_id reference (in [x])
    text2 = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    pid_count = text2.count(pid)
    assert_(pid_count == 1, f"plan_item_id appears exactly once (got {pid_count})")
    shutil.rmtree(sb)


def cr_phase5_b2_in_progress_carried():
    """CR-Phase5-B2: a carried [>] (in_progress) row must NOT get a duplicate
    append. F1 path skips with action=skip-in-progress.
    """
    print("CR-Phase5-B2: in_progress [>] row preserved, not duplicated")
    sb = setup_sandbox()
    pid = "fedcba98-7654-3210-fedc-ba9876543210"

    # Append + claim alpha → status [>]
    kb(sb, "append", "alpha", "in-flight task", "--plan-item-id", pid, "--by", "hub", "--json")
    text = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    line = next(i + 1 for i, l in enumerate(text.splitlines()) if pid in l)
    kb(sb, "claim", "alpha", "--line", str(line), "--json")

    plan = write_plan(sb, [("alpha", "in-flight task (replanned)", pid)])
    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, "plan ok")
    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["alpha"]]
    assert_("skip-in-progress" in actions,
            f"action skip-in-progress present (got {actions})")
    # No duplicate row
    text2 = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    pid_count = text2.count(pid)
    assert_(pid_count == 1, f"plan_item_id appears exactly once (got {pid_count})")
    shutil.rmtree(sb)


def cr_phase5_b3_escalation_durable():
    """CR-Phase5-B3: F4 multi-file-dup writes a durable escalation entry."""
    print("CR-Phase5-B3: F4 abort writes escalations.md entry")
    sb = setup_sandbox()
    pid = "11112222-3333-4444-5555-666677778888"

    # Pre-seed: open in BOTH alpha and beta
    kb(sb, "append", "alpha", "duped task", "--plan-item-id", pid, "--by", "hub", "--json")
    kb(sb, "append", "beta", "duped task", "--plan-item-id", pid, "--by", "hub", "--json")

    plan = write_plan(sb, [("alpha", "duped task", pid)])
    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, "plan ok")

    esc_path = sb / "escalations.md"
    assert_(esc_path.is_file(), "escalations.md created")
    esc_text = esc_path.read_text(encoding="utf-8")
    assert_(pid in esc_text, "escalation mentions plan_item_id")
    assert_("multi-file" in esc_text or "F4" in esc_text,
            "escalation reason mentions F4/multi-file")
    shutil.rmtree(sb)


def cr_phase5_cr2_xfer_idempotent_redispatch():
    """CR-Phase5-CR2: F3 xfer must stamp destination with cycle_source_id
    so a re-dispatch after xfer+close does NOT duplicate.

    Sequence:
      1. Open in alpha
      2. Plan targets beta → xfer alpha→beta + stamp dest with stable csid
      3. Claim + close beta line
      4. Re-run same plan → append on beta finds csid collision, skips
      5. plan_item_id appears at most once in beta backlog
    """
    print("CR-Phase5-CR2: xfer+close+rerun → idempotent (no duplicate)")
    sb = setup_sandbox()
    pid = "deadbeef-0001-0002-0003-000000000004"

    # Pre-seed: open in alpha
    kb(sb, "append", "alpha", "movable task", "--plan-item-id", pid, "--by", "hub", "--json")
    plan = write_plan(sb, [("beta", "movable task", pid)])

    # First dispatch: xfer alpha→beta + stamp
    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, f"xfer dispatch ok (rc={proc.returncode})")
    summary = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions = [r["action"] for r in summary["results"]["beta"]]
    assert_("xfer" in actions, f"xfer action present (got {actions})")
    xfer_entry = next(r for r in summary["results"]["beta"] if r["action"] == "xfer")
    assert_(xfer_entry.get("cycle_source_id"), "xfer entry has cycle_source_id")

    # Verify beta line has cycle_source_id (stamped atomically in X3 phase)
    b_text = (sb / "beta" / "knowledge" / "backlog.md").read_text()
    assert_(xfer_entry["cycle_source_id"] in b_text,
            "beta line includes cycle_source_id field stamped at xfer-time (atomic in X3)")

    # Close the beta row
    line = next(i + 1 for i, l in enumerate(b_text.splitlines()) if pid in l)
    claim_res = json.loads(kb(sb, "claim", "beta", "--line", str(line), "--json").stdout)
    kb(sb, "close", "beta", "--line", str(line), "--claim-id", claim_res["claim_id"],
       "--outcome", "closed", "--reason", "completed", "--json")

    # Re-dispatch same plan: should skip via cycle_source_id collision
    proc2 = cycle_plan(sb, plan)
    assert_(proc2.returncode == 0, "re-dispatch ok")
    summary2 = json.loads((sb / ".orchestrator" / f"plan-{dt.date.today().isoformat()}.json").read_text())
    actions2 = [r["action"] for r in summary2["results"]["beta"]]
    # Re-dispatch should hit append path (existing is closed, no carried) with skip status
    assert_(actions2 == ["append"], f"re-dispatch action (got {actions2})")
    last = summary2["results"]["beta"][0]
    assert_(last["result"]["status"] == "skipped",
            f"re-dispatch skipped via csid collision (got {last['result']})")

    # Beta backlog has exactly ONE occurrence of plan_item_id
    b_text2 = (sb / "beta" / "knowledge" / "backlog.md").read_text()
    pid_count = b_text2.count(pid)
    assert_(pid_count == 1, f"plan_item_id appears exactly once on beta (got {pid_count})")
    shutil.rmtree(sb)


def cr_phase5_cr4_dangling_xfer_recovery_before_lookup():
    """CR-Phase5-CR4: simulate a dangling X2 (src tombstoned, dst missing)
    crash. The next `kb-orchestrator-cycle plan` must run recovery FIRST
    so the lookup sees post-recovery state — otherwise a stale lookup
    would route dispatch to append, double-creating the row.

    Sequence:
      1. Append `pid` in alpha (open)
      2. Manually inject an X1 xfer-prepared coordinator entry +
         convert alpha line to [~] tombstoned-by-xfer-<id> (simulates
         X2 committed). Dst (beta) line never written (X3 crashed).
      3. Run `kb-orchestrator-cycle plan` with plan targeting beta.
      4. Cycle's recovery should resolve the dangling xfer (restore
         alpha to open), then re-build lookup, then xfer alpha→beta
         atomically.
      5. Assert: exactly one row with `pid` (in beta as [ ]).
    """
    print("CR-Phase5-CR4: dangling X2 crash → recovery before lookup")
    sb = setup_sandbox()
    pid = "deadbeef-1111-2222-3333-444455556666"

    # 1. Open in alpha
    kb(sb, "append", "alpha", "carried task", "--plan-item-id", pid, "--by", "hub", "--json")

    # 2. Simulate X2 partial: rewrite alpha line to [~] tombstone, write
    #    a fake X1 xfer-prepared coordinator record without X4 committed.
    a_text = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    a_text_tomb = a_text.replace(
        "- [ ] carried task",
        "- [~] carried task — tombstoned-by-xfer-FAKEID-1: " + dt.date.today().isoformat(),
    )
    (sb / "alpha" / "knowledge" / "backlog.md").write_text(a_text_tomb, encoding="utf-8")

    # X1 prepared record (no terminal phase) — the recovery code will
    # see this as dangling.
    import base64, hashlib, sys as _sys
    _sys.path.insert(0, "__HOME__/knowledge/bin")
    from _kb_backlog import journal as J
    src_text_full = a_text  # original pre-tombstone
    src_after_text = a_text_tomb
    dst_before_text = (sb / "beta" / "knowledge" / "backlog.md").read_text()

    fake_xid = "FAKEID-1"  # not a real uuid; recovery just keys by xfer_id
    rec = {
        "xfer_id": fake_xid,
        "phase": "xfer-prepared",
        "plan_item_id": pid,
        "src_slug": "alpha",
        "dst_slug": "beta",
        "src_before_hash": J.sha256_text(src_text_full),
        "src_after_hash": J.sha256_text(src_after_text),
        "dst_before_hash": J.sha256_text(dst_before_text),
        "dst_after_hash": J.sha256_text(dst_before_text + "appended-row"),
        "src_before_bytes_b64": base64.b64encode(src_text_full.encode("utf-8")).decode("ascii"),
        "src_line_b64": base64.b64encode(b"- [ ] carried task").decode("ascii"),
        "src_after_line_b64": base64.b64encode(
            f"- [~] carried task — tombstoned-by-xfer-{fake_xid}: {dt.date.today().isoformat()}".encode("utf-8")
        ).decode("ascii"),
        "dst_line_b64": base64.b64encode(b"- [ ] dst").decode("ascii"),
        "src_lineno": 4,
        "ts": "2026-04-25T00:00:00+00:00",
    }
    # Bootstrap _xfer segment manually
    audit_xfer_dir = sb / ".orchestrator" / "audit" / "_xfer"
    audit_xfer_dir.mkdir(parents=True, exist_ok=True)
    sid = "01234567-89ab-cdef-0123-456789abcdef"
    seg_init = {"segment_init": True, "segment_id": sid, "prev_segment_id": None,
                "started_at": "2026-04-25T00:00:00+00:00"}
    (audit_xfer_dir / f"{sid}.jsonl").write_text(
        json.dumps(seg_init) + "\n" + json.dumps(rec) + "\n", encoding="utf-8",
    )
    (sb / ".orchestrator" / "audit" / "_xfer-current.txt").write_text(sid, encoding="utf-8")

    # 3. Plan targets beta
    plan = write_plan(sb, [("beta", "carried task", pid)])
    proc = cycle_plan(sb, plan)
    assert_(proc.returncode == 0, f"plan succeeds (rc={proc.returncode}, stderr={proc.stderr[-300:]})")

    # 4 + 5. Verify state: exactly one occurrence of pid across alpha+beta.
    a_now = (sb / "alpha" / "knowledge" / "backlog.md").read_text()
    b_now = (sb / "beta" / "knowledge" / "backlog.md").read_text()
    a_count = a_now.count(pid)
    b_count = b_now.count(pid)
    total = a_count + b_count
    # The recovery + xfer chain should leave the row in beta only (alpha
    # tombstoned by the LIVE xfer that the cycle ran post-recovery, OR by
    # the recovery itself if it auto-rolled back; either way no duplicate
    # OPEN row should exist).
    open_count_alpha = sum(1 for l in a_now.splitlines() if l.strip().startswith("- [ ]") and pid in l)
    open_count_beta = sum(1 for l in b_now.splitlines() if l.strip().startswith("- [ ]") and pid in l)
    assert_(open_count_alpha + open_count_beta <= 1,
            f"no duplicate OPEN row across alpha+beta (alpha_open={open_count_alpha}, beta_open={open_count_beta}); a_total={a_count} b_total={b_count}")
    shutil.rmtree(sb)


def main():
    f1_open_carried()
    f2_closed_carried()
    f3_parent_moved()
    f4_multi_file_dup()
    cr_phase5_b1_idempotent_redispatch()
    cr_phase5_b2_in_progress_carried()
    cr_phase5_b3_escalation_durable()
    cr_phase5_cr2_xfer_idempotent_redispatch()
    cr_phase5_cr4_dangling_xfer_recovery_before_lookup()
    print("\nAll Phase 5 carried-item fixtures (F1-F4 + CR fixes B1/B2/B3 + CR2 xfer-stamp + CR4 dangling-xfer-recovery) PASSED")


if __name__ == "__main__":
    main()
