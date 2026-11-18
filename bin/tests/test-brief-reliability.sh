#!/usr/bin/env bash
# Brief reliability (spec morning-digest-inputs-rebalance-2026-07-11 v14,
# Phase D / D11-upstream): the brief is the single day-aggregator (D13), so its
# failures must be LOUD and its delivery VERIFIED.
#   kb-brief    — non-zero exit on orchestrator failure (AC-6), per-date error-
#                 Telegram dedup, verified Telegram delivery marker in the day
#                 file frontmatter (delivery: telegram_ok + delivery_message_id),
#                 delivery-only retry that reuses the same-day body (no 2nd LLM),
#                 no-op once verified-delivered.
#   kb-retro    — same verified-delivery treatment (retro_delivery keys), retro
#                 persisted before send so a failed send retries delivery only.
#   kb-planner  — fired state reconstructed from VERIFIED delivery evidence,
#                 never from the clock, never from bare file existence (AC-9).
#   kb-orchestrator-run — a missing provider binary is rc=127 'unavailable' →
#                 failover, never a Python crash.
set -uo pipefail
PASS=0; FAIL=0
SRC_BIN="${KB_BRIEF_SRC_BIN:-$HOME/knowledge/bin}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
# Hermetic: product code must never reach a real agent CLI (a contributor's
# logged-in Claude Code or Codex would make real, paid calls with test data).
AGENT_STUBS="$TMP/agent-stubs"; mkdir -p "$AGENT_STUBS"
for _cli in claude codex; do
  printf '#!/bin/sh\necho "test stub: no real %s calls" >&2\nexit 1\n' "$_cli" > "$AGENT_STUBS/$_cli"
  chmod +x "$AGENT_STUBS/$_cli"
done
export PATH="$AGENT_STUBS:$PATH" KB_CLAUDE_BIN="$AGENT_STUBS/claude" KB_CODEX_BIN="$AGENT_STUBS/codex"
# Isolate from the machine: never read the real Claude runner index (its
# same-day success tombstones made planner checks fail after the evening retro).
export KB_CLAUDE_RUN_ROOT="$TMP/claude-runs"
# Resolve python3 before tests restrict PATH to /usr/bin:/bin, where the Xcode
# stub exits 69 until the Xcode license is accepted.
PY3="$(command -v python3)"
TODAY=$(date +%Y-%m-%d)

# --- fixture hub with fake collaborators --------------------------------------
mk_hub() { # $1 = hub dir
  local H="$1"
  mkdir -p "$H/personal" "$H/bin" "$H/logs" "$H/briefs" "$H/.orchestrator" "$H/fakebin"
  printf 'TELEGRAM_TOKEN=fake-token\nTELEGRAM_CHAT_ID=1\n' > "$H/personal/.secrets"
  # cheap local readers
  printf '#!/bin/sh\necho "(empty)"\n' > "$H/bin/kb-idea"
  printf '#!/bin/sh\necho "{\\"available\\":false,\\"overdue\\":[],\\"today\\":[],\\"upcoming\\":[],\\"errors\\":[]}"\n' > "$H/bin/kb-agenda"
  printf '#!/bin/sh\necho "MAIL: fixture"\n' > "$H/bin/kb-mail-block"
  printf '#!/bin/sh\necho "{}"\n' > "$H/bin/kb-brief-preflight"
  printf '#!/bin/sh\necho ""\n' > "$H/bin/kb-board"
  # fake orchestrator: logs every call; rc + payload controlled via env
  cat > "$H/bin/kb-orchestrator-run" <<'SH'
#!/bin/sh
echo "call" >> "$KB_HUB/orch.log"
# FAKE_ORCH_STDERR: the broker's own stderr report (e.g. "all providers exhausted: ...").
[ -n "${FAKE_ORCH_STDERR:-}" ] && printf '%s\n' "$FAKE_ORCH_STDERR" >&2
if [ "${FAKE_ORCH_RC:-0}" -ne 0 ]; then echo "fixture orchestrator down"; exit "${FAKE_ORCH_RC}"; fi
if [ "${FAKE_ORCH_MODE:-brief}" = "retro" ]; then
  printf 'preamble\n---RETRO---\nFIXTURE_RETRO_BODY line one.\n---REFLECTION---\nFIXTURE_REFLECTION_LINE\n'
elif [ "${FAKE_ORCH_MODE:-brief}" = "brief-long" ]; then
  printf 'pass1 table\n---BRIEF---\nPART_ONE_MARKER first part of the long brief, plenty of text to split up.\n\nPART_TWO_MARKER second part of the long brief, also a fairly long line.\n'
else
  printf 'pass1 table\n---BRIEF---\nFIXTURE_BRIEF_BODY %s\n' "${FAKE_BRIEF_MARKER:-v1}"
fi
exit 0
SH
  # fake curl: logs sends; response per KB_FAKE_TG_MODE (ok | notok) or, when
  # KB_FAKE_TG_MODES is set (comma list), per-call sequenced via tg.count
  cat > "$H/fakebin/curl" <<'SH'
#!/bin/sh
echo "send $*" >> "$KB_HUB/tg.log"
N=$(cat "$KB_HUB/tg.count" 2>/dev/null || echo 0)
N=$((N+1)); echo "$N" > "$KB_HUB/tg.count"
MODE="${KB_FAKE_TG_MODE:-ok}"
if [ -n "${KB_FAKE_TG_MODES:-}" ]; then
  MODE=$(echo "$KB_FAKE_TG_MODES" | cut -d, -f"$N")
  [ -n "$MODE" ] || MODE=$(echo "$KB_FAKE_TG_MODES" | awk -F, '{print $NF}')
fi
if [ "$MODE" = "ok" ]; then
  echo "{\"ok\":true,\"result\":{\"message_id\":$((40+N))}}"
else
  echo '{"ok":false,"description":"fixture telegram down"}'
fi
SH
  # kb-brief now owns text delivery through the typed one-part sender. Keep the
  # same outcome controls/counter as the legacy curl fake so this suite still
  # covers brief + Retro in one fixture without any network call.
  cat > "$H/bin/kb-channel-send-text" <<'SH'
#!/bin/sh
echo "send typed $*" >> "$KB_HUB/tg.log"
N=$(cat "$KB_HUB/tg.count" 2>/dev/null || echo 0)
N=$((N+1)); echo "$N" > "$KB_HUB/tg.count"
MODE="${KB_FAKE_TG_MODE:-ok}"
if [ -n "${KB_FAKE_TG_MODES:-}" ]; then
  MODE=$(echo "$KB_FAKE_TG_MODES" | cut -d, -f"$N")
  [ -n "$MODE" ] || MODE=$(echo "$KB_FAKE_TG_MODES" | awk -F, '{print $NF}')
fi
if [ "$MODE" = "ok" ]; then
  echo "{\"outcome\":\"success\",\"message_id\":$((40+N))}"
  exit 0
fi
if [ "$MODE" = "notconfigured" ]; then
  echo "telegram not configured" >&2
  echo '{"outcome":"not_configured","message_id":null}'
  exit 3
fi
echo '{"outcome":"known_rejection","message_id":null}'
exit 20
SH
  chmod +x "$H/bin/"* "$H/fakebin/curl"
}

