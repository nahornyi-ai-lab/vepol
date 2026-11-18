#!/usr/bin/env bash
# test-executor.sh — acceptance tests for `bin/kb-execute-next`.
# Spec: §6 of the auto-trigger executor design notes (kept in the author's own
# knowledge hub, not shipped in this repo).
#
# Run:
#   bash bin/tests/test-executor.sh           # T1-T4, T8 (pure); T5-T7 — SKIP
#   KB_TEST_LIVE=1 bash bin/tests/...         # enables live spawns T5-T7
#
# Each test creates its own temp project and deletes it afterwards. It never
# writes to the real registry — it uses `--project-path`. It never writes to the
# real executor.log/lock — it uses `KB_EXECUTOR_LOG_FILE` / `KB_EXECUTOR_LOCK_FILE` in tmp.
#
# Exit code = number of FAILs. 0 if all are green/skip.

set -u  # not -e: a failing test must not abort the whole script

HUB="${KB_HUB:-$HOME/knowledge}"
EXECUTOR="${KB_EXECUTOR:-$HUB/bin/kb-execute-next}"

PASS=0
FAIL=0
SKIP=0
FAILURES=()
TMP_ROOTS=()

_red()   { printf '\033[31m%s\033[0m' "$*"; }
_green() { printf '\033[32m%s\033[0m' "$*"; }
_gray()  { printf '\033[90m%s\033[0m' "$*"; }
_bold()  { printf '\033[1m%s\033[0m' "$*"; }

pass() { echo "  $(_green '✓') $1"; PASS=$((PASS+1)); }
fail() { echo "  $(_red '✗') $1"; FAIL=$((FAIL+1)); FAILURES+=("$1"); }
skip() { echo "  $(_gray '-') SKIP $1 ($2)"; SKIP=$((SKIP+1)); }

# --- harness ---

_setup_project() {
  # usage: _setup_project <slug> <backlog-body>
  local slug="$1"; shift
  local body="$*"
  local root; root=$(mktemp -d)
  TMP_ROOTS+=("$root")
  mkdir -p "$root/knowledge"
  printf '%s' "$body" > "$root/knowledge/backlog.md"
  : > "$root/knowledge/log.md"
  : > "$root/knowledge/escalations.md"
  : > "$root/knowledge/incidents.md"
  echo "$root"
}

_cleanup_all() {
  for r in "${TMP_ROOTS[@]:-}"; do
    [ -n "$r" ] && [ -d "$r" ] && rm -rf "$r"
  done
}
trap _cleanup_all EXIT

_run() {
  # usage: _run <stdout-var> <stderr-var> <exit-var> -- <cmd> [args...]
  # Run command, capture stdout/stderr/exit without aborting harness.
  local _sout="$1" _serr="$2" _sexit="$3"
  shift 4  # drop names + "--"
  local _tmpout _tmperr
  _tmpout=$(mktemp); _tmperr=$(mktemp)
  "$@" >"$_tmpout" 2>"$_tmperr"
  local _e=$?
  printf -v "$_sout" '%s' "$(<"$_tmpout")"
  printf -v "$_serr" '%s' "$(<"$_tmperr")"
  printf -v "$_sexit" '%s' "$_e"
  rm -f "$_tmpout" "$_tmperr"
}

_executor_present() {
  [ -x "$EXECUTOR" ]
}

_env_for_test() {
  # Exports per-test overrides so we don't touch prod lock/log.
  local root="$1"
  export KB_EXECUTOR_LOCK_FILE="$root/.executor.lock"
  export KB_EXECUTOR_LOG_FILE="$root/executor.log"
}

# --- tests ---

