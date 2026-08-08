#!/usr/bin/env bash
# RED-first integration tests for local Qwen daily/retro audio delivery.
# Contracts:
# - delivery: spec-contract:sha256:4d1e9ea4e8d09c3725739f269407c63200d4d6dd40489f6b35e87533b7467fd4
# - v0.6 freshness/release: spec-contract:sha256:bf26a39bdd96df0e8e4c7c0fd588ade5a23f5d73bfd4eb740eb4016d15e57752
# - selector: spec-contract:sha256:64c99d1d0e31cc701bcedcbe371b603ef179991db5ab508a17abb31ea8d99062

set -uo pipefail

PASS=0
FAIL=0
TMP=$(mktemp -d)
SRC_BIN="${KB_DIGEST_SRC_BIN:-$HOME/knowledge/bin}"
DIGEST="$SRC_BIN/kb-morning-digest"
NOVEPOL="$TMP/no-vepol"
mkdir -p "$NOVEPOL"

cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
ok() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
bad() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

make_hub() {
  local hub="$1"
  mkdir -p "$hub/bin" "$hub/personal" "$hub/reports" "$hub/.orchestrator" "$hub/briefs" "$hub/logs" "$hub/tts"
  : >"$hub/log.md"
  : >"$hub/personal/.secrets"
  printf '{"fixture":true}\n' >"$hub/tts/install.json"

  cat >"$hub/bin/kb-idea" <<'SH'
#!/usr/bin/env bash
[[ -n "${KB_FAKE_GATHER_LOG:-}" ]] && echo idea >>"$KB_FAKE_GATHER_LOG"
if [[ -s "${KB_HUB:?}/idea.txt" ]]; then cat "$KB_HUB/idea.txt"; else echo '(нет идей)'; fi
SH
  # D6 (morning-digest-inputs-rebalance-2026-07-11): the board block now calls
  # `kb-board list <board> --all --json`. This fake emits a valid JSON array whose
  # single task title carries the board.txt content, so a board change still
  # surfaces in the packet (semantic-snapshot test) via the JSON path.
  cat >"$hub/bin/kb-board" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"--json"* ]]; then
  if [[ -s "${KB_HUB:?}/board.txt" ]]; then
    python3 -c 'import json,sys;print(json.dumps([{"status":"Ready","title":open(sys.argv[1]).read().strip(),"plan_item_id":"t1"}]))' "$KB_HUB/board.txt"
  else
    echo '[]'
  fi
else
  if [[ -s "${KB_HUB:?}/board.txt" ]]; then cat "$KB_HUB/board.txt"; else echo '(нет задач)'; fi
fi
SH
  cat >"$hub/bin/kb-mail-block" <<'SH'
#!/usr/bin/env bash
if [[ -s "${KB_HUB:?}/mail.txt" ]]; then cat "$KB_HUB/mail.txt"; else echo 'MAIL (morning): no fresh mail brief for today. Proceed without mail.'; fi
SH
  cat >"$hub/bin/claude" <<'SH'
#!/usr/bin/env bash
prompt="${2:-}"
marker=$(printf '%s' "$prompt" | grep -o 'SNAPSHOT_[A-Z0-9_]*' | tail -1 || true)
cat <<EOF
## Утро: коротко о главном

Это тестовая синтезированная сводка для проверки снимка входных данных. Она намеренно длиннее двухсот символов, чтобы пройти минимальный контракт синтезатора без обращения к реальной модели.

## Деньги и возможности

Последний наблюдаемый маркер источника: ${marker:-SNAPSHOT_EMPTY}. Все остальные предложения являются стабильной тестовой рамкой и не меняются между запусками.

## Что предлагаю сделать сегодня

Проверить, что новый вход создаёт ровно одну новую доставку, а неизменившийся вход не вызывает повторную отправку.
EOF
SH
  cat >"$hub/bin/kb-tts-render" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
if [[ "${1:-}" == "--check" ]]; then
  if [[ -f "${KB_TTS_HOME:?}/install.json" ]]; then
    echo '{"ready": true, "engine": "qwen"}'
    exit 0
  fi
  echo '{"ready": false, "engine": "qwen", "error": "local Qwen runtime/marker unavailable; run kb-tts-install"}'
  exit 3
fi
echo "$*" >>"$KB_FAKE_RENDER_LOG"
in=''; out=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --file) in="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[[ "${KB_FAKE_RENDER_MODE:-success}" == failure ]] && exit 7
[[ -s "$in" && -n "$out" ]] || exit 8
if [[ "${KB_FAKE_RENDER_MODE:-success}" == slow ]]; then
  sleep 300 & child=$!
  printf '%s %s\n' "$$" "$child" >"$KB_FAKE_RENDER_PIDS"
  stop() { kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; exit 143; }
  trap stop TERM INT
  wait "$child"
fi
printf 'ID3-local-qwen-test-audio:%s' "$(shasum -a 256 "$in" | awk '{print $1}')" >"$out"
SH
  cat >"$hub/bin/kb-channel-send-audio" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "$(shasum -a 256 "$2" | awk '{print $1}')" >>"$KB_FAKE_SEND_LOG"
case "${KB_FAKE_SEND_MODE:-success}" in
  reject)
    echo '{"outcome":"known_rejection","error":"fixture rejection"}'
    exit 20
    ;;
  ambiguous)
    echo '{"outcome":"ambiguous","error":"fixture disconnect"}'
    exit 21
    ;;
  success)
    echo '{"outcome":"success","message_id":9001,"audio":{"file_id":"f1","file_unique_id":"u1","duration":23,"file_name":"digest.mp3","mime_type":"audio/mpeg","file_size":77}}'
    ;;
esac
SH
  cat >"$hub/bin/notebooklm" <<'SH'
#!/usr/bin/env bash
echo "NOTEBOOKLM_CALLED $*" >>"$KB_FAKE_NOTEBOOKLM_LOG"
[[ "${KB_FAKE_NOTEBOOKLM_MODE:-failure}" == success ]] || exit 99
case "$1 ${2:-}" in
  "list --json") echo '{"notebooks":[]}' ;;
  "create "*) echo '{"id":"nb-selector"}' ;;
  "source add") echo '{"source_id":"src-selector"}' ;;
  "source wait") echo 'source wait must not be called' >&2; exit 9 ;;
  "generate audio")
    case "${KB_FAKE_NOTEBOOKLM_ACK_KIND:-artifact}" in
      task) echo '{"task_id":"task-selector"}' ;;
      artifact) echo '{"artifact_id":"audio-selector"}' ;;
      id) echo '{"id":"generic-selector"}' ;;
      empty) echo '{}' ;;
      malformed) echo 'not-json' ;;
      reject) echo 'fixture auth/rejection' >&2; exit 8 ;;
      kill)
        kill -KILL "$PPID"
        sleep 1
        ;;
      *) echo 'unknown KB_FAKE_NOTEBOOKLM_ACK_KIND' >&2; exit 9 ;;
    esac
    ;;
  *) echo '{}' ;;
esac
SH
  chmod +x "$hub/bin/"*
}

run_digest() {
  local hub="$1"; shift
  KB_HUB="$hub" KB_VEPOL_DEV="$NOVEPOL" KB_MORNING_SYNTH_AGENTS=none \
  KB_NOTEBOOKLM_BIN="$hub/bin/notebooklm" KB_FAKE_RENDER_LOG="$hub/render.log" \
  KB_TTS_HOME="$hub/tts" \
  KB_FAKE_SEND_LOG="$hub/send.log" KB_FAKE_GATHER_LOG="$hub/gather.log" \
  KB_FAKE_NOTEBOOKLM_LOG="$hub/notebooklm.log" \
    "$DIGEST" "$@"
}

