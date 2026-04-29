"""kb-backlog internal package.

Spec: ~/.claude/plans/rustling-marinating-sketch.md (Phase 1b).

Layout:
- parsing.py    — backlog line parsing (extract plan_item_id, cycle_source_id, claim_id, etc.)
- locks.py      — LockId, global lock order, set-based held_locks, flock acquisition
- journal.py    — per-slug audit journal segments (prepared/committed protocol, recovery, rotation)
- mutation.py   — `_apply_mutation` primitive (single code path for CLI + recovery)
- xfer.py       — cross-backlog xfer coordinator (X1-X4 phases, byte-safe rollback)
- preflight.py  — journal-integrity scan (terminal_count > 1 detection, scoped)
- ops.py        — subcommand handlers (append/update/tombstone/close/claim/revert/xfer)
- view.py       — original list-mode viewer (back-compat for bare `kb-backlog`)

All `kb-backlog` mutations follow the canonical global lock order:
    _xfer.lock < <slug-A>.lock < <slug-B>.lock < spawns.lock

Held-lock subsets are passed explicitly between functions as `set[LockId]`.
"""