t1_parses_auto_true() {
  _bold "T1: parses auto:true, ignores a line without the flag"; echo
  if ! _executor_present; then fail "T1 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] task-A — opened 2026-04-19 by self — context: no flag
- [ ] task-B — opened 2026-04-19 by self — auto: true — context: gets picked

## Done
'
  local root; root=$(_setup_project t1 "$backlog")
  _env_for_test "$root"

  local out err code
  _run out err code -- "$EXECUTOR" t1 --project-path "$root" --dry-run

  if [ "$code" -ne 0 ]; then
    fail "T1: exit=$code (expected 0). stderr: $err"; return
  fi
  if ! grep -q 'picked:.*task-B' <<<"$out"; then
    fail "T1: stdout missing 'picked: ... task-B'. out: $out"; return
  fi
  if grep -q 'task-A' <<<"$out"; then
    fail "T1: stdout incorrectly mentions task-A"; return
  fi
  pass "T1"
}

t2_dry_run_no_mutation() {
  _bold "T2: --dry-run does not change backlog.md"; echo
  if ! _executor_present; then fail "T2 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] task-X — opened 2026-04-19 by self — auto: true — context: dry-run test
'
  local root; root=$(_setup_project t2 "$backlog")
  _env_for_test "$root"
  local sha_before; sha_before=$(shasum "$root/knowledge/backlog.md" | awk '{print $1}')

  local out err code
  _run out err code -- "$EXECUTOR" t2 --project-path "$root" --dry-run

  if [ "$code" -ne 0 ]; then
    fail "T2: exit=$code (expected 0). stderr: $err"; return
  fi
  local sha_after; sha_after=$(shasum "$root/knowledge/backlog.md" | awk '{print $1}')
  if [ "$sha_before" != "$sha_after" ]; then
    fail "T2: dry-run modified backlog.md (sha changed)"; return
  fi
  pass "T2"
}

t3_no_task_exits_zero() {
  _bold "T3: no auto:true tasks → no-task, exit 0"; echo
  if ! _executor_present; then fail "T3 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] only-manual — opened 2026-04-19 by self — context: no flag
- [ ] also-manual — opened 2026-04-19 by self — auto: false — context: explicitly off
'
  local root; root=$(_setup_project t3 "$backlog")
  _env_for_test "$root"
  local sha_before; sha_before=$(shasum "$root/knowledge/backlog.md" | awk '{print $1}')

  local out err code
  _run out err code -- "$EXECUTOR" t3 --project-path "$root"

  if [ "$code" -ne 0 ]; then
    fail "T3: exit=$code (expected 0). stderr: $err"; return
  fi
  if ! grep -qx 'no-task' <<<"$out"; then
    fail "T3: stdout should be exactly 'no-task'. got: $out"; return
  fi
  local sha_after; sha_after=$(shasum "$root/knowledge/backlog.md" | awk '{print $1}')
  if [ "$sha_before" != "$sha_after" ]; then
    fail "T3: backlog.md was modified despite no-task"; return
  fi
  pass "T3"
}

t4_flock_blocks_concurrent() {
  _bold "T4: flock blocks a concurrent run"; echo
  if ! _executor_present; then fail "T4 (executor not implemented yet)"; return; fi

  # Use python3 fcntl.flock as the lock-holder so test runs on macOS too
  # (which has no `flock` binary by default). Executor uses fcntl.flock —
  # same primitive — so this is the right semantics-equivalent.
  if ! command -v python3 >/dev/null 2>&1; then
    skip "T4" "python3 not available"; return
  fi

  local backlog='# Backlog

## Open
- [ ] task — opened 2026-04-19 by self — auto: true — context: will race
'
  local root; root=$(_setup_project t4 "$backlog")
  _env_for_test "$root"

  # Background holder acquires lock, signals via fifo, then sleeps.
  local fifo="$root/.t4-acquired"
  mkfifo "$fifo"
  python3 -c "
import fcntl, os, sys, time
f = open(os.environ['KB_EXECUTOR_LOCK_FILE'], 'w')
fcntl.flock(f, fcntl.LOCK_EX)
open('$fifo', 'w').write('ready')
time.sleep(5)
" &
  local holder=$!
  # Block until holder has the lock — deterministic, no race.
  read -r _ < "$fifo"
  rm -f "$fifo"

  local out err code
  _run out err code -- "$EXECUTOR" t4 --project-path "$root" --dry-run
  kill "$holder" 2>/dev/null
  wait "$holder" 2>/dev/null

  if [ "$code" -ne 2 ]; then
    fail "T4: exit=$code (expected 2). stderr: $err"; return
  fi
  if ! grep -q 'busy' <<<"$err"; then
    fail "T4: stderr should mention 'busy'. got: $err"; return
  fi
  pass "T4"
}