run_brief() { # $1 = hub, rest = extra env
  local H="$1"; shift
  # KB_BRIEF_PREVIEW_BEFORE=00:00: a manual run is today's brief at any hour
  # (by default a run before 06:00 is a separate preview file).
  env KB_BRIEF_PREVIEW_BEFORE=00:00 "$@" KB_HUB="$H" PATH="$H/fakebin:$PATH" zsh "$SRC_BIN/kb-brief" 2>/dev/null
}
run_retro() { # $1 = hub, rest = extra env
  local H="$1"; shift
  env "$@" KB_HUB="$H" PATH="$H/fakebin:$PATH" zsh "$SRC_BIN/kb-retro" 2>/dev/null
}
tg_count()   { grep -c '^send ' "$1/tg.log" 2>/dev/null || echo 0; }
orch_count() { wc -l < "$1/orch.log" 2>/dev/null | tr -d ' ' || echo 0; }
fm_get() { # $1=file $2=key → frontmatter value or empty
  awk -v k="$2" 'NR==1&&$0=="---"{fm=1;next} fm&&$0=="---"{exit} fm&&index($0,k": ")==1{print substr($0,length(k)+3)}' "$1"
}

# =============== AC-6: orchestrator failure is loud and deduped ===============
H1="$TMP/h1"; mk_hub "$H1"
run_brief "$H1" FAKE_ORCH_RC=75; RC=$?
[[ $RC -ne 0 ]] && ok "AC-6: orchestrator failure exits non-zero" \
                || fail "AC-6: failure masked as rc=0"
[[ $(tg_count "$H1") == "1" ]] && ok "AC-6: one error telegram sent" \
                              || fail "AC-6: error telegram count=$(tg_count "$H1")"
[[ ! -f "$H1/briefs/$TODAY.md" ]] && ok "AC-6: no day file on failure" \
                                  || fail "AC-6: day file written on failure"
run_brief "$H1" FAKE_ORCH_RC=75; RC=$?
[[ $RC -ne 0 ]] && ok "AC-6: retry still exits non-zero" || fail "AC-6: retry rc=0"
[[ $(tg_count "$H1") == "1" ]] && ok "AC-6: error telegram deduped per date" \
                              || fail "AC-6: error spam count=$(tg_count "$H1")"

# =============== D11: verified delivery marker on success =====================
H2="$TMP/h2"; mk_hub "$H2"
run_brief "$H2"; RC=$?
F2="$H2/briefs/$TODAY.md"
[[ $RC -eq 0 ]] && ok "D11: success run exits 0" || fail "D11: success rc=$RC"
[[ "$(fm_get "$F2" delivery)" == "telegram_ok" ]] \
  && ok "D11: delivery: telegram_ok marker" || fail "D11: marker=$(fm_get "$F2" delivery)"
[[ -n "$(fm_get "$F2" delivery_message_id)" ]] \
  && ok "D11: delivery_message_id recorded" || fail "D11: message id missing"
grep -q "FIXTURE_BRIEF_BODY" "$F2" && ok "D11: body persisted" || fail "D11: body missing"

# no-op once verified-delivered: no LLM, no send
OC=$(orch_count "$H2"); TC=$(tg_count "$H2")
run_brief "$H2"; RC=$?
[[ $RC -eq 0 && $(orch_count "$H2") == "$OC" && $(tg_count "$H2") == "$TC" ]] \
  && ok "D11: delivered day is a no-op (no LLM, no resend)" \
  || fail "D11: delivered day re-ran (orch $OC->$(orch_count "$H2") tg $TC->$(tg_count "$H2"))"

# =============== D11: send failure keeps file, retries delivery only ==========
H3="$TMP/h3"; mk_hub "$H3"
run_brief "$H3" KB_FAKE_TG_MODE=notok; RC=$?
F3="$H3/briefs/$TODAY.md"
[[ $RC -ne 0 ]] && ok "D11: unverified send exits non-zero" || fail "D11: unverified send rc=0"
[[ -f "$F3" ]] && ok "D11: day file retained on send failure" || fail "D11: file lost"
[[ "$(fm_get "$F3" delivery)" == "telegram_failed" ]] \
  && ok "D11: delivery: telegram_failed recorded" || fail "D11: state=$(fm_get "$F3" delivery)"
[[ -z "$(fm_get "$F3" delivery_message_id)" ]] \
  && ok "D11: no message id without verification" || fail "D11: phantom message id"
BODY_BEFORE=$(awk 'NR==1&&$0=="---"{fm=1;next} fm&&$0=="---"{fm=0;body=1;next} body' "$F3")
OC=$(orch_count "$H3")
run_brief "$H3"; RC=$?
[[ $RC -eq 0 ]] && ok "D11: delivery retry succeeds" || fail "D11: retry rc=$RC"
[[ $(orch_count "$H3") == "$OC" ]] \
  && ok "D11: retry reused body — no second LLM run" \
  || fail "D11: retry re-ran LLM ($OC->$(orch_count "$H3"))"
[[ "$(fm_get "$F3" delivery)" == "telegram_ok" && -n "$(fm_get "$F3" delivery_message_id)" ]] \
  && ok "D11: marker upgraded in place after verified retry" \
  || fail "D11: marker not upgraded"
BODY_AFTER=$(awk 'NR==1&&$0=="---"{fm=1;next} fm&&$0=="---"{fm=0;body=1;next} body' "$F3")
[[ "$BODY_AFTER" == "$BODY_BEFORE" ]] \
  && ok "D11: body byte-identical across delivery retry" || fail "D11: body drifted"

