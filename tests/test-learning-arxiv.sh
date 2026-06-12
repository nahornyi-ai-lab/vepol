#!/usr/bin/env bash
# Tests for kb-learning-arxiv (scheduled learning v2: arXiv-only 3-paper
# digest + Grok social check + Russian Telegram digest).
#
# Spec: learning-arxiv-implementation-spec-2026-06-12 (KB decisions;
# cross-reviewed round 2: codex approve-with-nits, agy approve-with-nits).
# Covers Phase 1 RED tests 2-15 (tests 1 and tick-fired semantics live in
# test-arxiv-tick-integration.sh).
#
# Usage: bash tests/test-learning-arxiv.sh
#   KB_LEARNING_ARXIV_SRC_BIN=<dir> to test a different source dir
#   (default: $HOME/knowledge/bin — the live install).

set -uo pipefail

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

SRC_BIN="${KB_LEARNING_ARXIV_SRC_BIN:-$HOME/knowledge/bin}"
RUNNER="$SRC_BIN/kb-learning-arxiv"
PY=python3
TODAY=$(date +%Y-%m-%d)

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

if [[ ! -f "$RUNNER" ]]; then
  fail "kb-learning-arxiv exists in $SRC_BIN"
  echo
  echo "=== kb-learning-arxiv tests: $PASS passed, $FAIL failed ==="
  exit 1
fi

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

# Atom feed: 5 relevant papers (distinct topic profiles; two near-duplicates
# among them) + 2 irrelevant papers. Entry shape mirrors the real arXiv API.
atom_entry() { # id title summary published authors...
  local id="$1" title="$2" summary="$3" published="$4"; shift 4
  local authors=""
  for a in "$@"; do authors+="<author><name>$a</name></author>"; done
  cat <<EOF
  <entry>
    <id>http://arxiv.org/abs/${id}v1</id>
    <title>$title</title>
    <summary>$summary</summary>
    <published>$published</published>
    $authors
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.AI"/>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/$id"/>
  </entry>
EOF
}

write_atom() { # outfile entries...
  local out="$1"; shift
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<feed xmlns="http://www.w3.org/2005/Atom">'
    cat "$@"
    echo '</feed>'
  } > "$out"
}

E=$TMP/entries; mkdir -p "$E"

atom_entry "2606.10001" \
  "Agentic Planning with Tool Use for LLM Agents" \
  "We study the problem of long-horizon planning for autonomous agents. We propose a framework combining tool use and MCP-style function calling. We show our method achieves 87% accuracy on the AgentBench benchmark and outperforms baselines. Code is available as open-source." \
  "2026-06-11T10:00:00Z" "Alice Researcher" "Bob Scholar" > "$E/p1.xml"

atom_entry "2606.10002" \
  "Memory-Augmented Retrieval for Knowledge-Base Agents" \
  "We investigate persistent memory and retrieval-augmented generation for agent knowledge bases. We introduce a hierarchical RAG index. Results show a 12% improvement in retrieval accuracy. We release our code for local deployment." \
  "2026-06-11T09:00:00Z" "Carol Author" > "$E/p2.xml"

atom_entry "2606.10003" \
  "Evaluating Chain-of-Thought Reasoning in Small Local Models" \
  "We study chain-of-thought reasoning quality under quantization for on-device inference. We present an evaluation benchmark. Our method improves reasoning score by 9 points while staying efficient for local deployment." \
  "2026-06-11T08:00:00Z" "Dave Writer" "Eve Coauthor" > "$E/p3.xml"

# Near-duplicate of p1 (same topic words, slightly lower signal) — the
# diversity rule must not select both.
atom_entry "2606.10004" \
  "Agentic Planning with Tool Use for LLM Agents: An Extended Study" \
  "We study the problem of long-horizon planning for autonomous agents. We propose a framework combining tool use and MCP-style function calling. We show our method achieves strong accuracy on the AgentBench benchmark and outperforms baselines." \
  "2026-06-10T10:00:00Z" "Alice Researcher" > "$E/p4.xml"

atom_entry "2606.10005" \
  "Safety Alignment for Multi-Agent Systems" \
  "We investigate alignment and safety challenges in multi-agent settings. We propose a safety evaluation protocol. Results show improved robustness." \
  "2026-06-10T09:00:00Z" "Frank Safety" > "$E/p5.xml"

atom_entry "2606.20001" \
  "Protein Folding Dynamics in Cold Plasma" \
  "We analyze protein folding pathways using molecular dynamics. Our simulations reveal new folding intermediates in plasma conditions." \
  "2026-06-11T07:00:00Z" "Grace Bio" > "$E/x1.xml"

