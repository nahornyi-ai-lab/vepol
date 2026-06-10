#!/usr/bin/env bash
# Tests for the processes release cut (spec: processes-release-spec-2026-06-09).
#
# Covers the 13 "Tests First" acceptance cases:
#   T1/T2   processes.yaml schema (five fields, fail-closed)
#   T3      independent enabled flags for daily/retro/learning
#   T4      learning --text-only: packet+manifest, telegram digest, zero notebooklm
#   T5      required notebooklm_audio output failure → not fired
#   T6      people-extract via kb-extract-people, no Calendar involvement
#   T7      --init-watermarks bootstrap before scheduled enablement
#   T8      staged People cards never auto-approved (reject flow works)
#   T9      people-remind launchd-equivalent smoke + send-failure exit code
#   T10     calendar disabled / on-demand never scheduled by tick
#   T11     after:* runs only after successful same-day parent
#   T12     file-only output is not user delivery
#   T13     process-improve: failing eval not applied, no silent apply
#
# Real scripts against temp KB fixtures; command shims only to prevent real
# external sends / quota use.
#
# Usage: bash tests/processes/run.sh

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="${KB_PROCESS_TEST_BIN:-$ROOT/bin}"
HUB_BIN="$HOME/knowledge/bin"   # kb-extract-people is hub-only (not in seed yet)
PY=python3
TODAY=$(date +%Y-%m-%d)