run_digest_synth() {
  local hub="$1"; shift
  KB_HUB="$hub" KB_VEPOL_DEV="${KB_TEST_VEPOL_DEV:-$NOVEPOL}" KB_MORNING_SYNTH_AGENTS=claude \
  KB_CLAUDE_BIN="$hub/bin/claude" KB_MORNING_SYNTH_MODEL='' \
  KB_NOTEBOOKLM_BIN="$hub/bin/notebooklm" KB_FAKE_RENDER_LOG="$hub/render.log" \
  KB_TTS_HOME="$hub/tts" \
  KB_FAKE_SEND_LOG="$hub/send.log" KB_FAKE_GATHER_LOG="$hub/gather.log" \
  KB_FAKE_NOTEBOOKLM_LOG="$hub/notebooklm.log" \
    "$DIGEST" "$@"
}

run_scheduled_synth() {
  local hub="$1"
  KB_PROCESS_BACKGROUND=1 KB_PROCESS_ID=morning-digest \
  KB_PROCESS_OUTPUTS=file,telegram_audio run_digest_synth "$hub"
}

run_scheduled_notebooklm_synth() {
  local hub="$1"; shift
  KB_FAKE_NOTEBOOKLM_MODE=success KB_PROCESS_BACKGROUND=1 \
  KB_PROCESS_ID=morning-digest KB_PROCESS_OUTPUTS=file,notebooklm_audio \
    run_digest_synth "$hub" "$@"
}

run_scheduled_both_synth() {
  local hub="$1"
  KB_FAKE_NOTEBOOKLM_MODE=success KB_PROCESS_BACKGROUND=1 \
  KB_PROCESS_ID=morning-digest \
  KB_PROCESS_OUTPUTS=file,telegram_audio,notebooklm_audio \
    run_digest_synth "$hub"
}

json_check() {
  local file="$1" expr="$2" label="$3"
  if python3 - "$file" "$expr" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert eval(sys.argv[2], {"__builtins__": {}}, {"d": d})
PY
  then ok "$label"; else bad "$label"; fi
}

BODY="$TMP/body.md"
cat >"$BODY" <<'EOF'
## Главное

Сегодня **готово**. [Ссылка](https://example.com/x) для озвучки не нужна.

- Сделать один конкретный шаг.

Смотри [[План|knowledge/decisions/private-plan.md]], [[knowledge/decisions/secret-note.md]] и [локальную заметку](knowledge/solutions/private.md).
EOF

# ── 1. Happy path: report -> speech -> Qwen MP3 -> Telegram ────────────────
H="$TMP/happy"; D=2026-07-11; make_hub "$H"
run_digest "$H" --date "$D" --digest-file "$BODY" >"$H/stdout" 2>"$H/stderr"; RC=$?
[[ $RC -eq 0 ]] && ok "happy path exits 0" || bad "happy path exits 0 (rc=$RC)"
for ext in md txt mp3; do
  [[ -s "$H/reports/morning-digest-$D.$ext" ]] && ok "happy path writes non-empty .$ext" || bad "happy path writes non-empty .$ext"
done
M="$H/.orchestrator/morning-digest-$D.json"
json_check "$M" 'd["delivery"] == "local_qwen_telegram" and d["status"] == "completed" and d["retry_disposition"] == "terminal"' "manifest completes under local delivery tag"
json_check "$M" 'd["attempts"] == {"build": 1, "tts": 1, "telegram": 1, "total": 3} and d["caps"] == {"build": 2, "tts": 2, "telegram": 3, "total": 5}' "exact counters and immutable caps are persisted"
json_check "$M" 'd["telegram"]["message_id"] == 9001 and d["telegram"]["audio"]["file_id"] == "f1" and d["telegram"]["audio"]["file_unique_id"] == "u1" and d["telegram"]["audio"]["duration"] == 23' "normalized Telegram audio metadata is durable"
python3 - "$H" "$D" <<'PY' && ok "manifest paths/hashes match canonical private artifacts" || bad "manifest paths/hashes match canonical private artifacts"
import hashlib, json, os, pathlib, stat, sys
h, day = pathlib.Path(sys.argv[1]), sys.argv[2]
m = json.loads((h / ".orchestrator" / f"morning-digest-{day}.json").read_text())
for key, ext in (("report_path","md"),("speech_path","txt"),("audio_path","mp3")):
    p = h / m[key]
    assert p == h / "reports" / f"morning-digest-{day}.{ext}"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
speech = h / m["speech_path"]; audio = h / m["audio_path"]
assert hashlib.sha256(speech.read_bytes()).hexdigest() == m["speech_sha256"]
assert hashlib.sha256(audio.read_bytes()).hexdigest() == m["audio_sha256"]
assert stat.S_IMODE((h / ".orchestrator" / f"morning-digest-{day}.json").stat().st_mode) == 0o600
PY
SPEECH=$(cat "$H/reports/morning-digest-$D.txt" 2>/dev/null)
[[ "$SPEECH" == *"Главное"* && "$SPEECH" == *"Сегодня готово"* && "$SPEECH" == *"Сделать один конкретный шаг"* \
   && "$SPEECH" != *"NotebookLM"* && "$SPEECH" != *"Источники"* && "$SPEECH" != *"https://"* \
   && "$SPEECH" != *"**"* && "$SPEECH" != *"##"* && "$SPEECH" != *"knowledge/"* \
   && "$SPEECH" != *".md"* && "$SPEECH" != *"[["* && "$SPEECH" == *"План"* \
   && "$SPEECH" == *"secret note"* && "$SPEECH" == *"локальную заметку"* ]] \
  && ok "speech is deterministic body-only plain text" || bad "speech contains markup/source appendix or lost body"
[[ $(wc -l <"$H/render.log" 2>/dev/null) -eq 1 && $(wc -l <"$H/send.log" 2>/dev/null) -eq 1 ]] \
  && ok "happy path invokes renderer and sender exactly once" || bad "unexpected happy-path call count"
[[ ! -s "$H/notebooklm.log" ]] && ok "happy path makes zero NotebookLM calls" || bad "NotebookLM was called"

# Completed rerun is a pre-gather no-op and preserves all frozen artifacts.
: >"$H/gather.log"; : >"$H/render.log"; : >"$H/send.log"
DONE_HASHES_BEFORE=$(shasum -a 256 "$H/reports/morning-digest-$D.md" \
  "$H/reports/morning-digest-$D.txt" "$H/reports/morning-digest-$D.mp3" "$M")
run_digest "$H" --date "$D" >"$H/rerun-out" 2>"$H/rerun-err"; RC=$?
DONE_HASHES_AFTER=$(shasum -a 256 "$H/reports/morning-digest-$D.md" \
  "$H/reports/morning-digest-$D.txt" "$H/reports/morning-digest-$D.mp3" "$M")
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" \
   && "$DONE_HASHES_BEFORE" == "$DONE_HASHES_AFTER" ]] \
  && ok "completed rerun is a byte-preserving pre-gather no-op" \
  || bad "completed rerun repeated an external stage"

# Even a background invocation with a non-allowlisted argv remains a completed
# no-op; the guard may not rewrite canonical report/speech before it exits.
KB_PROCESS_BACKGROUND=1 KB_PROCESS_ID=morning-digest \
  KB_PROCESS_OUTPUTS=file,telegram_audio run_digest "$H" --date "$D" \
  >"$H/guard-rerun-out" 2>"$H/guard-rerun-err"; GUARD_RC=$?
GUARD_HASHES_AFTER=$(shasum -a 256 "$H/reports/morning-digest-$D.md" \
  "$H/reports/morning-digest-$D.txt" "$H/reports/morning-digest-$D.mp3" "$M")
[[ $GUARD_RC -eq 0 && "$DONE_HASHES_BEFORE" == "$GUARD_HASHES_AFTER" ]] \
  && ok "completed background argv mismatch cannot rewrite frozen artifacts" \
  || bad "completed background guard path mutated frozen artifacts"

# Explicit owner force reuses only verified speech, resets new counters, and
# deliberately rerenders/resends without gathering.
: >"$H/gather.log"; : >"$H/render.log"; : >"$H/send.log"
run_digest "$H" --date "$D" --force >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && $(wc -l <"$H/render.log") -eq 1 && $(wc -l <"$H/send.log") -eq 1 ]] \
  && ok "--force rerenders/resends verified speech without gather" || bad "--force recovery path is wrong"
json_check "$M" 'd["status"] == "completed" and d["attempts"] == {"build":0,"tts":1,"telegram":1,"total":2}' "--force resets stage counters"