atom_entry "2606.20002" \
  "A Survey of Cloud Formation Models for Weather Prediction" \
  "We survey numerical weather prediction models with a focus on cloud microphysics parameterizations." \
  "2026-06-11T06:00:00Z" "Heidi Meteo" > "$E/x2.xml"

FIXTURE5=$TMP/arxiv-5rel.xml
write_atom "$FIXTURE5" "$E/p1.xml" "$E/p2.xml" "$E/p3.xml" "$E/p4.xml" "$E/p5.xml" "$E/x1.xml" "$E/x2.xml"

FIXTURE2=$TMP/arxiv-2rel.xml
write_atom "$FIXTURE2" "$E/p1.xml" "$E/p2.xml" "$E/x1.xml"

FIXTURE0=$TMP/arxiv-0rel.xml
write_atom "$FIXTURE0" "$E/x1.xml" "$E/x2.xml"

# Oversized fixture: 3 relevant papers with very long titles/abstracts.
LONG_ABS=$($PY -c "
base='We study the problem of agent planning with tool use and retrieval. We propose a method. We show results that outperform baselines on the benchmark with 93% accuracy. '
print((base*30).strip())")
atom_entry "2606.30001" "Agents and Planning: $(printf 'Very Long Title Words %.0s' {1..20})" "$LONG_ABS" "2026-06-11T05:00:00Z" "Long One" > "$E/L1.xml"
atom_entry "2606.30002" "Memory Retrieval RAG Knowledge: $(printf 'Extended Naming Chain %.0s' {1..20})" "$LONG_ABS" "2026-06-11T04:00:00Z" "Long Two" > "$E/L2.xml"
atom_entry "2606.30003" "Reasoning Evaluation Benchmark: $(printf 'Elaborate Heading Tokens %.0s' {1..20})" "$LONG_ABS" "2026-06-11T03:00:00Z" "Long Three" > "$E/L3.xml"
FIXTURELONG=$TMP/arxiv-long.xml
write_atom "$FIXTURELONG" "$E/L1.xml" "$E/L2.xml" "$E/L3.xml"

# --------------------------------------------------------------------------
# Hub factory + shims
# --------------------------------------------------------------------------

new_hub() { # name [lang] → prints hub dir
  local d="$TMP/hub-$1" lang="${2:-ru}"
  mkdir -p "$d"/{bin,logs,personal,reports,sources,.orchestrator}
  echo "language: $lang" > "$d/personal/profile.yaml"
  if [[ -f "$SRC_BIN/_kb_profile.py" ]]; then
    cp "$SRC_BIN/_kb_profile.py" "$d/bin/_kb_profile.py"
  fi
  # channel-send shim: records every send, rc from marker file
  cat > "$d/bin/kb-channel-send" <<EOF
#!/usr/bin/env bash
echo "\$1" >> "$d/channel-calls.log"
printf '%s' "\$2" > "$d/last-digest.txt"
exit \$(cat "$d/channel-rc" 2>/dev/null || echo 0)
EOF
  chmod +x "$d/bin/kb-channel-send"
  # notebooklm canary — any invocation is a failure
  for nb in notebooklm kb-arxiv-notebooklm; do
    cat > "$d/bin/$nb" <<EOF
#!/usr/bin/env bash
touch "$d/notebooklm-called.marker"
exit 0
EOF
    chmod +x "$d/bin/$nb"
  done
  echo "$d"
}

write_grok() { # hub json-body rc
  local d="$1" body="$2" rc="${3:-0}"
  cat > "$d/bin/grok-fake" <<EOF
#!/usr/bin/env bash
N=\$(cat "$d/grok-calls" 2>/dev/null || echo 0)
echo \$((N+1)) > "$d/grok-calls"
if [[ "$rc" != "0" ]]; then echo "grok exploded" >&2; exit $rc; fi
cat <<'JSON'
$body
JSON
exit 0
EOF
  chmod +x "$d/bin/grok-fake"
}

GROK_FULL='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"weak","evidence":"https://x.com/somebody/status/1 — thread about agentic planning","prior_context":"Идею agentic-планирования обсуждали на X ещё за месяц до выхода статьи.","title_loc":"Агентное планирование с tool use для LLM-агентов","studied_loc":"Исследовали долгосрочное планирование автономных агентов с tool use и MCP-вызовами.","found_loc":"Метод достигает 87% точности на AgentBench и обходит базовые подходы.","why_loc":"Готовый паттерн планирования для твоего оркестратора задач."},
 {"id":"2606.10002","x_status":"not_found","reddit_status":"found","evidence":"reddit.com/r/LocalLLaMA/abc — memory-RAG тред","prior_context":"Похожие иерархические RAG-индексы уже всплывали на Reddit.","title_loc":"Память с retrieval для агентных баз знаний","studied_loc":"Изучали персистентную память и RAG для агентных баз знаний.","found_loc":"Иерархический RAG-индекс даёт +12% к точности retrieval."},
 {"id":"2606.10003","x_status":"weak","reddit_status":"not_found","evidence":"","prior_context":"Квантизация и reasoning обсуждались поверхностно.","title_loc":"Оценка chain-of-thought в малых локальных моделях","studied_loc":"Проверяли качество chain-of-thought под квантизацией на on-device моделях.","found_loc":"Их метод улучшает reasoning на 9 пунктов при сохранении эффективности."}
]}'