PASS=0
FAIL=0
ok()  { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
check() { # check <rc-expr> <label>  — rc-expr "0" means last cmd rc==0 expected
  local want="$1" got="$2" label="$3"
  if [[ "$got" == "$want" ]]; then ok "$label"; else bad "$label (want rc=$want got rc=$got)"; fi
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

new_hub() { # new_hub <name> → prints hub dir
  local d="$TMP/hub-$1"
  mkdir -p "$d"/{bin,logs,personal,reports,people,.orchestrator}
  printf '{"date": "%s", "brief_hm": "00:00", "retro_hm": "00:00"}\n' "$TODAY" \
    > "$d/logs/today-plan.json"
  echo "$d"
}

mkshim() { # mkshim <hub> <name> [rc]
  local hub="$1" name="$2" rc="${3:-0}"
  cat > "$hub/bin/$name" <<EOF
#!/usr/bin/env bash
echo "$name \$* outputs=\${KB_PROCESS_OUTPUTS:-} bg=\${KB_PROCESS_BACKGROUND:-}" >> "$hub/calls.log"
exit $rc
EOF
  chmod +x "$hub/bin/$name"
}

mkchannel() { # mkchannel <hub> [rc] — kb-channel-send shim recording messages
  local hub="$1" rc="${2:-0}"
  cat > "$hub/bin/kb-channel-send" <<EOF
#!/usr/bin/env bash
printf 'type=%s\nmsg=%s\n---\n' "\$1" "\$2" >> "$hub/channel.log"
exit $rc
EOF
  chmod +x "$hub/bin/kb-channel-send"
}

mknotebooklm() { # mknotebooklm <hub> — recorder that fails on ANY call
  local hub="$1"
  cat > "$hub/bin/notebooklm-recorder" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$hub/notebooklm-calls.log"
exit 1
EOF
  chmod +x "$hub/bin/notebooklm-recorder"
}

run_tick() { KB_HUB="$1" "$PY" "$BIN/kb-tick" >/dev/null 2>&1; }

validate() { "$PY" "$BIN/_kb_processes.py" "$1" >/dev/null 2>&1; }

plan_get() { # plan_get <hub> <key> → "true"/"false"/"absent"
  "$PY" - "$1/logs/today-plan.json" "$2" <<'EOF'
import json, sys
plan = json.load(open(sys.argv[1]))
v = plan.get(sys.argv[2])
print("absent" if v is None else ("true" if v else "false"))
EOF
}

calls_has() { grep -q "$2" "$1/calls.log" 2>/dev/null; }

# Base valid config block writer
write_cfg() { cat > "$1/personal/processes.yaml"; }

echo "=== T1/T2: processes.yaml schema (fail-closed) ==="

CFG="$TMP/cfg"
mkdir -p "$CFG"

cat > "$CFG/valid.yaml" <<'EOF'
# release defaults shape
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram, file]
- id: retro
  enabled: true
  when: "20:45"
  run: kb-retro
  outputs: [telegram, file]
- id: learning
  enabled: true
  when: after:daily
  run: kb-daily-research --text-only
  outputs: [telegram, file]
- id: people-extract
  enabled: false
  when: after:retro
  run: kb-extract-people --hub ~/knowledge --no-llm --quiet
  outputs: [people, telegram, file]
- id: people-remind
  enabled: false
  when: "09:00"
  run: kb-people-remind --horizon 0
  outputs: [telegram]
- id: calendar
  enabled: false
  when: on-demand
  run: kb-calendar-sync --dry-run
  outputs: [file]
- id: process-improve
  enabled: false
  when: on-demand
  run: kb-evolution check-policy
  outputs: [file]
EOF
validate "$CFG/valid.yaml"; check 0 $? "T2 release-default config accepted"

cat > "$CFG/audio-on-demand.yaml" <<'EOF'
- id: release-audio
  enabled: false
  when: on-demand
  run: kb-daily-research
  outputs: [notebooklm_audio, file]
EOF
validate "$CFG/audio-on-demand.yaml"; check 0 $? "T2 notebooklm_audio allowed for on-demand"

cat > "$CFG/missing-field.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
EOF
validate "$CFG/missing-field.yaml" && bad "T1 missing field rejected" || ok "T1 missing field rejected"

cat > "$CFG/extra-field.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram]
  retries: 3
EOF
validate "$CFG/extra-field.yaml" && bad "T1 extra field rejected" || ok "T1 extra field rejected"

cat > "$CFG/dup-id.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram]
- id: daily
  enabled: false
  when: "08:30"
  run: kb-brief
  outputs: [telegram]
EOF
validate "$CFG/dup-id.yaml" && bad "T1 duplicate id rejected" || ok "T1 duplicate id rejected"

cat > "$CFG/bad-when.yaml" <<'EOF'
- id: daily
  enabled: true
  when: sometimes
  run: kb-brief
  outputs: [telegram]
EOF
validate "$CFG/bad-when.yaml" && bad "T1 invalid when rejected" || ok "T1 invalid when rejected"

cat > "$CFG/bad-when-25.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "25:99"
  run: kb-brief
  outputs: [telegram]
EOF
validate "$CFG/bad-when-25.yaml" && bad "T1 when 25:99 rejected" || ok "T1 when 25:99 rejected"

cat > "$CFG/bad-output.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram, notebook]
EOF
validate "$CFG/bad-output.yaml" && bad "T1 invalid output rejected" || ok "T1 invalid output rejected"

cat > "$CFG/audio-background.yaml" <<'EOF'
- id: learning
  enabled: true
  when: "08:00"
  run: kb-daily-research
  outputs: [notebooklm_audio, file]
EOF
validate "$CFG/audio-background.yaml" && bad "T1 background notebooklm_audio rejected" || ok "T1 background notebooklm_audio rejected"

cat > "$CFG/bad-enabled.yaml" <<'EOF'
- id: daily
  enabled: yes please
  when: "07:30"
  run: kb-brief
  outputs: [telegram]
EOF
validate "$CFG/bad-enabled.yaml" && bad "T1 non-bool enabled rejected" || ok "T1 non-bool enabled rejected"

cat > "$CFG/after-unknown.yaml" <<'EOF'
- id: learning
  enabled: true
  when: after:ghost
  run: kb-daily-research --text-only
  outputs: [telegram, file]
EOF
validate "$CFG/after-unknown.yaml" && bad "T1 after:<unknown> rejected" || ok "T1 after:<unknown> rejected"

cat > "$CFG/after-cycle.yaml" <<'EOF'
- id: a
  enabled: true
  when: after:b
  run: x
  outputs: [file]
- id: b
  enabled: true
  when: after:a
  run: y
  outputs: [file]
EOF
validate "$CFG/after-cycle.yaml" && bad "T1 after-cycle rejected" || ok "T1 after-cycle rejected"

cat > "$CFG/empty-outputs.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: []
EOF
validate "$CFG/empty-outputs.yaml" && bad "T1 empty outputs rejected" || ok "T1 empty outputs rejected"

echo
echo "=== fail-closed: invalid config → tick runs nothing ==="

HUB=$(new_hub failclosed)
mkshim "$HUB" shim-daily
cp "$CFG/extra-field.yaml" "$HUB/personal/processes.yaml"
# point the (invalid) config's run at the shim anyway: tick must not run it
run_tick "$HUB"
if [[ -f "$HUB/calls.log" ]]; then bad "invalid config: no process ran"; else ok "invalid config: no process ran"; fi
grep -q "fail closed" "$HUB/logs/planner.log" 2>/dev/null \
  && ok "invalid config: reason logged" || bad "invalid config: reason logged"

echo
echo "=== missing config → safe default created ==="

HUB=$(new_hub defaultcfg)
run_tick "$HUB"
if [[ -f "$HUB/personal/processes.yaml" ]]; then ok "default processes.yaml created"; else bad "default processes.yaml created"; fi
validate "$HUB/personal/processes.yaml"; check 0 $? "default processes.yaml is valid"
# people-remind/calendar/process-improve must default disabled
for pid in people-remind calendar process-improve; do
  "$PY" - "$HUB/personal/processes.yaml" "$pid" <<'EOF' && ok "default: $pid disabled" || bad "default: $pid disabled"
import sys, re
text = open(sys.argv[1]).read()
pid = sys.argv[2]
m = re.search(rf"- id: {re.escape(pid)}\n((?:  .*\n)*)", text)
assert m, f"{pid} missing"
assert re.search(r"enabled:\s*false", m.group(1)), f"{pid} not disabled"
EOF
done

echo
echo "=== T3: independent enabled flags ==="

HUB=$(new_hub flags1)
mkshim "$HUB" shim-daily; mkshim "$HUB" shim-retro; mkshim "$HUB" shim-learning
write_cfg "$HUB" <<'EOF'
- id: daily
  enabled: false
  when: "00:00"
  run: shim-daily
  outputs: [telegram, file]
- id: retro
  enabled: true
  when: "00:00"
  run: shim-retro
  outputs: [telegram, file]
- id: learning
  enabled: true
  when: "00:00"
  run: shim-learning
  outputs: [telegram, file]
EOF
run_tick "$HUB"
calls_has "$HUB" shim-daily && bad "daily disabled → daily not run" || ok "daily disabled → daily not run"
calls_has "$HUB" shim-retro && ok "daily disabled → retro still runs" || bad "daily disabled → retro still runs"
calls_has "$HUB" shim-learning && ok "daily disabled → learning still runs" || bad "daily disabled → learning still runs"
[[ "$(plan_get "$HUB" retro_fired)" == "true" ]] && ok "retro_fired set" || bad "retro_fired set"
[[ "$(plan_get "$HUB" daily_research_fired)" == "true" ]] && ok "learning → daily_research_fired set" || bad "learning → daily_research_fired set"
[[ "$(plan_get "$HUB" brief_fired)" != "true" ]] && ok "brief_fired not set" || bad "brief_fired not set"

HUB=$(new_hub flags2)
mkshim "$HUB" shim-daily; mkshim "$HUB" shim-retro; mkshim "$HUB" shim-learning
write_cfg "$HUB" <<'EOF'
- id: daily
  enabled: true
  when: "00:00"
  run: shim-daily
  outputs: [telegram, file]
- id: retro
  enabled: true
  when: "00:00"
  run: shim-retro
  outputs: [telegram, file]
- id: learning
  enabled: false
  when: "00:00"
  run: shim-learning
  outputs: [telegram, file]
EOF
run_tick "$HUB"
calls_has "$HUB" shim-learning && bad "learning disabled → learning not run" || ok "learning disabled → learning not run"
calls_has "$HUB" shim-daily && ok "learning disabled → daily still runs" || bad "learning disabled → daily still runs"
calls_has "$HUB" shim-retro && ok "learning disabled → retro still runs" || bad "learning disabled → retro still runs"

echo
echo "=== T11: after:* parent gating ==="

HUB=$(new_hub after-ok)
mkshim "$HUB" shim-daily; mkshim "$HUB" shim-learning
write_cfg "$HUB" <<'EOF'
- id: daily
  enabled: true
  when: "00:00"
  run: shim-daily
  outputs: [telegram, file]
- id: learning
  enabled: true
  when: after:daily
  run: shim-learning
  outputs: [telegram, file]
EOF
run_tick "$HUB"
calls_has "$HUB" shim-daily && ok "tick1: parent ran" || bad "tick1: parent ran"
calls_has "$HUB" shim-learning && bad "tick1: dependent waits for next tick" || ok "tick1: dependent waits for next tick"
run_tick "$HUB"
calls_has "$HUB" shim-learning && ok "tick2: dependent ran after parent success" || bad "tick2: dependent ran after parent success"
[[ "$(plan_get "$HUB" daily_research_fired)" == "true" ]] && ok "tick2: dependent fired" || bad "tick2: dependent fired"

HUB=$(new_hub after-fail)
mkshim "$HUB" shim-daily 1; mkshim "$HUB" shim-learning
write_cfg "$HUB" <<'EOF'
- id: daily
  enabled: true
  when: "00:00"
  run: shim-daily
  outputs: [telegram, file]
- id: learning
  enabled: true
  when: after:daily
  run: shim-learning
  outputs: [telegram, file]
EOF
run_tick "$HUB"; run_tick "$HUB"
[[ "$(plan_get "$HUB" brief_fired)" != "true" ]] && ok "failed parent: not fired" || bad "failed parent: not fired"
calls_has "$HUB" shim-learning && bad "failed parent blocks dependent" || ok "failed parent blocks dependent"

echo
echo "=== T10: calendar / on-demand never scheduled ==="

HUB=$(new_hub calendar)
mkshim "$HUB" kb-calendar-sync; mkshim "$HUB" shim-improve
write_cfg "$HUB" <<'EOF'
- id: calendar
  enabled: false
  when: on-demand
  run: kb-calendar-sync --dry-run
  outputs: [file]
- id: process-improve
  enabled: true
  when: on-demand
  run: shim-improve
  outputs: [file]
EOF
run_tick "$HUB"
calls_has "$HUB" kb-calendar-sync && bad "calendar.enabled=false → kb-calendar-sync never called" || ok "calendar.enabled=false → kb-calendar-sync never called"
calls_has "$HUB" shim-improve && bad "on-demand never scheduled even when enabled" || ok "on-demand never scheduled even when enabled"

echo
echo "=== T4: learning --text-only (zero NotebookLM, telegram digest) ==="

HUB=$(new_hub textonly)
mknotebooklm "$HUB"; mkchannel "$HUB"
FIXTURE="$HUB/radar-fixture.json"
cat > "$FIXTURE" <<'EOF'
[
  {"title": "Running Codex safely at OpenAI", "url": "https://openai.com/index/running-codex-safely/",
   "source_type": "official", "score": 95, "date": "2026-06-08", "reason": "official governance signal"},
  {"title": "HarnessAPI: Skill-First Framework for MCP Tools", "url": "https://arxiv.org/abs/2605.22733",
   "source_type": "paper", "score": 74, "date": "2026-06-07", "reason": "agent tooling paper"}
]
EOF
KB_HUB="$HUB" KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-recorder" \
  KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE" \
  KB_PROCESS_OUTPUTS="telegram,file" KB_PROCESS_BACKGROUND=1 \
  "$PY" "$BIN/kb-daily-research" --text-only --date "$TODAY" >/dev/null 2>&1
check 0 $? "text-only exits 0"
PACKET="$HUB/reports/daily-research-notebooklm-brief-$TODAY.md"
[[ -s "$PACKET" ]] && ok "text-only writes packet" || bad "text-only writes packet"
MANIFEST="$HUB/.orchestrator/daily-research-$TODAY.json"
grep -q '"status": "completed"' "$MANIFEST" 2>/dev/null && ok "manifest completed" || bad "manifest completed"
grep -q 'text_only' "$MANIFEST" 2>/dev/null && ok "manifest marked text_only" || bad "manifest marked text_only"
[[ ! -s "$HUB/notebooklm-calls.log" ]] && ok "zero notebooklm calls" || bad "zero notebooklm calls"
grep -q "Running Codex safely" "$HUB/channel.log" 2>/dev/null && ok "telegram digest contains source" || bad "telegram digest contains source"

# second live switch deprecated: daily-research.yaml enabled=false must not block
HUB=$(new_hub secondswitch)
mknotebooklm "$HUB"; mkchannel "$HUB"
cat > "$HUB/personal/daily-research.yaml" <<'EOF'
enabled: false
mode: ai_agents_radar
language: ru
EOF
KB_HUB="$HUB" KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-recorder" \
  KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE" \
  KB_PROCESS_OUTPUTS="telegram,file" \
  "$PY" "$BIN/kb-daily-research" --text-only --date "$TODAY" >/dev/null 2>&1
check 0 $? "daily-research.yaml.enabled is not a second live switch"

# background full-mode (would call NotebookLM) must refuse
HUB=$(new_hub bgguard)
mknotebooklm "$HUB"
KB_HUB="$HUB" KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-recorder" \
  KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE" KB_PROCESS_BACKGROUND=1 \
  "$PY" "$BIN/kb-daily-research" --date "$TODAY" >/dev/null 2>&1
RC=$?
[[ "$RC" -ne 0 ]] && ok "background full-mode refused (rc=$RC)" || bad "background full-mode refused"
[[ ! -s "$HUB/notebooklm-calls.log" ]] && ok "background guard: zero notebooklm calls" || bad "background guard: zero notebooklm calls"

echo
echo "=== T5: explicit notebooklm_audio with no artifact → not fired ==="

HUB=$(new_hub audiofail)
mkchannel "$HUB"
cat > "$HUB/bin/notebooklm-mock" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$HUB/notebooklm-calls.log"
case "\$1" in
  create) printf '{"id":"nb_test"}\n';;
  source) printf '{"source_id":"s1"}\n';;
  generate) printf '{}\n';;   # no artifact id
  *) printf '{}\n';;
