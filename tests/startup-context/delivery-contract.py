#!/usr/bin/env python3
"""Startup-context delivery contract acceptance tests.

Implements the RED suite for the owner-approved contract
`decisions/startup-context-delivery-contract-2026-08-26.md`
(spec-contract sha256:089d86bf9883939e85e745896d190a511830bcfaa4693f8764e6d9dc1b1f73be).

Exercises the SessionStart shell entrypoint, never implementation internals, so
the suite stays valid for the live hub, the orchestrator-seed copy and the public
seed copy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SESSION_START = Path(os.environ.get(
    "KB_SESSION_START",
    str(Path.home() / "knowledge" / "bin" / "kb-session-start"),
))
HUB = Path(os.environ.get("KB_STARTUP_TEST_HUB", str(SESSION_START.parent.parent)))

SENTINEL_RE = re.compile(
    r"^KB-STARTUP-BUNDLE-END v1 chars=(\d+) sha256=([0-9a-f]{64})$", re.M)
ENVELOPE_CAP = 1200
BUDGET_DEFAULT = 250000
NORMAL_SLICES = {
    "today_roster", "agent_card", "state", "log", "active_work",
    "open_escalations", "prevention_rules", "ongoing_incidents", "recent_daily",
}
STATUS_WORDS = {"present", "clipped", "omitted", "empty", "missing"}

failures: list[str] = []


def check(cond, label, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f"\n       {detail}" if detail else ""))
        failures.append(label)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def hook_env(extra=None):
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("KB_STARTUP_MAX_CONTEXT", None)
    env["KB_HUB"] = str(HUB)
    if extra:
        env.update(extra)
    return env


def hook(cwd: Path, extra=None):
    r = subprocess.run(
        [str(SESSION_START)], input=json.dumps({"cwd": str(cwd)}),
        capture_output=True, text=True, env=hook_env(extra), timeout=40)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout or "{}")
    return payload.get("hookSpecificOutput", {}).get("additionalContext", "")


def make_project(root: Path, *, wiki=True, card=True, state="# State\n\n## Current Snapshot\n\nAlive.\n"):
    root.mkdir(parents=True, exist_ok=True)
    write(root / "AGENTS.md", "# proj\n")
    if not wiki:
        return root
    k = root / "knowledge"
    write(k / "log.md", "# Log\n\n## [2026-08-26] note | proj | \"hello\"\n")
    write(k / "state.md", state)
    write(k / "index.md", "# Index\n")
    write(k / "backlog.md", "# Backlog\n\n## Ready\n\n## In Progress\n\n## Done\n")
    write(k / "escalations.md", "# Escalations\n")
    write(k / "incidents.md", "# Incidents\n\n## Prevention rules\n\n- be careful\n\n## Ongoing\n\n- none\n")
    if card:
        write(k / "agents" / "agent-card.md",
              "---\nname: proj\ndisplay_name: proj agent\n---\n\n# proj agent\n\n## Self-introduction\n\nI am proj.\n")
    return root


def parse_manifest(ctx: str) -> dict[str, str]:
    out = {}
    m = re.search(r"^## Startup Context Manifest\s*$", ctx, re.M)
    if not m:
        return out
    tail = ctx[m.end():]
    stop = re.search(r"^## ", tail, re.M)
    block = tail[: stop.start()] if stop else tail
    for line in block.splitlines():
        mm = re.match(r"^- ([a-z_]+): (.*)$", line.strip())
        if mm:
            out[mm.group(1)] = mm.group(2).strip()
    return out


def sentinel_of(ctx: str):
    ms = SENTINEL_RE.findall(ctx)
    return ms


# ---------------------------------------------------------------- C3 sentinel
def t_sentinel(tmp: Path):
    print("\nC3 — sentinel")
    p = make_project(tmp / "p1")
    ctx = hook(p)
    ms = sentinel_of(ctx)
    check(len(ms) == 1, "exactly one sentinel line", f"found {len(ms)}")
    if not ms:
        return
    n, h = ms[0]
    check(ctx.rstrip("\n").endswith(f"sha256={h}"), "sentinel is the final line")
    check(int(n) == len(ctx), "chars is a fixed point over the whole emission",
          f"declared {n}, actual {len(ctx)}")
    last = ctx.rstrip("\n").rfind("\n")
    body = ctx[: last + 1] if last >= 0 else ""
    check(hashlib.sha256(body.encode("utf-8")).hexdigest() == h,
          "sha256 verifies over the body excluding the final line")


# --------------------------------------------------------------- C2 envelope
def t_envelope(tmp: Path):
    print("\nC2 — recovery block")
    p = make_project(tmp / "p2")
    ctx = hook(p)
    head = ctx[:4000]
    idx_env = 0
    idx_manifest = ctx.find("## Startup Context Manifest")
    check(idx_manifest > 0, "manifest present")
    envelope = ctx[:idx_manifest] if idx_manifest > 0 else head
    check(len(envelope) <= ENVELOPE_CAP,
          f"recovery block <= {ENVELOPE_CAP} chars", f"got {len(envelope)}")
    check("KB-STARTUP-BUNDLE-END v1" in envelope, "envelope names the sentinel")
    check(re.search(r"bundle_id:\s*[0-9a-f-]{8,}", envelope) is not None,
          "envelope carries bundle_id")
    check("kb-session-start" in envelope and "--print" in envelope,
          "envelope carries the re-run fallback command")
    check(re.search(r"KB_HUB", envelope) is not None,
          "fallback resolves the hook by absolute path, not PATH")
    check(idx_env < idx_manifest, "envelope precedes the manifest")


# --------------------------------------------------------------- C5 manifest
def t_manifest(tmp: Path):
    print("\nC5 — manifest honesty")
    p = make_project(tmp / "p3")
    ctx = hook(p)
    man = parse_manifest(ctx)
    check("included" not in " ".join(man.values()),
          "'included' retired as a status word", str(man))
    check(any(k.startswith("delivery") for k in man) or "delivery:" in ctx,
          "mandatory delivery line present")
    missing = NORMAL_SLICES - set(man)
    check(not missing, "every expected normal-mode slice is in the manifest",
          f"missing: {sorted(missing)}")
    bad = {k: v for k, v in man.items()
           if k in NORMAL_SLICES and v.split()[0] not in STATUS_WORDS}
    check(not bad, "every slice carries exactly one legal status word", str(bad))


# ------------------------------------------------------------- C4 budget/caps
def t_budget(tmp: Path):
    print("\nC4 — budget, caps retired")
    big = "# State\n\n## Current Snapshot\n\n" + ("snapshot line\n" * 900)
    p = make_project(tmp / "p4", state=big)
    ctx = hook(p)
    check("...(clipped by startup-context budget)" not in ctx,
          "no per-section clipping below the ceiling")
    check(len(ctx) < BUDGET_DEFAULT, "emission under the default ceiling",
          f"len={len(ctx)}")
    src = (p / "knowledge" / "state.md").read_text(encoding="utf-8")
    tail_marker = src.rstrip().splitlines()[-1]
    check(tail_marker in ctx, "large state survives whole (caps retired)")


# -------------------------------------------------------------- C1 modes
def t_modes(tmp: Path):
    print("\nC1 — emission modes")
    # empty: no project markers
    empty_dir = tmp / "nothing"
    empty_dir.mkdir(parents=True, exist_ok=True)
    ctx = hook(empty_dir)
    check(ctx == "", "empty mode emits nothing", repr(ctx[:200]))

    # kb-ignore
    p = make_project(tmp / "p5")
    (p / ".kb-ignore").write_text("", encoding="utf-8")
    check(hook(p) == "", "kb-ignore emits nothing")

    # stub: markers, no wiki
    stub = make_project(tmp / "p6", wiki=False)
    ctx = hook(stub)
    if ctx:
        check(len(sentinel_of(ctx)) == 1, "stub mode carries a sentinel")
        check("KB-STARTUP-BUNDLE-END v1" in ctx[:ENVELOPE_CAP],
              "stub mode carries the recovery block")
        check("## Startup Context Manifest" not in ctx,
              "stub mode emits no manifest")
    else:
        check(False, "stub mode emits a bundle", "got empty output")


# -------------------------------------------------------------- no-card path
def t_no_card(tmp: Path):
    print("\nAgent-card hierarchy")
    p = make_project(tmp / "p7", card=False)
    ctx = hook(p)
    man = parse_manifest(ctx)
    check("agent_card" in man, "agent_card reported even when absent")
    check(man.get("agent_card", "").split()[0] in {"missing", "present", "empty"},
          "agent_card status is legal", man.get("agent_card", ""))


def main() -> int:
    if not SESSION_START.exists():
        print(f"missing hook: {SESSION_START}")
        return 2
    with tempfile.TemporaryDirectory(prefix="kb-delivery-") as td:
        tmp = Path(td)
        for fn in (t_sentinel, t_envelope, t_manifest, t_budget, t_modes, t_no_card):
            try:
                fn(tmp)
            except Exception as exc:  # a crashing check is a failure, not a skip
                print(f"  FAIL {fn.__name__} raised {exc!r}")
                failures.append(fn.__name__)
    print(f"\n{'FAILED' if failures else 'PASSED'}: {len(failures)} failing check(s)")
    if failures:
        for f in failures:
            print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