# =============== R-impl blocker 3: split-part delivery idempotency ============
H7="$TMP/h7"; mk_hub "$H7"
run_brief "$H7" FAKE_ORCH_MODE=brief-long BRIEF_CHAR_LIMIT=80 KB_FAKE_TG_MODES="ok,notok"; RC=$?
F7="$H7/briefs/$TODAY.md"
[[ $RC -ne 0 ]] && ok "split: part-2 failure exits non-zero" || fail "split: rc=0 on part-2 failure"
[[ "$(fm_get "$F7" delivery_parts_sent)" == "1" && "$(fm_get "$F7" delivery_parts_total)" == "2" ]] \
  && ok "split: durable per-part state (1 of 2 sent)" \
  || fail "split: parts state=$(fm_get "$F7" delivery_parts_sent)/$(fm_get "$F7" delivery_parts_total)"
MSG_ID_P1=$(fm_get "$F7" delivery_message_id)
[[ -n "$MSG_ID_P1" ]] && ok "split: part-1 message id anchored" || fail "split: no part-1 id"
T7=$(tg_count "$H7"); O7=$(orch_count "$H7")
run_brief "$H7" FAKE_ORCH_MODE=brief-long BRIEF_CHAR_LIMIT=80; RC=$?
[[ $RC -eq 0 ]] && ok "split: retry completes delivery" || fail "split: retry rc=$RC"
[[ $(tg_count "$H7") == $((T7+1)) ]] \
  && ok "split: retry resends ONLY the failed part (no part-1 duplicate)" \
  || fail "split: sends $T7 -> $(tg_count "$H7") (expected +1)"
[[ $(orch_count "$H7") == "$O7" ]] \
  && ok "split: retry without a second LLM run" || fail "split: LLM re-ran"
[[ "$(fm_get "$F7" delivery)" == "telegram_ok" && "$(fm_get "$F7" delivery_message_id)" == "$MSG_ID_P1" \
   && "$(fm_get "$F7" delivery_parts_sent)" == "2" ]] \
  && ok "split: final marker keeps part-1 anchor id" || fail "split: final marker wrong"

# =============== R-impl blocker 4: malformed same-day file → regenerate =======
H8="$TMP/h8"; mk_hub "$H8"
printf 'legacy brief without frontmatter\n' > "$H8/briefs/$TODAY.md"
run_brief "$H8"; RC=$?
F8="$H8/briefs/$TODAY.md"
[[ $RC -eq 0 ]] && ok "legacy: frontmatter-less file regenerated, delivered" || fail "legacy: rc=$RC (stuck?)"
[[ $(orch_count "$H8") == "1" ]] && ok "legacy: exactly one LLM run" || fail "legacy: orch=$(orch_count "$H8")"
[[ "$(head -n 1 "$F8")" == "---" && "$(fm_get "$F8" delivery)" == "telegram_ok" ]] \
  && ok "legacy: file rewritten with verified frontmatter" || fail "legacy: file shape wrong"

# =============== Telegram not configured is "not delivered, not an error" =====
H11="$TMP/h11"; mk_hub "$H11"
F11="$H11/briefs/$TODAY.md"
OUT=$(run_brief "$H11" KB_FAKE_TG_MODE=notconfigured KB_BRIEF_PREVIEW_BEFORE=00:00); RC=$?
[[ $RC -eq 0 ]] && ok "not-configured: brief exits 0 (after:daily still runs)" \
                || fail "not-configured: rc=$RC"
grep -q "FIXTURE_BRIEF_BODY" "$F11" && ok "not-configured: brief saved" || fail "not-configured: brief not saved"
[[ $(grep -c "telegram not configured, not delivered" "$H11/logs/brief.log") == "1" ]] \
  && ok "not-configured: one log line" || fail "not-configured: log=$(tail -3 "$H11/logs/brief.log")"
[[ "$OUT" == "Brief saved to $F11; not delivered: Telegram is not configured"* ]] \
  && ok "manual run: prints the saved path and why it was not delivered" \
  || fail "manual run output: $OUT"
[[ "$(fm_get "$F11" delivery)" == "not_configured" && "$(fm_get "$F11" delivery_parts_sent)" == "0" ]] \
  && ok "not-configured: day file records delivery: not_configured (not telegram_failed)" \
  || fail "not-configured: day file delivery=$(fm_get "$F11" delivery)"
EV11=$(KB_HUB="$H11" "$PY3" - "$SRC_BIN/kb-planner" <<'PY'
import datetime, importlib.machinery, importlib.util, sys
spec = importlib.util.spec_from_loader("kbplanner_nc", importlib.machinery.SourceFileLoader("kbplanner_nc", sys.argv[1]))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print(*mod._delivery_evidence(datetime.date.today().isoformat()))
PY
)
[[ "$EV11" == "False False" ]] && ok "not-configured: planner counts the brief as not delivered" \
  || fail "not-configured: planner evidence → $EV11"
OUT=$(run_brief "$H11" KB_FAKE_TG_MODE=notconfigured KB_BRIEF_PREVIEW_BEFORE=00:00); RC=$?
[[ $RC -eq 0 && "$(fm_get "$F11" delivery)" == "not_configured" && $(orch_count "$H11") == "1" ]] \
  && ok "not-configured: a rerun still without Telegram keeps not_configured, no second LLM" \
  || fail "not-configured rerun rc=$RC delivery=$(fm_get "$F11" delivery) orch=$(orch_count "$H11")"
# Telegram set up later that day: a rerun delivers the saved brief, no second LLM run.
OC=$(orch_count "$H11")
OUT=$(run_brief "$H11" KB_BRIEF_PREVIEW_BEFORE=00:00); RC=$?
[[ $RC -eq 0 && $(orch_count "$H11") == "$OC" && "$(fm_get "$F11" delivery)" == "telegram_ok" ]] \
  && ok "not-configured: a later run delivers the saved brief (no second LLM)" \
  || fail "not-configured: later delivery rc=$RC orch $OC->$(orch_count "$H11") state=$(fm_get "$F11" delivery)"
[[ "$OUT" == "Brief saved to $F11; delivered to Telegram." ]] \
  && ok "manual run: prints the saved path and the delivery" || fail "manual success output: $OUT"
H12="$TMP/h12"; mk_hub "$H12"
OUT=$(run_brief "$H12" KB_FAKE_TG_MODE=notok KB_BRIEF_PREVIEW_BEFORE=00:00); RC=$?
[[ $RC -ne 0 && "$OUT" == "Brief saved to $H12/briefs/$TODAY.md; not delivered: the Telegram send failed"* ]] \
  && ok "manual run: a failed send says so and still exits non-zero" || fail "failed send rc=$RC output: $OUT"