esac
exit 0
EOF
chmod +x "$HUB/bin/notebooklm-mock"
KB_HUB="$HUB" KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-mock" \
  KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE" \
  "$PY" "$BIN/kb-daily-research" --date "$TODAY" >/dev/null 2>&1
RC=$?
[[ "$RC" -ne 0 ]] && ok "no artifact → rc!=0 (tick will not set fired)" || bad "no artifact → rc!=0"
grep -q '"status": "failed"' "$HUB/.orchestrator/daily-research-$TODAY.json" 2>/dev/null \
  && ok "manifest status failed" || bad "manifest status failed"

echo
echo "=== T12: file-only is not user delivery ==="

HUB=$(new_hub delivery)
mknotebooklm "$HUB"; mkchannel "$HUB" 3   # channel send FAILS
# kb-tick resolves bare run commands strictly against $HUB/bin —
# link the real script into the fixture hub.
ln -s "$BIN/kb-daily-research" "$HUB/bin/kb-daily-research"
write_cfg "$HUB" <<EOF
- id: learning
  enabled: true
  when: "00:00"
  run: kb-daily-research --text-only
  outputs: [telegram, file]
EOF
export KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-recorder"
export KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE"
run_tick "$HUB"
unset KB_NOTEBOOKLM_BIN KB_DAILY_RESEARCH_COLLECTOR_FIXTURE
[[ "$(plan_get "$HUB" daily_research_fired)" != "true" ]] \
  && ok "telegram declared + send failed → not fired (file alone ≠ delivery)" \
  || bad "telegram declared + send failed → not fired"
