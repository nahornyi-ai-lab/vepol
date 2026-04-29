#!/usr/bin/env bash
# test-executor.sh — acceptance tests для `bin/kb-execute-next`.
# Спека: ~/knowledge/concepts/auto-trigger-executor.md §6.
#
# Запуск:
#   bash bin/tests/test-executor.sh           # T1-T4, T8 (pure); T5-T7 — SKIP
#   KB_TEST_LIVE=1 bash bin/tests/...         # включает живые спавны T5-T7
#
# Каждый тест создаёт свой temp-проект и удаляет после. На реальный registry
# не пишет — использует `--project-path`. На реальный executor.log/lock — не пишет,
# использует `KB_EXECUTOR_LOG_FILE` / `KB_EXECUTOR_LOCK_FILE` в tmp.
#
# Exit code = число FAIL. 0 если все зелёные/skip.

set -u  # не -e: ошибка в тесте не должна валить весь скрипт

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
  _bold "T1: парсит auto:true, игнорирует строку без флага"; echo
  if ! _executor_present; then fail "T1 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] task-A — opened 2026-04-19 by self — context: нет флага
- [ ] task-B — opened 2026-04-19 by self — auto: true — context: забирается

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
  _bold "T2: --dry-run не меняет backlog.md"; echo
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
  _bold "T3: нет auto:true задач → no-task, exit 0"; echo
  if ! _executor_present; then fail "T3 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] only-manual — opened 2026-04-19 by self — context: нет флага
- [ ] also-manual — opened 2026-04-19 by self — auto: false — context: явно выключено
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
  _bold "T4: flock блокирует конкурентный запуск"; echo
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
  _bold "T5: live-запуск, задача уезжает в Done"; echo
  if [ "${KB_TEST_LIVE:-0}" != "1" ]; then
    skip "T5" "set KB_TEST_LIVE=1 to run real claude spawn"; return
  fi
  if ! _executor_present; then fail "T5 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Создай файл hello.txt с содержимым PING — opened 2026-04-19 by self — auto: true — context: smoke-test T5

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
  _bold "T6: задача требующая человека → escalations.md"; echo
  if [ "${KB_TEST_LIVE:-0}" != "1" ]; then
    skip "T6" "set KB_TEST_LIVE=1 to run real claude spawn"; return
  fi
  if ! _executor_present; then fail "T6 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Подключись к банку и сними 1000 EUR — opened 2026-04-19 by self — auto: true — context: T6 escalation

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
  _bold "T7: timeout — строка возвращается в Open"; echo
  if [ "${KB_TEST_LIVE:-0}" != "1" ]; then
    skip "T7" "set KB_TEST_LIVE=1 to run real claude spawn"; return
  fi
  if ! _executor_present; then fail "T7 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Выполняй команду `sleep 600` и не возвращайся пока не закончится — opened 2026-04-19 by self — auto: true — context: T7 timeout

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
  _bold "T9: поле prompt: в строке переопределяет дефолтный prompt"; echo
  if ! _executor_present; then fail "T9 (executor not implemented yet)"; return; fi

  local backlog='# Backlog

## Open
- [ ] Полная задача с кучей метаданных — opened 2026-04-20 by self — auto: true — prompt: Скажи PONG одним словом — context: остальное игнорируется

## Done
'
  local root; root=$(_setup_project t9 "$backlog")
  _env_for_test "$root"

  local out err code
  _run out err code -- "$EXECUTOR" t9 --project-path "$root" --dry-run

  if [ "$code" -ne 0 ]; then
    fail "T9: exit=$code (expected 0). stderr: $err"; return
  fi
  # Dry-run выводит prompt, который будет передан агенту.
  # При заданном prompt: — должен быть ровно его текст, без задачи и контекста.
  if ! grep -q 'Скажи PONG одним словом' <<<"$out"; then
    fail "T9: stdout missing prompt-override text. got: $out"; return
  fi
  if grep -q 'остальное игнорируется' <<<"$out"; then
    fail "T9: context leaked into prompt (должен быть пропущен при prompt:-override)"; return
  fi
  if grep -q 'куча метаданных' <<<"$out"; then
    fail "T9: task body leaked into prompt (должен быть заменён prompt-полем)"; return
  fi
  pass "T9"
}

t8_depth_limit_rejects() {
  _bold "T8: KB_EXECUTOR_DEPTH ≥ 3 → reject до запуска"; echo
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
