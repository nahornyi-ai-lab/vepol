#!/usr/bin/env bash
# Tests for kb-daily-research (daily AI-agent radar → NotebookLM audio).
#
# Usage: bash bin/tests/test-daily-research.sh

set -euo pipefail

PASS=0
FAIL=0
TMPHUB=$(mktemp -d)
trap 'rm -rf "$TMPHUB"' EXIT

mkdir -p "$TMPHUB"/{bin,logs,personal,reports,.orchestrator,projects/demo-project,fixtures}
export KB_HUB="$TMPHUB"

REAL_BIN="$HOME/knowledge/bin/kb-daily-research"
MOCK="$TMPHUB/bin/notebooklm-mock"
CALL_LOG="$TMPHUB/notebooklm-calls.log"
FIXTURE="$TMPHUB/fixtures/radar.json"

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

cat > "$FIXTURE" <<'EOF'
[
  {
    "title": "Running Codex safely at OpenAI",
    "url": "https://openai.com/index/running-codex-safely/",
    "source_type": "official",
    "score": 95,
    "date": "2026-05-08",
    "reason": "official coding-agent governance signal"
  },
  {
    "title": "What ClickHouse learned from a year of coding with AI agents",
    "url": "https://clickhouse.com/blog/ai-agents-coding",
    "source_type": "community",
    "score": 88,
    "date": "2026-05-25",
    "reason": "popular engineering write-up on agent workflows"
  },
  {
    "title": "HarnessAPI: Skill-First Framework for MCP Tools",
    "url": "https://arxiv.org/abs/2605.22733",
    "source_type": "paper",
    "score": 74,
    "date": "2026-05-21",
    "reason": "agent tooling paper from arXiv snapshot"
  }
]
EOF

write_mock() {
  local reject_clickhouse="${1:-0}"
  cat > "$MOCK" <<EOF
#!/usr/bin/env bash
set -euo pipefail
echo "\$*" >> "\${NOTEBOOKLM_CALL_LOG:?}"

if [[ "\$1" == "create" ]]; then
  printf '{"id":"nb_daily","title":"%s"}\n' "\$2"
  exit 0
fi

if [[ "\$1" == "source" && "\$2" == "add" ]]; then
  if [[ "$reject_clickhouse" == "1" && "\$3" == "https://clickhouse.com/blog/ai-agents-coding" ]]; then
    echo "mock rejected URL" >&2
    exit 8
  fi
  case "\$3" in
    http*) printf '{"source_id":"src_url_%s","status":"processing"}\n' "\$RANDOM" ;;
    *) printf '{"source_id":"src_context","status":"processing"}\n' ;;
  esac
  exit 0
fi

if [[ "\$1" == "source" && "\$2" == "wait" ]]; then
  printf '{"source_id":"%s","status":"ready"}\n' "\$3"
  exit 0
fi

if [[ "\$1" == "source" && "\$2" == "add-research" ]]; then
  printf '{"status":"completed","imported":3}\n'
  exit 0
fi

if [[ "\$1" == "generate" && "\$2" == "audio" ]]; then
  printf '{"artifact_id":"art_daily","status":"completed"}\n'
  exit 0
fi

# Audio is listened to in NotebookLM; the runtime must NOT call download audio.
if [[ "\$1" == "download" && "\$2" == "audio" ]]; then
  printf 'unexpected: download audio must not be called (no local mp3)\n' >&2
  exit 9
fi

printf 'unexpected command: %s\n' "\$*" >&2
exit 9
EOF
  chmod +x "$MOCK"
  export KB_NOTEBOOKLM_BIN="$MOCK"
  export NOTEBOOKLM_CALL_LOG="$CALL_LOG"
  : > "$CALL_LOG"
}

write_config() {
  local max_sources="${1:-2}"
  cat > "$TMPHUB/personal/daily-research.yaml" <<EOF
enabled: true
focus_project: demo-project
mode: ai_agents_radar
topic_override: ""
language: ru
research_mode: deep
source_mode: curated
max_attempts: 3
max_sources: $max_sources
EOF
}

write_mock 0
write_config 2
export KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE"
export KB_DAILY_RESEARCH_DISABLE_NETWORK=1