# Corrupt audio with verified speech rerenders only; it must not rebuild text.
printf 'tampered-audio' >"$H/reports/morning-digest-$D.mp3"
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d["status"]="tts_rendered"; d["retry_disposition"]="retryable"; d["failed_stage"]=None
open(p,"w").write(json.dumps(d))
PY
: >"$H/gather.log"; : >"$H/render.log"; : >"$H/send.log"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && $(wc -l <"$H/render.log") -eq 1 && $(wc -l <"$H/send.log") -eq 1 ]] \
  && ok "audio corruption rerenders verified speech only" || bad "audio corruption triggered wrong recovery"

# Corrupt speech is never rebuilt/sent implicitly; owner force is required.
H="$TMP/speech-corrupt"; D=2026-07-24; make_hub "$H"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1
M="$H/.orchestrator/morning-digest-$D.json"
printf 'tamper' >>"$H/reports/morning-digest-$D.txt"
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d["status"]="tts_rendered"; d["retry_disposition"]="retryable"; d["failed_stage"]=None
open(p,"w").write(json.dumps(d))
PY
: >"$H/gather.log"; : >"$H/render.log"; : >"$H/send.log"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "speech corruption makes zero implicit external calls" || bad "speech corruption was rebuilt or sent"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "integrity" and d["retry_disposition"] == "force_required"' "speech corruption requires force"

# Missing sender is a terminal actionable install failure, never an unbounded
# retry with unchanged telegram counters.
H="$TMP/missing-sender"; D=2026-07-27; make_hub "$H"; rm "$H/bin/kb-channel-send-audio"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -eq 0 && -s "$H/reports/morning-digest-$D.mp3" ]] \
  && ok "missing sender terminates after keeping rendered MP3" || bad "missing sender failure contract is wrong"
json_check "$M" 'd["status"] == "unavailable" and d["failed_stage"] == "telegram" and d["retry_disposition"] == "terminal" and d["attempts"] == {"build":1,"tts":1,"telegram":0,"total":2}' "missing sender cannot create an unbounded retry"
: >"$H/gather.log"; : >"$H/render.log"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" ]] \
  && ok "missing-sender terminal rerun makes zero calls" || bad "missing-sender terminal state retried"

# Unknown semantic state, boolean counters and altered caps fail closed before
# every stage, but one explicit --force must reset the corrupt schema and recover.
for CASE in unknown-state bool-counter bad-caps; do
  H="$TMP/$CASE"; D=2026-07-28
  [[ "$CASE" == bool-counter ]] && D=2026-07-29
  [[ "$CASE" == bad-caps ]] && D=2026-08-01
  make_hub "$H"; M="$H/.orchestrator/morning-digest-$D.json"
  if [[ "$CASE" == unknown-state ]]; then
    STATUS=mystery; BUILD=0; BUILD_CAP=2
  elif [[ "$CASE" == bad-caps ]]; then
    STATUS=started; BUILD=0; BUILD_CAP=99
  else
    STATUS=started; BUILD=true; BUILD_CAP=2
  fi
  cat >"$M" <<EOF
{"delivery":"local_qwen_telegram","date":"$D","period":"morning","status":"$STATUS","retry_disposition":"retryable","failed_stage":null,"attempts":{"build":$BUILD,"tts":0,"telegram":0,"total":0},"caps":{"build":$BUILD_CAP,"tts":2,"telegram":3,"total":5},"report_path":"reports/morning-digest-$D.md","speech_path":"reports/morning-digest-$D.txt","audio_path":"reports/morning-digest-$D.mp3"}
EOF
  run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
    && ok "$CASE manifest fails closed before stages" || bad "$CASE manifest performed work"
  json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "integrity" and d["retry_disposition"] == "force_required"' "$CASE manifest requires force"
  run_digest "$H" --date "$D" --force --digest-file "$BODY" >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 && $(wc -l <"$H/render.log") -eq 1 && $(wc -l <"$H/send.log") -eq 1 ]] \
    && ok "$CASE recovers with one explicit force" || bad "$CASE force recovery stayed blocked"
  json_check "$M" 'd["status"] == "completed" and d["attempts"] == {"build":1,"tts":1,"telegram":1,"total":3} and d["caps"] == {"build":2,"tts":2,"telegram":3,"total":5}' "$CASE force restores exact schema"
done

# Failed manifests must agree with their stage and retry disposition.  Any
# mismatch is integrity corruption and must never resume gather/TTS/Telegram.
for CASE in integrity-retryable manifest-terminal build-force build-terminal unknown-failed-stage; do
  H="$TMP/failed-semantic-$CASE"; D=2026-07-30; make_hub "$H"
  M="$H/.orchestrator/morning-digest-$D.json"
  case "$CASE" in
    integrity-retryable) STAGE=integrity; DISP=retryable ;;
    manifest-terminal) STAGE=manifest; DISP=terminal ;;
    build-force) STAGE=build; DISP=force_required ;;
    build-terminal) STAGE=build; DISP=terminal ;;
    unknown-failed-stage) STAGE=mystery; DISP=retryable ;;
  esac
  cat >"$M" <<EOF
{"delivery":"local_qwen_telegram","date":"$D","period":"morning","status":"failed","retry_disposition":"$DISP","failed_stage":"$STAGE","attempts":{"build":0,"tts":0,"telegram":0,"total":0},"caps":{"build":2,"tts":2,"telegram":3,"total":5},"report_path":"reports/morning-digest-$D.md","speech_path":"reports/morning-digest-$D.txt","audio_path":"reports/morning-digest-$D.mp3"}
EOF
  run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
    && ok "$CASE failed manifest makes zero stage calls" || bad "$CASE failed manifest performed work"
  json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "integrity" and d["retry_disposition"] == "force_required"' "$CASE failed manifest is rewritten fail-closed"
done

# A failed stage is terminal only when its own or total attempt cap is reached.
H="$TMP/failed-semantic-at-cap"; D=2026-07-31; make_hub "$H"
M="$H/.orchestrator/morning-digest-$D.json"
cat >"$M" <<EOF
{"delivery":"local_qwen_telegram","date":"$D","period":"morning","status":"failed","retry_disposition":"terminal","failed_stage":"tts","attempts":{"build":1,"tts":2,"telegram":0,"total":3},"caps":{"build":2,"tts":2,"telegram":3,"total":5},"report_path":"reports/morning-digest-$D.md","speech_path":"reports/morning-digest-$D.txt","audio_path":"reports/morning-digest-$D.mp3"}
EOF
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "at-cap failed manifest remains terminal without calls" || bad "at-cap failed manifest performed work"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "tts" and d["retry_disposition"] == "terminal"' "at-cap terminal failed manifest remains valid"

# ── 2. Known Telegram rejection retries delivery only ──────────────────────
H="$TMP/retry"; D=2026-07-12; make_hub "$H"
KB_FAKE_SEND_MODE=reject run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
[[ $RC -ne 0 ]] && ok "known rejection returns non-zero before cap" || bad "known rejection did not request retry"
M="$H/.orchestrator/morning-digest-$D.json"
json_check "$M" 'd["status"] == "telegram_failed" and d["failed_stage"] == "telegram" and d["retry_disposition"] == "retryable" and d["attempts"] == {"build":1,"tts":1,"telegram":1,"total":3}' "known rejection records retryable Telegram state"
: >"$H/gather.log"; : >"$H/render.log"
KB_FAKE_SEND_MODE=success run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && $(wc -l <"$H/send.log") -eq 2 ]] \
  && ok "Telegram retry sends original MP3 without gather/rerender" || bad "Telegram retry repeated an earlier stage"
json_check "$M" 'd["status"] == "completed" and d["attempts"] == {"build":1,"tts":1,"telegram":2,"total":4}' "Telegram retry owns only its counter"