run_runner() { # hub fixture extra-env...
  local d="$1" fixture="$2"; shift 2
  KB_HUB="$d" \
  KB_LEARNING_ARXIV_DISABLE_NETWORK=1 \
  KB_LEARNING_ARXIV_FIXTURE="$fixture" \
  KB_LEARNING_ARXIV_GROK_BIN="$d/bin/grok-fake" \
  KB_PROCESS_OUTPUTS="telegram,file" \
  KB_PROCESS_BACKGROUND=1 \
  env "$@" "$PY" "$RUNNER" --text-only --date "$TODAY"
}

manifest() { echo "$1/.orchestrator/learning-arxiv-$TODAY.json"; }
mget() { # hub jq-ish python expr
  local d="$1" expr="$2"
  $PY -c "
import json,sys
m=json.load(open('$(manifest "$1")'))
print($expr)
" 2>/dev/null
}

# ==========================================================================
echo "=== S1: 5 relevant + 2 irrelevant → exactly 3 selected, runner-ups recorded ==="
HUB=$(new_hub select)
write_grok "$HUB" "$GROK_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S1: rc=0" || fail "S1: rc=$RC (expected 0)"
[[ "$(mget "$HUB" "len(m['selected_papers'])")" == "3" ]] \
  && ok "S1: exactly 3 papers selected" || fail "S1: selected != 3"
RU=$(mget "$HUB" "len(m['runner_ups'])")
[[ -n "$RU" && "$RU" -ge 1 ]] && ok "S1: runner-ups recorded ($RU)" || fail "S1: runner-ups empty"
# irrelevant papers never selected
SEL_IDS=$(mget "$HUB" "' '.join(p['id'] for p in m['selected_papers'])")
case "$SEL_IDS" in
  *2606.2000*) fail "S1: irrelevant paper selected ($SEL_IDS)" ;;
  *) ok "S1: no irrelevant papers selected" ;;
esac
# diversity: near-duplicates 10001/10004 must not both be selected
case "$SEL_IDS" in
  *2606.10001*2606.10004*|*2606.10004*2606.10001*) fail "S1: near-duplicate pair both selected" ;;
  *) ok "S1: near-duplicate pair not both selected" ;;
esac
# per-paper required fields
FIELDS_OK=$(mget "$HUB" "all(p.get('title') and p.get('authors') and p.get('link','').startswith('https://arxiv.org/abs/') and p.get('abstract') and p.get('summary_loc') and p.get('reason') and isinstance(p.get('scores',{}).get('final'),int) for p in m['selected_papers'])")
[[ "$FIELDS_OK" == "True" ]] && ok "S1: every paper has title/authors/link/abstract/summary_ru/reason/scores" \
  || fail "S1: missing per-paper fields"
AS=$(mget "$HUB" "m['selected_papers'][0]['scores'].get('author_signal')")
[[ "$AS" == "0" ]] && ok "S1: author_signal pinned to 0 (v1, no hallucinated affiliations)" \
  || fail "S1: author_signal=$AS (expected 0)"
[[ -s "$HUB/reports/learning-arxiv-summary-$TODAY.md" ]] && ok "S1: report written" || fail "S1: report missing"
[[ -s "$HUB/sources/arxiv-learning-snapshot-$TODAY.md" ]] && ok "S1: snapshot source written" || fail "S1: snapshot missing"
[[ -s "$HUB/sources/arxiv-learning-social-grok-$TODAY.md" ]] && ok "S1: grok social source written" || fail "S1: social source missing"

echo "=== S2: digest content (arXiv links only, Russian, statuses split) ==="
DIGEST=$(cat "$HUB/last-digest.txt" 2>/dev/null || echo "")
LINKS=$(grep -o "arxiv.org/abs/[0-9.]*" <<<"$DIGEST" | sort -u | wc -l | tr -d ' ')
[[ "$LINKS" == "3" ]] && ok "S2: digest has 3 distinct arXiv links" || fail "S2: digest arXiv links=$LINKS"
if grep -qiE "openai\.com|blog\.google|news\.ycombinator|github\.com" <<<"$DIGEST"; then
  fail "S2: digest contains non-arXiv primary links"
