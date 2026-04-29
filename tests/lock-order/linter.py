#!/usr/bin/env python3
"""linter.py — verify canonical global lock order rules.

Per CR9-N1: any acquired lock sequence must be a SUBSET of the canonical
order with relative positions preserved. We exercise the
locks.is_canonical_subset_order helper against good and bad sequences.

Canonical order: _xfer < <slug-A> < <slug-B> < ... < spawns
Per-slug locks share rank (RANK_SLUG_BASE) and sort alphabetically.
"""
import sys
sys.path.insert(0, "__HOME__/knowledge/bin")
from _kb_backlog import locks  # noqa: E402


def assert_(cond, msg):
    if not cond:
        print(f"✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ {msg}")


def main():
    xfer = locks.LockId.xfer()
    spawns = locks.LockId.spawns()
    a = locks.LockId.slug("alpha")
    b = locks.LockId.slug("beta")

    # Valid sequences:
    assert_(locks.is_canonical_subset_order([xfer, a, b, spawns]),
            "full canonical: _xfer, alpha, beta, spawns")
    assert_(locks.is_canonical_subset_order([a, spawns]),
            "subset: alpha, spawns (skip _xfer)")
    assert_(locks.is_canonical_subset_order([xfer, spawns]),
            "subset: _xfer, spawns (no slug locks)")
    assert_(locks.is_canonical_subset_order([a]),
            "single lock subset")
    assert_(locks.is_canonical_subset_order([]),
            "empty subset")

    # Invalid sequences (relative order broken):
    assert_(not locks.is_canonical_subset_order([spawns, a]),
            "INVALID: spawns before slug")
    assert_(not locks.is_canonical_subset_order([b, a]),
            "INVALID: beta before alpha (alphabetical broken)")
    assert_(not locks.is_canonical_subset_order([a, xfer]),
            "INVALID: slug before _xfer")
    assert_(not locks.is_canonical_subset_order([spawns, xfer, a]),
            "INVALID: completely reversed")

    # Reserved-name guard
    try:
        locks.LockId.slug("_xfer")
        ok = False
    except ValueError:
        ok = True
    assert_(ok, "LockId.slug rejects reserved name '_xfer'")

    print("\nAll lock-order linter checks PASSED")


if __name__ == "__main__":
    main()