echo "=== T1 radar default uses AI-agent topic and curated URL sources ==="
DATE1="2026-05-25"
"$REAL_BIN" --date "$DATE1" >/tmp/daily-research-t1.out 2>/tmp/daily-research-t1.err
MANIFEST="$TMPHUB/.orchestrator/daily-research-$DATE1.json"
PACKET="$TMPHUB/reports/daily-research-notebooklm-brief-$DATE1.md"
[[ -s "$PACKET" ]] && ok "T1: packet written" || fail "T1: packet missing"
grep -q "AI-agent radar" "$PACKET" && ok "T1: radar packet title present" || fail "T1: radar packet title missing"
grep -q "Selected sources" "$PACKET" && ok "T1: selected sources section present" || fail "T1: selected sources section missing"
grep -q "Watchlist" "$PACKET" && ok "T1: watchlist present" || fail "T1: watchlist missing"
[[ ! -e "$TMPHUB/reports/daily-research-audio-$DATE1.mp3" ]] && ok "T1: no local mp3 downloaded" || fail "T1: unexpected local mp3"
grep -q '^source add https://openai.com/index/running-codex-safely/' "$CALL_LOG" && ok "T1: official URL source added" || fail "T1: official URL source not added"
grep -q '^source add-research ' "$CALL_LOG" && fail "T1: add-research should not run in radar mode" || ok "T1: add-research not called"
python3 - "$MANIFEST" <<'PYEOF' && ok "T1: manifest records radar metadata" || fail "T1: manifest invalid"
import json, sys
m = json.load(open(sys.argv[1]))
assert m["status"] == "completed", m
assert m["artifact_id"] == "art_daily", m
assert "audio_path" not in m, m
assert m["selection_source"] == "ai_agents_radar", m
assert m["source_mode"] == "curated", m
assert m["selected_source_count"] == 2, m
assert "Runtime smoke test" not in m["topic"], m
PYEOF

echo "=== T2 max_sources is honored ==="
URL_ADDS=$(grep -c '^source add http' "$CALL_LOG" || true)
[[ "$URL_ADDS" == "2" ]] && ok "T2: max_sources capped URL additions at 2" || fail "T2: URL additions=$URL_ADDS"

echo "=== T2b GitHub-heavy collector output is diversity-capped ==="
HEAVY_FIXTURE="$TMPHUB/fixtures/github-heavy.json"
cat > "$HEAVY_FIXTURE" <<'EOF'
[
  {"title":"Official agent release","url":"https://openai.com/index/running-codex-safely/","source_type":"official","score":90,"date":"2026-05-25","reason":"official signal"},
  {"title":"Repo 1","url":"https://github.com/example/repo1","source_type":"github","score":999999,"date":"2026-05-25","reason":"repo"},
  {"title":"Repo 2","url":"https://github.com/example/repo2","source_type":"github","score":999998,"date":"2026-05-25","reason":"repo"},
  {"title":"Repo 3","url":"https://github.com/example/repo3","source_type":"github","score":999997,"date":"2026-05-25","reason":"repo"},
  {"title":"Repo 4","url":"https://github.com/example/repo4","source_type":"github","score":999996,"date":"2026-05-25","reason":"repo"},
  {"title":"Repo 5","url":"https://github.com/example/repo5","source_type":"github","score":999995,"date":"2026-05-25","reason":"repo"}
]
EOF
export KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$HEAVY_FIXTURE"
write_mock 0
write_config 6
DATE_HEAVY="2026-05-30"
"$REAL_BIN" --date "$DATE_HEAVY" >/tmp/daily-research-t2b.out 2>/tmp/daily-research-t2b.err
MANIFEST_HEAVY="$TMPHUB/.orchestrator/daily-research-$DATE_HEAVY.json"
python3 - "$MANIFEST_HEAVY" <<'PYEOF' && ok "T2b: official kept and GitHub capped" || fail "T2b: diversity cap failed"
import json, sys
m = json.load(open(sys.argv[1]))
sources = m["selected_sources"]
assert any(s["source_type"] == "official" for s in sources), sources
assert sum(1 for s in sources if s["source_type"] == "github") <= 3, sources
PYEOF

export KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE"

echo "=== T3 completed rerun is idempotent ==="
LINES_BEFORE=$(wc -l < "$CALL_LOG")
"$REAL_BIN" --date "$DATE1" >/tmp/daily-research-t3.out 2>/tmp/daily-research-t3.err
LINES_AFTER=$(wc -l < "$CALL_LOG")
[[ "$LINES_BEFORE" == "$LINES_AFTER" ]] && ok "T3: no NotebookLM calls on completed rerun" || fail "T3: duplicate calls on rerun"