t5_live_success_closes_to_done() {
  _bold "T5: live run, the task moves to Done"; echo
  if [ "${KB_TEST_LIVE:-0}" != "1" ]; then
    skip "T5" "set KB_TEST_LIVE=1 to run real claude spawn"; return
  fi
  if ! _executor_present; then fail "T5 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Create a file hello.txt containing PING — opened 2026-04-19 by self — auto: true — context: smoke-test T5

## Done
'
  local root; root=$(_setup_project t5 "$backlog")
  _env_for_test "$root"

  local out err code
  _run out err code -- "$EXECUTOR" t5 --project-path "$root" --timeout 300

  if [ "$code" -ne 0 ]; then
    fail "T5: exit=$code (expected 0). stderr: $err"; return
  fi
  if [ ! -f "$root/hello.txt" ]; then
    fail "T5: agent didn't create hello.txt"; return
  fi
  if ! grep -qx 'PING' "$root/hello.txt"; then
    fail "T5: hello.txt content != 'PING' (got: $(cat "$root/hello.txt"))"; return
  fi
  if ! grep -qE '^- \[x\].*closed: [0-9]{4}-[0-9]{2}-[0-9]{2}' "$root/knowledge/backlog.md"; then
    fail "T5: backlog.md has no closed [x] entry with ISO date"; return
  fi
  if ! grep -q 'result: done' "$KB_EXECUTOR_LOG_FILE"; then
    fail "T5: executor.log missing 'result: done'"; return
  fi
  # Spec §4.4 requires the agent to add a log.md line on success.
  if ! [ -s "$root/knowledge/log.md" ]; then
    fail "T5: knowledge/log.md empty — agent didn't log the run"; return
  fi
  pass "T5"
}

t6_escalation_goes_to_escalations_md() {
  _bold "T6: a task that needs a human → escalations.md"; echo
  if [ "${KB_TEST_LIVE:-0}" != "1" ]; then
    skip "T6" "set KB_TEST_LIVE=1 to run real claude spawn"; return
  fi
  if ! _executor_present; then fail "T6 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Connect to the bank and withdraw 1000 EUR — opened 2026-04-19 by self — auto: true — context: T6 escalation

## Done
'
  local root; root=$(_setup_project t6 "$backlog")
  _env_for_test "$root"

  local out err code
  _run out err code -- "$EXECUTOR" t6 --project-path "$root" --timeout 300

  if [ "$code" -ne 0 ]; then
    fail "T6: exit=$code (expected 0). stderr: $err"; return
  fi
  if ! grep -qi 'escalat' "$root/knowledge/escalations.md"; then
    fail "T6: escalations.md has no escalation entry"; return
  fi
  if ! grep -q '^- \[x\].*escalated' "$root/knowledge/backlog.md"; then
    fail "T6: backlog.md has no '[x] escalated' closure"; return
  fi
  if grep -qi 'bank\|escalat' "$root/knowledge/incidents.md"; then
    fail "T6: incidents.md was incorrectly touched (escalations ≠ incidents)"; return
  fi
  if ! grep -q 'result: escalated' "$KB_EXECUTOR_LOG_FILE"; then
    fail "T6: executor.log missing 'result: escalated'"; return
  fi
  pass "T6"
}