# ── 3. Interrupted/failed TTS resumes report_ready before gather ───────────
H="$TMP/tts-retry"; D=2026-07-13; make_hub "$H"
KB_FAKE_RENDER_MODE=failure run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
[[ $RC -ne 0 ]] && ok "TTS failure returns non-zero before cap" || bad "TTS failure did not request retry"
M="$H/.orchestrator/morning-digest-$D.json"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "tts" and d["retry_disposition"] == "retryable" and d["attempts"] == {"build":1,"tts":1,"telegram":0,"total":2}' "TTS failure has exact stage/counters"
: >"$H/gather.log"; : >"$H/send.log"
KB_FAKE_RENDER_MODE=success run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && $(wc -l <"$H/render.log") -eq 2 && $(wc -l <"$H/send.log") -eq 1 ]] \
  && ok "TTS retry uses stored speech before gather and then sends" || bad "TTS retry did not resume report_ready"
json_check "$M" 'd["status"] == "completed" and d["attempts"] == {"build":1,"tts":2,"telegram":1,"total":4}' "TTS retry owns only TTS + Telegram counters"

# A digest-level TERM must reach the renderer, reap its child, keep report_ready,
# and resume from stored speech without a second build.
H="$TMP/interrupted"; D=2026-07-23; make_hub "$H"; PIDS="$H/render-pids"
KB_HUB="$H" KB_VEPOL_DEV="$NOVEPOL" KB_MORNING_SYNTH_AGENTS=none \
KB_NOTEBOOKLM_BIN="$H/bin/notebooklm" KB_TTS_HOME="$H/tts" \
KB_FAKE_RENDER_LOG="$H/render.log" KB_FAKE_SEND_LOG="$H/send.log" \
KB_FAKE_GATHER_LOG="$H/gather.log" KB_FAKE_NOTEBOOKLM_LOG="$H/notebooklm.log" \
KB_FAKE_RENDER_MODE=slow KB_FAKE_RENDER_PIDS="$PIDS" \
  "$DIGEST" --date "$D" --digest-file "$BODY" >/dev/null 2>&1 & DIGEST_PID=$!
for _ in $(seq 1 100); do [[ -s "$PIDS" ]] && break; sleep 0.05; done
if [[ -s "$PIDS" ]]; then
  read -r RENDER_PID CHILD_PID <"$PIDS"
  kill -TERM "$DIGEST_PID" 2>/dev/null || true
  wait "$DIGEST_PID" 2>/dev/null; RC=$?
  sleep 0.15
  ALIVE=0
  kill -0 "$RENDER_PID" 2>/dev/null && ALIVE=1
  kill -0 "$CHILD_PID" 2>/dev/null && ALIVE=1
  [[ $RC -ne 0 && $ALIVE -eq 0 && ! -e "$H/reports/morning-digest-$D.mp3" ]] \
    && ok "TERM reaps digest renderer tree and leaves no final MP3" \
    || bad "TERM cleanup failed (rc=$RC alive=$ALIVE)"
else
  bad "slow digest reached renderer"
  kill -KILL "$DIGEST_PID" 2>/dev/null || true; wait "$DIGEST_PID" 2>/dev/null || true
fi
M="$H/.orchestrator/morning-digest-$D.json"
json_check "$M" 'd["status"] == "report_ready" and d["attempts"] == {"build":1,"tts":1,"telegram":0,"total":2}' "interrupted render leaves resumable report_ready state"
: >"$H/gather.log"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" ]] \
  && ok "post-interruption retry resumes before gather" || bad "post-interruption retry rebuilt context"
json_check "$M" 'd["status"] == "completed" and d["attempts"] == {"build":1,"tts":2,"telegram":1,"total":4}' "post-interruption retry completes with exact counters"

# ── 4. Ambiguous upload is force-required and never auto-resends ───────────
H="$TMP/ambiguous"; D=2026-07-14; make_hub "$H"
KB_FAKE_SEND_MODE=ambiguous run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "ambiguous delivery exits 0 to stop scheduler loop" || bad "ambiguous delivery rc=$RC"
M="$H/.orchestrator/morning-digest-$D.json"
json_check "$M" 'd["status"] == "telegram_ambiguous" and d["failed_stage"] == "telegram" and d["retry_disposition"] == "force_required"' "ambiguous delivery is durably force-required"
: >"$H/gather.log"; : >"$H/render.log"; BEFORE=$(wc -l <"$H/send.log")
KB_FAKE_SEND_MODE=success run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
AFTER=$(wc -l <"$H/send.log")
[[ $RC -eq 0 && $BEFORE -eq $AFTER && ! -s "$H/gather.log" && ! -s "$H/render.log" ]] \
  && ok "ambiguous rerun makes zero automatic external calls" || bad "ambiguous upload was auto-retried"

# Restart left in telegram_sending is equally ambiguous and sends nothing.
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d["status"]="telegram_sending"; d["retry_disposition"]="retryable"
open(p,"w").write(json.dumps(d))
PY
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && $(wc -l <"$H/send.log") -eq $AFTER ]] \
  && ok "restart in telegram_sending becomes ambiguous without resend" || bad "telegram_sending restart duplicated upload"

# ── 5. Foreign and malformed manifests ─────────────────────────────────────
H="$TMP/foreign"; D=2026-07-15; make_hub "$H"
printf '%s\n' '{"status":"completed","attempts":99,"artifact_id":"old-art","notebook_id":"old-nb"}' >"$H/.orchestrator/morning-digest-$D.json"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -eq 0 && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "completed-looking foreign manifest fails closed before adapters" \
  || bad "foreign completed manifest reached local delivery"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "integrity" and d["retry_disposition"] == "force_required" and d["completion_evidence_invalid"] is True and d["artifact_id"] == "old-art"' "foreign completion retains diagnostics and requires force"

H="$TMP/corrupt"; D=2026-07-16; make_hub "$H"
printf '{not-json' >"$H/.orchestrator/morning-digest-$D.json"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -eq 0 && ! -s "$H/render.log" && ! -s "$H/send.log" && $(find "$H/.orchestrator" -name 'morning-digest-*.json.corrupt-*' | wc -l | tr -d ' ') -eq 1 ]] \
  && ok "malformed manifest fails closed and preserves corrupt bytes" || bad "malformed manifest called external stage or lost evidence"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "manifest" and d["retry_disposition"] == "force_required"' "malformed manifest requires force"

# ── 6. Cap, optional runtime, fallback and trusted private content ──────────
H="$TMP/cap"; D=2026-07-17; make_hub "$H"
cat >"$H/.orchestrator/morning-digest-$D.json" <<EOF
{"delivery":"local_qwen_telegram","date":"$D","period":"morning","status":"failed","failed_stage":"build","retry_disposition":"terminal","attempts":{"build":2,"tts":0,"telegram":0,"total":2},"caps":{"build":2,"tts":2,"telegram":3,"total":5}}
EOF
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "stage cap is terminal with zero external calls" || bad "stage cap still performed work"
json_check "$M" 'd["retry_disposition"] == "terminal" and d["attempts"]["build"] == 2' "cap-blocked invocation does not change counters"

H="$TMP/tts-cap"; D=2026-07-25; make_hub "$H"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1
M="$H/.orchestrator/morning-digest-$D.json"
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d.update(status="report_ready", retry_disposition="retryable", failed_stage=None)
d["attempts"]={"build":1,"tts":2,"telegram":0,"total":3}; open(p,"w").write(json.dumps(d))
PY
: >"$H/gather.log"; : >"$H/render.log"; : >"$H/send.log"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "TTS cap is terminal with zero external calls" || bad "TTS cap still called a stage"
json_check "$M" 'd["retry_disposition"] == "terminal" and d["attempts"]["tts"] == 2' "TTS cap preserves exact counters"

H="$TMP/telegram-cap"; D=2026-07-26; make_hub "$H"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1
M="$H/.orchestrator/morning-digest-$D.json"
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d.update(status="failed", retry_disposition="terminal", failed_stage="telegram")
d["attempts"]={"build":1,"tts":1,"telegram":3,"total":5}; open(p,"w").write(json.dumps(d))
PY
: >"$H/gather.log"; : >"$H/render.log"; : >"$H/send.log"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/gather.log" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "Telegram/total cap is terminal with zero external calls" || bad "Telegram cap still called a stage"
json_check "$M" 'd["retry_disposition"] == "terminal" and d["attempts"] == {"build":1,"tts":1,"telegram":3,"total":5}' "Telegram cap preserves exact counters"