else
  ok "S2: no OpenAI/Google/HN/GitHub links in digest"
fi
grep -q "Что исследовали" <<<"$DIGEST" && ok "S2: digest has 'Что исследовали'" || fail "S2: no 'Что исследовали'"
grep -q "Что выяснили" <<<"$DIGEST" && ok "S2: digest has 'Что выяснили'" || fail "S2: no 'Что выяснили'"
# Summary CONTENT must be Russian (grok bounded translation), not just labels
RU_CONTENT=$(grep -c "Что исследовали: [^ ]*[А-Яа-я]" <<<"$DIGEST" || true)
[[ "$RU_CONTENT" == "3" ]] && ok "S2: all 3 summaries have Russian content (not just labels)" \
  || fail "S2: Russian summary content lines=$RU_CONTENT (expected 3)"
SRC_OK=$(mget "$HUB" "all(p.get('summary_source')=='grok' for p in m['selected_papers'])")
[[ "$SRC_OK" == "True" ]] && ok "S2: summary_source=grok for all papers" || fail "S2: summary_source"
# Owner feedback 2026-06-12: stats line, Russian selection reason, Russian
# titles and Russian status words — no RU/EN mix in the user surface.
grep -q "Просмотрел .* свежих статей" <<<"$DIGEST" && ok "S2: digest states how many papers were scanned" \
  || fail "S2: no scanned-stats line"
grep -q "по темам подошло" <<<"$DIGEST" && ok "S2: digest states relevant count" || fail "S2: no relevant count"
REASONS=$(grep -c "Почему выбрана:" <<<"$DIGEST" || true)
[[ "$REASONS" == "3" ]] && ok "S2: per-paper selection reason present (3)" || fail "S2: reasons=$REASONS"
grep -q "X: есть" <<<"$DIGEST" && ok "S2: statuses rendered in Russian (X: есть)" || fail "S2: English status leaked"
if grep -qE "(X|Reddit): (found|weak|not_found|degraded)" <<<"$DIGEST"; then
  fail "S2: raw status token leaked into digest"
else
  ok "S2: no raw status tokens in digest"
fi
grep -q "Агентное планирование" <<<"$DIGEST" && ok "S2: Russian title from grok rendered" || fail "S2: title_ru not used"
grep -q "Готовый паттерн планирования" <<<"$DIGEST" && ok "S2: per-paper why_ru from grok rendered" || fail "S2: why_ru not used"
grep -q "Зачем тебе" <<<"$DIGEST" && ok "S2: digest has 'Зачем тебе'" || fail "S2: no 'Зачем тебе'"
grep -qE "X: " <<<"$DIGEST" && grep -qE "Reddit: " <<<"$DIGEST" \
  && ok "S2: X and Reddit statuses rendered separately" || fail "S2: X/Reddit not split"
CALLS=$(wc -l < "$HUB/channel-calls.log" 2>/dev/null | tr -d ' ')
[[ "$CALLS" == "1" ]] && ok "S2: exactly one telegram send" || fail "S2: sends=$CALLS"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S2: digest_delivered=true" || fail "S2: digest_delivered"

echo "=== S3: grok fixture merged per paper ==="
X1=$(mget "$HUB" "[p['social']['x_status'] for p in m['selected_papers'] if p['id']=='2606.10001'][0]")
R2=$(mget "$HUB" "[p['social']['reddit_status'] for p in m['selected_papers'] if p['id']=='2606.10002'][0]")
[[ "$X1" == "found" ]] && ok "S3: paper1 x_status=found merged" || fail "S3: paper1 x_status=$X1"
[[ "$R2" == "found" ]] && ok "S3: paper2 reddit_status=found merged" || fail "S3: paper2 reddit_status=$R2"
[[ "$(mget "$HUB" "m['social_check']")" == "ok" ]] && ok "S3: social_check=ok" || fail "S3: social_check"
grep -q "не найдено\|not_found" "$HUB/reports/learning-arxiv-summary-$TODAY.md" \
  && ok "S3: report carries social statuses" || fail "S3: report missing social statuses"

echo "=== S4: empty grok stdout → degraded (not not_found), digest still sent ==="
HUB=$(new_hub grok-empty)
write_grok "$HUB" "" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S4: rc=0" || fail "S4: rc=$RC"
ALL_DEG=$(mget "$HUB" "all(p['social']['x_status']=='degraded' and p['social']['reddit_status']=='degraded' for p in m['selected_papers'])")
[[ "$ALL_DEG" == "True" ]] && ok "S4: all statuses degraded" || fail "S4: statuses not degraded"
NF=$(mget "$HUB" "any('not_found' in (p['social']['x_status'],p['social']['reddit_status']) for p in m['selected_papers'])")
[[ "$NF" == "False" ]] && ok "S4: no invented not_found" || fail "S4: invented not_found"
[[ "$(mget "$HUB" "m['social_check']")" == "degraded" ]] && ok "S4: social_check=degraded" || fail "S4: social_check"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S4: digest still delivered" || fail "S4: digest not delivered"
FB=$(mget "$HUB" "all(p.get('summary_source')=='fallback_en' for p in m['selected_papers'])")
[[ "$FB" == "True" ]] && ok "S4: degraded summaries marked fallback_en" || fail "S4: summary_source on degraded"
grep -q "сбой проверки" "$HUB/last-digest.txt" && ok "S4: degraded status rendered in Russian" \
  || fail "S4: degraded status not Russian"