# The real typed sender with the installer's empty .secrets: exit 3 before any
# network use (the API base points at a closed port, so a send attempt would fail).
H13="$TMP/h13"; mk_hub "$H13"; rm -f "$H13/bin/kb-channel-send-text"
printf 'TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nUSER_NAME=\n' > "$H13/personal/.secrets"
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_TG_API_BASE=http://127.0.0.1:9 \
  KB_BRIEF_PREVIEW_BEFORE=00:00 KB_HUB="$H13" PATH="$H13/fakebin:$PATH" \
  zsh "$SRC_BIN/kb-brief" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && -f "$H13/briefs/$TODAY.md" ]] \
  && ok "not-configured (real sender): brief saved, exit 0" || fail "not-configured real sender rc=$RC"
zsh "$SRC_BIN/kb-brief" --help 2>/dev/null | grep -q "KB_BRIEF_DRY=1" \
  && ok "kb-brief --help documents KB_BRIEF_DRY" || fail "kb-brief --help lacks KB_BRIEF_DRY"

# =============== no agent answered: the person sees why, in plain words =======
# kb-orchestrator-run exits 75 and reports each provider it tried on stderr.
# A manual run prints the reason on stderr (stdout stays for the saved-path
# line); a scheduled run prints it only when the notice cannot reach Telegram.
run_brief_split() { # $1 = hub, $2 = stdout file, $3 = stderr file, rest = extra env
  local H="$1" out="$2" err="$3"; shift 3
  env -u KB_PROCESS_ID KB_BRIEF_PREVIEW_BEFORE=00:00 "$@" KB_HUB="$H" PATH="$H/fakebin:$PATH" \
    zsh "$SRC_BIN/kb-brief" >"$out" 2>"$err"
}
EXHAUSTED='all providers exhausted: codex: unavailable — Codex executable unavailable: /fixture/codex | claude: auth — Invalid API key · Please run /login'
H18="$TMP/h18"; mk_hub "$H18"
run_brief_split "$H18" "$H18/out" "$H18/err" FAKE_ORCH_RC=75 FAKE_ORCH_STDERR="$EXHAUSTED" \
  KB_FAKE_TG_MODE=notconfigured; RC=$?
ERR18=$(cat "$H18/err")
[[ $RC -eq 1 && ! -s "$H18/out" ]] && ok "no agent: exits 1, nothing on stdout" \
  || fail "no agent: rc=$RC stdout=$(cat "$H18/out")"