H="$TMP/unavailable"; D=2026-07-18; make_hub "$H"; rm "$H/bin/kb-tts-render"
run_digest "$H" --date "$D" --digest-file "$BODY" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -eq 0 && -s "$H/reports/morning-digest-$D.md" && -s "$H/reports/morning-digest-$D.txt" && ! -e "$H/reports/morning-digest-$D.mp3" && ! -s "$H/send.log" ]] \
  && ok "missing local runtime keeps report/speech and sends nothing" || bad "optional-runtime degradation is wrong"
json_check "$M" 'd["status"] == "unavailable" and d["retry_disposition"] == "terminal" and "kb-tts-install" in d["error"]' "missing runtime records actionable install guidance"

H="$TMP/fallback"; D=2026-07-19; make_hub "$H"
run_digest "$H" --date "$D" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -ne 0 && -s "$H/reports/morning-digest-$D.md" && ! -e "$H/reports/morning-digest-$D.txt" && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "raw fallback packet is never spoken or sent" || bad "fallback packet reached speech/audio path"
json_check "$M" 'd["failed_stage"] == "build" and d["retry_disposition"] == "retryable"' "fallback failure is durable and retryable before cap"

H="$TMP/private-content"; D=2026-07-20; make_hub "$H"
PRIV="$TMP/private-body.md"
printf '%s\n' '## Главное' 'Письмо от raw.person@example.com.' 'План personal/goals и личный бюджет — озвучить.' >"$PRIV"
run_digest "$H" --date "$D" --digest-file "$PRIV" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
SPEECH=$(cat "$H/reports/morning-digest-$D.txt" 2>/dev/null)
[[ $RC -eq 0 && "$SPEECH" == *'raw.person@example.com'* \
   && "$SPEECH" == *'personal/goals'* && "$SPEECH" == *'личный бюджет'* \
   && $(wc -l <"$H/render.log") -eq 1 && $(wc -l <"$H/send.log") -eq 1 ]] \
  && ok "trusted private content reaches Qwen and Telegram" \
  || bad "trusted private content was filtered or blocked"
json_check "$M" 'd["status"] == "completed" and d["failed_stage"] is None' "private content completes normally"

# ── 7. Evening path: trusted Retro block only, no second synthesis ─────────
H="$TMP/evening"; D=2026-07-21; make_hub "$H"
cat >"$H/briefs/$D.md" <<'EOF'
## Morning brief
old morning topic must not be spoken

## Retro (20:45)

Сегодня закрыли важный локальный TTS переход.

## Reflection (20:50)
private reflection must not be spoken
EOF
run_digest "$H" --period evening --date "$D" >/dev/null 2>&1; RC=$?
SPEECH=$(cat "$H/reports/evening-digest-$D.txt" 2>/dev/null)
[[ $RC -eq 0 && "$SPEECH" == *"Сегодня закрыли важный локальный TTS переход"* && "$SPEECH" != *"old morning topic"* && "$SPEECH" != *"private reflection"* \
   && "$SPEECH" != *"Output language"* && "$SPEECH" != *"briefs/"* && "$SPEECH" != *"source:"* ]] \
  && ok "evening speech contains only trusted Retro block" || bad "evening path mixed morning/reflection content"
json_check "$H/.orchestrator/evening-digest-$D.json" 'd["period"] == "evening" and d["status"] == "completed"' "evening uses isolated completed manifest"

H="$TMP/evening-missing"; D=2026-07-22; make_hub "$H"
run_digest "$H" --period evening --date "$D" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/evening-digest-$D.json"
[[ $RC -eq 75 && ! -e "$H/reports/evening-digest-$D.md" && ! -e "$H/reports/evening-digest-$D.txt" && ! -e "$H/reports/evening-digest-$D.mp3" && ! -s "$H/send.log" ]] \
  && ok "missing evening Retro returns retry 75 with no placeholder report" || bad "missing evening Retro did not fail closed before report/audio/send"
json_check "$M" 'd["status"] == "blocked_invalid_retro"' "missing evening Retro records blocked_invalid_retro"

# ── 8. morning-input/v1 freshness regression (RED before v0.6 hotfix) ─────
if false; then # superseded by terminal morning-input/v3 whole-block contract
H="$TMP/snapshot-refresh"; D=$(date +%F); make_hub "$H"
run_digest_synth "$H" --date "$D" >/dev/null 2>&1; RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $RC -eq 0 && $(wc -l <"$H/send.log") -eq 1 ]] \
  && ok "snapshot: initial manual delivery completes" || bad "snapshot: initial delivery failed"

# A pre-v0.6 completed manifest without a snapshot remains a manual no-op.
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d.pop("upstream_snapshot", None)
open(p,"w").write(json.dumps(d))
PY
: >"$H/render.log"; BEFORE=$(wc -l <"$H/send.log")
run_digest_synth "$H" --date "$D" >/dev/null 2>&1; RC=$?
AFTER=$(wc -l <"$H/send.log")
[[ $RC -eq 0 && $AFTER -eq $BEFORE && ! -s "$H/render.log" ]] \
  && ok "snapshot: legacy completed manifest stays manual no-op" \
  || bad "snapshot: manual legacy rerun duplicated delivery"

# The exact scheduled caller must rebuild once after a newer chain-owned input.
printf '%s\n' 'SNAPSHOT_MONEY_V1' >"$H/.orchestrator/money-radar-$D-codex-out.txt"
: >"$H/render.log"; BEFORE=$(wc -l <"$H/send.log")
run_scheduled_synth "$H" >/dev/null 2>&1; RC=$?
AFTER=$(wc -l <"$H/send.log")
SPEECH=$(cat "$H/reports/morning-digest-$D.txt" 2>/dev/null)
[[ $RC -eq 0 && $AFTER -eq $((BEFORE + 1)) && "$SPEECH" == *"SNAPSHOTMONEYV1"* ]] \
  && ok "snapshot: scheduled caller replaces stale same-day delivery exactly once" \
  || bad "snapshot: replacement mismatch rc=$RC sends=$BEFORE->$AFTER speech_marker=$([[ "$SPEECH" == *"SNAPSHOTMONEYV1"* ]] && echo yes || echo no)"
json_check "$M" 'd["upstream_snapshot"]["schema"] == "morning-input/v2" and d["upstream_snapshot"]["semantic_sha256"].__len__() == 64' "snapshot: replacement stores versioned semantic hash"

# D13 compatibility: a stored v1-schema snapshot (pre input-contract upgrade) is
# NOT corruption — a manual rerun stays a no-op, exactly like the no-provenance
# legacy path.
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p))
d["upstream_snapshot"]={"schema":"morning-input/v1","inputs":[],"semantic_sha256":"0"*64}
open(p,"w").write(json.dumps(d))
PY
: >"$H/render.log"; BEFORE=$(wc -l <"$H/send.log")
run_digest_synth "$H" --date "$D" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && $(wc -l <"$H/send.log") -eq $BEFORE && ! -s "$H/render.log" ]] \
  && ok "snapshot: stored v1 schema upgrades as legacy no-op, not corruption (D13)" \
  || bad "snapshot: v1-schema manifest mishandled rc=$RC"
run_scheduled_synth "$H" >/dev/null 2>&1
json_check "$M" 'd["upstream_snapshot"]["schema"] == "morning-input/v2"' "snapshot: scheduled caller upgrades v1 manifest to v2 once"

# Completion's own hub-log write and mtime-only touch are semantic no-ops.
BEFORE=$(wc -l <"$H/send.log"); touch "$H/.orchestrator/money-radar-$D-codex-out.txt"
run_scheduled_synth "$H" >/dev/null 2>&1; RC=$?
AFTER=$(wc -l <"$H/send.log")
[[ $RC -eq 0 && $AFTER -eq $BEFORE ]] \
  && ok "snapshot: unchanged content/touch/self-log makes zero sends" \
  || bad "snapshot: diagnostic churn caused duplicate send"

