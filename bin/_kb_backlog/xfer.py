"""xfer.py — cross-backlog transfer coordinator (X1-X4 phases).

Spec: ~/.claude/plans/rustling-marinating-sketch.md Section 5 п.6 + CR7-B3
+ CR8-B4 (byte-safe rollback) + CR9-B1 (state-safe recovery).

Phases:
    X1 (xfer-prepared):    write coordinator entry with byte-encoded src/dst content
    X2 (src tombstone):    per-file mutation in src backlog
    X3 (dst append):       per-file mutation in dst backlog
    X4 (xfer-committed):   coordinator terminal

Recovery (state-safe; auto-rollback only when conditions match):
    - both committed → xfer-committed-recovered
    - src committed but dst missing:
        if sha256(src_current) == src_after_hash → restore from base64 + xfer-aborted
        else → xfer-escalated-orphan (manual)
    - neither committed → xfer-aborted
    - dst committed but src missing → xfer-escalated-orphan (impossible per lock order)
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import pathlib
import time
import uuid
from typing import Optional

from . import journal, locks, mutation, ops, parsing, preflight, spawns

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _b64_decode(s: str) -> str:
    return base64.b64decode(s.encode("ascii")).decode("utf-8")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _xfer_lock_set(src: str, dst: str) -> list[locks.LockId]:
    """Return canonical lock list for an xfer between src and dst (sorted)."""
    a, b = sorted([src, dst])
    return [locks.LockId.xfer(), locks.LockId.slug(a), locks.LockId.slug(b), locks.LockId.spawns()]


def op_xfer(
    *,
    plan_item_id: str,
    src: str,
    dst: str,
    by: str = "hub",
    cycle_source_id: Optional[str] = None,
    lock_timeout: float = 30.0,
) -> dict:
    """Atomically move an open task identified by plan_item_id from src→dst.

    Steps:
        1. Acquire full canonical lock stack.
        2. Preflight (both src + dst journals).
        3. Recovery on src + dst (idempotent).
        4. Locate src open line by plan_item_id; build dst body.
        5. X1 prepared with src/dst byte-encoded content + hashes.
        6. X2 src tombstone (using internal mutation primitive).
        7. X3 dst append (internal primitive).
        8. X4 committed.
    """
    if src == dst:
        return {"status": "bad-args", "reason": "src == dst", "src": src, "dst": dst}

    lock_set = _xfer_lock_set(src, dst)
    with locks.acquire(lock_set, timeout_s=lock_timeout) as held:
        # Preflight (xfer + both slugs)
        rep = preflight.preflight_for_xfer(src, dst)
        preflight.assert_no_corruption(rep)

        # Recovery on each slug
        src_path = ops.resolve_backlog_path(src)
        dst_path = ops.resolve_backlog_path(dst)
        journal.recover_pending(src, src_path.read_text(encoding="utf-8") if src_path.is_file() else "")
        journal.recover_pending(dst, dst_path.read_text(encoding="utf-8") if dst_path.is_file() else "")

        # Coordinator-level recovery (handles dangling xfers touching either slug)
        _recover_dangling_xfers(src, dst, held)

        # Locate src open line by plan_item_id
        src_text = src_path.read_text(encoding="utf-8")
        matches = parsing.find_by_field(src_text, "plan_item_id", plan_item_id)
        opens = [(ln, p) for ln, p in matches if p.status == "open"]
        if not opens:
            return {"status": "not-found", "src": src, "plan_item_id": plan_item_id}
        if len(opens) > 1:
            return {"status": "ambiguous", "src": src, "lines": [ln for ln, _ in opens]}
        src_lineno, src_parsed = opens[0]
        original_line_text = src_parsed.render()

        # Build dst version: same body, marker [ ], opened today by hub, plan_item_id preserved
        dst_parsed = parsing.parse_line(original_line_text)
        if dst_parsed is None:
            return {"status": "parse-failed", "src": src, "lineno": src_lineno}
        dst_parsed.set_marker("[ ]")
        # Overwrite some fields to reflect the move
        dst_parsed.set_field("opened", f"{_today_str()} by {by}")
        dst_parsed.set_field("xfer_from", src)
        # CR-Phase5-CR3 fix: stamp dst with cycle_source_id atomically in
        # X3 phase. Without this, a separate post-xfer update would race
        # against kb-execute-next claiming the new row before the stamp.
        if cycle_source_id:
            dst_parsed.set_field("cycle_source_id", cycle_source_id)
        dst_line_text = dst_parsed.render()

        xfer_id = str(uuid.uuid4())

        # Compute hashes pre-write (X1)
        src_before = src_text
        src_before_hash = journal.sha256_text(src_before)
        # tombstone_marker = mark [~] tombstoned-by-xfer-<xfer_id>: <today>
        src_parsed_after = parsing.parse_line(original_line_text)
        assert src_parsed_after is not None
        src_parsed_after.set_marker("[~]")
        src_parsed_after.set_field(f"tombstoned-by-xfer-{xfer_id}", _today_str())
        src_after_line = src_parsed_after.render()
        src_after_text = parsing.replace_line(src_before, src_lineno, src_after_line)
        src_after_hash = journal.sha256_text(src_after_text)

        dst_before = dst_path.read_text(encoding="utf-8") if dst_path.is_file() else ""
        dst_before_hash = journal.sha256_text(dst_before)
        dst_after_text = parsing.append_to_open_section(dst_before, dst_line_text)
        dst_after_hash = journal.sha256_text(dst_after_text)

        # Phase X1: xfer-prepared
        prepared_record = {
            "xfer_id": xfer_id,
            "phase": "xfer-prepared",
            "plan_item_id": plan_item_id,
            "src_slug": src,
            "dst_slug": dst,
            "src_before_hash": src_before_hash,
            "src_after_hash": src_after_hash,
            "dst_before_hash": dst_before_hash,
            "dst_after_hash": dst_after_hash,
            "src_before_bytes_b64": _b64(src_before),
            "src_line_b64": _b64(original_line_text),
            "src_after_line_b64": _b64(src_after_line),
            "dst_line_b64": _b64(dst_line_text),
            "src_lineno": src_lineno,
            "ts": _now(),
        }
        journal.append_record("_xfer", prepared_record)

        # Phase X2: src tombstone via internal mutation primitive
        def src_transform(current: str) -> tuple[str, Optional[int], dict]:
            return src_after_text, src_lineno, {"xfer_id": xfer_id, "role": "src"}

        mutation.apply_mutation(
            slug=src,
            backlog_path=src_path,
            op="tombstone",
            actor=by,
            transform=src_transform,
            held_locks=held,
            extra_required_locks={locks.LockId.xfer()},
        )

        # Phase X3: dst append via internal mutation primitive
        def dst_transform(current: str) -> tuple[str, Optional[int], dict]:
            return dst_after_text, None, {"xfer_id": xfer_id, "role": "dst", "plan_item_id": plan_item_id}

        mutation.apply_mutation(
            slug=dst,
            backlog_path=dst_path,
            op="append",
            actor=by,
            transform=dst_transform,
            held_locks=held,
            extra_required_locks={locks.LockId.xfer()},
        )

        # Phase X4: xfer-committed
        journal.append_record("_xfer", {
            "xfer_id": xfer_id,
            "phase": "xfer-committed",
            "ts": _now(),
        })

        return {
            "status": "xferred",
            "xfer_id": xfer_id,
            "plan_item_id": plan_item_id,
            "src": src,
            "src_lineno": src_lineno,
            "dst": dst,
        }


def _today_str() -> str:
    return dt.date.today().isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Recovery (coordinator-level): finalize dangling xfers
# ──────────────────────────────────────────────────────────────────────────

def _recover_dangling_xfers(src: str, dst: str, held: set[locks.LockId]) -> list[dict]:
    """For each xfer-prepared without terminal where {src, dst} matches our op,
    finalize via state-safe rollback (CR9-B1). Caller holds full lock stack.

    Returns list of resolution dicts.
    """
    resolutions: list[dict] = []
    grouped = journal.collapse_xfer_by_id(journal.iter_records_chain("_xfer"))
    for xid, st in grouped.items():
        if st.prepared is None or st.terminal_count >= 1:
            continue
        rec = st.prepared
        x_src = rec.get("src_slug")
        x_dst = rec.get("dst_slug")
        if {x_src, x_dst} != {src, dst}:
            continue
        # Already inside src/dst recovery (per-file). Now decide coordinator state.
        src_text = ops.resolve_backlog_path(x_src).read_text(encoding="utf-8")
        dst_text = ops.resolve_backlog_path(x_dst).read_text(encoding="utf-8")
        src_hash_now = journal.sha256_text(src_text)
        dst_hash_now = journal.sha256_text(dst_text)

        src_after = rec.get("src_after_hash")
        src_before = rec.get("src_before_hash")
        dst_after = rec.get("dst_after_hash")
        dst_before = rec.get("dst_before_hash")

        if src_hash_now == src_after and dst_hash_now == dst_after:
            # Both committed (recovered)
            journal.append_record("_xfer", {
                "xfer_id": xid, "phase": "xfer-committed-recovered", "ts": _now(),
            })
            resolutions.append({"xfer_id": xid, "phase": "xfer-committed-recovered"})
        elif src_hash_now == src_before and dst_hash_now == dst_before:
            # Neither committed — clean rollback (X1→X2 crash)
            journal.append_record("_xfer", {
                "xfer_id": xid, "phase": "xfer-aborted", "reason": "no work persisted", "ts": _now(),
            })
            resolutions.append({"xfer_id": xid, "phase": "xfer-aborted"})
        else:
            # Crash X2→X3 candidate (or other partial states). Rollback is
            # only safe under one of two conditions (CR1-N3 + CR9-B1):
            #   (a) sha256(src_current) == src_after_hash — exact full-file
            #       match: src is in the expected tombstoned state.
            #   (b) the EXACT tombstone line bytes for this xfer_id are
            #       present unambiguously in src (single occurrence, exact
            #       byte match).
            # If neither → escalated-orphan (no auto-rollback).
            condition_a = (src_hash_now == src_after and dst_hash_now == dst_before)
            condition_b = False
            try:
                expected_after_line = _b64_decode(rec["src_after_line_b64"])
                src_path = ops.resolve_backlog_path(x_src)
                src_text_now = src_path.read_text(encoding="utf-8")
                src_lines = src_text_now.splitlines()
                occurrences = sum(1 for ln in src_lines if ln == expected_after_line)
                condition_b = (occurrences == 1 and dst_hash_now == dst_before)
            except (KeyError, ValueError, base64.binascii.Error):
                pass

            if not (condition_a or condition_b):
                journal.append_record("_xfer", {
                    "xfer_id": xid, "phase": "xfer-escalated-orphan",
                    "reason": (
                        f"unsafe to auto-rollback: src_hash={src_hash_now[:8]}, "
                        f"dst_hash={dst_hash_now[:8]} (expected exact match or "
                        f"unambiguous tombstone line bytes)"
                    ),
                    "ts": _now(),
                })
                resolutions.append({"xfer_id": xid, "phase": "xfer-escalated-orphan"})
                continue

            # Safe to roll back. Decode src_before_bytes (whole-file restore)
            # or use line-level restore via src_line_b64.
            try:
                src_before_bytes = _b64_decode(rec["src_before_bytes_b64"])
            except (KeyError, ValueError, base64.binascii.Error):
                journal.append_record("_xfer", {
                    "xfer_id": xid, "phase": "xfer-escalated-orphan",
                    "reason": "missing/bad src_before_bytes_b64", "ts": _now(),
                })
                resolutions.append({"xfer_id": xid, "phase": "xfer-escalated-orphan"})
                continue

            src_path = ops.resolve_backlog_path(x_src)
            if condition_a:
                # Whole-file restore: condition_a means src exactly matches
                # src_after, so restoring src_before is safe.
                target_text = src_before_bytes
            else:
                # condition_b: line-level restore of just the tombstone line.
                # Other content may have changed legitimately since
                # src_before — restore only the tombstoned line.
                target_text = parsing.replace_line(
                    src_text_now,
                    src_lines.index(expected_after_line) + 1,
                    _b64_decode(rec["src_line_b64"]),
                )

            def transform(_current: str) -> tuple[str, Optional[int], dict]:
                return target_text, rec.get("src_lineno"), {"xfer_id": xid, "role": "rollback"}

            try:
                mutation.apply_mutation(
                    slug=x_src,
                    backlog_path=src_path,
                    op="update",
                    actor="recovery",
                    transform=transform,
                    held_locks=held,
                    extra_required_locks={locks.LockId.xfer()},
                )
                rb_kind = "whole-file" if condition_a else "line-bytes"
                journal.append_record("_xfer", {
                    "xfer_id": xid, "phase": "xfer-aborted",
                    "reason": f"rolled back X2→X3 crash ({rb_kind})", "ts": _now(),
                })
                resolutions.append({"xfer_id": xid, "phase": "xfer-aborted"})
            except Exception as exc:
                journal.append_record("_xfer", {
                    "xfer_id": xid, "phase": "xfer-escalated-orphan",
                    "reason": f"rollback failed: {exc!r}", "ts": _now(),
                })
                resolutions.append({"xfer_id": xid, "phase": "xfer-escalated-orphan"})
    return resolutions