echo "=== S5: grok rc!=0 → degraded with provenance, digest still sent ==="
HUB=$(new_hub grok-rc)
write_grok "$HUB" "" 3
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S5: rc=0" || fail "S5: rc=$RC"
[[ "$(mget "$HUB" "m['grok_rc']")" == "3" ]] && ok "S5: grok_rc=3 recorded" || fail "S5: grok_rc"
GS=$(mget "$HUB" "m['grok_stderr_tail']")
[[ "$GS" == *"grok exploded"* ]] && ok "S5: grok_stderr_tail recorded" || fail "S5: stderr tail missing"
[[ "$(mget "$HUB" "m['social_check']")" == "degraded" ]] && ok "S5: social_check=degraded" || fail "S5: social_check"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S5: digest delivered" || fail "S5: digest"

echo "=== S6: partial grok (2 of 3 papers, one malformed reddit) → per-paper/per-channel degraded ==="
GROK_PARTIAL='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"banana","evidence":"x link","prior_context":"ok"},
 {"id":"2606.10002","x_status":"weak","reddit_status":"not_found","evidence":"","prior_context":"ok"}
]}'
HUB=$(new_hub grok-partial)
write_grok "$HUB" "$GROK_PARTIAL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S6: rc=0" || fail "S6: rc=$RC"
X1=$(mget "$HUB" "[p['social']['x_status'] for p in m['selected_papers'] if p['id']=='2606.10001'][0]")
R1=$(mget "$HUB" "[p['social']['reddit_status'] for p in m['selected_papers'] if p['id']=='2606.10001'][0]")
[[ "$X1" == "found" ]] && ok "S6: parsed x_status preserved" || fail "S6: x_status=$X1"
[[ "$R1" == "degraded" ]] && ok "S6: malformed reddit value → degraded" || fail "S6: reddit_status=$R1"
MISSING_DEG=$(mget "$HUB" "all(p['social']['x_status']=='degraded' and p['social']['reddit_status']=='degraded' for p in m['selected_papers'] if p['id'] not in ('2606.10001','2606.10002'))")
[[ "$MISSING_DEG" == "True" ]] && ok "S6: uncovered paper degraded both channels" || fail "S6: uncovered paper not degraded"
[[ "$(mget "$HUB" "m['social_check']")" == "partial" ]] && ok "S6: social_check=partial" || fail "S6: social_check"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S6: digest delivered" || fail "S6: digest"

echo "=== S7: arXiv fetch failure → rc!=0, failed manifest ==="
HUB=$(new_hub arxiv-fail)
write_grok "$HUB" "$GROK_FULL" 0
run_runner "$HUB" "$TMP/does-not-exist.xml" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S7: rc!=0 on fetch failure" || fail "S7: rc=0"
[[ "$(mget "$HUB" "m['status']")" == "failed" ]] && ok "S7: manifest status=failed" || fail "S7: status"
[[ ! -f "$HUB/last-digest.txt" ]] && ok "S7: no digest sent" || fail "S7: digest sent on failure"

echo "=== S8: idempotent rerun; --force resends ==="
HUB=$(new_hub idem)
write_grok "$HUB" "$GROK_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
CALLS=$(wc -l < "$HUB/channel-calls.log" | tr -d ' ')
[[ "$RC" == "0" && "$CALLS" == "1" ]] && ok "S8: rerun rc=0, no duplicate send" || fail "S8: rc=$RC calls=$CALLS"
KB_HUB="$HUB" KB_LEARNING_ARXIV_DISABLE_NETWORK=1 KB_LEARNING_ARXIV_FIXTURE="$FIXTURE5" \
  KB_LEARNING_ARXIV_GROK_BIN="$HUB/bin/grok-fake" KB_PROCESS_OUTPUTS="telegram,file" \
  "$PY" "$RUNNER" --text-only --date "$TODAY" --force >/dev/null 2>&1
CALLS=$(wc -l < "$HUB/channel-calls.log" | tr -d ' ')
[[ "$CALLS" == "2" ]] && ok "S8: --force resends" || fail "S8: force calls=$CALLS"

