#!/usr/bin/env python3
"""parse.py — exercise parse_outcome() across all 7 fixture shapes.

We don't run the full executor here (which would require a real claude/broker
spawn) — instead we capture stdout from fake-agent.sh and feed it directly to
parse_outcome(). Replay-chain detector is exercised in a separate fixture.
"""
from __future__ import annotations

import importlib.util
import importlib.machinery
import os
import pathlib
import subprocess
import sys


def load_executor():
    """Import kb-execute-next as a module (it has no .py extension)."""
    p = pathlib.Path("__HOME__/knowledge/bin/kb-execute-next")
    loader = importlib.machinery.SourceFileLoader("kb_execute_next", str(p))
    spec = importlib.util.spec_from_loader("kb_execute_next", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def fake_stdout(mode: str) -> str:
    proc = subprocess.run(
        ["bash", "__HOME__/knowledge/tests/agent-contract/fake-agent.sh", mode],
        capture_output=True, text=True,
    )
    return proc.stdout


def main():
    mod = load_executor()
    parse_outcome = mod.parse_outcome

    # valid-single
    print("valid-single")
    status, enum, reason = parse_outcome(fake_stdout("valid-single"))
    assert_(status == "ok" and enum == "closed", f"ok+closed (got {status}, {enum})")
    assert_(reason == "task complete", "reason captured")

    # valid-escalated
    print("valid-escalated")
    status, enum, _ = parse_outcome(fake_stdout("valid-escalated"))
    assert_(status == "ok" and enum == "escalated", f"escalated (got {enum})")

    # valid-failed
    print("valid-failed")
    status, enum, _ = parse_outcome(fake_stdout("valid-failed"))
    assert_(status == "ok" and enum == "failed", f"failed (got {enum})")

    # missing
    print("missing")
    status, _, _ = parse_outcome(fake_stdout("missing"))
    assert_(status == "missing", f"missing (got {status})")

    # multiple
    print("multiple")
    status, _, _ = parse_outcome(fake_stdout("multiple"))
    assert_(status == "multiple", f"multiple (got {status})")

    # trailing
    print("trailing")
    status, _, _ = parse_outcome(fake_stdout("trailing"))
    assert_(status == "trailing", f"trailing (got {status})")

    # stderr-only — stdout will be empty/normal, so OUTCOME is missing.
    print("stderr-only")
    status, _, _ = parse_outcome(fake_stdout("stderr-only"))
    assert_(status == "missing", f"stderr-only treated as missing (got {status})")

    # bad-enum — regex anchored to closed|escalated|failed, so this won't match.
    print("bad-enum")
    status, _, _ = parse_outcome(fake_stdout("bad-enum"))
    assert_(status == "missing", f"bad-enum treated as missing (got {status})")

    print("\nAll agent-contract parse.py fixtures PASSED")


if __name__ == "__main__":
    main()