[[ -s "$HUB/reports/daily-research-notebooklm-brief-$TODAY.md" ]] \
  && ok "file output still written (internal memory)" || bad "file output still written"

# Retry cap must stay fail-closed for text-only: even after max_attempts
# failed deliveries, the process must NOT exit 0 (tick would mark it fired
# with zero user delivery). Run the tick three more times to exhaust the
# cap (attempts increment per run), then assert the next run still fails.
export KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-recorder"
export KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE"
run_tick "$HUB"; run_tick "$HUB"; run_tick "$HUB"
KB_HUB="$HUB" KB_PROCESS_OUTPUTS="telegram,file" \
  "$PY" "$BIN/kb-daily-research" --text-only --date "$TODAY" >/dev/null 2>&1
RC_CAP=$?
unset KB_NOTEBOOKLM_BIN KB_DAILY_RESEARCH_COLLECTOR_FIXTURE
[[ "$RC_CAP" -ne 0 ]] && ok "retry cap: undelivered digest still exits non-zero" \
  || bad "retry cap: undelivered digest still exits non-zero (rc=0 would mark fired)"
[[ "$(plan_get "$HUB" daily_research_fired)" != "true" ]] \
  && ok "retry cap: fired never set without delivery" \
  || bad "retry cap: fired never set without delivery"

