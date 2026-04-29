"""ops.py — subcommand handlers for kb-backlog mutations.

Each op:
1. Resolves backlog path from slug (via ~/knowledge/projects/<slug> symlink, or
   slug=="hub" → ~/knowledge/backlog.md).
2. Acquires required locks (canonical order via locks.acquire).
3. Runs preflight (refuses on duplicate-terminal corruption).
4. Runs recovery (idempotent — finishes any dangling prepared tx_ids).
5. Calls `mutation.apply_mutation` with a transform.

Each op returns an exit code + result dict that the CLI dispatcher
serializes to JSON or human-readable text.

Exit codes used (kb-backlog convention):
    0  — success
    1  — generic error (bad args, file missing, etc.)
    2  — lock busy (timeout)
    3  — preflight refused (journal corruption found)
    4  — claim-token drift detected (close/revert without authoritative claim)
    5  — collision skipped (idempotency duplicate, no work done)
    6  — duplicate found across files (multi-file dup, escalation entry created)
   23  — drift recheck failed during close/revert (line content changed)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import pathlib
import re
import sys
import time
from typing import Optional

from . import journal, locks, mutation, parsing, preflight, spawns

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))


def resolve_backlog_path(slug: str) -> pathlib.Path:
    """Return path to backlog.md for slug. slug=="hub" → hub-level backlog."""
    if slug == "hub":
        return HUB / "backlog.md"
    link = HUB / "projects" / slug
    if not link.exists():
        raise SystemExit(f"✘ slug {slug!r} not found in {HUB}/projects/ "
                         f"(expected symlink to <project>/knowledge/)")
    if link.is_symlink():
        target = link.resolve()
    else:
        target = link
    bl = target / "backlog.md"
    if not bl.is_file():
        raise SystemExit(f"✘ {bl} does not exist (project may not have triad set up)")
    return bl


def _today() -> str:
    return dt.date.today().isoformat()


def _claim_token_for_line(line_text: str, ts: float) -> str:
    """Generate a short claim token from line content + timestamp.

    NOTE: token alone is not enough — see `_claim_content_hash` for the
    content-hash binding that close/revert use to detect line-content drift.
    """
    h = hashlib.sha256()
    h.update(line_text.encode("utf-8"))
    h.update(f"{ts:.6f}".encode("utf-8"))
    return h.hexdigest()[:16]


def _claim_content_hash(parsed: parsing.BacklogLine) -> str:
    """Compute a content hash for a claimed line, EXCLUDING per-claim fields.

    Used as a strong drift detector: at claim time we compute and store this
    hash in the line as `claim_content_hash: <sha>`. At close/revert we
    recompute it from the current line (with claim_content_hash itself
    removed) and reject if they differ. This catches the case where another
    writer modifies the line content but preserves the visible claim_id
    (CR1-B4).

    Excluded fields: `claim_id`, `picked`, `claim_content_hash` themselves
    (otherwise the hash would never round-trip).
    """
    # Render a normalized form without the per-claim fields.
    excluded = {"claim_id", "picked", "claim_content_hash"}
    parts = [parsed.title.rstrip()]
    for k, v in parsed.fields:
        if k in excluded:
            continue
        parts.append(f"{k}: {v}")
    canonical = " — ".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _check_for_duplicate_across(slug: str, key: str, value: str) -> list[tuple[str, int]]:
    """Search all enabled backlogs for `key:value`. Returns [(slug, lineno), ...].

    Used by `append` collision check (CR1-B6 + CR1-B7).
    """
    matches: list[tuple[str, int]] = []
    # Hub
    hub = HUB / "backlog.md"
    if hub.is_file():
        for ln, parsed in parsing.parse_lines(hub.read_text(encoding="utf-8")):
            if parsed and parsed.status == "open" and parsed.get(key) == value:
                matches.append(("hub", ln))
    # Project backlogs
    proj_dir = HUB / "projects"
    if proj_dir.exists():
        for link in sorted(proj_dir.iterdir()):
            if not (link.is_symlink() or link.is_dir()):
                continue
            target = link.resolve() if link.is_symlink() else link
            bl = target / "backlog.md"
            if not bl.is_file():
                continue
            other_slug = link.name
            if other_slug == slug:
                continue
            for ln, parsed in parsing.parse_lines(bl.read_text(encoding="utf-8")):
                if parsed and parsed.status == "open" and parsed.get(key) == value:
                    matches.append((other_slug, ln))
    return matches


# ──────────────────────────────────────────────────────────────────────────
# Common preamble: locks + preflight + recovery
# ──────────────────────────────────────────────────────────────────────────

class _OpContext:
    """Convenience helper: holds slug, path, current_text, locks."""

    def __init__(self, slug: str, held: set[locks.LockId]):
        self.slug = slug
        self.path = resolve_backlog_path(slug)
        self.held = held

    def current_text(self) -> str:
        return self.path.read_text(encoding="utf-8") if self.path.is_file() else ""


def _resolve_dangling_xfers_for_slug(slug: str, lock_timeout: float) -> None:
    """If any xfer-prepared without terminal touches `slug`, run coordinator
    recovery under the full canonical lock stack.

    CR2-B3 fix: preflight runs FIRST, under the same lock stack as recovery.
    If duplicate-terminal corruption coexists with a dangling xfer, we refuse
    + escalate before any mutation rather than mutating then refusing.

    Caller must NOT hold any locks. We acquire-and-release the full xfer stack
    inside this function for any dangling xfers found.
    """
    dangling = preflight.find_dangling_xfers_for_slug(slug)
    if not dangling:
        return
    # Group by other_slug to acquire each pair's lock stack once.
    pairs: dict[str, list[dict]] = {}
    for rec in dangling:
        other = rec["dst_slug"] if rec["src_slug"] == slug else rec["src_slug"]
        pairs.setdefault(other, []).append(rec)
    # Lazy import to avoid circular dependency: ops <- xfer <- ops.
    from . import xfer as _xfer_mod
    for other, recs in pairs.items():
        lock_set = [locks.LockId.xfer(),
                    locks.LockId.slug(min(slug, other)),
                    locks.LockId.slug(max(slug, other)),
                    locks.LockId.spawns()]
        with locks.acquire(lock_set, timeout_s=lock_timeout) as held:
            # CR2-B3: preflight under the full lock stack BEFORE any recovery
            # mutation. If duplicate-terminal corruption exists for this xfer
            # or for either slug, refuse + escalate — recovery cannot resolve
            # corruption, only manual edits can.
            report = preflight.preflight_for_xfer(slug, other)
            preflight.assert_no_corruption(report)
            # Per-file recovery on both slugs first (idempotent).
            for s in (slug, other):
                p = resolve_backlog_path(s)
                journal.recover_pending(s, p.read_text(encoding="utf-8") if p.is_file() else "")
            _xfer_mod._recover_dangling_xfers(slug, other, held)


class _DanglingXferDetectedAfterLock(Exception):
    """Raised when, after acquiring slug+spawns lock, we discover a new
    dangling xfer touching this slug. Caught by _open_op which releases,
    re-resolves, and re-acquires.
    """


class DanglingXferRetryExhausted(Exception):
    """Public exception raised when _open_op exhausts its retry budget
    (3 attempts) for resolving dangling xfers without converging. Maps
    to exit code 2 (busy) in the CLI dispatcher — the caller should retry.
    Indicates either an extreme contention storm or a bug in lock ordering.
    """


def _open_op(slug: str, *, lock_timeout: float = 30.0):
    """Context-manager helper. Acquires <slug>.lock + spawns.lock,
    runs preflight, runs recovery. Yields _OpContext.

    CR2-B1 fix: TOCTOU between dangling-xfer scan and lock acquire is
    closed by re-checking under <slug>.lock + spawns.lock. If a new
    dangling xfer appeared in the gap (rare — would require an xfer to
    have started + crashed in microseconds before our lock-acquire), we
    release the lock, re-run _resolve_dangling_xfers_for_slug under the
    full canonical stack, and retry. After acquiring my_slug+spawns, no
    new xfer involving my_slug can begin (xfer needs my_slug.lock too),
    so the dangling-set is frozen — at most one re-resolve loop is
    needed in practice.
    """
    from contextlib import contextmanager

    @contextmanager
    def _gen():
        max_retries = 3
        for attempt in range(max_retries):
            # Step 0: resolve any dangling xfers touching this slug first.
            # Acquires full lock stack briefly, then releases.
            _resolve_dangling_xfers_for_slug(slug, lock_timeout)

            lock_set = [locks.LockId.slug(slug), locks.LockId.spawns()]
            try:
                with locks.acquire(lock_set, timeout_s=lock_timeout) as held:
                    # Re-check for dangling xfers under <slug>.lock + spawns.
                    # If any appeared in the TOCTOU gap, abort this attempt
                    # and retry from step 0 (under full lock stack).
                    if preflight.find_dangling_xfers_for_slug(slug):
                        raise _DanglingXferDetectedAfterLock()
                    # Preflight (now safe).
                    report = preflight.preflight_for_slug(slug)
                    preflight.assert_no_corruption(report)
                    # Recovery (idempotent).
                    ctx = _OpContext(slug, held)
                    journal.recover_pending(slug, ctx.current_text())
                    yield ctx
                return  # exit the retry loop on success (yield returned)
            except _DanglingXferDetectedAfterLock:
                continue  # retry from step 0
        raise DanglingXferRetryExhausted(
            f"_open_op({slug}): too many dangling-xfer races in {max_retries} attempts; "
            "retry the operation"
        )

    return _gen()


# ──────────────────────────────────────────────────────────────────────────
# append
# ──────────────────────────────────────────────────────────────────────────

def op_append(
    slug: str,
    body: str,
    *,
    cycle_source_id: Optional[str] = None,
    plan_item_id: Optional[str] = None,
    auto: bool = False,
    prompt: Optional[str] = None,
    by: str = "self",
    due: Optional[str] = None,
    context: Optional[str] = None,
    lock_timeout: float = 30.0,
) -> dict:
    """Append a task to slug's backlog. Idempotent on cycle_source_id|plan_item_id.

    Returns dict with status: appended | skipped | duplicate.
    """
    with _open_op(slug, lock_timeout=lock_timeout) as ctx:
        text = ctx.current_text()
        # Collision check (within this slug):
        # - cycle_source_id: ANY status (CR-Phase5-B1) — a stable
        #   cycle_source_id from the orchestrator means "this exact dispatch
        #   already happened on this slug"; skip even if the row is closed.
        # - plan_item_id: only OPEN/IN_PROGRESS rows (closed plan_item_id can
        #   recur; the orchestrator's F2 path expects fresh-append).
        if cycle_source_id:
            existing = parsing.find_by_field(text, "cycle_source_id", cycle_source_id)
            for ln, parsed in existing:
                return {
                    "status": "skipped",
                    "reason": f"cycle_source_id collision (status={parsed.status})",
                    "slug": slug,
                    "lineno": ln,
                }
        if plan_item_id:
            existing = parsing.find_by_field(text, "plan_item_id", plan_item_id)
            for ln, parsed in existing:
                if parsed.status in ("open", "in_progress"):
                    return {
                        "status": "skipped",
                        "reason": f"plan_item_id collision ({parsed.status} in same slug)",
                        "slug": slug,
                        "lineno": ln,
                    }
            # Cross-slug dup detection — informational only, doesn't abort here.
            # The plan layer (Phase 5) handles multi-file dup as F4.

        # Build the line
        parts = [body]
        parts.append(f"opened {_today()} by {by}")
        if due:
            parts.append(f"due: {due}")
        if context:
            parts.append(f"context: {context}")
        if auto:
            parts.append("auto: true")
        if prompt:
            parts.append(f"prompt: {prompt}")
        if cycle_source_id:
            parts.append(f"cycle_source_id: {cycle_source_id}")
        if plan_item_id:
            parts.append(f"plan_item_id: {plan_item_id}")
        line = "- [ ] " + " — ".join(parts)

        def transform(current: str) -> tuple[str, Optional[int], dict]:
            new = parsing.append_to_open_section(current, line)
            return new, None, {"plan_item_id": plan_item_id, "cycle_source_id": cycle_source_id}

        result = mutation.apply_mutation(
            slug=slug,
            backlog_path=ctx.path,
            op="append",
            actor=by,
            transform=transform,
            held_locks=ctx.held,
        )
        return {
            "status": "appended" if not result.no_op else "noop",
            "slug": slug,
            "tx_id": result.tx_id,
            "line": line,
        }


# ──────────────────────────────────────────────────────────────────────────
# update — refresh fields on an existing open line by plan_item_id
# ──────────────────────────────────────────────────────────────────────────

def op_update(
    slug: str,
    *,
    plan_item_id: str,
    field_updates: dict[str, str],
    by: str = "hub",
    lock_timeout: float = 30.0,
) -> dict:
    with _open_op(slug, lock_timeout=lock_timeout) as ctx:
        text = ctx.current_text()
        matches = parsing.find_by_field(text, "plan_item_id", plan_item_id)
        opens = [(ln, p) for ln, p in matches if p.status == "open"]
        if not opens:
            return {"status": "not-found", "slug": slug, "plan_item_id": plan_item_id}
        if len(opens) > 1:
            return {"status": "ambiguous", "slug": slug, "plan_item_id": plan_item_id,
                    "lines": [ln for ln, _ in opens]}
        target_lineno, parsed = opens[0]
        for k, v in field_updates.items():
            parsed.set_field(k, v)
        new_line = parsed.render()

        def transform(current: str) -> tuple[str, Optional[int], dict]:
            new = parsing.replace_line(current, target_lineno, new_line)
            return new, target_lineno, {"plan_item_id": plan_item_id}

        result = mutation.apply_mutation(
            slug=slug,
            backlog_path=ctx.path,
            op="update",
            actor=by,
            transform=transform,
            held_locks=ctx.held,
        )
        return {
            "status": "updated" if not result.no_op else "noop",
            "slug": slug,
            "tx_id": result.tx_id,
            "lineno": target_lineno,
        }


# ──────────────────────────────────────────────────────────────────────────
# tombstone — mark line as [~] with reason
# ──────────────────────────────────────────────────────────────────────────

def op_tombstone(
    slug: str,
    *,
    plan_item_id: str,
    reason: str,
    by: str = "hub",
    lock_timeout: float = 30.0,
) -> dict:
    with _open_op(slug, lock_timeout=lock_timeout) as ctx:
        text = ctx.current_text()
        matches = parsing.find_by_field(text, "plan_item_id", plan_item_id)
        opens = [(ln, p) for ln, p in matches if p.status == "open"]
        if not opens:
            return {"status": "not-found", "slug": slug, "plan_item_id": plan_item_id}
        if len(opens) > 1:
            return {"status": "ambiguous", "slug": slug, "lines": [ln for ln, _ in opens]}
        target_lineno, parsed = opens[0]
        parsed.set_marker("[~]")
        parsed.set_field(f"tombstoned-by-{reason}", _today())
        new_line = parsed.render()

        def transform(current: str) -> tuple[str, Optional[int], dict]:
            new = parsing.replace_line(current, target_lineno, new_line)
            return new, target_lineno, {"plan_item_id": plan_item_id, "reason": reason}

        result = mutation.apply_mutation(
            slug=slug,
            backlog_path=ctx.path,
            op="tombstone",
            actor=by,
            transform=transform,
            held_locks=ctx.held,
        )
        return {
            "status": "tombstoned" if not result.no_op else "noop",
            "slug": slug,
            "tx_id": result.tx_id,
            "lineno": target_lineno,
        }


# ──────────────────────────────────────────────────────────────────────────
# claim — [ ] → [>] with picked marker + claim_id token
# ──────────────────────────────────────────────────────────────────────────

def op_claim(
    slug: str,
    *,
    line: int,
    by: str = "executor",
    lock_timeout: float = 30.0,
) -> dict:
    with _open_op(slug, lock_timeout=lock_timeout) as ctx:
        text = ctx.current_text()
        parsed = parsing.find_line(text, line)
        if parsed is None:
            return {"status": "no-such-line", "slug": slug, "line": line}
        if parsed.status != "open":
            return {"status": "not-open", "slug": slug, "line": line, "current_status": parsed.status}

        # Generate claim token from current content + ts. Token is small (16 hex)
        # so it fits cleanly in the line for human readability. We ALSO store
        # a content hash (excluding per-claim fields) — this is the strong
        # drift detector that catches another writer modifying the line while
        # preserving the visible claim_id (CR1-B4).
        claim_id = _claim_token_for_line(parsed.render(), time.time())
        parsed.set_marker("[>]")
        parsed.set_field("picked", f"{_today()} by {by}")
        parsed.set_field("claim_id", claim_id)
        # Compute content hash AFTER the marker change but BEFORE adding
        # the hash itself — i.e. the hash represents "what the claimed
        # content looks like" excluding per-claim fields.
        content_hash = _claim_content_hash(parsed)
        parsed.set_field("claim_content_hash", content_hash)
        new_line = parsed.render()

        def transform(current: str) -> tuple[str, Optional[int], dict]:
            new = parsing.replace_line(current, line, new_line)
            return new, line, {"claim_id": claim_id}

        result = mutation.apply_mutation(
            slug=slug,
            backlog_path=ctx.path,
            op="claim",
            actor=by,
            transform=transform,
            held_locks=ctx.held,
        )
        return {
            "status": "claimed" if not result.no_op else "noop",
            "slug": slug,
            "tx_id": result.tx_id,
            "lineno": line,
            "claim_id": claim_id,
        }


# ──────────────────────────────────────────────────────────────────────────
# close — [>] → [x] with outcome (closed | escalated | failed)
# ──────────────────────────────────────────────────────────────────────────

VALID_OUTCOMES = {"closed", "escalated", "failed"}


def op_close(
    slug: str,
    *,
    line: int,
    claim_id: str,
    outcome: str,
    reason: Optional[str] = None,
    by: str = "executor",
    lock_timeout: float = 30.0,
) -> dict:
    if outcome not in VALID_OUTCOMES:
        return {"status": "bad-outcome", "outcome": outcome, "valid": list(VALID_OUTCOMES)}

    with _open_op(slug, lock_timeout=lock_timeout) as ctx:
        text = ctx.current_text()
        parsed = parsing.find_line(text, line)
        if parsed is None:
            return {"status": "no-such-line", "slug": slug, "line": line}
        if parsed.status != "in_progress":
            return {"status": "not-claimed", "slug": slug, "line": line,
                    "current_status": parsed.status}
        # Drift recheck — two-layer (CR1-B4):
        # 1. claim_id token must match (sanity check, cheap)
        # 2. content hash (excluding per-claim fields) must match the stored
        #    claim_content_hash. This catches another writer modifying line
        #    content while preserving the visible claim_id substring.
        existing_token = parsed.get("claim_id")
        if existing_token != claim_id:
            return {"status": "drift", "slug": slug, "line": line,
                    "expected_claim_id": claim_id, "actual_claim_id": existing_token,
                    "drift_kind": "claim_id"}
        stored_content_hash = parsed.get("claim_content_hash")
        recomputed = _claim_content_hash(parsed)
        if stored_content_hash != recomputed:
            return {"status": "drift", "slug": slug, "line": line,
                    "expected_content_hash": stored_content_hash,
                    "actual_content_hash": recomputed,
                    "drift_kind": "content_hash"}

        parsed.set_marker("[x]")
        parsed.remove_field("claim_id")
        parsed.remove_field("claim_content_hash")
        parsed.remove_field("picked")
        parsed.set_field("closed", _today())
        parsed.set_field("outcome", outcome)
        if reason:
            parsed.set_field("result", reason)
        new_line = parsed.render()

        # Move closed line to ## Done section (preserve order otherwise).
        # Implementation: replace in place, then move line to end of Done.
        def transform(current: str) -> tuple[str, Optional[int], dict]:
            text2 = parsing.replace_line(current, line, new_line)
            text3 = _move_to_done(text2, line)
            return text3, line, {"outcome": outcome, "claim_id": claim_id}

        result = mutation.apply_mutation(
            slug=slug,
            backlog_path=ctx.path,
            op="close",
            actor=by,
            transform=transform,
            held_locks=ctx.held,
        )
        return {
            "status": "closed" if not result.no_op else "noop",
            "slug": slug,
            "tx_id": result.tx_id,
            "lineno": line,
            "outcome": outcome,
        }


def _move_to_done(text: str, lineno: int) -> str:
    """Move the line at `lineno` to the end of `## Done` section.

    If `## Done` is missing, creates it at end of file.
    """
    lines = text.splitlines()
    if not (1 <= lineno <= len(lines)):
        return text
    line_text = lines[lineno - 1]
    # Remove from current position
    del lines[lineno - 1]
    text2 = "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    done_re = re.compile(r"^##\s*Done\s*$", re.MULTILINE)
    m = done_re.search(text2)
    if m is None:
        prefix = text2.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + "## Done\n\n" + line_text + "\n"
    start = m.end()
    next_hdr = re.search(r"\n##\s+\S", text2[start:])
    section_end = start + (next_hdr.start() if next_hdr else len(text2) - start)
    before = text2[:section_end].rstrip()
    after = text2[section_end:]
    sep = "" if before.endswith("\n") else "\n"
    new_text = before + sep + line_text + "\n"
    if after:
        if not after.startswith("\n"):
            new_text += "\n"
        new_text += after
    elif not new_text.endswith("\n"):
        new_text += "\n"
    return new_text


# ──────────────────────────────────────────────────────────────────────────
# revert — [>] → [ ] (executor crash, agent missed OUTCOME, etc.)
# ──────────────────────────────────────────────────────────────────────────

def op_revert(
    slug: str,
    *,
    line: int,
    claim_id: str,
    reason: str = "reverted",
    by: str = "executor",
    lock_timeout: float = 30.0,
) -> dict:
    with _open_op(slug, lock_timeout=lock_timeout) as ctx:
        text = ctx.current_text()
        parsed = parsing.find_line(text, line)
        if parsed is None:
            return {"status": "no-such-line", "slug": slug, "line": line}
        if parsed.status != "in_progress":
            return {"status": "not-claimed", "slug": slug, "line": line,
                    "current_status": parsed.status}
        # Two-layer drift recheck — same as close (CR1-B4).
        existing_token = parsed.get("claim_id")
        if existing_token != claim_id:
            return {"status": "drift", "slug": slug, "line": line,
                    "expected_claim_id": claim_id, "actual_claim_id": existing_token,
                    "drift_kind": "claim_id"}
        stored_content_hash = parsed.get("claim_content_hash")
        recomputed = _claim_content_hash(parsed)
        if stored_content_hash != recomputed:
            return {"status": "drift", "slug": slug, "line": line,
                    "expected_content_hash": stored_content_hash,
                    "actual_content_hash": recomputed,
                    "drift_kind": "content_hash"}

        parsed.set_marker("[ ]")
        parsed.remove_field("claim_id")
        parsed.remove_field("claim_content_hash")
        parsed.remove_field("picked")
        parsed.set_field(f"reverted-{reason}", _today())
        new_line = parsed.render()

        def transform(current: str) -> tuple[str, Optional[int], dict]:
            new = parsing.replace_line(current, line, new_line)
            return new, line, {"reason": reason, "claim_id": claim_id}

        result = mutation.apply_mutation(
            slug=slug,
            backlog_path=ctx.path,
            op="revert",
            actor=by,
            transform=transform,
            held_locks=ctx.held,
        )
        return {
            "status": "reverted" if not result.no_op else "noop",
            "slug": slug,
            "tx_id": result.tx_id,
            "lineno": line,
        }