echo "=== S9: telegram failure → rc!=0; recovery delivers exactly once from stage cache ==="
HUB=$(new_hub tg-fail)
write_grok "$HUB" "$GROK_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S9: rc!=0 when telegram fails" || fail "S9: rc=0 on failed delivery"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "False" ]] && ok "S9: digest_delivered=false" || fail "S9: digest_delivered"
[[ -s "$HUB/reports/learning-arxiv-summary-$TODAY.md" ]] && ok "S9: report still written" || fail "S9: report missing"
GROK_CALLS_BEFORE=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
# recovery: channel healthy again; fixture REMOVED — cache must carry the run
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$TMP/removed-fixture.xml" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S9: recovery run rc=0 without re-fetch (stage cache)" || fail "S9: recovery rc=$RC"
DELIVERED=$(mget "$HUB" "m['digest_delivered']")
[[ "$DELIVERED" == "True" ]] && ok "S9: recovery delivered" || fail "S9: recovery not delivered"
GROK_CALLS_AFTER=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
[[ "$GROK_CALLS_AFTER" == "$GROK_CALLS_BEFORE" ]] && ok "S9: grok not re-invoked on recovery" || fail "S9: grok re-invoked (${GROK_CALLS_BEFORE} -> ${GROK_CALLS_AFTER})"
SENDS=$(wc -l < "$HUB/channel-calls.log" | tr -d ' ')
[[ "$SENDS" == "2" ]] && ok "S9: exactly one successful delivery after recovery (2 attempts total)" || fail "S9: sends=$SENDS"

echo "=== S10: fewer than three relevant papers ==="
HUB=$(new_hub fewer)
write_grok "$HUB" "$GROK_FULL" 0
run_runner "$HUB" "$FIXTURE2" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S10: rc=0 with 2 papers" || fail "S10: rc=$RC"
[[ "$(mget "$HUB" "len(m['selected_papers'])")" == "2" ]] && ok "S10: 2 papers selected" || fail "S10: selected"
grep -q "только 2" "$HUB/last-digest.txt" && ok "S10: digest notes 'только 2'" || fail "S10: no explicit note"
HUB=$(new_hub zero)
write_grok "$HUB" "$GROK_FULL" 0
run_runner "$HUB" "$FIXTURE0" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S10: rc=0 with 0 papers" || fail "S10: rc=$RC (0 papers)"
grep -q "релевантных статей сегодня нет" "$HUB/last-digest.txt" \
  && ok "S10: zero-papers digest says so explicitly" || fail "S10: zero-papers note missing"

echo "=== S11: digest length budget ≤ 3900 (single Telegram message) ==="
HUB=$(new_hub long)
write_grok "$HUB" '{"papers":[]}' 0
run_runner "$HUB" "$FIXTURELONG" >/dev/null 2>&1
LEN=$($PY -c "print(len(open('$HUB/last-digest.txt',encoding='utf-8').read()))" 2>/dev/null || echo 99999)
[[ "$LEN" -le 3900 ]] && ok "S11: digest length $LEN ≤ 3900" || fail "S11: digest length $LEN > 3900"
LINKS=$(grep -o "arxiv.org/abs/[0-9.]*" "$HUB/last-digest.txt" | sort -u | wc -l | tr -d ' ')
[[ "$LINKS" == "3" ]] && ok "S11: all 3 papers still present" || fail "S11: links=$LINKS"

echo "=== S12: zero NotebookLM calls in background mode (all hubs) ==="
NB_MARKERS=$(find "$TMP" -name "notebooklm-called.marker" | wc -l | tr -d ' ')
[[ "$NB_MARKERS" == "0" ]] && ok "S12: no notebooklm invocation across all scenarios" || fail "S12: notebooklm called ($NB_MARKERS)"

echo "=== S14: lock contention semantics ==="
HUB=$(new_hub lock)
write_grok "$HUB" "$GROK_FULL" 0
mkdir -p "$HUB/.orchestrator"
hold_lock() { # background: hold flock for 6s
  python3 -c "
import fcntl, time
fh = open('$HUB/.orchestrator/learning-arxiv-$TODAY.lock', 'a')
fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
print('held', flush=True)
time.sleep(6)
" &
  LOCK_PID=$!
  sleep 1
}
hold_lock
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S14: lock held, nothing delivered → rc!=0" || fail "S14: rc=0 under contention"
wait "$LOCK_PID" 2>/dev/null
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1   # normal delivery
hold_lock
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S14: lock held but digest already delivered → rc=0" || fail "S14: rc=$RC after delivery"
wait "$LOCK_PID" 2>/dev/null
LOCK_META=$(cat "$HUB/.orchestrator/learning-arxiv-$TODAY.lock" 2>/dev/null || echo "")
[[ "$LOCK_META" == pid=* ]] && ok "S14: holder lock metadata not truncated by contender" || fail "S14: lock metadata lost"