# Text-only failures must not consume the full-mode NotebookLM retry cap:
# after repeated failed deliveries, an explicit manual full-mode run (the
# only path allowed to call NotebookLM) must still proceed.
HUB=$(new_hub capisolation)
mknotebooklm "$HUB"; mkchannel "$HUB" 3   # failing channel
for _ in 1 2 3; do
  KB_HUB="$HUB" KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-recorder" \
    KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE" KB_PROCESS_OUTPUTS="telegram,file" \
    "$PY" "$BIN/kb-daily-research" --text-only --date "$TODAY" >/dev/null 2>&1
done
cat > "$HUB/bin/notebooklm-good" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$HUB/notebooklm-good-calls.log"
case "\$1" in
  create) printf '{"id":"nb_full"}\n';;
  source) printf '{"source_id":"s_full"}\n';;
  generate) printf '{"artifact_id":"art_full"}\n';;
  *) printf '{}\n';;
esac
exit 0
EOF
chmod +x "$HUB/bin/notebooklm-good"
KB_HUB="$HUB" KB_NOTEBOOKLM_BIN="$HUB/bin/notebooklm-good" \
  KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE" \
  "$PY" "$BIN/kb-daily-research" --date "$TODAY" >/dev/null 2>&1
RC_FULL=$?
[[ "$RC_FULL" -eq 0 ]] && ok "text-only failures do not exhaust full-mode retry cap" \
  || bad "text-only failures do not exhaust full-mode retry cap (rc=$RC_FULL)"