echo "=== T4 all collectors fail still completes with local packet only ==="
unset KB_DAILY_RESEARCH_COLLECTOR_FIXTURE
write_mock 0
write_config 3
DATE2="2026-05-26"
"$REAL_BIN" --date "$DATE2" >/tmp/daily-research-t4.out 2>/tmp/daily-research-t4.err
MANIFEST2="$TMPHUB/.orchestrator/daily-research-$DATE2.json"
PACKET2="$TMPHUB/reports/daily-research-notebooklm-brief-$DATE2.md"
grep -q "No external sources were selected" "$PACKET2" && ok "T4: empty-source fallback documented" || fail "T4: fallback note missing"
URL_ADDS2=$(grep -c '^source add http' "$CALL_LOG" || true)
[[ "$URL_ADDS2" == "0" ]] && ok "T4: no URL sources added when collectors empty" || fail "T4: URL additions=$URL_ADDS2"
python3 - "$MANIFEST2" <<'PYEOF' && ok "T4: completed with zero selected sources" || fail "T4: manifest invalid"
import json, sys
m = json.load(open(sys.argv[1]))
assert m["status"] == "completed", m
assert m["selected_source_count"] == 0, m
PYEOF

echo "=== T5 URL rejection is degraded, not fatal ==="
export KB_DAILY_RESEARCH_COLLECTOR_FIXTURE="$FIXTURE"
write_mock 1
write_config 3
DATE3="2026-05-27"
"$REAL_BIN" --date "$DATE3" >/tmp/daily-research-t5.out 2>/tmp/daily-research-t5.err
MANIFEST3="$TMPHUB/.orchestrator/daily-research-$DATE3.json"
python3 - "$MANIFEST3" <<'PYEOF' && ok "T5: rejected URL recorded and run completed" || fail "T5: manifest invalid"
import json, sys
m = json.load(open(sys.argv[1]))
assert m["status"] == "completed", m
assert any("clickhouse.com" in item.get("url", "") for item in m.get("skipped_sources", [])), m
assert m["selected_source_count"] == 3, m
PYEOF

echo "=== T6 auto-topic returns to radar; legacy mode is explicit ==="
"$REAL_BIN" --set-topic "MCP tool safety for local AI agents" >/tmp/daily-research-t6a.out
grep -q "mode: override" "$TMPHUB/personal/daily-research.yaml" && ok "T6: set-topic marks override mode" || fail "T6: override mode missing"
"$REAL_BIN" --auto-topic >/tmp/daily-research-t6b.out
grep -q "mode: ai_agents_radar" "$TMPHUB/personal/daily-research.yaml" && ok "T6: auto-topic returns to radar" || fail "T6: auto-topic did not restore radar"
"$REAL_BIN" --legacy-auto-topic >/tmp/daily-research-t6c.out
grep -q "mode: auto" "$TMPHUB/personal/daily-research.yaml" && ok "T6: legacy-auto-topic sets legacy auto" || fail "T6: legacy auto mode missing"

echo "=== T7 override topic keeps legacy add-research path with fast/deep mode only ==="
write_mock 0
cat > "$TMPHUB/personal/daily-research.yaml" <<'EOF'
enabled: true
focus_project: demo-project
mode: override
topic_override: MCP tool safety for local AI agents
language: ru
research_mode: curated
source_mode: curated
max_attempts: 3
max_sources: 2
EOF
DATE4="2026-05-28"
"$REAL_BIN" --date "$DATE4" >/tmp/daily-research-t7.out 2>/tmp/daily-research-t7.err
grep -q '^source add-research .* --mode deep ' "$CALL_LOG" && ok "T7: override path coerces invalid research_mode to deep" || fail "T7: override path did not use deep"
grep -q -- '--mode curated' "$CALL_LOG" && fail "T7: curated leaked into add-research" || ok "T7: curated not passed to add-research"

echo "=== T8 retry cap for missing NotebookLM ==="
DATE5="2026-05-29"
export KB_NOTEBOOKLM_BIN="$TMPHUB/bin/missing-notebooklm"
set +e
"$REAL_BIN" --date "$DATE5" >/tmp/daily-research-t8a.out 2>/tmp/daily-research-t8a.err
R1=$?
"$REAL_BIN" --date "$DATE5" >/tmp/daily-research-t8b.out 2>/tmp/daily-research-t8b.err
R2=$?
"$REAL_BIN" --date "$DATE5" >/tmp/daily-research-t8c.out 2>/tmp/daily-research-t8c.err
R3=$?
"$REAL_BIN" --date "$DATE5" >/tmp/daily-research-t8d.out 2>/tmp/daily-research-t8d.err
R4=$?
set -e
[[ $R1 -ne 0 && $R2 -ne 0 && $R3 -ne 0 && $R4 -eq 0 ]] && ok "T8: retries cap after 3 failures" || fail "T8: rc sequence $R1/$R2/$R3/$R4"

echo
echo "=== daily-research tests: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]]