echo "=== S16: zero-papers day recovers from stage cache after telegram failure ==="
HUB=$(new_hub zerocache)
write_grok "$HUB" '{"papers":[]}' 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE0" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S16: zero-papers + telegram fail → rc!=0" || fail "S16: rc=0"
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$TMP/removed-zero-fixture.xml" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S16: recovery rc=0 without re-fetch (zero-papers cache)" || fail "S16: recovery rc=$RC"
grep -q "релевантных статей сегодня нет" "$HUB/last-digest.txt" \
  && ok "S16: recovered digest keeps zero-papers note" || fail "S16: recovered digest wrong"

echo "=== S17: sender exception (non-executable kb-channel-send) → failed manifest, rc!=0 ==="
HUB=$(new_hub senderexc)
write_grok "$HUB" "$GROK_FULL" 0
chmod -x "$HUB/bin/kb-channel-send"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S17: sender PermissionError → rc!=0" || fail "S17: rc=0 on sender exception"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "False" ]] && ok "S17: digest_delivered=false" || fail "S17: digest_delivered"
[[ "$(mget "$HUB" "m['status']")" == "failed" ]] && ok "S17: manifest status=failed (provenance written)" || fail "S17: status"

echo "=== S18: English studied_ru/found_ru from grok → marked fallback_en, not grok ==="
GROK_EN='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"weak","evidence":"x","prior_context":"ok","studied_loc":"They studied planning for agents.","found_loc":"The method achieves 87% accuracy."},
 {"id":"2606.10002","x_status":"weak","reddit_status":"found","evidence":"","prior_context":"ok","studied_loc":"Memory and RAG for agents.","found_loc":"12% retrieval gain."},
 {"id":"2606.10003","x_status":"weak","reddit_status":"weak","evidence":"","prior_context":"ok","studied_loc":"CoT under quantization.","found_loc":"9 points better."}
]}'
HUB=$(new_hub grok-en)
write_grok "$HUB" "$GROK_EN" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
FB=$(mget "$HUB" "all(p.get('summary_source')=='fallback_en' for p in m['selected_papers'])")
[[ "$FB" == "True" ]] && ok "S18: non-Cyrillic grok summaries → fallback_en" || fail "S18: English accepted as grok summary"
ST=$(mget "$HUB" "all(p['social']['x_status'] in ('found','weak') for p in m['selected_papers'])")
[[ "$ST" == "True" ]] && ok "S18: social statuses still parsed normally" || fail "S18: social statuses lost"

echo "=== S15: inline YAML comments do not poison config values ==="
HUB=$(new_hub cfgcomment)
write_grok "$HUB" "$GROK_FULL" 0
cat > "$HUB/personal/daily-research.yaml" <<'EOF'
language: ru
max_papers: 2 # cap for the digest
EOF
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
[[ "$(mget "$HUB" "len(m['selected_papers'])")" == "2" ]] \
  && ok "S15: max_papers honored despite inline comment" || fail "S15: inline comment broke max_papers"

echo "=== S13: default learning command in _kb_processes.py ==="
DEFAULT_OK=$(KB_X=1 $PY -c "
import sys; sys.path.insert(0,'$SRC_BIN')
import importlib.util
spec=importlib.util.spec_from_file_location('kp','$SRC_BIN/_kb_processes.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print('kb-learning-arxiv --text-only' in mod.DEFAULT_PROCESSES_YAML and 'kb-daily-research' not in mod.DEFAULT_PROCESSES_YAML)
")
[[ "$DEFAULT_OK" == "True" ]] && ok "S13: default learning run = kb-learning-arxiv --text-only" \
  || fail "S13: default learning command still legacy"

echo "=== S19: profile en → fully English digest, prompt asks for English ==="
GROK_EN_LOC='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"weak","evidence":"x link","prior_context":"The agentic-planning idea circulated on X a month before the paper.","title_loc":"Agentic Planning with Tool Use for LLM Agents","studied_loc":"They studied long-horizon planning for autonomous agents with tool use and MCP calls.","found_loc":"The method reaches 87% accuracy on AgentBench and beats the baselines.","why_loc":"A ready planning pattern for your task orchestrator."},
 {"id":"2606.10002","x_status":"not_found","reddit_status":"found","evidence":"reddit thread","prior_context":"Similar hierarchical RAG indexes surfaced on Reddit before.","title_loc":"Memory-Augmented Retrieval for KB Agents","studied_loc":"They studied persistent memory and RAG for agent knowledge bases.","found_loc":"A hierarchical RAG index gives +12% retrieval accuracy.","why_loc":"Directly applicable to the KB architecture."},
 {"id":"2606.10003","x_status":"weak","reddit_status":"not_found","evidence":"","prior_context":"Quantization and reasoning were discussed in passing.","title_loc":"Evaluating CoT in Small Local Models","studied_loc":"They evaluated chain-of-thought quality under quantization on-device.","found_loc":"Their method improves reasoning by 9 points while staying efficient.","why_loc":"Useful for local model choices."}
]}'
HUB=$(new_hub lang-en en)
write_grok "$HUB" "$GROK_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S19: rc=0 with en profile" || fail "S19: rc=$RC"
DIGEST_EN=$(cat "$HUB/last-digest.txt" 2>/dev/null || echo "")
grep -q "Scanned .* fresh arXiv papers" <<<"$DIGEST_EN" && ok "S19: English stats line" || fail "S19: stats line"
grep -q "Why selected:" <<<"$DIGEST_EN" && ok "S19: English reason label" || fail "S19: reason label"
grep -q "What they studied:" <<<"$DIGEST_EN" && ok "S19: English studied label" || fail "S19: studied label"
grep -q "X: found" <<<"$DIGEST_EN" && ok "S19: English status words" || fail "S19: statuses"
if grep -q "[А-Яа-я]" <<<"$DIGEST_EN"; then
  fail "S19: Cyrillic leaked into en digest"
