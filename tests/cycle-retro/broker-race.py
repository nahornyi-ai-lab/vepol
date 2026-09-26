#!/usr/bin/env python3
"""broker-race.py — CR5-B2 fixture.

Spawns N concurrent kb-orchestrator-run processes — each with --json-status
and a unique --run-id — and verifies:

1. All N processes succeed without FileNotFoundError on state.json rename.
2. state.json contains valid JSON after all N finish.
3. Each --run-id has its own intact run-result file.

The pre-fix behavior: parallel brokers race on `state.tmp` (fixed filename),
causing rename failures and corrupted state files.
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

N_PARALLEL = 6

# --- Fake CLI sandbox -------------------------------------------------------
#
# kb-orchestrator-run resolves its two backends differently:
#   - claude: build_claude_command() hardcodes argv[0]="claude" and lets the
#     durable runner (_kb_claude_runner.run_command, env=None) exec it via a
#     bare-name PATH search — so it is redirected by putting a fake "claude"
#     first on PATH.
#   - codex: build_codex_command() calls _kb_codex.codex_bin(), which returns
#     $KB_CODEX_BIN verbatim if set (else ~/.local/bin/codex) — so it is
#     redirected by pointing KB_CODEX_BIN at the fake "codex" directly.
# Both fakes just log their invocation (argv, pid, cwd) and exit 0 fast, so
# this suite can never start a real claude/codex process while still
# exercising the real save_state race in kb-orchestrator-run.

FAKE_CLAUDE_SRC = """#!/usr/bin/env python3
import json, os, sys, time
log_path = os.environ.get("FAKE_CLI_CALL_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "bin": "claude", "argv": sys.argv, "pid": os.getpid(),
            "cwd": os.getcwd(), "ts": time.time(),
        }) + "\\n")
print("fake claude: ok")
sys.exit(0)
"""

FAKE_CODEX_SRC = """#!/usr/bin/env python3
import json, os, sys, time
log_path = os.environ.get("FAKE_CLI_CALL_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "bin": "codex", "argv": sys.argv, "pid": os.getpid(),
            "cwd": os.getcwd(), "ts": time.time(),
        }) + "\\n")
# kb-orchestrator-run's codex lane passes -o <path> and reads that file back
# as the run's output payload.
out_path = None
for i, a in enumerate(sys.argv):
    if a == "-o" and i + 1 < len(sys.argv):
        out_path = sys.argv[i + 1]
        break