grep -q '"artifact_id": "art_full"' "$HUB/.orchestrator/daily-research-$TODAY.json" 2>/dev/null \
  && ok "manual full run completed with artifact after text failures" \
  || bad "manual full run completed with artifact after text failures"

echo
echo "=== T6: people-extract creates People without Calendar ==="

if [[ ! -x "$HUB_BIN/kb-extract-people" ]]; then
  bad "kb-extract-people present in hub bin"
else
ok "kb-extract-people present in hub bin"
PHUB="$TMP/hub-people6"; mkdir -p "$PHUB"/{bin,people,.orchestrator}
PROJ="$TMP/proj-a"; mkdir -p "$PROJ/knowledge"
cat > "$PHUB/registry.md" <<EOF
| slug | path | status |
|------|------|--------|
| proj-a | $PROJ | live |
EOF
cat > "$PROJ/knowledge/log.md" <<'EOF'
## [2026-06-09] meeting | intro call

Talked to anna.petrova@example.com about the pilot.
EOF
# calendar guard: recording shims first in PATH
GUARD="$TMP/guard-bin"; mkdir -p "$GUARD"
for g in kb-calendar-sync claude; do
  cat > "$GUARD/$g" <<EOF
#!/usr/bin/env bash
echo "$g \$*" >> "$TMP/guard-calls.log"
exit 0
EOF
  chmod +x "$GUARD/$g"
done
PATH="$GUARD:$PATH" "$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --no-llm --quiet
check 0 $? "people-extract exits 0"
[[ -f "$PHUB/people/anna-petrova.md" ]] && ok "live card created from high-confidence email" || bad "live card created from high-confidence email"
AUDIT="$PHUB/.orchestrator/people-extraction-$(date -u +%Y-%m-%d).json"
grep -q '"live_created": 1' "$AUDIT" 2>/dev/null && ok "audit evidence written" || bad "audit evidence written"
[[ ! -f "$TMP/guard-calls.log" ]] && ok "no Calendar / MCP host invoked" || bad "no Calendar / MCP host invoked"
fi

echo
echo "=== T7: watermark bootstrap gates scheduled scans ==="

if [[ -x "$HUB_BIN/kb-extract-people" ]]; then
PHUB="$TMP/hub-people7"; mkdir -p "$PHUB"/{bin,people,.orchestrator}
PROJ="$TMP/proj-b"; mkdir -p "$PROJ/knowledge"
cat > "$PHUB/registry.md" <<EOF
| slug | path | status |
|------|------|--------|
| proj-b | $PROJ | live |
EOF
cat > "$PROJ/knowledge/log.md" <<'EOF'
## [2026-06-01] note | historical