# A second semantic change enters the existing ambiguity state and never retries.
printf '%s\n' 'SNAPSHOT_MONEY_V2' >"$H/.orchestrator/money-radar-$D-codex-out.txt"
BEFORE=$(wc -l <"$H/send.log")
KB_FAKE_SEND_MODE=ambiguous run_scheduled_synth "$H" >/dev/null 2>&1; RC=$?
AFTER=$(wc -l <"$H/send.log")
[[ $RC -eq 0 && $AFTER -eq $((BEFORE + 1)) ]] \
  && ok "snapshot: replacement ambiguous upload attempts once" \
  || bad "snapshot: ambiguous replacement did not reach exactly one send"
json_check "$M" 'd["status"] == "telegram_ambiguous" and d["retry_disposition"] == "force_required"' "snapshot: ambiguous replacement is force-required"
KB_FAKE_SEND_MODE=success run_scheduled_synth "$H" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && $(wc -l <"$H/send.log") -eq $AFTER ]] \
  && ok "snapshot: ambiguous replacement never auto-resends" \
  || bad "snapshot: ambiguous replacement was duplicated"

# Malformed snapshot is integrity corruption before synthesis/render/send.
H="$TMP/snapshot-malformed"; D=$(date +%F); make_hub "$H"
run_digest_synth "$H" --date "$D" >/dev/null 2>&1
M="$H/.orchestrator/morning-digest-$D.json"
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d["upstream_snapshot"]={"schema":"morning-input/v2","semantic_sha256":"bad"}
open(p,"w").write(json.dumps(d))
PY
: >"$H/render.log"; : >"$H/send.log"
run_scheduled_synth "$H" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "snapshot: malformed schema makes zero external calls" \
  || bad "snapshot: malformed schema reached an external stage"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "integrity" and d["retry_disposition"] == "force_required"' "snapshot: malformed schema fails closed"

# Only EXACTLY morning-input/v1 gets the legacy-compat upgrade (D13); an
# unknown/future schema is integrity corruption, never a silent reset/resend.
H="$TMP/snapshot-future"; D=$(date +%F); make_hub "$H"
run_digest_synth "$H" --date "$D" >/dev/null 2>&1
M="$H/.orchestrator/morning-digest-$D.json"
python3 - "$M" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p))
d["upstream_snapshot"]={"schema":"morning-input/v3","inputs":[],"semantic_sha256":"0"*64}
open(p,"w").write(json.dumps(d))
PY
: >"$H/render.log"; : >"$H/send.log"
run_scheduled_synth "$H" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && ! -s "$H/render.log" && ! -s "$H/send.log" ]] \
  && ok "snapshot: future schema makes zero external calls" \
  || bad "snapshot: future schema reached an external stage"
json_check "$M" 'd["status"] == "failed" and d["failed_stage"] == "integrity"' "snapshot: future schema fails closed (no legacy bypass)"

# Flock serializes two stale scheduled callers; contention is retryable rc 75.
H="$TMP/snapshot-concurrent"; D=$(date +%F); make_hub "$H"
run_digest_synth "$H" --date "$D" >/dev/null 2>&1
printf '%s\n' 'SNAPSHOT_CONCURRENT' >"$H/.orchestrator/money-radar-$D-codex-out.txt"
PIDS="$H/render-pids"
KB_FAKE_RENDER_MODE=slow KB_FAKE_RENDER_PIDS="$PIDS" \
  KB_PROCESS_BACKGROUND=1 KB_PROCESS_ID=morning-digest KB_PROCESS_OUTPUTS=file,telegram_audio \
  KB_HUB="$H" KB_VEPOL_DEV="$NOVEPOL" KB_MORNING_SYNTH_AGENTS=claude \
  KB_CLAUDE_BIN="$H/bin/claude" KB_MORNING_SYNTH_MODEL='' KB_TTS_HOME="$H/tts" \
  KB_FAKE_RENDER_LOG="$H/render.log" KB_FAKE_SEND_LOG="$H/send.log" \
  KB_FAKE_GATHER_LOG="$H/gather.log" KB_FAKE_RENDER_PIDS="$PIDS" \
  "$DIGEST" >/dev/null 2>&1 & SNAP_PID=$!
for _ in $(seq 1 80); do [[ -s "$PIDS" ]] && break; sleep 0.05; done
if [[ -s "$PIDS" ]]; then
  run_scheduled_synth "$H" >/dev/null 2>&1; CONTEND_RC=$?
  kill -TERM "$SNAP_PID" 2>/dev/null || true; wait "$SNAP_PID" 2>/dev/null || true
  [[ $CONTEND_RC -eq 75 ]] \
    && ok "snapshot: concurrent stale caller gets rc 75" \
    || bad "snapshot: concurrent caller rc=$CONTEND_RC"
else
  bad "snapshot: freshness rebuild never reached slow renderer"
  kill -KILL "$SNAP_PID" 2>/dev/null || true; wait "$SNAP_PID" 2>/dev/null || true
fi

# Every content-bearing input owns a stable logical snapshot entry and a
# semantic change to any one entry replaces the completed delivery once.
H="$TMP/snapshot-surface"; D=$(date +%F); make_hub "$H"
PROJECT="$H/project"; mkdir -p "$PROJECT/knowledge"; KB_TEST_VEPOL_DEV="$PROJECT"
printf '%s\n' 'SNAPSHOT_LEARNING_A' >"$H/reports/learning-arxiv-summary-$D.md"
printf '%s\n' 'SNAPSHOT_MONEY_A' >"$H/.orchestrator/money-radar-$D-codex-out.txt"
printf '%s\n' 'SNAPSHOT_BRIEF_A' >"$H/briefs/$D.md"
printf '%s\n' '{"marker":"SNAPSHOT_RESEARCH_A"}' >"$H/.orchestrator/daily-research-$D.json"
printf '%s\n' 'SNAPSHOT_IDEA_A' >"$H/idea.txt"
printf '%s\n' 'SNAPSHOT_STATE_A' >"$PROJECT/knowledge/state.md"
printf '%s\n' 'SNAPSHOT_PROJECT_LOG_A' >"$PROJECT/knowledge/log.md"
printf '%s\n' 'board source exists' >"$PROJECT/knowledge/backlog.md"
printf '%s\n' 'SNAPSHOT_BOARD_A' >"$H/board.txt"
printf '%s\n' 'SNAPSHOT_HUB_LOG_A' >"$H/log.md"
printf '%s\n' 'SNAPSHOT_ESCALATION_A' >"$H/escalations.md"
printf '%s\n' '<untrusted-source-nonce-a>SNAPSHOT_MAIL_A</untrusted-source-nonce-a>' >"$H/mail.txt"
run_digest_synth "$H" --date "$D" >/dev/null 2>&1
M="$H/.orchestrator/morning-digest-$D.json"
# D13 (v14): "project_board" and "mail" left the input contract with their
# blocks — the brief is the single day-aggregator.
json_check "$M" '[i["name"] for i in d["upstream_snapshot"]["inputs"]] == ["learning","money_radar","brief","daily_research","ideas","project_state","project_log","hub_log","escalations"]' "snapshot: full logical input roster is canonical (v2, no board/mail)"

expect_surface_refresh() {
  local label="$1" before after rc
  before=$(wc -l <"$H/send.log")
  run_scheduled_synth "$H" >/dev/null 2>&1; rc=$?
  after=$(wc -l <"$H/send.log")
  [[ $rc -eq 0 && $after -eq $((before + 1)) ]] \
    && ok "snapshot surface: $label change rebuilds once" \
    || bad "snapshot surface: $label rc=$rc sends=$before->$after"
}