[[ "$ERR18" == "⚠️ The brief was not made: no AI agent answered.
Codex: not installed.
Claude Code: not signed in — run \`claude\` once to sign in.
Check $H18/logs/brief.log" ]] \
  && ok "no agent (manual, no Telegram): stderr names each provider tried and how to fix it" \
  || fail "no agent stderr: $ERR18"
[[ "$ERR18" != *"rc=75"* && "$ERR18" != *"exhausted"* && "$ERR18" != *"Invalid API key"* && "$ERR18" != *"/fixture/codex"* ]] \
  && ok "no agent: no rc number, jargon or raw provider detail in the user text" \
  || fail "no agent: raw detail leaked: $ERR18"
grep -q "orchestrator failed rc=75" "$H18/logs/brief.log" && grep -qF "$EXHAUSTED" "$H18/logs/brief.log" \
  && ok "no agent: the log keeps the rc and the broker's raw report" || fail "no agent: log lacks rc/raw report"
[[ "$(fm_get "$H18/.orchestrator/brief-error-$TODAY.md" delivery)" == "not_configured" ]] \
  && grep -q "Claude Code: not signed in" "$H18/.orchestrator/brief-error-$TODAY.md" \
  && ok "no agent: saved notice has the same text and delivery: not_configured" \
  || fail "no agent: notice delivery=$(fm_get "$H18/.orchestrator/brief-error-$TODAY.md" delivery)"
# Scheduled run whose notice reached Telegram: nothing extra on stderr.
H19="$TMP/h19"; mk_hub "$H19"
run_brief_split "$H19" "$H19/out" "$H19/err" KB_PROCESS_ID=daily FAKE_ORCH_RC=75 FAKE_ORCH_STDERR="$EXHAUSTED"; RC=$?
[[ $RC -eq 1 && ! -s "$H19/err" && $(tg_count "$H19") == "1" ]] \
  && ok "no agent (scheduled, notice delivered): sent to Telegram, stderr quiet" \
  || fail "no agent scheduled+delivered: rc=$RC tg=$(tg_count "$H19") stderr=$(cat "$H19/err")"
# Scheduled run without Telegram: the reason goes to stderr (kb-tick's log).
H20="$TMP/h20"; mk_hub "$H20"
run_brief_split "$H20" "$H20/out" "$H20/err" KB_PROCESS_ID=daily FAKE_ORCH_RC=75 FAKE_ORCH_STDERR="$EXHAUSTED" \
  KB_FAKE_TG_MODE=notconfigured; RC=$?
[[ $RC -eq 1 ]] && grep -q "^Claude Code: not signed in" "$H20/err" \
  && ok "no agent (scheduled, no Telegram): reason printed on stderr" \
  || fail "no agent scheduled+not configured: rc=$RC stderr=$(cat "$H20/err")"
# Manual run with Telegram: sent and printed.
H21="$TMP/h21"; mk_hub "$H21"
run_brief_split "$H21" "$H21/out" "$H21/err" FAKE_ORCH_RC=75 FAKE_ORCH_STDERR="$EXHAUSTED"; RC=$?
[[ $RC -eq 1 && $(tg_count "$H21") == "1" ]] && grep -q "^Codex: not installed.$" "$H21/err" \
  && ok "no agent (manual, Telegram set): notice sent and printed" \
  || fail "no agent manual+telegram: rc=$RC tg=$(tg_count "$H21") stderr=$(cat "$H21/err")"
# Other reasons, and the ru table.
H22="$TMP/h22"; mk_hub "$H22"
run_brief_split "$H22" "$H22/out" "$H22/err" FAKE_ORCH_RC=75 KB_FAKE_TG_MODE=notconfigured \
  FAKE_ORCH_STDERR='all providers exhausted: codex: timeout — codex timed out after 5s | claude: other — (no stderr)'
[[ "$(sed -n 2,3p "$H22/err")" == "Codex: did not answer in time.
Claude Code: stopped with an error (if it is not signed in, run \`claude\` once to sign in)." ]] \
  && ok "no agent: timeout and an unclassified Claude error read in plain words" \
  || fail "no agent timeout/other: $(cat "$H22/err")"
H23="$TMP/h23"; mk_hub "$H23"; printf 'language: ru\n' > "$H23/personal/profile.yaml"
run_brief_split "$H23" "$H23/out" "$H23/err" FAKE_ORCH_RC=75 KB_FAKE_TG_MODE=notconfigured \
  FAKE_ORCH_STDERR='all providers exhausted: codex: rate_limit — usage limit | claude: blocked until 2099-06-15T12:00:00Z'
[[ "$(sed -n 1p "$H23/err")" == "⚠️ Брифинг не составлен: ни один ИИ-агент не ответил." \
   && "$(sed -n 2p "$H23/err")" == "Codex: исчерпан лимит использования, попробуй позже." \
   && "$(sed -n 3p "$H23/err")" == "Claude Code: на паузе после прошлой ошибки (до 2099-06-1"* \
   && "$(sed -n 4p "$H23/err")" == "Проверь $H23/logs/brief.log" ]] \
  && ok "no agent (ru): Russian lines from the ru table, pause end time shown" \
  || fail "no agent ru: $(cat "$H23/err")"
H24="$TMP/h24"; mk_hub "$H24"
run_brief_split "$H24" "$H24/out" "$H24/err" FAKE_ORCH_RC=75 KB_FAKE_TG_MODE=notconfigured \
  FAKE_ORCH_STDERR='all providers exhausted: no providers configured'
[[ "$(sed -n 2p "$H24/err")" == "No AI agent is set up: install Claude Code or Codex and sign in." ]] \
  && ok "no agent: no provider configured says so" || fail "no providers: $(cat "$H24/err")"
# Without the broker's report (older broker, odd output): headline and log path only.
H25="$TMP/h25"; mk_hub "$H25"
run_brief_split "$H25" "$H25/out" "$H25/err" FAKE_ORCH_RC=75 KB_FAKE_TG_MODE=notconfigured
[[ "$(cat "$H25/err")" == "⚠️ The brief was not made: no AI agent answered.
Check $H25/logs/brief.log" ]] \
  && ok "no agent: without a provider report the text still says what happened" \
  || fail "no report: $(cat "$H25/err")"
# A " | " inside a provider's own error text is not another provider; a Claude
# binary that cannot be found (the durable runner says "launch failed: [Errno 2]",
# category other) reads "not installed".
H26="$TMP/h26"; mk_hub "$H26"
run_brief_split "$H26" "$H26/out" "$H26/err" FAKE_ORCH_RC=75 KB_FAKE_TG_MODE=notconfigured \
  FAKE_ORCH_STDERR='all providers exhausted: codex: unavailable — Codex executable unavailable: /x | claude: other — Error: bad | codex: auth — fake'
[[ "$(cat "$H26/err")" == "⚠️ The brief was not made: no AI agent answered.
Codex: not installed.
Claude Code: stopped with an error (if it is not signed in, run \`claude\` once to sign in).
Check $H26/logs/brief.log" ]] \
  && ok "no agent: a ' | ' inside a provider's error text adds no line" \
  || fail "no agent pipe in detail: $(cat "$H26/err")"
H27="$TMP/h27"; mk_hub "$H27"
run_brief_split "$H27" "$H27/out" "$H27/err" FAKE_ORCH_RC=75 KB_FAKE_TG_MODE=notconfigured \
  FAKE_ORCH_STDERR="all providers exhausted: codex: unavailable — Codex executable unavailable: /x | claude: other — launch failed: [Errno 2] No such file or directory: 'claude'"
[[ "$(sed -n 2,3p "$H27/err")" == "Codex: not installed.
Claude Code: not installed." ]] \
  && ok "no agent: a Claude binary that cannot be found reads 'not installed'" \
  || fail "no agent claude missing: $(cat "$H27/err")"

# =============== health wait stays inside kb-tick's process cap ===============
# The run never outlives its cap: with the deadline still ahead it exits 75
# before the model call (kb-tick runs it again next tick, so the brief keeps
# waiting for the mark until the deadline, as configured).
H14="$TMP/h14"; mk_hub "$H14"
T0=$SECONDS
run_brief "$H14" KB_PROCESS_ID=daily KB_PROCESS_TIMEOUT=600 \
  KB_BRIEF_HEALTH_READY_FILE="$H14/health-ready.json" KB_BRIEF_HEALTH_WAIT_UNTIL=23:59 >/dev/null; RC=$?
if [[ "$(date +%H:%M)" < "23:59" ]]; then
  [[ $RC -eq 75 && $((SECONDS - T0)) -lt 25 && $(orch_count "$H14") == "0" && ! -e "$H14/briefs/$TODAY.md" ]] \
    && ok "health wait: no room under a 600 s cap → exits 75 before the model call, retried next tick" \
    || fail "health wait: rc=$RC after $((SECONDS - T0)) s, orch=$(orch_count "$H14")"
  grep -q "health wait paused after .* the process cap is 600 s" "$H14/logs/brief.log" \
    && ok "health wait: logs that it paused because of the cap" \
    || fail "health wait: no cap log line ($(tail -2 "$H14/logs/brief.log"))"
else
  ok "health wait: cap checks skipped at 23:59"; ok "health wait: cap log check skipped at 23:59"
fi
# Past the deadline the brief goes without the mark (one log line, exit 0).
H16="$TMP/h16"; mk_hub "$H16"
run_brief "$H16" KB_PROCESS_ID=daily KB_PROCESS_TIMEOUT=600 \
  KB_BRIEF_HEALTH_READY_FILE="$H16/health-ready.json" KB_BRIEF_HEALTH_WAIT_UNTIL=00:00 >/dev/null; RC=$?
[[ $RC -eq 0 && $(orch_count "$H16") == "1" ]] \
  && grep -q "health ready mark missing at 00:00; brief goes without it" "$H16/logs/brief.log" \
  && ok "health wait: past the deadline the brief goes without the mark" \
  || fail "health wait: past-deadline rc=$RC orch=$(orch_count "$H16")"
H15="$TMP/h15"; mk_hub "$H15"
printf '{"morning_wait": {"date": "%s", "done": true}}\n' "$TODAY" > "$H15/health-ready.json"
run_brief "$H15" KB_PROCESS_ID=daily KB_PROCESS_TIMEOUT=7200 \
  KB_BRIEF_HEALTH_READY_FILE="$H15/health-ready.json" KB_BRIEF_HEALTH_WAIT_UNTIL=23:59 >/dev/null; RC=$?
[[ $RC -eq 0 ]] && ! grep -q "health wait paused\|ready mark missing" "$H15/logs/brief.log" \
  && ok "health wait: ready mark present → no wait, no warning" || fail "health wait: ready mark path rc=$RC"

# =============== the bot token reaches only the sender, never the model run ==
H17="$TMP/h17"; mk_hub "$H17"
printf 'TELEGRAM_BOT_TOKEN=tok-only-for-sender\nTELEGRAM_CHAT_ID=1\n' > "$H17/personal/.secrets"
cat > "$H17/bin/kb-orchestrator-run" <<'SH'
#!/bin/sh
env > "$KB_HUB/orch-env"
printf 'pass1 table\n---BRIEF---\nFIXTURE_BRIEF_BODY env\n'
SH
cat > "$H17/bin/kb-channel-send-text" <<'SH'
#!/bin/sh
echo "${TELEGRAM_BOT_TOKEN:-none}/${TELEGRAM_CHAT_ID:-none}" > "$KB_HUB/sender-env"
echo '{"outcome":"success","message_id":7}'
SH
chmod +x "$H17/bin/kb-orchestrator-run" "$H17/bin/kb-channel-send-text"
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_BRIEF_PREVIEW_BEFORE=00:00 \
  KB_HUB="$H17" PATH="$H17/fakebin:$PATH" zsh "$SRC_BIN/kb-brief" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 && -s "$H17/orch-env" ]] && ! grep -q 'tok-only-for-sender' "$H17/orch-env" \
  && ok "secrets: the bot token is not in the model run's environment" \
  || fail "secrets: model env rc=$RC hits=$(grep -c 'tok-only-for-sender' "$H17/orch-env" 2>/dev/null)"
[[ "$(cat "$H17/sender-env" 2>/dev/null)" == "tok-only-for-sender/1" ]] \
  && ok "secrets: the sender still gets the .secrets token and chat id" \
  || fail "secrets: sender env=$(cat "$H17/sender-env" 2>/dev/null)"

# =============== kb-retro: persisted-before-send + verified marker ============
H4="$TMP/h4"; mk_hub "$H4"
printf -- '---\ndate: %s\ndelivery: telegram_ok\ndelivery_message_id: 42\nreflection: pending\n---\n\nBRIEF_BODY_FIXTURE\n' "$TODAY" > "$H4/briefs/$TODAY.md"
run_retro "$H4" FAKE_ORCH_MODE=retro KB_FAKE_TG_MODE=notok; RC=$?
F4="$H4/briefs/$TODAY.md"
[[ $RC -ne 0 ]] && ok "retro: unverified send exits non-zero" || fail "retro: unverified rc=0"
grep -q '^## Retro (' "$F4" && ok "retro: Retro persisted before send" || fail "retro: Retro not persisted"
[[ "$(fm_get "$F4" retro_delivery)" == "telegram_failed" ]] \
  && ok "retro: retro_delivery: telegram_failed recorded" \
  || fail "retro: state=$(fm_get "$F4" retro_delivery)"
OC=$(orch_count "$H4")
run_retro "$H4" FAKE_ORCH_MODE=retro; RC=$?
[[ $RC -eq 0 ]] && ok "retro: delivery retry succeeds" || fail "retro: retry rc=$RC"
[[ $(orch_count "$H4") == "$OC" ]] \
  && ok "retro: retry reused persisted retro — no second LLM" \
  || fail "retro: retry re-ran LLM"
[[ "$(fm_get "$F4" retro_delivery)" == "telegram_ok" && -n "$(fm_get "$F4" retro_delivery_message_id)" ]] \
  && ok "retro: verified marker + message id" || fail "retro: marker missing"
[[ $(grep -c '^## Retro (' "$F4") == "1" ]] \
  && ok "retro: exactly one Retro section" || fail "retro: duplicate Retro sections"
TC=$(tg_count "$H4"); OC=$(orch_count "$H4")
run_retro "$H4" FAKE_ORCH_MODE=retro; RC=$?
[[ $RC -eq 0 && $(tg_count "$H4") == "$TC" && $(orch_count "$H4") == "$OC" ]] \
  && ok "retro: delivered evening is a no-op" || fail "retro: delivered evening re-ran"

# =============== R-impl blocker 1: retro with NO day file ======================
H6="$TMP/h6"; mk_hub "$H6"
run_retro "$H6" FAKE_ORCH_MODE=retro; RC=$?
F6="$H6/briefs/$TODAY.md"
[[ $RC -eq 0 ]] && ok "retro-nofile: verified send succeeds" || fail "retro-nofile: rc=$RC"
[[ -f "$F6" && "$(head -n 1 "$F6")" == "---" ]] \
  && ok "retro-nofile: minimal day file created for evidence" || fail "retro-nofile: no day file"
grep -q '^## Retro (' "$F6" && ok "retro-nofile: Retro persisted" || fail "retro-nofile: Retro missing"
[[ "$(fm_get "$F6" retro_delivery)" == "telegram_ok" ]] \
  && ok "retro-nofile: verified marker recorded" || fail "retro-nofile: marker=$(fm_get "$F6" retro_delivery)"
[[ -z "$(fm_get "$F6" delivery)" ]] \
  && ok "retro-nofile: brief still counts as undelivered (no delivery key)" \
  || fail "retro-nofile: phantom brief delivery key"
OC6=$(orch_count "$H6"); TC6=$(tg_count "$H6")
run_retro "$H6" FAKE_ORCH_MODE=retro; RC=$?
[[ $RC -eq 0 && $(orch_count "$H6") == "$OC6" && $(tg_count "$H6") == "$TC6" ]] \
  && ok "retro-nofile: rerun is a no-op (fires exactly once, AC-9)" \
  || fail "retro-nofile: rerun duplicated work"
EV6=$(run_planner_evidence "$H6" 2>/dev/null || echo "helper-below")
if [[ "$EV6" == "False True" ]]; then
  ok "retro-nofile: planner sees retro_fired=true, brief_fired=false"
elif [[ "$EV6" == "helper-below" ]]; then
  RETRO_NOFILE_HUB="$H6"   # planner helper defined later; checked there
else
  fail "retro-nofile: planner evidence → $EV6"
fi

# =============== R-impl-2 blocker: late brief must not destroy retro evidence =
H9="$TMP/h9"; mk_hub "$H9"
run_retro "$H9" FAKE_ORCH_MODE=retro >/dev/null; RC=$?
F9="$H9/briefs/$TODAY.md"
[[ $RC -eq 0 && "$(fm_get "$F9" retro_delivery)" == "telegram_ok" ]] \
  || fail "regen-preserve: retro setup failed (rc=$RC)"
RETRO_ID_BEFORE=$(fm_get "$F9" retro_delivery_message_id)
run_brief "$H9"; RC=$?
[[ $RC -eq 0 ]] && ok "regen-preserve: late brief regenerates over minimal day file" \
               || fail "regen-preserve: late brief rc=$RC"
grep -q "FIXTURE_BRIEF_BODY" "$F9" && ok "regen-preserve: new brief body present" \
                                    || fail "regen-preserve: brief body missing"
[[ $(grep -c '^## Retro (' "$F9") == "1" ]] \
  && ok "regen-preserve: Retro section survived regeneration" \
  || fail "regen-preserve: Retro section destroyed"
[[ "$(fm_get "$F9" retro_delivery)" == "telegram_ok" && "$(fm_get "$F9" retro_delivery_message_id)" == "$RETRO_ID_BEFORE" ]] \
  && ok "regen-preserve: retro delivery evidence survived" \
  || fail "regen-preserve: retro evidence lost (state=$(fm_get "$F9" retro_delivery))"
[[ "$(fm_get "$F9" delivery)" == "telegram_ok" ]] \
  && ok "regen-preserve: brief delivered with own marker" \
  || fail "regen-preserve: brief marker=$(fm_get "$F9" delivery)"
TC9=$(tg_count "$H9"); OC9=$(orch_count "$H9")
run_retro "$H9" FAKE_ORCH_MODE=retro >/dev/null; RC=$?
[[ $RC -eq 0 && $(tg_count "$H9") == "$TC9" && $(orch_count "$H9") == "$OC9" ]] \
  && ok "regen-preserve: retro stays exactly-once after brief regen" \
  || fail "regen-preserve: retro re-fired after brief regen"

# =============== R-impl-2 nit: reflection repair on the no-op path ============
H10="$TMP/h10"; mk_hub "$H10"
printf -- '---\ndate: %s\ndelivery: telegram_ok\nretro_delivery: telegram_ok\nreflection: pending\n---\n\nbody\n\n## Retro (21:00)\n\nretro text\n\n## Reflection (21:00)\n\nreflection text\n' "$TODAY" > "$H10/briefs/$TODAY.md"
run_retro "$H10" FAKE_ORCH_MODE=retro >/dev/null; RC=$?
[[ $RC -eq 0 ]] && ok "reflection-repair: no-op path exits 0" || fail "reflection-repair: rc=$RC"
[[ "$(fm_get "$H10/briefs/$TODAY.md" reflection)" == "done" ]] \
  && ok "reflection-repair: pending flipped to done on no-op path" \
  || fail "reflection-repair: still $(fm_get "$H10/briefs/$TODAY.md" reflection)"

# retro orchestrator failure: loud + deduped
H5="$TMP/h5"; mk_hub "$H5"
printf -- '---\ndate: %s\ndelivery: telegram_ok\nreflection: pending\n---\n\nbody\n' "$TODAY" > "$H5/briefs/$TODAY.md"
run_retro "$H5" FAKE_ORCH_MODE=retro FAKE_ORCH_RC=75; RC=$?
[[ $RC -ne 0 ]] && ok "retro: orchestrator failure exits non-zero" || fail "retro: failure rc=0"
T5=$(tg_count "$H5")
run_retro "$H5" FAKE_ORCH_MODE=retro FAKE_ORCH_RC=75; RC=$?
[[ $RC -ne 0 && $(tg_count "$H5") == "$T5" ]] \
  && ok "retro: error telegram deduped per date" || fail "retro: error spam"

# =============== kb-planner: evidence-based fired reconstruction (AC-9) =======
PL="$TMP/planner"; mkdir -p "$PL/briefs" "$PL/logs"
run_planner_evidence() { # $1 = hub → prints "brief_fired retro_fired"
  KB_HUB="$1" python3 - "$SRC_BIN/kb-planner" "$1" <<'PY'
import importlib.util, importlib.machinery, pathlib, sys
spec = importlib.util.spec_from_loader(
    "kbplanner",
    importlib.machinery.SourceFileLoader("kbplanner", sys.argv[1]),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import datetime
today = datetime.date.today().isoformat()
b, r = mod._delivery_evidence(today)
print(f"{b} {r}")
PY
}
EV=$(run_planner_evidence "$PL")
[[ "$EV" == "False False" ]] && ok "planner: no file → both unfired" || fail "planner: no-file → $EV"
printf -- '---\ndate: %s\ndelivery: telegram_ok\ndelivery_message_id: 7\n---\nbody\n' "$TODAY" > "$PL/briefs/$TODAY.md"
EV=$(run_planner_evidence "$PL")
[[ "$EV" == "True False" ]] && ok "planner: verified brief → brief_fired only" || fail "planner: verified-brief → $EV"
printf -- '---\ndate: %s\ndelivery: telegram_failed\n---\nbody\n' "$TODAY" > "$PL/briefs/$TODAY.md"
EV=$(run_planner_evidence "$PL")
[[ "$EV" == "False False" ]] && ok "planner: undelivered brief → unfired (retry)" || fail "planner: undelivered → $EV"
printf -- '---\ndate: %s\ndelivery: sent\n---\nbody\n' "$TODAY" > "$PL/briefs/$TODAY.md"
EV=$(run_planner_evidence "$PL")
[[ "$EV" == "False False" ]] && ok "planner: legacy unverified 'sent' → unfired" || fail "planner: legacy sent → $EV"
printf -- '---\ndate: %s\ndelivery: telegram_ok\nretro_delivery: telegram_ok\n---\nbody\n\n## Retro (21:00)\n\nretro text\n' "$TODAY" > "$PL/briefs/$TODAY.md"
EV=$(run_planner_evidence "$PL")
[[ "$EV" == "True True" ]] && ok "planner: verified retro heading+marker → retro_fired" || fail "planner: retro → $EV"
printf -- '---\ndate: %s\ndelivery: telegram_ok\n---\nbody\n\n## Retro (21:00)\n\nretro text\n' "$TODAY" > "$PL/briefs/$TODAY.md"
EV=$(run_planner_evidence "$PL")
[[ "$EV" == "True False" ]] && ok "planner: Retro heading without marker → unfired" || fail "planner: heading-only → $EV"

# deferred blocker-1 planner check (helper was not yet defined at H6 time)
if [[ -n "${RETRO_NOFILE_HUB:-}" ]]; then
  EV6=$(run_planner_evidence "$RETRO_NOFILE_HUB")
  [[ "$EV6" == "False True" ]] \
    && ok "retro-nofile: planner sees retro_fired=true, brief_fired=false" \
    || fail "retro-nofile: planner evidence → $EV6"
fi

# main() wiring: plan fields come from evidence, not the clock
WIRE=$(KB_HUB="$PL" python3 - "$SRC_BIN/kb-planner" <<'PY'
import importlib.util, importlib.machinery, json, sys, datetime
spec = importlib.util.spec_from_loader(
    "kbplanner2", importlib.machinery.SourceFileLoader("kbplanner2", sys.argv[1]))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
now = datetime.datetime.now()
early = now.replace(hour=0, minute=1)
mod.geo = lambda: (0.0, 0.0, "UTC")
mod.sun_times = lambda lat, lon, tz, date: (early, early)  # both "already past"
mod.main()
plan = json.loads(mod.PLAN_PATH.read_text())
print(plan["brief_fired"], plan["retro_fired"])
PY
)
[[ "$WIRE" == "True False" ]] \
  && ok "planner: main() ignores the clock, uses delivery evidence" \
  || fail "planner: main() wiring → $WIRE (clock leaked back in?)"

# The planner never blocks the day: the installer's empty .secrets values must
# not crash it, every lookup may fail (simulated offline, no real network), and
# today's plan is still written with default times. A configured fallback
# location is preferred over the plain-HTTP IP lookup.
planner_offline() { # $1 = hub → prints "<ok|bad plan> <lookups>"
  KB_HUB="$1" python3 - "$SRC_BIN/kb-planner" <<'PY'
import importlib.util, importlib.machinery, json, sys, datetime
spec = importlib.util.spec_from_loader(
    "kbplanner_offline", importlib.machinery.SourceFileLoader("kbplanner_offline", sys.argv[1]))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
calls = []
def offline(*_a, **_k):
    calls.append("sun")
    raise OSError("network is unreachable")
def ipapi():
    calls.append("ip-api")
    return None
mod._geo_corelocation = lambda: None
mod._geo_ipapi = ipapi
mod.sun_times = offline
mod.main()
plan = json.loads(mod.PLAN_PATH.read_text())
good = (plan["date"] == datetime.date.today().isoformat()
        and plan["brief_hm"] == "07:00" and plan["retro_hm"] == "20:45")
print(("ok" if good else f"bad:{plan}") + " " + (",".join(calls) or "none"))
PY
}
PR="$TMP/planner-offline"; mkdir -p "$PR/personal" "$PR/logs"
printf 'TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nKB_FALLBACK_LAT=\nKB_FALLBACK_LON=\nKB_FALLBACK_TZ=\n' > "$PR/personal/.secrets"
EV=$( (unset KB_FALLBACK_LAT KB_FALLBACK_LON KB_FALLBACK_TZ; planner_offline "$PR") 2>&1 | tail -1)
[[ "$EV" == "ok ip-api" ]] && ok "planner: installer .secrets + no location → today's plan, default times" \
  || fail "planner: offline/no-location → $EV"
printf 'KB_FALLBACK_LAT=40.4\nKB_FALLBACK_LON=-3.7\nKB_FALLBACK_TZ=Europe/Madrid\n' > "$PR/personal/.secrets"
EV=$( (unset KB_FALLBACK_LAT KB_FALLBACK_LON KB_FALLBACK_TZ; planner_offline "$PR") 2>&1 | tail -1)
[[ "$EV" == "ok sun" ]] && ok "planner: fallback location skips ip-api; failed sun lookup → defaults" \
  || fail "planner: fallback/offline → $EV"

# =============== kb-orchestrator-run: missing binary is failover, not crash ===
OD="$TMP/orch"; mkdir -p "$OD/bins" "$OD/state"
cat > "$OD/bins/codex" <<'SH'
#!/bin/sh
# minimal codex exec fake: honor `-o <file>`
out=""
prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
[ -n "$out" ] && printf 'CODEX_FALLBACK_ANSWER\n' > "$out"
printf 'CODEX_FALLBACK_ANSWER\n'
exit 0
SH
chmod +x "$OD/bins/codex"
# "Missing" providers are stubs that fail like an absent command (rc 127). A
# truly absent KB_CLAUDE_BIN/KB_CODEX_BIN would fall through to PATH and to
# /opt/homebrew/bin or /usr/local/bin, i.e. a contributor's real, logged-in CLI.
for _cli in claude-missing codex-missing; do
  printf '#!/bin/sh\necho "%s: command not found" >&2\nexit 127\n' "${_cli%-missing}" > "$OD/bins/$_cli"
  chmod +x "$OD/bins/$_cli"
done
O1=$(env PATH="/usr/bin:/bin" \
  KB_ORCHESTRATOR_BACKENDS="claude,codex" \
  KB_CLAUDE_BIN="$OD/bins/claude-missing" \
  KB_CODEX_BIN="$OD/bins/codex" \
  KB_ORCHESTRATOR_STATE_DIR="$OD/state" \
  KB_ORCHESTRATOR_STATE_FILE="$OD/state/state.json" \
  KB_ORCHESTRATOR_LOG_FILE="$OD/state/orch.log" \
  "$PY3" "$SRC_BIN/kb-orchestrator-run" --cwd "$OD" "ping" 2>"$OD/stderr.txt"); RC=$?
[[ $RC -eq 0 && "$O1" == *"CODEX_FALLBACK_ANSWER"* ]] \
  && ok "orch: missing claude binary → failover to codex" \
  || fail "orch: missing claude rc=$RC out=$(head -c 80 <<<"$O1")"
grep -q "Traceback" "$OD/stderr.txt" && fail "orch: crash traceback on missing binary" \
                                     || ok "orch: no Python crash on missing binary"
O2=$(env PATH="/usr/bin:/bin" \
  KB_ORCHESTRATOR_BACKENDS="claude,codex" \
  KB_CLAUDE_BIN="$OD/bins/claude-missing" \
  KB_CODEX_BIN="$OD/bins/codex-missing" \
  KB_ORCHESTRATOR_STATE_DIR="$OD/state2" \
  KB_ORCHESTRATOR_STATE_FILE="$OD/state2/state.json" \
  KB_ORCHESTRATOR_LOG_FILE="$OD/state2/orch.log" \
  "$PY3" "$SRC_BIN/kb-orchestrator-run" --cwd "$OD" "ping" 2>"$OD/stderr2.txt"); RC=$?
[[ $RC -eq 75 ]] && ok "orch: both providers missing → rc=75 exhausted" \
                 || fail "orch: both-missing rc=$RC"
grep -q "Traceback" "$OD/stderr2.txt" && fail "orch: crash traceback when both missing" \
                                      || ok "orch: clean exhaustion, no traceback"

echo; echo "PASS=$PASS FAIL=$FAIL"; [[ "$FAIL" == "0" ]]
