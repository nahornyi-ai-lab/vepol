#!/usr/bin/env bash
# Tests for kb-daily-research (one daily topic → NotebookLM audio).
#
# Usage: bash bin/tests/test-daily-research.sh

set -euo pipefail

PASS=0
FAIL=0
TMPHUB=$(mktemp -d)
trap 'rm -rf "$TMPHUB"' EXIT

mkdir -p "$TMPHUB"/{bin,logs,personal,reports,.orchestrator,projects/demo-project}
mkdir -p "$TMPHUB/projects/demo-project"/{knowledge,}
export KB_HUB="$TMPHUB"

REAL_BIN="$HOME/knowledge/bin/kb-daily-research"
MOCK="$TMPHUB/bin/notebooklm-mock"
CALL_LOG="$TMPHUB/notebooklm-calls.log"

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

cat > "$TMPHUB/projects/demo-project/state.md" <<'EOF'
# demo-project — state

Vepol is focusing on daily NotebookLM research and safe local agent runtime.
EOF
cat > "$TMPHUB/projects/demo-project/backlog.md" <<'EOF'
# Backlog

## Open

- [ ] Spec: MCP tool safety for local AI agents — opened 2026-05-23 — context: improve Vepol runtime guardrails
- [ ] Public launch prep — opened 2026-05-23 — context: write announcement
EOF
cat > "$TMPHUB/projects/demo-project/log.md" <<'EOF'
## [2026-05-23] feature | daily research | NotebookLM product loop discussed.
EOF

cat > "$MOCK" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${NOTEBOOKLM_CALL_LOG:?}"

if [[ "$1" == "create" ]]; then
  printf '{"id":"nb_daily","title":"%s"}\n' "$2"
  exit 0
fi

if [[ "$1" == "source" && "$2" == "add" ]]; then
  printf '{"source_id":"src_context","status":"processing"}\n'
  exit 0
fi

if [[ "$1" == "source" && "$2" == "wait" ]]; then
  printf '{"source_id":"%s","status":"ready"}\n' "$3"
  exit 0
fi

if [[ "$1" == "source" && "$2" == "add-research" ]]; then
  printf '{"status":"completed","imported":3}\n'
  exit 0
fi

if [[ "$1" == "generate" && "$2" == "audio" ]]; then
  printf '{"artifact_id":"art_daily","status":"completed"}\n'
  exit 0
fi

if [[ "$1" == "download" && "$2" == "audio" ]]; then
  out=""
  for arg in "$@"; do
    case "$arg" in
      *.mp3) out="$arg" ;;
    esac
  done
  mkdir -p "$(dirname "$out")"
  printf 'mock daily mp3' > "$out"
  printf 'downloaded %s\n' "$out"
  exit 0
fi

printf 'unexpected command: %s\n' "$*" >&2
exit 9
EOF
chmod +x "$MOCK"
export KB_NOTEBOOKLM_BIN="$MOCK"
export NOTEBOOKLM_CALL_LOG="$CALL_LOG"
: > "$CALL_LOG"

DATE1="2026-05-23"

echo "=== T1 set-topic writes config ==="
"$REAL_BIN" --set-topic "MCP tool safety for local AI agents" >/tmp/daily-research-t1.out
grep -q "topic_override: MCP tool safety for local AI agents" "$TMPHUB/personal/daily-research.yaml" \
  && ok "T1: topic_override written" || fail "T1: topic_override missing"

echo "=== T2 override topic creates NotebookLM research audio ==="
"$REAL_BIN" --date "$DATE1" >/tmp/daily-research-t2.out 2>/tmp/daily-research-t2.err
MANIFEST="$TMPHUB/.orchestrator/daily-research-$DATE1.json"
PACKET="$TMPHUB/reports/daily-research-notebooklm-brief-$DATE1.md"
AUDIO="$TMPHUB/reports/daily-research-audio-$DATE1.mp3"
[[ -s "$PACKET" ]] && ok "T2: packet written" || fail "T2: packet missing"
grep -q "Как применить в Vepol" "$PACKET" && ok "T2: Russian Vepol instructions present" || fail "T2: instructions missing"
[[ -s "$AUDIO" ]] && ok "T2: audio downloaded" || fail "T2: audio missing"
grep -q "source add-research .*MCP tool safety" "$CALL_LOG" && ok "T2: NotebookLM web research called with topic" || fail "T2: add-research missing topic"
python3 - "$MANIFEST" <<'PYEOF' && ok "T2: manifest completed" || fail "T2: manifest invalid"
import json, sys
m = json.load(open(sys.argv[1]))
assert m["status"] == "completed", m
assert m["topic"] == "MCP tool safety for local AI agents", m
assert m["notebook_id"] == "nb_daily", m
assert m["artifact_id"] == "art_daily", m
PYEOF