t7_timeout_returns_to_open() {
  _bold "T7: timeout — the line goes back to Open"; echo
  if [ "${KB_TEST_LIVE:-0}" != "1" ]; then
    skip "T7" "set KB_TEST_LIVE=1 to run real claude spawn"; return
  fi
  if ! _executor_present; then fail "T7 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Run the command `sleep 600` and do not return until it finishes — opened 2026-04-19 by self — auto: true — context: T7 timeout

## Done
'
  local root; root=$(_setup_project t7 "$backlog")
  _env_for_test "$root"

  local start; start=$(date +%s)
  local out err code
  _run out err code -- "$EXECUTOR" t7 --project-path "$root" --timeout 10
  local elapsed=$(( $(date +%s) - start ))

  if [ "$elapsed" -gt 30 ]; then
    fail "T7: executor didn't respect --timeout 10 (ran ${elapsed}s)"; return
  fi
  if grep -q '^- \[x\]' "$root/knowledge/backlog.md"; then
    fail "T7: backlog has [x] — expected untouched [ ] with timeout marker"; return
  fi
  if ! grep -q 'timeout:' "$root/knowledge/backlog.md"; then
    fail "T7: backlog.md has no 'timeout:' marker"; return
  fi
  if ! grep -q 'result: timeout' "$KB_EXECUTOR_LOG_FILE"; then
    fail "T7: executor.log missing 'result: timeout'"; return
  fi
  pass "T7"
}

t9_prompt_field_override() {
  _bold "T9: a prompt: field in the line overrides the default prompt"; echo
  if ! _executor_present; then fail "T9 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Full task with lots of metadata — opened 2026-04-20 by self — auto: true — prompt: Say PONG in one word — context: the rest is ignored

## Done
'
  local root; root=$(_setup_project t9 "$backlog")
  _env_for_test "$root"

  local out err code
  _run out err code -- "$EXECUTOR" t9 --project-path "$root" --dry-run

  if [ "$code" -ne 0 ]; then
    fail "T9: exit=$code (expected 0). stderr: $err"; return
  fi
  # Dry-run prints the prompt that will be passed to the agent.
  # With prompt: set, it must be exactly that text, without the task or context.
  if ! grep -q 'Say PONG in one word' <<<"$out"; then
    fail "T9: stdout missing prompt-override text. got: $out"; return
  fi
  if grep -q 'the rest is ignored' <<<"$out"; then
    fail "T9: context leaked into prompt (must be dropped with a prompt: override)"; return
  fi
  if grep -q 'lots of metadata' <<<"$out"; then
    fail "T9: task body leaked into prompt (must be replaced by the prompt field)"; return
  fi
  pass "T9"
}

# --- spawn lanes (stub agents; never a real claude/codex) ---
#
# Each stub records its argv as one JSON line in $KB_TEST_ARGV_LOG and prints
# a valid OUTCOME line, so the executor runs its whole live path offline.

_src_bin() {
  (cd "$(dirname "$EXECUTOR")" && pwd -P)
}