Old contact old.contact@example.com from history must not be scanned by scheduled run.
EOF
KB_PROCESS_BACKGROUND=1 "$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --no-llm --quiet >/dev/null 2>&1
check 0 $? "scheduled run before bootstrap exits 0 (skip, not crash)"
[[ ! -f "$PHUB/people/old-contact.md" ]] && ok "scheduled run before bootstrap scans nothing" || bad "scheduled run before bootstrap scans nothing"
"$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --init-watermarks
check 0 $? "--init-watermarks exits 0"
[[ -f "$PROJ/knowledge/.kb-people-extracted" ]] && ok "watermark file created" || bad "watermark file created"
cat >> "$PROJ/knowledge/log.md" <<EOF
## [$TODAY] intro | met fresh contact

Met fresh.person@example.com after bootstrap.
EOF
KB_PROCESS_BACKGROUND=1 "$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --no-llm --quiet >/dev/null 2>&1
check 0 $? "scheduled run after bootstrap exits 0"
[[ -f "$PHUB/people/fresh-person.md" ]] && ok "incremental hit applied after bootstrap" || bad "incremental hit applied after bootstrap"
[[ ! -f "$PHUB/people/old-contact.md" ]] && ok "history before watermark never scanned" || bad "history before watermark never scanned"
fi

echo
echo "=== T8: staged cards never auto-approved; reject flow ==="

if [[ -x "$HUB_BIN/kb-extract-people" ]]; then
PHUB="$TMP/hub-people8"; mkdir -p "$PHUB"/{bin,people,.orchestrator}
mkchannel "$PHUB"
PROJ="$TMP/proj-c"; mkdir -p "$PROJ/knowledge"
cat > "$PHUB/registry.md" <<EOF
| slug | path | status |
|------|------|--------|
| proj-c | $PROJ | live |
EOF
cat > "$PROJ/knowledge/log.md" <<'EOF'
## [2026-06-01] note | baseline

Nothing here yet.
EOF
"$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --init-watermarks
cat >> "$PROJ/knowledge/log.md" <<EOF
## [$TODAY] note | new telegram-only contact

Ping @TestStagedPerson about the demo.
EOF
KB_HUB="$PHUB" KB_PROCESS_BACKGROUND=1 KB_PROCESS_OUTPUTS="people,telegram,file" \
  "$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --no-llm --quiet >/dev/null 2>&1
check 0 $? "scheduled run staging draft exits 0"
[[ -f "$PHUB/people/teststagedperson.staged.md" ]] && ok "telegram-only hit staged (not live)" || bad "telegram-only hit staged (not live)"
[[ ! -f "$PHUB/people/teststagedperson.md" ]] && ok "no live card auto-created" || bad "no live card auto-created"
grep -q "staged" "$PHUB/channel.log" 2>/dev/null && ok "staged-review digest sent to telegram" || bad "staged-review digest sent to telegram"
# re-run: staged stays staged
KB_HUB="$PHUB" KB_PROCESS_BACKGROUND=1 "$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --no-llm --quiet >/dev/null 2>&1
[[ -f "$PHUB/people/teststagedperson.staged.md" && ! -f "$PHUB/people/teststagedperson.md" ]] \
  && ok "re-run keeps card staged (no auto-approve)" || bad "re-run keeps card staged (no auto-approve)"
"$PY" "$HUB_BIN/kb-extract-people" --hub "$PHUB" --reject teststagedperson --reason "test false positive"
check 0 $? "--reject exits 0"
[[ ! -f "$PHUB/people/teststagedperson.staged.md" ]] && ok "rejected staged card removed" || bad "rejected staged card removed"
grep -q "TestStagedPerson" "$PHUB/people/.rejected.yaml" 2>/dev/null && ok "identity recorded in .rejected.yaml" || bad "identity recorded in .rejected.yaml"
fi

echo
echo "=== T9: people-remind launchd-equivalent smoke ==="

PHUB="$TMP/hub-remind"; mkdir -p "$PHUB"/{bin,people,logs}
cat > "$PHUB/people/test-person.md" <<'EOF'
---
id: 00000000-0000-0000-0000-000000000001
name: Test Person
slug: test-person
next_touch_due: 2026-06-09
tags: [test]
---