echo "=== T3 completed rerun is idempotent ==="
LINES_BEFORE=$(wc -l < "$CALL_LOG")
"$REAL_BIN" --date "$DATE1" >/tmp/daily-research-t3.out 2>/tmp/daily-research-t3.err
LINES_AFTER=$(wc -l < "$CALL_LOG")
[[ "$LINES_BEFORE" == "$LINES_AFTER" ]] && ok "T3: no NotebookLM calls on completed rerun" || fail "T3: duplicate calls on rerun"

echo "=== T4 auto-topic clears override and chooses backlog topic ==="
"$REAL_BIN" --auto-topic >/tmp/daily-research-t4.out
if grep -q 'topic_override: ""' "$TMPHUB/personal/daily-research.yaml"; then ok "T4: override cleared"; else fail "T4: override not cleared"; fi
DATE2="2026-05-24"
"$REAL_BIN" --date "$DATE2" >/tmp/daily-research-t4b.out 2>/tmp/daily-research-t4b.err
MANIFEST2="$TMPHUB/.orchestrator/daily-research-$DATE2.json"
python3 - "$MANIFEST2" <<'PYEOF' && ok "T4: auto-topic came from backlog" || fail "T4: auto-topic manifest invalid"
import json, sys
m = json.load(open(sys.argv[1]))
assert "MCP tool safety" in m["topic"], m
assert m["selection_source"] == "backlog", m
PYEOF

echo "=== T5 concurrent daily runs do not create duplicate notebooks ==="
cat > "$MOCK" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${NOTEBOOKLM_CALL_LOG:?}"

if [[ "$1" == "create" ]]; then
  printf '{"id":"nb_lock","title":"%s"}\n' "$2"
  exit 0
fi

if [[ "$1" == "source" && "$2" == "add" ]]; then
  printf '{"source_id":"src_lock","status":"processing"}\n'
  exit 0
fi

if [[ "$1" == "source" && "$2" == "wait" ]]; then
  printf '{"source_id":"%s","status":"ready"}\n' "$3"
  exit 0
fi

if [[ "$1" == "source" && "$2" == "add-research" ]]; then
  sleep 2
  printf '{"status":"completed","imported":3}\n'
  exit 0
fi

if [[ "$1" == "generate" && "$2" == "audio" ]]; then
  printf '{"artifact_id":"art_lock","status":"completed"}\n'
  exit 0
fi

if [[ "$1" == "download" && "$2" == "audio" ]]; then
  out=""
  for arg in "$@"; do
    case "$arg" in
      *.mp3) out="$arg" ;;
    esac
  done
  mkdir -p "$(dirname "$out")"
  printf 'mock lock mp3' > "$out"
  printf 'downloaded %s\n' "$out"
  exit 0
fi

printf 'unexpected command: %s\n' "$*" >&2
exit 9
EOF
chmod +x "$MOCK"
export KB_NOTEBOOKLM_BIN="$MOCK"
: > "$CALL_LOG"
DATE3="2026-05-25"
"$REAL_BIN" --date "$DATE3" >/tmp/daily-research-t5a.out 2>/tmp/daily-research-t5a.err &
PID1=$!
sleep 0.2
"$REAL_BIN" --date "$DATE3" >/tmp/daily-research-t5b.out 2>/tmp/daily-research-t5b.err
wait "$PID1"
CREATE_COUNT=$(grep -c '^create ' "$CALL_LOG" || true)
[[ "$CREATE_COUNT" == "1" ]] && ok "T5: concurrent run did not create duplicate notebook" || fail "T5: create_count=$CREATE_COUNT"

echo "=== T6 retry cap for missing NotebookLM ==="
DATE4="2026-05-26"
export KB_NOTEBOOKLM_BIN="$TMPHUB/bin/missing-notebooklm"
set +e
"$REAL_BIN" --date "$DATE4" >/tmp/daily-research-t6a.out 2>/tmp/daily-research-t6a.err
R1=$?
"$REAL_BIN" --date "$DATE4" >/tmp/daily-research-t6b.out 2>/tmp/daily-research-t6b.err
R2=$?
"$REAL_BIN" --date "$DATE4" >/tmp/daily-research-t6c.out 2>/tmp/daily-research-t6c.err
R3=$?
"$REAL_BIN" --date "$DATE4" >/tmp/daily-research-t6d.out 2>/tmp/daily-research-t6d.err
R4=$?
set -e
[[ $R1 -ne 0 && $R2 -ne 0 && $R3 -ne 0 && $R4 -eq 0 ]] && ok "T6: retries cap after 3 failures" || fail "T6: rc sequence $R1/$R2/$R3/$R4"

echo
echo "=== daily-research tests: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]]