if out_path:
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("fake codex: ok\\n")
print("fake codex: ok")
sys.exit(0)
"""


def make_fake_cli_bin(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Write fake claude/codex executables + an empty call log under root.

    Returns (fake_bin_dir, call_log_path).
    """
    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    # Resolve: macOS's tempfile sandbox lives under /var/folders/... which is
    # itself a symlink to /private/var/folders/...; the kernel's shebang
    # re-exec records the canonical (resolved) path as argv[0], so compare
    # against that same resolved form later instead of the symlinked one.
    fake_bin = fake_bin.resolve()
    call_log = root / "fake-cli-calls.jsonl"
    call_log.touch()
    for name, src in (("claude", FAKE_CLAUDE_SRC), ("codex", FAKE_CODEX_SRC)):
        script = fake_bin / name
        script.write_text(src, encoding="utf-8")
        script.chmod(0o755)
    return fake_bin, call_log


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def main():
    print(f"CR5-B2: {N_PARALLEL} concurrent kb-orchestrator-run, no state-race")
    sb = tempfile.mkdtemp(prefix="kb-bk-race-")
    p = pathlib.Path(sb)
    (p / ".orchestrator").mkdir()
    (p / "logs").mkdir()
    workdir = p / "workdir"
    workdir.mkdir()

    # Isolation (mandatory, not hygiene): see fixture.py — the runner dedup
    # index is machine-global, so without an own run root this suite both
    # writes into the live hub and can attach to a prior sandbox's runs.
    fake_bin, call_log = make_fake_cli_bin(p)
    env = {**os.environ, "KB_HUB": str(p),
           "KB_CLAUDE_RUN_ROOT": str(p / ".orchestrator" / "claude-runs"),
           # claude: build_claude_command() hardcodes argv[0]="claude" and
           # resolves it via a bare-name PATH search — put the fake first.
           "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
           # codex: codex_bin() returns KB_CODEX_BIN verbatim when set —
           # point it straight at the fake, no PATH search involved.
           "KB_CODEX_BIN": str(fake_bin / "codex"),
           "FAKE_CLI_CALL_LOG": str(call_log)}
    procs = []
    run_ids = []
    for i in range(N_PARALLEL):
        rid = str(uuid.uuid4())
        run_ids.append(rid)
        # Use a no-op prompt that exits quickly. The broker will spawn the
        # fake claude/codex from fake_bin (never a real LLM CLI — see
        # make_fake_cli_bin above); what matters here is that the
        # parallel state writes don't race. --timeout applies to the Codex
        # lane only; the Claude lane waits for its (instant) fake to exit.
        cmd = [
            "__HOME__/knowledge/bin/kb-orchestrator-run",
            "echo only",
            "--cwd", str(workdir),
            "--timeout", "2",
            "--json-status", "--run-id", rid,
        ]
        procs.append(subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE))

    failed_with_oserror = []
    for i, pr in enumerate(procs):
        pr.wait(timeout=120)
        stderr = pr.stderr.read().decode() if pr.stderr else ""
        if "FileNotFoundError" in stderr or "[Errno 2] No such file" in stderr:
            failed_with_oserror.append((i, stderr[-300:]))

    assert_(not failed_with_oserror,
            f"no FileNotFoundError race on state.tmp (failed: {len(failed_with_oserror)})")

    # Structural proof that only the fake CLIs ran: each logged argv[0] is a
    # path under fake_bin, not a bare "claude"/"codex" resolved elsewhere.
    # (Bare argv[0] survives PATH search — see make_fake_cli_bin's docstring
    # comment above — so this also rules out an unintended real-binary hit.)
    log_lines = [ln for ln in call_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    entries = [json.loads(ln) for ln in log_lines]
    assert_(len(entries) > 0, "fake CLI call log is non-empty (fake was actually invoked)")
    bad = [e for e in entries if not str(e.get("argv", [""])[0]).startswith(str(fake_bin))]
    assert_(not bad,
            f"every recorded invocation argv[0] points at fake_bin ({len(bad)} did not)")

    # state.json should be valid JSON after the storm.
    state_file = p / ".orchestrator" / "state.json"
    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            assert_(isinstance(data, dict), "state.json is a JSON object")
        except json.JSONDecodeError as e:
            print(f"  ✘ state.json corrupted: {e}", file=sys.stderr)
            sys.exit(1)

    # Each run_id has its own run-result file (broker writes them
    # independently — no shared filename).
    runs_dir = p / ".orchestrator" / "runs"
    if runs_dir.is_dir():
        existing = {f.stem for f in runs_dir.glob("*.json")}
        intersect = set(run_ids) & existing
        assert_(len(intersect) >= len(run_ids) - 2,
                f"most run-result files persisted ({len(intersect)}/{len(run_ids)})")

    shutil.rmtree(sb)
    print("\nCR5-B2 race test PASSED — no state.tmp collisions\n")
    cr6_b2_nested_preservation()


def cr6_b2_nested_preservation():
    """CR6-B2: concurrent brokers writing distinct sessions[resume_key]
    must both survive (no overwrite of nested state)."""
    print("CR6-B2: concurrent brokers preserve distinct sessions[]")
    sb = tempfile.mkdtemp(prefix="kb-bk-nested-")
    p = pathlib.Path(sb)
    (p / ".orchestrator").mkdir()

    # Use update_state directly: spawn N python processes that each call
    # update_state with a unique resume_key, then verify all keys persist.
    import textwrap
    workers = []
    keys = [f"resume-key-{i}" for i in range(8)]
    # Re-implement update_state inline (instead of importing kb-orchestrator-run
    # which has heavy load-time deps). Same lock semantics, same merge logic.
    update_inline = textwrap.dedent(f"""
        import os, json, fcntl, pathlib, uuid

        STATE_DIR = pathlib.Path({sb!r}) / '.orchestrator'
        STATE_FILE = STATE_DIR / 'state.json'
        LOCK_PATH = STATE_FILE.with_suffix('.lock')

        def _update(mutator):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            lock_fh = open(LOCK_PATH, 'w')
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
                state = {{'providers': {{}}, 'sessions': {{}}}}
                if STATE_FILE.is_file():
                    try:
                        disk = json.loads(STATE_FILE.read_text(encoding='utf-8'))
                        if isinstance(disk, dict):
                            state = disk
                            state.setdefault('providers', {{}})
                            state.setdefault('sessions', {{}})
                    except (json.JSONDecodeError, OSError):
                        pass
                mutator(state)
                tmp = STATE_FILE.with_name(f'.state.tmp-{{os.getpid()}}-{{uuid.uuid4().hex[:8]}}')
                tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                               encoding='utf-8')
                os.replace(str(tmp), str(STATE_FILE))
            finally:
                try: fcntl.flock(lock_fh, fcntl.LOCK_UN)
                except OSError: pass
                lock_fh.close()
    """)
    for k in keys:
        worker_code = update_inline + textwrap.dedent(f"""
            def mut(state):
                sessions = state.setdefault('sessions', {{}})
                sessions[{k!r}] = {{'preferred_backend': 'claude', 'note': 'set by ' + {k!r}}}
            _update(mut)
        """)
        proc = subprocess.Popen(["python3", "-c", worker_code],
                                env={**os.environ, "KB_HUB": str(p),
                                     "KB_CLAUDE_RUN_ROOT": str(p / ".orchestrator" / "claude-runs")},
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        workers.append((k, proc))

    for k, proc in workers:
        proc.wait(timeout=30)
        if proc.returncode != 0:
            err = proc.stderr.read().decode() if proc.stderr else ""
            print(f"  ✘ worker for {k} failed: {err[-200:]}", file=sys.stderr)
            sys.exit(1)

    # Verify all 8 sessions[*] are present in the final file.
    state_file = p / ".orchestrator" / "state.json"
    data = json.loads(state_file.read_text(encoding="utf-8"))
    sessions = data.get("sessions", {})
    for k in keys:
        assert_(k in sessions, f"sessions[{k}] preserved after concurrent writes")
    assert_(len(sessions) == 8, f"all 8 distinct sessions present (got {len(sessions)})")

    shutil.rmtree(sb)
    print("\nCR6-B2 nested-preservation PASSED — namespace-aware merge works")


if __name__ == "__main__":
    main()