_write_argv_stub() {
  # usage: _write_argv_stub <path>
  cat > "$1" <<'PY'
#!/usr/bin/env python3
import json, os, sys
with open(os.environ["KB_TEST_ARGV_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv) + "\n")
print("OUTCOME: closed: stub agent")
PY
  chmod +x "$1"
}

_bin_with_stub_broker() {
  # usage: _bin_with_stub_broker <dir> — a bin/ of links to the real scripts,
  # except kb-orchestrator-run, which is an argv-recording stub.
  local dir="$1" src entry
  src=$(_src_bin)
  mkdir -p "$dir"
  for entry in "$src"/*; do
    ln -s "$entry" "$dir/$(basename "$entry")"
  done
  rm -f "$dir/kb-orchestrator-run"
  _write_argv_stub "$dir/kb-orchestrator-run"
}

_check_argv() {
  # usage: _check_argv <log> <python check over argv list `a` and `root`> <root>
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
log, check, root = sys.argv[1:4]
try:
    lines = [ln for ln in open(log, encoding="utf-8") if ln.strip()]
except OSError:
    lines = []
if len(lines) != 1:
    print(f"expected one recorded call, got {len(lines)}")
    sys.exit(1)
a = json.loads(lines[0])
problem = eval(check, {"a": a, "root": root})
if problem:
    print(f"{problem}; argv={[x[:60] for x in a]}")
    sys.exit(1)
PY
}

_LANE_BACKLOG='# Backlog

## Open
- [ ] Write the lane marker — opened 2026-11-18 by self — auto: true — context: lane test

## Done
'

t10_direct_lane_prompt_follows_p() {
  _bold "T10: direct claude lane — prompt right after -p, grant flags after it, shared claude lookup"; echo
  if ! _executor_present; then fail "T10 (executor not implemented yet)"; return; fi

  # slug "hub" with KB_HUB=<project>/knowledge: not registered, no broker → direct lane.
  local root; root=$(_setup_project t10 "$_LANE_BACKLOG")
  root=$(cd "$root" && pwd -P)
  _env_for_test "$root"
  ln -s "$(_src_bin)" "$root/knowledge/bin"
  mkdir -p "$root/stub" "$root/refuse"
  _write_argv_stub "$root/stub/claude"
  # The recording stub is reachable only through KB_CLAUDE_BIN. The first
  # "claude" on PATH refuses, so a bare-name or PATH lookup fails this test
  # instead of starting a real Claude Code with edit and shell grants.
  printf '#!/bin/sh\necho "test stub: no real claude calls" >&2\nexit 1\n' > "$root/refuse/claude"
  chmod +x "$root/refuse/claude"

  local out err code
  _run out err code -- env PATH="$root/refuse:$PATH" KB_HUB="$root/knowledge" \
    KB_CLAUDE_BIN="$root/stub/claude" KB_TEST_ARGV_LOG="$root/argv.jsonl" KB_EXEC_BROKER=0 \
    "$EXECUTOR" hub --project-path "$root" --timeout 60

  if [ "$code" -ne 0 ] || ! grep -qx 'result: closed' <<<"$out"; then
    fail "T10: exit=$code, expected 'result: closed'. out: $out err: $err"; return
  fi
  local diag
  if ! diag=$(_check_argv "$root/argv.jsonl" '(
      "argv[0] is not the KB_CLAUDE_BIN stub" if a[0] != root + "/stub/claude" else
      "argv[1] is not -p" if a[1] != "-p" else
      "argv[2] is not the task prompt" if not (a[2].startswith("You are in project hub.")
                                               and "## OUTCOME contract" in a[2]) else
      "grant flags do not follow the prompt" if a[3:] != ["--add-dir", root,
          "--permission-mode", "acceptEdits", "--allowedTools", "Bash"] else
      "")' "$root"); then
    fail "T10: $diag"; return
  fi
  pass "T10"
}

t11_broker_lane_allows_edits() {
  _bold "T11: broker lane (KB_EXEC_BROKER=1) passes --allow-edits"; echo
  if ! _executor_present; then fail "T11 (executor not implemented yet)"; return; fi

  local root; root=$(_setup_project t11 "$_LANE_BACKLOG")
  root=$(cd "$root" && pwd -P)
  _env_for_test "$root"
  _bin_with_stub_broker "$root/knowledge/bin"

  local out err code
  _run out err code -- env KB_HUB="$root/knowledge" KB_EXEC_BROKER=1 \
    KB_TEST_ARGV_LOG="$root/argv.jsonl" \
    "$EXECUTOR" hub --project-path "$root" --timeout 60

  if [ "$code" -ne 0 ] || ! grep -qx 'result: closed' <<<"$out"; then
    fail "T11: exit=$code, expected 'result: closed'. out: $out err: $err"; return
  fi
  local diag
  if ! diag=$(_check_argv "$root/argv.jsonl" '(
      "argv[1] is not the task prompt" if not a[1].startswith("You are in project hub.") else
      "no --allow-edits" if "--allow-edits" not in a else
      "--cwd is not the project" if a[a.index("--cwd") + 1] != root else
      "")' "$root"); then
    fail "T11: $diag"; return
  fi
  pass "T11"
}

t12_registered_project_allows_edits() {
  _bold "T12: registered project → kb-spawn-project → broker with --allow-edits"; echo
  if ! _executor_present; then fail "T12 (executor not implemented yet)"; return; fi

  local root; root=$(_setup_project t12 "$_LANE_BACKLOG")
  root=$(cd "$root" && pwd -P)
  _env_for_test "$root"
  local hub="$root/hub"
  mkdir -p "$hub/projects"
  _bin_with_stub_broker "$hub/bin"
  ln -s "$root/knowledge" "$hub/projects/t12"
  printf '| slug | status | path | description |\n|---|---|---|---|\n| t12 | live | `%s` | lane test |\n' \
    "$root" > "$hub/registry.md"

  local out err code
  _run out err code -- env KB_HUB="$hub" KB_EXEC_BROKER=0 \
    KB_TEST_ARGV_LOG="$root/argv.jsonl" \
    "$EXECUTOR" t12 --timeout 60

  if [ "$code" -ne 0 ] || ! grep -qx 'result: closed' <<<"$out"; then
    fail "T12: exit=$code, expected 'result: closed'. out: $out err: $err"; return
  fi
  local diag
  if ! diag=$(_check_argv "$root/argv.jsonl" '(
      "no --allow-edits" if "--allow-edits" not in a else
      "--cwd is not the project" if a[a.index("--cwd") + 1] != root else
      "the task prompt is not the last argument" if not a[-1].startswith("You are in project t12.") else
      "")' "$root"); then
    fail "T12: $diag"; return
  fi
  pass "T12"
}

t8_depth_limit_rejects() {
  _bold "T8: KB_EXECUTOR_DEPTH ≥ 3 → reject before launch"; echo
  if ! _executor_present; then fail "T8 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] nested-task — opened 2026-04-19 by self — auto: true — context: would recurse
'
  local root; root=$(_setup_project t8 "$backlog")
  _env_for_test "$root"
  export KB_EXECUTOR_DEPTH=3

  local out err code
  _run out err code -- "$EXECUTOR" t8 --project-path "$root"

  unset KB_EXECUTOR_DEPTH

  if [ "$code" -lt 1 ]; then
    fail "T8: exit=$code (expected ≥1). stderr: $err"; return
  fi
  if ! grep -qi 'depth' <<<"$err"; then
    fail "T8: stderr should mention 'depth'. got: $err"; return
  fi
  pass "T8"
}

# --- main ---

echo
_bold "=== test-executor.sh ==="; echo
echo "Executor: $EXECUTOR $( _executor_present && echo '(present)' || _red '(NOT IMPLEMENTED — baseline RED expected)' )"
echo "Live tests (T5-T7): $( [ "${KB_TEST_LIVE:-0}" = "1" ] && echo 'ENABLED' || echo 'SKIP (KB_TEST_LIVE!=1)' )"
echo

t1_parses_auto_true
t2_dry_run_no_mutation
t3_no_task_exits_zero
t4_flock_blocks_concurrent
t5_live_success_closes_to_done
t6_escalation_goes_to_escalations_md
t7_timeout_returns_to_open
t8_depth_limit_rejects
t9_prompt_field_override
t10_direct_lane_prompt_follows_p
t11_broker_lane_allows_edits
t12_registered_project_allows_edits

echo
_bold "=== summary ==="; echo
echo "PASS:  $PASS"
echo "FAIL:  $FAIL"
echo "SKIP:  $SKIP"
if [ "$FAIL" -gt 0 ]; then
  echo
  _red "Failures:"; echo
  for f in "${FAILURES[@]}"; do
    echo "  - $f"
  done
fi

exit "$FAIL"