# Test Person
EOF
OUT=$(env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  KB_HUB="$PHUB" python3 "$BIN/kb-people-remind" --dry-run --horizon 0 2>&1)
RC=$?
[[ "$RC" -eq 0 ]] && ok "launchd-equivalent env: dry-run exits 0" || bad "launchd-equivalent env: dry-run exits 0 (rc=$RC: $OUT)"
echo "$OUT" | grep -q "Test Person" && ok "due contact surfaced under launchd env" || bad "due contact surfaced under launchd env"

mkchannel "$PHUB" 3   # send fails
KB_HUB="$PHUB" "$PY" "$BIN/kb-people-remind" --horizon 0 >/dev/null 2>&1
RC=$?
[[ "$RC" -ne 0 ]] && ok "failed telegram send → non-zero exit (tick will retry)" || bad "failed telegram send → non-zero exit"

mkchannel "$PHUB" 0
KB_HUB="$PHUB" "$PY" "$BIN/kb-people-remind" --horizon 0 >/dev/null 2>&1
check 0 $? "successful send → exit 0"
grep -q "Test Person" "$PHUB/channel.log" 2>/dev/null && ok "reminder delivered via channel" || bad "reminder delivered via channel"

echo
echo "=== T13: process-improve is proposal+eval only, no silent apply ==="

EVK="$TMP/know-evo"; mkdir -p "$EVK"
"$PY" - "$BIN" "$EVK" <<'EOF'
import sys, pathlib, json
bin_dir, know = sys.argv[1], pathlib.Path(sys.argv[2])
sys.path.insert(0, bin_dir)
from _kb_evolution import scaffold, proposals, policy
scaffold.ensure_evolution_tree(know)
(know / "agents").mkdir(exist_ok=True)
(know / "agents" / "agent-card.md").write_text("# Agent\n\n## Self-introduction\n\nI help.\n")
p = know / "evolution" / "proposals" / "prop-prompt-2026-06-10-001.md"
p.write_text("""---
proposal_id: prop-prompt-2026-06-10-001
type: mutation-proposal
status: pending
created: 2026-06-10T00:00:00Z
author:
  type: orchestrator
  identity: codex
surface_type: prompt
surface_target: agents/agent-card.md
scope:
  affected_section: Self-introduction
  unit_of_mutation: markdown-block
  blast_radius:
    files: 1
    bytes: 32
    runtimes_affected: [codex]
mutation_diff: inline
rationale:
  observation_signal: sig-2026-06-10-001
  hypothesis: Make the introduction clearer.
  expected_metric: accepted on next three tasks
  metric_objectivity: objective
risk_tier: 1
risk_justification: bounded wording change
reversibility:
  type: kb-revert
  atomicity_unit: markdown-block
  test_executed: true
  test_evidence: evolution/replay-fixtures/reference.txt
input_origins: ["runtime-generated"]
public_safe: false
evaluation_plan:
  reviewer_orchestrators: [claude-code]
  conflict_check: pass
  shadow_replay_tasks: null
  measure_on_next_real_tasks: 3
  regression_check: manual reference
  drift_check: pass
  invariant_check: pass
  hitl_required: false
  ambiguity_flags: []
related:
  parent_proposals: []
  related_signals: []
  affects_promoted_capability: null
---

# Proposal

Body.
""")
prop = proposals.validate_proposal_file(p)
failing = {"identity": "claude-code",
           "sahoo": {"drift_check": "pass", "invariant_check": "pass", "regression_check": "fail"},
           "conflict_check": "pass"}
r = policy.validate_apply_request(know, prop, evaluator=failing)
assert not r.allowed, "failing eval must not be applied"
author_self = {"identity": "codex",
               "sahoo": {"drift_check": "pass", "invariant_check": "pass", "regression_check": "pass"},
               "conflict_check": "pass"}
r2 = policy.validate_apply_request(know, prop, evaluator=author_self)
assert not r2.allowed and r2.hitl_required, "author-as-sole-evaluator must require cross-review/HITL"
card_before = (know / "agents" / "agent-card.md").read_text()
ledger = (know / "evolution" / "mutations.md").read_text() if (know / "evolution" / "mutations.md").exists() else ""
assert "prop-prompt-2026-06-10-001" not in ledger, "no ledger apply entry without explicit accept"
assert "clearer" not in card_before, "target file untouched by eval"
print("ok")
EOF
check 0 $? "failing/conflicted eval never applied; target untouched"

echo
echo "==========================================="
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