else
  ok "S19: zero Cyrillic in en digest"
fi
grep -q "in English" "$HUB/.orchestrator/learning-arxiv-grok-prompt-$TODAY.md" \
  && ok "S19: grok prompt requests English" || fail "S19: prompt language"
if grep -q "[А-Яа-я]" "$HUB/reports/learning-arxiv-summary-$TODAY.md"; then
  fail "S19: Cyrillic leaked into en report"
else
  ok "S19: en report fully English"
fi

echo "=== S20: KB_LANG=sr → English labels, ISO-safe directive, rc=0 ==="
HUB=$(new_hub lang-sr)
write_grok "$HUB" "$GROK_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" KB_LANG=sr >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S20: rc=0 with KB_LANG=sr" || fail "S20: rc=$RC"
grep -q "Why selected:" "$HUB/last-digest.txt" && ok "S20: English labels for unmapped code" || fail "S20: labels"
grep -q "ISO 639 code 'sr'" "$HUB/.orchestrator/learning-arxiv-grok-prompt-$TODAY.md" \
  && ok "S20: ISO-safe directive in prompt" || fail "S20: directive"

echo "=== S21: stage cache is language-gated ==="
HUB=$(new_hub lang-gate)
write_grok "$HUB" "$GROK_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1   # ru run, delivery fails, cache filled
G1=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
echo 0 > "$HUB/channel-rc"
write_grok "$HUB" "$GROK_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" KB_LANG=en >/dev/null 2>&1   # target switched → cache bypass
RC=$?
G2=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
[[ "$RC" == "0" ]] && ok "S21: en recovery rc=0" || fail "S21: rc=$RC"
[[ "$G2" -gt "$G1" ]] && ok "S21: language mismatch re-invoked grok (no stale cache)" || fail "S21: stale cache reused (${G1} -> ${G2})"
if grep -q "[А-Яа-я]" "$HUB/last-digest.txt"; then
  fail "S21: Russian leaked into en digest from ru cache"
else
  ok "S21: no Cyrillic after language switch"
fi
# same-language cache still works (ru → ru, fixture removed)
HUB=$(new_hub lang-gate-ru)
write_grok "$HUB" "$GROK_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$TMP/removed-again.xml" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S21: same-language cache recovery still works" || fail "S21: ru cache broken rc=$RC"

echo "=== S22: language switch + failed re-fetch must not resurrect old-language cache ==="
HUB=$(new_hub lang-switch-fail)
write_grok "$HUB" "$GROK_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1            # ru cache filled, delivery failed
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$TMP/gone.xml" KB_LANG=en >/dev/null 2>&1   # switch to en, fetch FAILS
RC=$?
[[ "$RC" != "0" ]] && ok "S22: switch + fetch failure → rc!=0" || fail "S22: rc=0"
write_grok "$HUB" "$GROK_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" KB_LANG=en >/dev/null 2>&1       # retry with fixture back
RC=$?
[[ "$RC" == "0" ]] && ok "S22: en retry rc=0" || fail "S22: retry rc=$RC"
if grep -q "[А-Яа-я]" "$HUB/last-digest.txt"; then
  fail "S22: stale ru cache resurrected after failed re-fetch"
else
  ok "S22: no stale-language content after failed re-fetch + retry"
fi

echo
echo "=== kb-learning-arxiv tests: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] || exit 1