printf '%s\n' 'SNAPSHOT_LEARNING_B' >"$H/reports/learning-arxiv-summary-$D.md"; expect_surface_refresh learning
printf '%s\n' 'SNAPSHOT_MONEY_B' >"$H/.orchestrator/money-radar-$D-codex-out.txt"; expect_surface_refresh money
printf '%s\n' 'SNAPSHOT_BRIEF_B' >"$H/briefs/$D.md"; expect_surface_refresh brief
# D8 (morning-digest-inputs-rebalance-2026-07-11): the daily-research block was
# removed from the digest (dead 29-day-stale duplicate of the arXiv research), so
# its artifact is no longer read and a change to it is a semantic no-op — the
# 'daily_research' key stays in the canonical roster (asserted above) but always
# renders 'missing'. Assert NO resend (matches the mail-nonce no-op below).
DR_BEFORE=$(wc -l <"$H/send.log")
printf '%s\n' '{"marker":"SNAPSHOT_RESEARCH_B"}' >"$H/.orchestrator/daily-research-$D.json"
run_scheduled_synth "$H" >/dev/null 2>&1; DR_RC=$?
[[ $DR_RC -eq 0 && $(wc -l <"$H/send.log") -eq $DR_BEFORE ]] \
  && ok "snapshot surface: daily-research removed (D8) is a semantic no-op" \
  || bad "snapshot surface: daily-research rc=$DR_RC unexpectedly resent"
printf '%s\n' 'SNAPSHOT_IDEA_B' >"$H/idea.txt"; expect_surface_refresh idea
printf '%s\n' 'SNAPSHOT_STATE_B' >"$PROJECT/knowledge/state.md"; expect_surface_refresh project-state
printf '%s\n' 'SNAPSHOT_PROJECT_LOG_B' >"$PROJECT/knowledge/log.md"; expect_surface_refresh project-log
# D13: the board block left the digest (brief is the single day-aggregator) —
# a board change is a semantic no-op, same shape as the D8 daily-research case.
BOARD_BEFORE=$(wc -l <"$H/send.log")
printf '%s\n' 'SNAPSHOT_BOARD_B' >"$H/board.txt"
run_scheduled_synth "$H" >/dev/null 2>&1; BOARD_RC=$?
[[ $BOARD_RC -eq 0 && $(wc -l <"$H/send.log") -eq $BOARD_BEFORE ]] \
  && ok "snapshot surface: board removed (D13) is a semantic no-op" \
  || bad "snapshot surface: board rc=$BOARD_RC unexpectedly resent"
printf '%s\n' 'SNAPSHOT_HUB_LOG_B' >"$H/log.md"; expect_surface_refresh hub-log
printf '%s\n' 'SNAPSHOT_ESCALATION_B' >"$H/escalations.md"; expect_surface_refresh escalations
# D13: the direct mail block left the digest too — a mail-envelope change is a
# semantic no-op (mail reaches the digest only via the brief's curated prose).
MAIL_BEFORE=$(wc -l <"$H/send.log")
printf '%s\n' '<untrusted-source-nonce-b>SNAPSHOT_MAIL_B</untrusted-source-nonce-b>' >"$H/mail.txt"
run_scheduled_synth "$H" >/dev/null 2>&1; MAIL_RC=$?
[[ $MAIL_RC -eq 0 && $(wc -l <"$H/send.log") -eq $MAIL_BEFORE ]] \
  && ok "snapshot surface: mail removed (D13) is a semantic no-op" \
  || bad "snapshot surface: mail rc=$MAIL_RC unexpectedly resent"
unset KB_TEST_VEPOL_DEV
fi

write_finalized_inputs() { # hub day marker
  local hub="$1" day="$2" marker="$3"
  cat > "$hub/briefs/$day.md" <<EOF
---
date: $day
delivery: telegram_ok
---

${marker}-BRIEF
EOF
  cat > "$hub/.orchestrator/learning-arxiv-$day.json" <<EOF
{"status":"completed","no_new_papers":false,"selected_papers":[{"id":"p1"}]}
EOF
  printf '%s\n' "${marker}-ARXIV" > "$hub/reports/learning-arxiv-summary-$day.md"
  printf '%s\n' "${marker}-MONEY" > "$hub/.orchestrator/money-radar-$day-digest.txt"
}

# New dates persist exactly the three finalized input records. Once delivery is
# completed, later same-day source changes are terminal without owner --force.
H="$TMP/snapshot-v3"; D=$(date +%F); make_hub "$H"
write_finalized_inputs "$H" "$D" SNAPSHOT_V3_A
run_scheduled_synth "$H" >/dev/null 2>&1; V3RC=$?
M="$H/.orchestrator/morning-digest-$D.json"
[[ $V3RC -eq 0 && $(wc -l < "$H/send.log") -eq 1 ]] \
  && ok "snapshot v3: initial whole-block delivery completes" \
  || bad "snapshot v3: initial delivery failed"
json_check "$M" 'd["upstream_snapshot"]["schema"] == "morning-input/v3" and [i["name"] for i in d["upstream_snapshot"]["inputs"]] == ["brief","learning","money_radar"]' "snapshot v3: exact canonical input roster"
write_finalized_inputs "$H" "$D" SNAPSHOT_V3_B
BEFORE=$(wc -l < "$H/send.log")
run_scheduled_synth "$H" >/dev/null 2>&1; V3RRC=$?
[[ $V3RRC -eq 0 && $(wc -l < "$H/send.log") -eq "$BEFORE" ]] \
  && ok "snapshot v3: completed date never auto-resends changed inputs" \
  || bad "snapshot v3: completed delivery was superseded automatically"

# With no finalized same-day blocks, the build remains report-only and makes
# zero Qwen, NotebookLM, or Telegram calls.
H="$TMP/all-missing"; D=$(date +%F); make_hub "$H"
run_scheduled_synth "$H" >/dev/null 2>&1; MISS_RC=$?
[[ $MISS_RC -ne 0 && ! -s "$H/render.log" && ! -s "$H/send.log" \
   && ! -s "$H/notebooklm.log" ]] \
  && ok "all-missing morning input makes zero adapter calls" \
  || bad "all-missing morning input reached an adapter"

# The explicitly enabled NotebookLM route receives the same trusted private daily.
H="$TMP/notebook-private"; D=$(date +%F); make_hub "$H"
write_finalized_inputs "$H" "$D" PRIVATE_DAILY
printf -- '---\ndate: %s\n---\n\nowner@example.com; personal/goals; private project status\n' "$D" > "$H/briefs/$D.md"
run_scheduled_notebooklm_synth "$H" >/dev/null 2>&1; NPRC=$?
NBSPEECH=$(cat "$H/reports/morning-digest-$D.txt" 2>/dev/null)
[[ $NPRC -eq 0 && "$NBSPEECH" == *'owner@example.com'* \
   && "$NBSPEECH" == *'personal/goals'* \
   && $(grep -c 'NOTEBOOKLM_CALLED generate audio' "$H/notebooklm.log") -eq 1 \
   && $(grep -c 'NOTEBOOKLM_CALLED source wait' "$H/notebooklm.log") -eq 0 \
   && $(grep -c 'NOTEBOOKLM_CALLED generate audio.*--no-wait.*--json' "$H/notebooklm.log") -eq 1 \
   && ! -s "$H/send.log" ]] \
  && ok "NotebookLM receives the trusted private daily" \
  || bad "NotebookLM private daily was filtered or blocked"

# ── 9. Independent channel flags ────────────────────────────────────────────
HQ="$TMP/selector-qwen"; HN="$TMP/selector-notebooklm"; D=$(date +%F)
make_hub "$HQ"; make_hub "$HN"
write_finalized_inputs "$HQ" "$D" SNAPSHOT_SELECTOR_SAME_TEXT
write_finalized_inputs "$HN" "$D" SNAPSHOT_SELECTOR_SAME_TEXT
run_scheduled_synth "$HQ" >/dev/null 2>&1; QRC=$?
run_scheduled_notebooklm_synth "$HN" >/dev/null 2>&1; NRC=$?
[[ $QRC -eq 0 && $NRC -eq 0 && $(wc -l <"$HQ/send.log") -eq 1 \
   && ! -s "$HQ/notebooklm.log" && ! -s "$HN/send.log" \
   && $(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HN/notebooklm.log") -eq 1 \
   && $(grep -c -- '--format deep-dive --length long' "$HN/notebooklm.log") -eq 1 \
   && $(grep -c "NOTEBOOKLM_CALLED source add $HN/reports/morning-digest-$D.txt " \
        "$HN/notebooklm.log") -eq 1 ]] \
  && ok "channel flags: morning NotebookLM uses the longer audio setting" \
  || bad "channel flags: morning NotebookLM did not use deep-dive + long"
cmp -s "$HQ/reports/morning-digest-$D.txt" "$HN/reports/morning-digest-$D.txt" \
  && ok "channel flags: ready digest text is identical before delivery" \
  || bad "channel flags: channel changed the frozen digest text"

# Both true flags independently dispatch both handlers against one frozen file.
HB="$TMP/channel-both"; make_hub "$HB"
write_finalized_inputs "$HB" "$D" SNAPSHOT_BOTH_CHANNELS
run_scheduled_both_synth "$HB" >/dev/null 2>&1; BRC=$?
[[ $BRC -eq 0 && $(wc -l <"$HB/send.log") -eq 1 \
   && $(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HB/notebooklm.log") -eq 1 \
   && $(grep -c "NOTEBOOKLM_CALLED source add $HB/reports/morning-digest-$D.txt " \
        "$HB/notebooklm.log") -eq 1 ]] \
  && ok "channel flags: both true dispatches Telegram and NotebookLM" \
  || bad "channel flags: both true did not dispatch both handlers"

# Toggling flags keeps one stable manifest per handler and never repeats a
# handler that already completed for the date.
HS="$TMP/selector-switch"; make_hub "$HS"
write_finalized_inputs "$HS" "$D" SNAPSHOT_SELECTOR_SWITCH
run_scheduled_synth "$HS" >/dev/null 2>&1; Q1=$?
run_scheduled_both_synth "$HS" >/dev/null 2>&1; N1=$?
SENDS_AFTER_BOTH=$(wc -l <"$HS/send.log")
run_scheduled_synth "$HS" >/dev/null 2>&1; Q2=$?
[[ $Q1 -eq 0 && $N1 -eq 0 && $Q2 -eq 0 \
   && $SENDS_AFTER_BOTH -eq 1 && $(wc -l <"$HS/send.log") -eq 1 \
   && $(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HS/notebooklm.log") -eq 1 \
   && -s "$HS/.orchestrator/morning-digest-$D.json" \
   && -s "$HS/.orchestrator/morning-digest-$D-notebooklm.json" ]] \
  && ok "channel flags: toggles preserve stable per-handler manifests" \
  || bad "channel flags: toggle repeated or crossed handlers"

HSN="$TMP/selector-switch-notebook-first"; make_hub "$HSN"
write_finalized_inputs "$HSN" "$D" SNAPSHOT_SELECTOR_SWITCH_NOTEBOOK
run_scheduled_notebooklm_synth "$HSN" >/dev/null 2>&1; NN1=$?
run_scheduled_both_synth "$HSN" >/dev/null 2>&1; NQ1=$?
run_scheduled_notebooklm_synth "$HSN" >/dev/null 2>&1; NN2=$?
[[ $NN1 -eq 0 && $NQ1 -eq 0 && $NN2 -eq 0 \
   && $(wc -l <"$HSN/send.log") -eq 1 \
   && $(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HSN/notebooklm.log") -eq 1 ]] \
  && ok "channel flags: NotebookLM-first toggle invokes only new Telegram handler" \
  || bad "channel flags: NotebookLM-first toggle repeated a completed handler"

# Every accepted ACK shape is terminal locally; every missing/rejected ACK
# leaves a pre-submit tombstone that ordinary reruns cannot cross.
for ACK in task id; do
  HA="$TMP/notebooklm-ack-$ACK"; make_hub "$HA"
  D=$(date +%F)
  write_finalized_inputs "$HA" "$D" "SNAPSHOT_ACK_${ACK^^}"
  KB_FAKE_NOTEBOOKLM_ACK_KIND="$ACK" run_scheduled_notebooklm_synth "$HA" \
    >/dev/null 2>&1; ARC=$?
  AM="$HA/.orchestrator/morning-digest-$D-notebooklm.json"
  EXPECTED_ID=$([[ "$ACK" == task ]] && echo task-selector || echo generic-selector)
  EXPECTED_KIND=$([[ "$ACK" == task ]] && echo task_id || echo id)
  json_check "$AM" \
    "d['status'] == 'completed' and d['submission_id'] == '$EXPECTED_ID' and d['submission_id_kind'] == '$EXPECTED_KIND' and d['remote_status'] == 'untracked_after_ack'" \
    "NotebookLM/$ACK: accepted ACK key is recorded"
  [[ $ARC -eq 0 ]] || bad "NotebookLM/$ACK: route returned rc=$ARC"
done

for CASE in empty malformed reject; do
  HF="$TMP/notebooklm-failure-$CASE"; make_hub "$HF"
  D=$(date +%F)
  write_finalized_inputs "$HF" "$D" "SNAPSHOT_FAILURE_${CASE^^}"
  KB_FAKE_NOTEBOOKLM_ACK_KIND="$CASE" run_scheduled_notebooklm_synth "$HF" \
    >/dev/null 2>&1; FRC=$?
  MID=$(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HF/notebooklm.log" || true)
  KB_FAKE_NOTEBOOKLM_ACK_KIND=task run_scheduled_notebooklm_synth "$HF" \
    >/dev/null 2>&1; RRC=$?
  AFTER=$(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HF/notebooklm.log" || true)
  FM="$HF/.orchestrator/morning-digest-$D-notebooklm.json"
  [[ $FRC -eq 0 && $RRC -eq 0 && $MID -eq 1 && $AFTER -eq 1 ]] \
    && ok "NotebookLM/$CASE: terminal failure is never auto-resubmitted" \
    || bad "NotebookLM/$CASE: ordinary rerun crossed tombstone"
  json_check "$FM" \
    "d['status'] == 'failed' and d['retry_disposition'] == 'force_required' and d['local_delivery_status'] == 'not_acknowledged'" \
    "NotebookLM/$CASE: force-required tombstone persists"
done

HK="$TMP/notebooklm-kill-force"; make_hub "$HK"
D=$(date +%F)
write_finalized_inputs "$HK" "$D" SNAPSHOT_KILL_FORCE
set +e
KB_FAKE_NOTEBOOKLM_ACK_KIND=kill run_scheduled_notebooklm_synth "$HK" \
  >/dev/null 2>&1
KRC=$?
set -e
MID=$(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HK/notebooklm.log" || true)
KB_FAKE_NOTEBOOKLM_ACK_KIND=task run_scheduled_notebooklm_synth "$HK" \
  >/dev/null 2>&1; RRC=$?
AFTER_RERUN=$(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HK/notebooklm.log" || true)
KB_FAKE_NOTEBOOKLM_MODE=success KB_FAKE_NOTEBOOKLM_ACK_KIND=artifact \
  run_digest_synth "$HK" --notebooklm --force \
  >/dev/null 2>&1; FRC=$?
AFTER_FORCE=$(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HK/notebooklm.log" || true)
KB_FAKE_NOTEBOOKLM_ACK_KIND=task run_scheduled_notebooklm_synth "$HK" \
  >/dev/null 2>&1; FINAL_RC=$?
FINAL=$(grep -c 'NOTEBOOKLM_CALLED generate audio' "$HK/notebooklm.log" || true)
KM="$HK/.orchestrator/morning-digest-$D-notebooklm.json"
[[ $KRC -ne 0 && $RRC -eq 0 && $FRC -eq 0 && $FINAL_RC -eq 0 \
   && $MID -eq 1 && $AFTER_RERUN -eq 1 && $AFTER_FORCE -eq 2 && $FINAL -eq 2 ]] \
  && ok "NotebookLM/kill: ordinary rerun is blocked; one --force submits once" \
  || bad "NotebookLM/kill: wrong submit counts or rc ($KRC/$RRC/$FRC/$FINAL_RC; $MID/$AFTER_RERUN/$AFTER_FORCE/$FINAL)"
json_check "$KM" \
  "d['status'] == 'completed' and d['submission_id'] == 'audio-selector' and d['submission_id_kind'] == 'artifact_id' and d['remote_status'] == 'untracked_after_ack'" \
  "NotebookLM/force: forced ACK is terminal accepted state"

echo
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
