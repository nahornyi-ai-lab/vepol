#!/usr/bin/env bash
# Tests for kb-learning-arxiv (scheduled learning v2: arXiv-only 3-paper
# digest + optional Grok social check + user-language Telegram digest).
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

FULLTEXT_DIR=$TMP/fulltext
mkdir -p "$FULLTEXT_DIR"
cat > "$FULLTEXT_DIR/2606.10001.txt" <<'EOF'
FULLTEXT_METHOD_MARKER_10001
This is the full paper body for 2606.10001, not just the abstract. It includes
an introduction, method section, ablation table narrative, limitations, and a
conclusion. The method section explains that the AgentBench benchmark is used
with multiple tool-use configurations and that the analysis compares planning
failures before and after MCP-style function calling.
EOF
cat > "$FULLTEXT_DIR/2606.10002.txt" <<'EOF'
FULLTEXT_METHOD_MARKER_10002
This is the full paper body for 2606.10002. It contains details about the
hierarchical memory index, retrieval corpus construction, evaluation protocol,
deployment constraints, and error analysis that are not present in the short
abstract alone.
EOF
cat > "$FULLTEXT_DIR/2606.10003.txt" <<'EOF'
FULLTEXT_METHOD_MARKER_10003
This is the full paper body for 2606.10003. It includes the quantization setup,
on-device hardware assumptions, benchmark split, chain-of-thought scoring
rubric, a detailed comparison between 4-bit and 8-bit runs, latency notes,
error categories for failed reasoning traces, and a limitations section.
EOF
cat > "$FULLTEXT_DIR/2606.10005.txt" <<'EOF'
FULLTEXT_METHOD_MARKER_10005
This is the full paper body for 2606.10005. It includes the multi-agent safety
alignment setup, adversarial coordination scenarios, safety evaluation protocol,
robustness metrics, ablation notes, and limitations beyond the short abstract.
EOF

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

write_grok() { # hub json-body rc   (social-only fixture: x/reddit/evidence/prior_context)
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

enable_grok() { # hub
  local d="$1"
  cat > "$d/personal/daily-research.yaml" <<'EOF'
social_check: grok
EOF
}

set_social_check() { # hub value
  local d="$1" val="$2"
  cat > "$d/personal/daily-research.yaml" <<EOF
social_check: $val
EOF
}

# Fake Codex translation bin: mimics `codex exec ... --output-last-message <f>`.
# Writes the JSON body to the -o/--output-last-message target (the path the
# runner reads) AND echoes to stdout (the fallback path). Tracks call count.
write_codex() { # hub json-body rc   (translation-only fixture: *_loc fields)
  local d="$1" body="$2" rc="${3:-0}"
  cat > "$d/bin/codex-fake" <<EOF
#!/usr/bin/env bash
N=\$(cat "$d/codex-calls" 2>/dev/null || echo 0)
echo \$((N+1)) > "$d/codex-calls"
printf '%s\n' "\$@" > "$d/codex-argv.txt"
OUT=""; prev=""
for a in "\$@"; do
  if [[ "\$prev" == "--output-last-message" || "\$prev" == "-o" ]]; then OUT="\$a"; fi
  prev="\$a"
done
if [[ "$rc" != "0" ]]; then echo "codex exploded" >&2; exit $rc; fi
BODY=\$(cat <<'JSON'
$body
JSON
)
if [[ -n "\$OUT" ]]; then printf '%s' "\$BODY" > "\$OUT"; fi
printf '%s' "\$BODY"
exit 0
EOF
  chmod +x "$d/bin/codex-fake"
}

# Social-only Grok fixture (x/reddit/evidence/prior_context).
GROK_FULL='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"weak","evidence":"https://x.com/somebody/status/1 — thread about agentic planning","prior_context":"Идею agentic-планирования обсуждали на X ещё за месяц до выхода статьи."},
 {"id":"2606.10002","x_status":"not_found","reddit_status":"found","evidence":"reddit.com/r/LocalLLaMA/abc — memory-RAG тред","prior_context":"Похожие иерархические RAG-индексы уже всплывали на Reddit."},
 {"id":"2606.10003","x_status":"weak","reddit_status":"not_found","evidence":"","prior_context":"Квантизация и reasoning обсуждались поверхностно."}
]}'

# Translation-only Codex fixture (*_loc fields), matching FIXTURE5 ids.
CODEX_FULL='{"papers":[
 {"id":"2606.10001","title_loc":"Агентное планирование с tool use для LLM-агентов","abstract_loc":"Статья изучает долгосрочное планирование автономных агентов с LLM (large language model, большая языковая модель), tool use (использование инструментов) и MCP (Model Context Protocol, протокол контекста модели). Метод достигает 87% точности на AgentBench (бенчмарк агентных задач).","studied_loc":"Исследовали долгосрочное планирование автономных агентов с tool use и MCP-вызовами.","method_loc":"Предложенный фреймворк проверяли на AgentBench, сравнивая точность с базовыми подходами.","found_loc":"Метод достигает 87% точности на AgentBench и обходит базовые подходы.","why_loc":"Готовый паттерн планирования для твоего оркестратора задач."},
 {"id":"2606.10002","title_loc":"Память с retrieval для агентных баз знаний","abstract_loc":"Авторы изучают persistent memory (персистентную память) и RAG (retrieval-augmented generation, генерацию с поисковым дополнением) для агентных баз знаний. Иерархический RAG-индекс даёт +12% к точности retrieval (поискового извлечения).","studied_loc":"Изучали персистентную память и RAG для агентных баз знаний.","method_loc":"Собрали иерархический RAG-индекс и оценивали его по точности retrieval.","found_loc":"Иерархический RAG-индекс даёт +12% к точности retrieval.","why_loc":"Прямо про архитектуру знаний Vepol."},
 {"id":"2606.10003","title_loc":"Оценка chain-of-thought в малых локальных моделях","abstract_loc":"Работа проверяет chain-of-thought (цепочку рассуждений) в малых локальных моделях при quantization (квантизации) для on-device inference (вывода на устройстве). Метод улучшает reasoning score (оценку рассуждения) на 9 пунктов.","studied_loc":"Проверяли качество chain-of-thought под квантизацией на on-device моделях.","method_loc":"Сравнивали reasoning score на benchmark для локального on-device inference после квантизации.","found_loc":"Их метод улучшает reasoning на 9 пунктов при сохранении эффективности.","why_loc":"Полезно для выбора локальных моделей."}
]}'

LONG_LOC=$($PY -c "
base='Статья объясняет LLM (large language model, большая языковая модель), RAG (retrieval-augmented generation, генерация с поисковым дополнением), MCP (Model Context Protocol, протокол контекста модели) и agent planning (планирование агента) в длинном abstract. '
print((base*8).strip())
")
GROK_LONG=$(cat <<EOF
{"papers":[
 {"id":"2606.30001","x_status":"weak","reddit_status":"weak","evidence":"","prior_context":"Длинный prior context."},
 {"id":"2606.30002","x_status":"weak","reddit_status":"weak","evidence":"","prior_context":"Длинный prior context."},
 {"id":"2606.30003","x_status":"weak","reddit_status":"weak","evidence":"","prior_context":"Длинный prior context."}
]}
EOF
)
CODEX_LONG=$(cat <<EOF
{"papers":[
 {"id":"2606.30001","title_loc":"Длинная статья про агентов","abstract_loc":"$LONG_LOC","studied_loc":"Изучали планирование агентов.","method_loc":"Проверяли метод на benchmark (бенчмарке), указанном в abstract.","found_loc":"Показали результат на benchmark (бенчмарке).","why_loc":"Полезно для проверки лимита digest."},
 {"id":"2606.30002","title_loc":"Длинная статья про память","abstract_loc":"$LONG_LOC","studied_loc":"Изучали память агентов.","method_loc":"Проверяли метод на benchmark (бенчмарке), указанном в abstract.","found_loc":"Показали результат на benchmark (бенчмарке).","why_loc":"Полезно для проверки лимита digest."},
 {"id":"2606.30003","title_loc":"Длинная статья про reasoning","abstract_loc":"$LONG_LOC","studied_loc":"Изучали reasoning (рассуждение).","method_loc":"Проверяли метод на benchmark (бенчмарке), указанном в abstract.","found_loc":"Показали результат на benchmark (бенчмарке).","why_loc":"Полезно для проверки лимита digest."}
]}
EOF
)

run_runner() { # hub fixture extra-env...
  local d="$1" fixture="$2"; shift 2
  KB_HUB="$d" \
  KB_LEARNING_ARXIV_DISABLE_NETWORK=1 \
  KB_LEARNING_ARXIV_FIXTURE="$fixture" \
  KB_LEARNING_ARXIV_GROK_BIN="$d/bin/grok-fake" \
  KB_CODEX_BIN="$d/bin/codex-fake" \
  KB_LEARNING_ARXIV_FULLTEXT_FIXTURE_DIR="$FULLTEXT_DIR" \
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
write_codex "$HUB" "$CODEX_FULL" 0
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
FIELDS_OK=$(mget "$HUB" "all(p.get('title') and p.get('authors') and p.get('link','').startswith('https://arxiv.org/abs/') and p.get('abstract') and p.get('abstract_loc') and p.get('method_loc') and p.get('abstract_source')=='codex' and p.get('summary_loc') and p.get('reason') and p.get('analysis_source')=='full_text' and p.get('analysis_chars',0) > len(p.get('abstract','')) and p.get('analysis_truncated') is False and isinstance(p.get('scores',{}).get('final'),int) for p in m['selected_papers'])")
[[ "$FIELDS_OK" == "True" ]] && ok "S1: every paper has title/authors/link/abstract/full-text provenance/abstract_loc/method_loc/summary/reason/scores" \
  || fail "S1: missing per-paper fields"
grep -q "FULLTEXT_METHOD_MARKER_10001" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && ok "S1: Codex prompt file includes full-text fixture marker" || fail "S1: Codex prompt lacks full-text marker"
grep -q "analysis_source: full_text" "$HUB/sources/arxiv-learning-translation-codex-$TODAY.md" \
  && ok "S1: translation source records analysis_source" || fail "S1: translation source missing analysis_source"
grep -q "learning-arxiv-codex-prompt-$TODAY.md" "$HUB/codex-argv.txt" \
  && ok "S1: Codex argv points at prompt file" || fail "S1: Codex argv does not point at prompt file"
ARGV_BYTES=$(wc -c < "$HUB/codex-argv.txt" | tr -d ' ')
[[ "$ARGV_BYTES" -lt 2000 ]] && ok "S1: Codex argv is short ($ARGV_BYTES bytes)" || fail "S1: Codex argv too large ($ARGV_BYTES bytes)"
AS=$(mget "$HUB" "m['selected_papers'][0]['scores'].get('author_signal')")
[[ "$AS" == "0" ]] && ok "S1: author_signal pinned to 0 (v1, no hallucinated affiliations)" \
  || fail "S1: author_signal=$AS (expected 0)"
[[ -s "$HUB/reports/learning-arxiv-summary-$TODAY.md" ]] && ok "S1: report written" || fail "S1: report missing"
[[ -s "$HUB/sources/arxiv-learning-snapshot-$TODAY.md" ]] && ok "S1: snapshot source written" || fail "S1: snapshot missing"
[[ ! -e "$HUB/sources/arxiv-learning-social-grok-$TODAY.md" ]] && ok "S1: default-off writes no grok social source" || fail "S1: social source should not exist by default"
[[ -s "$HUB/sources/arxiv-learning-translation-codex-$TODAY.md" ]] && ok "S1: codex translation source written" || fail "S1: translation source missing"
[[ "$(cat "$HUB/codex-calls" 2>/dev/null || echo 0)" == "1" ]] && ok "S1: exactly one Codex call" || fail "S1: codex calls=$(cat "$HUB/codex-calls" 2>/dev/null)"
[[ "$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)" == "0" ]] && ok "S1: default-off makes zero Grok calls" || fail "S1: grok calls=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)"
[[ "$(mget "$HUB" "m.get('social_check')")" == "skipped" ]] && ok "S1: manifest social_check=skipped" || fail "S1: social_check=$(mget "$HUB" "m.get('social_check')")"
[[ "$(mget "$HUB" "m.get('grok_rc')")" == "None" ]] && ok "S1: grok_rc=null when skipped" || fail "S1: grok_rc=$(mget "$HUB" "m.get('grok_rc')")"
[[ "$(mget "$HUB" "m.get('manifest_version')")" == "4" ]] && ok "S1: manifest_version=4 stamped" || fail "S1: manifest_version"

echo "=== S1b: missing full-text fixture + disabled network → abstract_fallback ==="
HUB=$(new_hub fulltext-fallback)
EMPTY_FULLTEXT="$TMP/empty-fulltext"; mkdir -p "$EMPTY_FULLTEXT"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE5" KB_LEARNING_ARXIV_FULLTEXT_FIXTURE_DIR="$EMPTY_FULLTEXT" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S1b: rc=0 with missing full text" || fail "S1b: rc=$RC"
FB=$(mget "$HUB" "all(p.get('analysis_source')=='abstract_fallback' and p.get('analysis_error') for p in m['selected_papers'])")
[[ "$FB" == "True" ]] && ok "S1b: all papers fall back to abstract with error provenance" || fail "S1b: fallback provenance missing"
if grep -q "FULLTEXT_METHOD_MARKER" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md"; then
  fail "S1b: full-text marker leaked into fallback prompt"
else
  ok "S1b: fallback prompt has no full-text marker"
fi

echo "=== S2: digest content (arXiv links only, Russian, statuses split) ==="
DIGEST=$(cat "$HUB/last-digest.txt" 2>/dev/null || echo "")
LINKS=$(grep -o "arxiv.org/abs/[0-9.]*" <<<"$DIGEST" | sort -u | wc -l | tr -d ' ')
[[ "$LINKS" == "3" ]] && ok "S2: digest has 3 distinct arXiv links" || fail "S2: digest arXiv links=$LINKS"
if grep -qiE "openai\.com|blog\.google|news\.ycombinator|github\.com" <<<"$DIGEST"; then
  fail "S2: digest contains non-arXiv primary links"
else
  ok "S2: no OpenAI/Google/HN/GitHub links in digest"
fi
grep -q "Аннотация" <<<"$DIGEST" && ok "S2: digest has translated abstract line" || fail "S2: no abstract line"
grep -q "LLM (large language model, большая языковая модель)" <<<"$DIGEST" \
  && ok "S2: digest expands LLM inline" || fail "S2: LLM not expanded inline"
grep -q "MCP (Model Context Protocol, протокол контекста модели)" <<<"$DIGEST" \
  && ok "S2: digest expands MCP inline" || fail "S2: MCP not expanded inline"
# Summary CONTENT must be Russian (codex bounded translation), not just labels
RU_CONTENT=$(grep -c "Аннотация: [^ ]*[А-Яа-я]" <<<"$DIGEST" || true)
[[ "$RU_CONTENT" == "3" ]] && ok "S2: all 3 abstract lines have Russian content (not just labels)" \
  || fail "S2: Russian abstract content lines=$RU_CONTENT (expected 3)"
SRC_OK=$(mget "$HUB" "all(p.get('summary_source')=='codex' for p in m['selected_papers'])")
[[ "$SRC_OK" == "True" ]] && ok "S2: summary_source=codex for all papers" || fail "S2: summary_source"
METH_OK=$(mget "$HUB" "all(p.get('method_loc') for p in m['selected_papers'])")
[[ "$METH_OK" == "True" ]] && ok "S2: method_loc persisted for all papers" || fail "S2: method_loc missing"
# Owner feedback 2026-06-12: stats line, Russian selection reason, Russian
# titles and Russian status words — no RU/EN mix in the user surface.
grep -q "Просмотрел .* свежих статей" <<<"$DIGEST" && ok "S2: digest states how many papers were scanned" \
  || fail "S2: no scanned-stats line"
grep -q "по темам подошло" <<<"$DIGEST" && ok "S2: digest states relevant count" || fail "S2: no relevant count"
REASONS=$(grep -c "Почему выбрана:" <<<"$DIGEST" || true)
[[ "$REASONS" == "3" ]] && ok "S2: per-paper selection reason present (3)" || fail "S2: reasons=$REASONS"
if grep -qE "(^|[[:space:]])(X|Reddit):" <<<"$DIGEST"; then
  fail "S2: social status line leaked into default-off digest"
else
  ok "S2: no X/Reddit status lines in default-off digest"
fi
grep -q "Агентное планирование" <<<"$DIGEST" && ok "S2: Russian title from codex rendered" || fail "S2: title_loc not used"
grep -q "Готовый паттерн планирования" <<<"$DIGEST" && ok "S2: per-paper why_loc from codex rendered" || fail "S2: why_loc not used"
grep -q "Зачем тебе" <<<"$DIGEST" && ok "S2: digest has 'Зачем тебе'" || fail "S2: no 'Зачем тебе'"
METHODS=$(grep -c "Как исследовали:" <<<"$DIGEST" || true)
[[ "$METHODS" == "3" ]] && ok "S2: digest has per-paper method/setup line (3)" || fail "S2: method lines=$METHODS"
grep -q "Предложенный фреймворк проверяли на AgentBench" <<<"$DIGEST" \
  && ok "S2: digest renders concrete method/setup from Codex" || fail "S2: method_loc not rendered"
grep -q "abstract_loc" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && grep -q "method_loc" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && grep -qi "dataset\\|benchmark\\|experiment\\|setup" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && grep -qi "expand.*acronym\\|acronym.*expand" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && ok "S2: codex prompt asks for abstract_loc/method_loc and term expansion" || fail "S2: codex prompt missing abstract/method/term contract"
# And the social prompt must not be created by default.
if [[ -e "$HUB/.orchestrator/learning-arxiv-grok-prompt-$TODAY.md" ]]; then
  fail "S2: grok prompt created despite social_check off"
else
  ok "S2: no grok prompt by default"
fi
grep -q "Аннотация (перевод)" "$HUB/reports/learning-arxiv-summary-$TODAY.md" \
  && ok "S2: report has translated abstract heading" || fail "S2: translated abstract heading missing"
grep -q "Как исследовали" "$HUB/reports/learning-arxiv-summary-$TODAY.md" \
  && ok "S2: report has method/setup heading" || fail "S2: report method heading missing"
if grep -q "Проверка X/Reddit\|\\*\\*X:\\*\\*\\|\\*\\*Reddit:\\*\\*\\|Прежнее обсуждение\\|Подтверждения" "$HUB/reports/learning-arxiv-summary-$TODAY.md"; then
  fail "S2: default-off report still contains social boilerplate"
else
  ok "S2: default-off report omits social boilerplate"
fi
if grep -q "arxiv-learning-social-grok" "$HUB/reports/learning-arxiv-summary-$TODAY.md"; then
  fail "S2: default-off report links social source"
else
  ok "S2: default-off report sources omit social source"
fi
grep -q "method_loc: Предложенный фреймворк" "$HUB/sources/arxiv-learning-translation-codex-$TODAY.md" \
  && ok "S2: translation source persists method_loc" || fail "S2: translation source missing method_loc"
if grep -q "Аннотация (EN)" "$HUB/reports/learning-arxiv-summary-$TODAY.md"; then
  fail "S2: report still uses EN abstract as primary heading"
else
  ok "S2: report no longer uses EN abstract heading"
fi
CALLS=$(wc -l < "$HUB/channel-calls.log" 2>/dev/null | tr -d ' ')
[[ "$CALLS" == "1" ]] && ok "S2: exactly one telegram send" || fail "S2: sends=$CALLS"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S2: digest_delivered=true" || fail "S2: digest_delivered"

echo "=== S3: grok fixture merged per paper ==="
HUB=$(new_hub grok-optin)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
X1=$(mget "$HUB" "[p['social']['x_status'] for p in m['selected_papers'] if p['id']=='2606.10001'][0]")
R2=$(mget "$HUB" "[p['social']['reddit_status'] for p in m['selected_papers'] if p['id']=='2606.10002'][0]")
[[ "$X1" == "found" ]] && ok "S3: paper1 x_status=found merged" || fail "S3: paper1 x_status=$X1"
[[ "$R2" == "found" ]] && ok "S3: paper2 reddit_status=found merged" || fail "S3: paper2 reddit_status=$R2"
[[ "$(mget "$HUB" "m['social_check']")" == "ok" ]] && ok "S3: social_check=ok" || fail "S3: social_check"
grep -q "не найдено\|not_found" "$HUB/reports/learning-arxiv-summary-$TODAY.md" \
  && ok "S3: report carries social statuses" || fail "S3: report missing social statuses"
grep -q "abstract_loc\\|studied_loc\\|method_loc\\|why_loc" "$HUB/.orchestrator/learning-arxiv-grok-prompt-$TODAY.md" \
  && fail "S3: grok prompt asks for translation fields (split incomplete)" || ok "S3: opt-in grok prompt is social-only"

echo "=== S3b: unknown social_check value disables social with warning ==="
HUB=$(new_hub social-typo)
set_social_check "$HUB" "banana"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S3b: rc=0 with unknown social_check" || fail "S3b: rc=$RC"
[[ "$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)" == "0" ]] && ok "S3b: unknown social_check makes zero Grok calls" || fail "S3b: unexpected grok call"
[[ "$(mget "$HUB" "m.get('social_check')")" == "skipped" ]] && ok "S3b: unknown social_check records skipped" || fail "S3b: social_check=$(mget "$HUB" "m.get('social_check')")"
grep -q "unknown social_check" "$HUB/logs/learning-arxiv.log" \
  && ok "S3b: warning logged for unknown social_check" || fail "S3b: missing warning"

echo "=== S4: empty grok → social degraded (not not_found); Codex translation SURVIVES (AC1) ==="
HUB=$(new_hub grok-empty)
enable_grok "$HUB"
write_grok "$HUB" "" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S4: rc=0" || fail "S4: rc=$RC"
ALL_DEG=$(mget "$HUB" "all(p['social']['x_status']=='degraded' and p['social']['reddit_status']=='degraded' for p in m['selected_papers'])")
[[ "$ALL_DEG" == "True" ]] && ok "S4: all social statuses degraded" || fail "S4: statuses not degraded"
NF=$(mget "$HUB" "any('not_found' in (p['social']['x_status'],p['social']['reddit_status']) for p in m['selected_papers'])")
[[ "$NF" == "False" ]] && ok "S4: no invented not_found" || fail "S4: invented not_found"
[[ "$(mget "$HUB" "m['social_check']")" == "degraded" ]] && ok "S4: social_check=degraded" || fail "S4: social_check"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S4: digest still delivered" || fail "S4: digest not delivered"
# Failure isolation (the whole point of the split): Grok dead, Codex survives.
SRC_OK=$(mget "$HUB" "all(p.get('summary_source')=='codex' for p in m['selected_papers'])")
[[ "$SRC_OK" == "True" ]] && ok "S4: translation survived Grok failure (summary_source=codex)" || fail "S4: translation died with grok"
ABS_OK=$(mget "$HUB" "all(p.get('abstract_source')=='codex' for p in m['selected_papers'])")
[[ "$ABS_OK" == "True" ]] && ok "S4: abstract_source=codex despite grok down" || fail "S4: abstract_source not codex"
[[ "$(mget "$HUB" "m['translate_check']")" == "ok" ]] && ok "S4: translate_check=ok" || fail "S4: translate_check"
grep -q "сбой проверки" "$HUB/last-digest.txt" && ok "S4: degraded social rendered in Russian" \
  || fail "S4: degraded status not Russian"
if grep -q "Перевод abstract недоступен" "$HUB/last-digest.txt"; then
  fail "S4: abstract wrongly marked unavailable when Codex succeeded"
else
  ok "S4: translated abstract present (no false unavailable note)"
fi

echo "=== S5: grok rc!=0 → social degraded with provenance; Codex translation survives ==="
HUB=$(new_hub grok-rc)
enable_grok "$HUB"
write_grok "$HUB" "" 3
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S5: rc=0" || fail "S5: rc=$RC"
[[ "$(mget "$HUB" "m['grok_rc']")" == "3" ]] && ok "S5: grok_rc=3 recorded" || fail "S5: grok_rc"
GS=$(mget "$HUB" "m['grok_stderr_tail']")
[[ "$GS" == *"grok exploded"* ]] && ok "S5: grok_stderr_tail recorded" || fail "S5: stderr tail missing"
[[ "$(mget "$HUB" "m['social_check']")" == "degraded" ]] && ok "S5: social_check=degraded" || fail "S5: social_check"
[[ "$(mget "$HUB" "m['translate_check']")" == "ok" ]] && ok "S5: translate_check=ok (codex unaffected)" || fail "S5: translate_check"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "S5: digest delivered" || fail "S5: digest"

echo "=== S6: partial grok (2 of 3 papers, one malformed reddit) → per-paper/per-channel degraded ==="
GROK_PARTIAL='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"banana","evidence":"x link","prior_context":"ok"},
 {"id":"2606.10002","x_status":"weak","reddit_status":"not_found","evidence":"","prior_context":"ok"}
]}'
HUB=$(new_hub grok-partial)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_PARTIAL" 0
write_codex "$HUB" "$CODEX_FULL" 0
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
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$TMP/does-not-exist.xml" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S7: rc!=0 on fetch failure" || fail "S7: rc=0"
[[ "$(mget "$HUB" "m['status']")" == "failed" ]] && ok "S7: manifest status=failed" || fail "S7: status"
[[ ! -f "$HUB/last-digest.txt" ]] && ok "S7: no digest sent" || fail "S7: digest sent on failure"

echo "=== S8: idempotent rerun; --force resends ==="
HUB=$(new_hub idem)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
CALLS=$(wc -l < "$HUB/channel-calls.log" | tr -d ' ')
[[ "$RC" == "0" && "$CALLS" == "1" ]] && ok "S8: rerun rc=0, no duplicate send" || fail "S8: rc=$RC calls=$CALLS"
KB_HUB="$HUB" KB_LEARNING_ARXIV_DISABLE_NETWORK=1 KB_LEARNING_ARXIV_FIXTURE="$FIXTURE5" \
  KB_LEARNING_ARXIV_GROK_BIN="$HUB/bin/grok-fake" \
  KB_CODEX_BIN="$HUB/bin/codex-fake" KB_PROCESS_OUTPUTS="telegram,file" \
  "$PY" "$RUNNER" --text-only --date "$TODAY" --force >/dev/null 2>&1
CALLS=$(wc -l < "$HUB/channel-calls.log" | tr -d ' ')
[[ "$CALLS" == "2" ]] && ok "S8: --force resends" || fail "S8: force calls=$CALLS"

echo "=== S9: telegram failure → rc!=0; recovery delivers exactly once from stage cache ==="
HUB=$(new_hub tg-fail)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
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

echo "=== S9b: skipped-cache is invalid after social_check flips to grok ==="
HUB=$(new_hub toggle-social)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S9b: first default-off delivery fails and leaves cache" || fail "S9b: first rc=$RC"
[[ "$(mget "$HUB" "m.get('social_check')")" == "skipped" ]] && ok "S9b: first manifest social_check=skipped" || fail "S9b: first social_check"
GROK_BEFORE=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
CODEX_BEFORE=$(cat "$HUB/codex-calls" 2>/dev/null || echo 0)
enable_grok "$HUB"
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S9b: retry after enabling grok succeeds" || fail "S9b: retry rc=$RC"
GROK_AFTER=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
CODEX_AFTER=$(cat "$HUB/codex-calls" 2>/dev/null || echo 0)
[[ "$GROK_AFTER" -gt "$GROK_BEFORE" ]] && ok "S9b: enabling grok invalidates skipped-cache and invokes Grok" || fail "S9b: grok not invoked (${GROK_BEFORE}->${GROK_AFTER})"
[[ "$CODEX_AFTER" -gt "$CODEX_BEFORE" ]] && ok "S9b: skipped-cache bypass re-runs translation stage" || fail "S9b: codex not re-run (${CODEX_BEFORE}->${CODEX_AFTER})"
[[ "$(mget "$HUB" "m.get('social_check')")" == "ok" ]] && ok "S9b: final manifest social_check=ok" || fail "S9b: final social_check"

echo "=== S10: fewer than three relevant papers ==="
HUB=$(new_hub fewer)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE2" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S10: rc=0 with 2 papers" || fail "S10: rc=$RC"
[[ "$(mget "$HUB" "len(m['selected_papers'])")" == "2" ]] && ok "S10: 2 papers selected" || fail "S10: selected"
grep -q "только 2" "$HUB/last-digest.txt" && ok "S10: digest notes 'только 2'" || fail "S10: no explicit note"
HUB=$(new_hub zero)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
run_runner "$HUB" "$FIXTURE0" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S10: rc=0 with 0 papers" || fail "S10: rc=$RC (0 papers)"
grep -q "релевантных статей сегодня нет" "$HUB/last-digest.txt" \
  && ok "S10: zero-papers digest says so explicitly" || fail "S10: zero-papers note missing"

echo "=== S11: digest length budget ≤ 3900 (single Telegram message) ==="
HUB=$(new_hub long)
write_grok "$HUB" "$GROK_LONG" 0
write_codex "$HUB" "$CODEX_LONG" 0
run_runner "$HUB" "$FIXTURELONG" >/dev/null 2>&1
LEN=$($PY -c "print(len(open('$HUB/last-digest.txt',encoding='utf-8').read()))" 2>/dev/null || echo 99999)
[[ "$LEN" -le 3900 ]] && ok "S11: digest length $LEN ≤ 3900" || fail "S11: digest length $LEN > 3900"
LINKS=$(grep -o "arxiv.org/abs/[0-9.]*" "$HUB/last-digest.txt" | sort -u | wc -l | tr -d ' ')
[[ "$LINKS" == "3" ]] && ok "S11: all 3 papers still present" || fail "S11: links=$LINKS"
grep -q "Аннотация" "$HUB/last-digest.txt" && ok "S11: abstract line present under budget" || fail "S11: abstract line dropped"

echo "=== S12: zero NotebookLM calls in background mode (all hubs) ==="
NB_MARKERS=$(find "$TMP" -name "notebooklm-called.marker" | wc -l | tr -d ' ')
[[ "$NB_MARKERS" == "0" ]] && ok "S12: no notebooklm invocation across all scenarios" || fail "S12: notebooklm called ($NB_MARKERS)"

echo "=== S14: lock contention semantics ==="
HUB=$(new_hub lock)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
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
write_codex "$HUB" '{"papers":[]}' 0
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
write_codex "$HUB" "$CODEX_FULL" 0
chmod -x "$HUB/bin/kb-channel-send"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "S17: sender PermissionError → rc!=0" || fail "S17: rc=0 on sender exception"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "False" ]] && ok "S17: digest_delivered=false" || fail "S17: digest_delivered"
[[ "$(mget "$HUB" "m['status']")" == "failed" ]] && ok "S17: manifest status=failed (provenance written)" || fail "S17: status"

echo "=== S18: English studied_loc/found_loc from Codex (ru profile) → fallback_en, not codex ==="
CODEX_EN='{"papers":[
 {"id":"2606.10001","studied_loc":"They studied planning for agents.","found_loc":"The method achieves 87% accuracy."},
 {"id":"2606.10002","studied_loc":"Memory and RAG for agents.","found_loc":"12% retrieval gain."},
 {"id":"2606.10003","studied_loc":"CoT under quantization.","found_loc":"9 points better."}
]}'
HUB=$(new_hub codex-en)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_EN" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
FB=$(mget "$HUB" "all(p.get('summary_source')=='fallback_en' for p in m['selected_papers'])")
[[ "$FB" == "True" ]] && ok "S18: non-Cyrillic Codex summaries → fallback_en" || fail "S18: English accepted as codex summary"
ST=$(mget "$HUB" "all(p['social']['x_status'] in ('found','weak','not_found') for p in m['selected_papers'])")
[[ "$ST" == "True" ]] && ok "S18: social statuses still parsed normally" || fail "S18: social statuses lost"

echo "=== S15: inline YAML comments do not poison config values ==="
HUB=$(new_hub cfgcomment)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
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
# Social-only en fixture (English prior_context) + companion English Codex translation.
GROK_EN_LOC='{"papers":[
 {"id":"2606.10001","x_status":"found","reddit_status":"weak","evidence":"x link","prior_context":"The agentic-planning idea circulated on X a month before the paper."},
 {"id":"2606.10002","x_status":"not_found","reddit_status":"found","evidence":"reddit thread","prior_context":"Similar hierarchical RAG indexes surfaced on Reddit before."},
 {"id":"2606.10003","x_status":"weak","reddit_status":"not_found","evidence":"","prior_context":"Quantization and reasoning were discussed in passing."}
]}'
CODEX_EN_LOC='{"papers":[
 {"id":"2606.10001","title_loc":"Agentic Planning with Tool Use for LLM Agents","abstract_loc":"The paper studies LLM (large language model) agents that plan over long horizons and use MCP (Model Context Protocol) calls. The method reaches 87% accuracy on AgentBench.","studied_loc":"They studied long-horizon planning for autonomous agents with tool use and MCP calls.","method_loc":"They evaluated the proposed framework on AgentBench against baseline approaches.","found_loc":"The method reaches 87% accuracy on AgentBench and beats the baselines.","why_loc":"A ready planning pattern for your task orchestrator."},
 {"id":"2606.10002","title_loc":"Memory-Augmented Retrieval for KB Agents","abstract_loc":"The paper studies persistent memory and RAG (retrieval-augmented generation) for agent knowledge bases. A hierarchical RAG index gives +12% retrieval accuracy.","studied_loc":"They studied persistent memory and RAG for agent knowledge bases.","method_loc":"They built a hierarchical RAG index and evaluated retrieval accuracy.","found_loc":"A hierarchical RAG index gives +12% retrieval accuracy.","why_loc":"Directly applicable to the KB architecture."},
 {"id":"2606.10003","title_loc":"Evaluating CoT in Small Local Models","abstract_loc":"The paper evaluates CoT (chain-of-thought) quality under quantization for on-device inference. Their method improves reasoning by 9 points while staying efficient.","studied_loc":"They evaluated chain-of-thought quality under quantization on-device.","method_loc":"They compared reasoning scores on an on-device inference benchmark after quantization.","found_loc":"Their method improves reasoning by 9 points while staying efficient.","why_loc":"Useful for local model choices."}
]}'
HUB=$(new_hub lang-en en)
write_grok "$HUB" "$GROK_EN_LOC" 0
write_codex "$HUB" "$CODEX_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S19: rc=0 with en profile" || fail "S19: rc=$RC"
DIGEST_EN=$(cat "$HUB/last-digest.txt" 2>/dev/null || echo "")
grep -q "Scanned .* fresh arXiv papers" <<<"$DIGEST_EN" && ok "S19: English stats line" || fail "S19: stats line"
grep -q "Why selected:" <<<"$DIGEST_EN" && ok "S19: English reason label" || fail "S19: reason label"
grep -q "Abstract:" <<<"$DIGEST_EN" && ok "S19: English abstract label" || fail "S19: abstract label"
if grep -qE "(^|[[:space:]])(X|Reddit):" <<<"$DIGEST_EN"; then
  fail "S19: social status line leaked into default-off en digest"
else
  ok "S19: no X/Reddit status lines in default-off en digest"
fi
if grep -q "X/Reddit check\|Prior discussion\|Evidence" "$HUB/reports/learning-arxiv-summary-$TODAY.md"; then
  fail "S19: social boilerplate leaked into default-off en report"
else
  ok "S19: en report omits social boilerplate by default"
fi
if grep -q "[А-Яа-я]" <<<"$DIGEST_EN"; then
  fail "S19: Cyrillic leaked into en digest"
else
  ok "S19: zero Cyrillic in en digest"
fi
grep -q "in English" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && ok "S19: codex prompt requests English translation" || fail "S19: codex prompt language"
if grep -q "[А-Яа-я]" "$HUB/reports/learning-arxiv-summary-$TODAY.md"; then
  fail "S19: Cyrillic leaked into en report"
else
  ok "S19: en report fully English"
fi

echo "=== S20: KB_LANG=sr → English labels, ISO-safe directive, rc=0 ==="
HUB=$(new_hub lang-sr)
write_grok "$HUB" "$GROK_EN_LOC" 0
write_codex "$HUB" "$CODEX_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" KB_LANG=sr >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S20: rc=0 with KB_LANG=sr" || fail "S20: rc=$RC"
grep -q "Why selected:" "$HUB/last-digest.txt" && ok "S20: English labels for unmapped code" || fail "S20: labels"
grep -q "ISO 639 code 'sr'" "$HUB/.orchestrator/learning-arxiv-codex-prompt-$TODAY.md" \
  && ok "S20: ISO-safe directive in codex prompt" || fail "S20: directive"

echo "=== S21: stage cache is language-gated ==="
HUB=$(new_hub lang-gate)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1   # ru run, delivery fails, cache filled
G1=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
C1=$(cat "$HUB/codex-calls" 2>/dev/null || echo 0)
echo 0 > "$HUB/channel-rc"
write_grok "$HUB" "$GROK_EN_LOC" 0
write_codex "$HUB" "$CODEX_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" KB_LANG=en >/dev/null 2>&1   # target switched → cache bypass
RC=$?
G2=$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)
C2=$(cat "$HUB/codex-calls" 2>/dev/null || echo 0)
[[ "$RC" == "0" ]] && ok "S21: en recovery rc=0" || fail "S21: rc=$RC"
[[ "$G2" -gt "$G1" ]] && ok "S21: language mismatch re-invoked grok (no stale cache)" || fail "S21: stale cache reused (${G1} -> ${G2})"
[[ "$C2" -gt "$C1" ]] && ok "S21: language mismatch re-invoked codex too" || fail "S21: codex not re-invoked (${C1} -> ${C2})"
if grep -q "[А-Яа-я]" "$HUB/last-digest.txt"; then
  fail "S21: Russian leaked into en digest from ru cache"
else
  ok "S21: no Cyrillic after language switch"
fi
# same-language cache still works (ru → ru, fixture removed)
HUB=$(new_hub lang-gate-ru)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$TMP/removed-again.xml" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "S21: same-language cache recovery still works" || fail "S21: ru cache broken rc=$RC"

echo "=== S22: language switch + failed re-fetch must not resurrect old-language cache ==="
HUB=$(new_hub lang-switch-fail)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
echo 3 > "$HUB/channel-rc"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1            # ru cache filled, delivery failed
echo 0 > "$HUB/channel-rc"
run_runner "$HUB" "$TMP/gone.xml" KB_LANG=en >/dev/null 2>&1   # switch to en, fetch FAILS
RC=$?
[[ "$RC" != "0" ]] && ok "S22: switch + fetch failure → rc!=0" || fail "S22: rc=0"
write_grok "$HUB" "$GROK_EN_LOC" 0
write_codex "$HUB" "$CODEX_EN_LOC" 0
run_runner "$HUB" "$FIXTURE5" KB_LANG=en >/dev/null 2>&1       # retry with fixture back
RC=$?
[[ "$RC" == "0" ]] && ok "S22: en retry rc=0" || fail "S22: retry rc=$RC"
if grep -q "[А-Яа-я]" "$HUB/last-digest.txt"; then
  fail "S22: stale ru cache resurrected after failed re-fetch"
else
  ok "S22: no stale-language content after failed re-fetch + retry"
fi

echo "=== T11: old v1/v2 manifests NOT reused (migration); delivered v1 idempotent ==="
HUB=$(new_hub mig-v1)
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_FULL" 0
# seed a same-day v1 manifest (old combined-Grok shape): selected_papers +
# social_check, NO translate_check / manifest_version, not yet delivered.
$PY -c "
import json,os
d='$HUB/.orchestrator'; os.makedirs(d,exist_ok=True)
m={'date':'$TODAY','status':'report_written','attempts':1,'language':'ru',
   'social_check':'ok','grok_rc':0,'digest_delivered':False,
   'arxiv_fetched':5,'arxiv_relevant':3,
   'selected_papers':[{'id':'2606.10001','title':'Old','authors':['X'],
     'link':'https://arxiv.org/abs/2606.10001','abstract':'old','published':'2026-06-11',
     'primary_category':'cs.AI','scores':{'final':10,'topic_relevance':2,'abstract_signal':1,'novelty_practicality':0,'author_signal':0},
     'reason':'r','summary_loc':'old','_groups':['agents'],
     'abstract_source':'grok','summary_source':'grok','abstract_loc':'СТАРЫЙ перевод от Grok'}],
   'runner_ups':[]}
json.dump(m,open(d+'/learning-arxiv-$TODAY.json','w'),ensure_ascii=False)
"
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1   # no --force
RC=$?
[[ "$RC" == "0" ]] && ok "T11: rc=0" || fail "T11: rc=$RC"
[[ "$(cat "$HUB/codex-calls" 2>/dev/null || echo 0)" -ge 1 ]] && ok "T11: Codex invoked (stale v1 cache bypassed)" || fail "T11: Codex skipped — stale cache reused"
[[ "$(cat "$HUB/grok-calls" 2>/dev/null || echo 0)" == "0" ]] && ok "T11: default-off skips Grok while bypassing stale v1 cache" || fail "T11: unexpected grok call"
[[ "$(mget "$HUB" "m.get('manifest_version')")" == "4" ]] && ok "T11: manifest rewritten to v4" || fail "T11: manifest_version not 4"
[[ -n "$(mget "$HUB" "m.get('translate_check')")" ]] && ok "T11: translate_check present after migration" || fail "T11: translate_check missing"
[[ "$(mget "$HUB" "m.get('social_check')")" == "skipped" ]] && ok "T11: migrated default-off manifest social_check=skipped" || fail "T11: social_check"
ABS_C=$(mget "$HUB" "all(p.get('abstract_source')=='codex' for p in m['selected_papers'])")
[[ "$ABS_C" == "True" ]] && ok "T11: translation now Codex-sourced (not stale grok)" || fail "T11: stale grok translation served"
METH_C=$(mget "$HUB" "all(p.get('method_loc') for p in m['selected_papers'])")
[[ "$METH_C" == "True" ]] && ok "T11: method_loc present after migration" || fail "T11: method_loc missing after migration"

# seed a same-day v2 manifest (split Codex/Grok shape) that is otherwise
# cache-eligible but lacks the new method_loc/full-text fields/manifest_version 4.
HUB3=$(new_hub mig-v2-no-method)
write_grok "$HUB3" "$GROK_FULL" 0
write_codex "$HUB3" "$CODEX_FULL" 0
$PY -c "
import json,os
d='$HUB3/.orchestrator'; os.makedirs(d,exist_ok=True)
m={'date':'$TODAY','status':'report_written','attempts':1,'language':'ru',
   'manifest_version':2,'translate_check':'ok','social_check':'ok','grok_rc':0,
   'codex_rc':0,'digest_delivered':False,'arxiv_fetched':5,'arxiv_relevant':3,
   'selected_papers':[{'id':'2606.10001','title':'Old v2','authors':['X'],
     'link':'https://arxiv.org/abs/2606.10001','abstract':'old','published':'2026-06-11',
     'primary_category':'cs.AI','scores':{'final':10,'topic_relevance':2,'abstract_signal':1,'novelty_practicality':0,'author_signal':0},
     'reason':'r','summary_loc':'old','_groups':['agents'],
     'abstract_source':'codex','summary_source':'codex','abstract_loc':'Старый v2 abstract',
     'studied_loc':'Старое поле без method_loc','found_loc':'Старый вывод'}],
   'runner_ups':[]}
json.dump(m,open(d+'/learning-arxiv-$TODAY.json','w'),ensure_ascii=False)
"
run_runner "$HUB3" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "T11b: v2 no-method rc=0" || fail "T11b: rc=$RC"
[[ "$(cat "$HUB3/codex-calls" 2>/dev/null || echo 0)" -ge 1 ]] && ok "T11b: stale v2 cache bypassed (Codex invoked)" || fail "T11b: stale v2 cache reused"
[[ "$(mget "$HUB3" "m.get('manifest_version')")" == "4" ]] && ok "T11b: v2 rewritten to v4" || fail "T11b: manifest_version"
[[ "$(cat "$HUB3/grok-calls" 2>/dev/null || echo 0)" == "0" ]] && ok "T11b: default-off skips Grok after v2 migration" || fail "T11b: unexpected grok call"
[[ "$(mget "$HUB3" "m.get('social_check')")" == "skipped" ]] && ok "T11b: social_check=skipped after v2 migration" || fail "T11b: social_check"
METH3=$(mget "$HUB3" "all(p.get('method_loc') for p in m['selected_papers'])")
[[ "$METH3" == "True" ]] && ok "T11b: method_loc present after v2 migration" || fail "T11b: method_loc missing"
# delivered v1 manifest must stay untouched (idempotent; needs --force to regenerate)
HUB2=$(new_hub mig-v1-delivered)
write_grok "$HUB2" "$GROK_FULL" 0
write_codex "$HUB2" "$CODEX_FULL" 0
$PY -c "
import json,os
d='$HUB2/.orchestrator'; os.makedirs(d,exist_ok=True)
m={'date':'$TODAY','status':'completed','attempts':1,'language':'ru','social_check':'ok','digest_delivered':True,'selected_papers':[],'runner_ups':[]}
json.dump(m,open(d+'/learning-arxiv-$TODAY.json','w'),ensure_ascii=False)
"
run_runner "$HUB2" "$FIXTURE5" >/dev/null 2>&1
[[ "$(cat "$HUB2/codex-calls" 2>/dev/null || echo 0)" == "0" ]] && ok "T11: delivered v1 manifest left untouched (no Codex call, needs --force)" || fail "T11: delivered manifest re-ran without --force"

echo "=== T12: timeout defaults (Grok 600 / Codex 300) reach subprocess.run + env override (AC6) ==="
T12=$(KB_HUB="$TMP/t12-hub" KB_CODEX_BIN="/usr/bin/true" $PY <<PYEOF
import os, sys, importlib.util, shutil
os.makedirs('$TMP/t12-hub/bin', exist_ok=True)
if os.path.exists('$SRC_BIN/_kb_profile.py'):
    shutil.copy('$SRC_BIN/_kb_profile.py', '$TMP/t12-hub/bin/_kb_profile.py')
sys.path.insert(0, '$SRC_BIN')
from importlib.machinery import SourceFileLoader
loader = SourceFileLoader('arxrunner', '$RUNNER')
spec = importlib.util.spec_from_loader('arxrunner', loader)
mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
captured = {}
class FakeProc:
    returncode = 0; stdout = '{"papers":[]}'; stderr = ''
def fake_run(cmd, **kw):
    captured['timeout'] = kw.get('timeout'); return FakeProc()
mod.subprocess.run = fake_run
papers = [{'id':'x','title':'t','abstract':'a','authors':[],'link':'l','_groups':[]}]
for k in ('KB_LEARNING_ARXIV_GROK_TIMEOUT','KB_LEARNING_ARXIV_CODEX_TIMEOUT'):
    os.environ.pop(k, None)
mod.run_grok('2026-01-01', papers); g_def = captured['timeout']
mod.run_codex('2026-01-01', papers); c_def = captured['timeout']
os.environ['KB_LEARNING_ARXIV_GROK_TIMEOUT']='42'; os.environ['KB_LEARNING_ARXIV_CODEX_TIMEOUT']='77'
mod.run_grok('2026-01-01', papers); g_ovr = captured['timeout']
mod.run_codex('2026-01-01', papers); c_ovr = captured['timeout']
print(mod.GROK_TIMEOUT_DEFAULT, mod.CODEX_TIMEOUT_DEFAULT, g_def, c_def, g_ovr, c_ovr)
PYEOF
)
read GD CD GDEF CDEF GOVR COVR <<<"$T12"
[[ "$GD" == "600" && "$CD" == "300" ]] && ok "T12: defaults GROK=600 CODEX=300" || fail "T12: defaults $GD/$CD"
[[ "$GDEF" == "600" && "$CDEF" == "300" ]] && ok "T12: defaults reach subprocess.run(timeout=)" || fail "T12: default not passed ($GDEF/$CDEF)"
[[ "$GOVR" == "42" && "$COVR" == "77" ]] && ok "T12: env overrides reach subprocess.run" || fail "T12: override not passed ($GOVR/$COVR)"

echo "=== T13: Codex failure honesty (AC8, engine-neutral) + partial Codex output ==="
# 13a: Codex fails, Grok ok → unavailable note must NOT name Grok; social intact
HUB=$(new_hub codex-fail)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "" 5
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "T13a: rc=0" || fail "T13a: rc=$RC"
[[ "$(mget "$HUB" "m['translate_check']")" == "degraded" ]] && ok "T13a: translate_check=degraded" || fail "T13a: translate_check"
[[ "$(mget "$HUB" "m['social_check']")" == "ok" ]] && ok "T13a: social_check=ok (grok unaffected)" || fail "T13a: social_check"
[[ "$(mget "$HUB" "m['codex_rc']")" == "5" ]] && ok "T13a: codex_rc=5 recorded" || fail "T13a: codex_rc"
AB=$(mget "$HUB" "all(p.get('abstract_source')=='unavailable' for p in m['selected_papers'])")
[[ "$AB" == "True" ]] && ok "T13a: abstract_source=unavailable" || fail "T13a: abstract_source"
grep -q "Перевод abstract недоступен" "$HUB/last-digest.txt" && ok "T13a: honest unavailable note present" || fail "T13a: note missing"
if grep -qi "Grok" "$HUB/last-digest.txt"; then
  fail "T13a: digest names Grok for a Codex-owned translation failure"
else
  ok "T13a: degraded note is engine-neutral (no Grok blame)"
fi
X1=$(mget "$HUB" "[p['social']['x_status'] for p in m['selected_papers'] if p['id']=='2606.10001'][0]")
[[ "$X1" == "found" ]] && ok "T13a: social signal intact despite codex failure" || fail "T13a: social lost ($X1)"
# 13b: partial Codex — 2 good Russian, 1 valid-JSON English-passthrough → partial
CODEX_PARTIAL='{"papers":[
 {"id":"2606.10001","title_loc":"Хорошо","abstract_loc":"Нормальный перевод про агентов и planning.","studied_loc":"Изучали агентов.","method_loc":"Проверяли на benchmark.","found_loc":"Достигли 87%.","why_loc":"Полезно."},
 {"id":"2606.10002","title_loc":"Хорошо два","abstract_loc":"Нормальный перевод про память и RAG.","studied_loc":"Изучали память.","method_loc":"Проверяли retrieval accuracy.","found_loc":"Плюс 12%.","why_loc":"Полезно."},
 {"id":"2606.10003","title_loc":"bad","abstract_loc":"English passthrough, no translation here.","studied_loc":"English only.","method_loc":"English method too.","found_loc":"English only too."}
]}'
HUB=$(new_hub codex-partial)
enable_grok "$HUB"
write_grok "$HUB" "$GROK_FULL" 0
write_codex "$HUB" "$CODEX_PARTIAL" 0
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
[[ "$(mget "$HUB" "m['translate_check']")" == "partial" ]] && ok "T13b: translate_check=partial (mixed)" || fail "T13b: translate_check=$(mget "$HUB" "m['translate_check']")"
G=$(mget "$HUB" "[p.get('summary_source') for p in m['selected_papers'] if p['id']=='2606.10001'][0]")
B=$(mget "$HUB" "[p.get('summary_source') for p in m['selected_papers'] if p['id']=='2606.10003'][0]")
[[ "$G" == "codex" ]] && ok "T13b: good paper → codex" || fail "T13b: good paper source=$G"
[[ "$B" == "fallback_en" ]] && ok "T13b: English-passthrough paper → fallback_en" || fail "T13b: bad paper source=$B"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "T13b: digest delivered despite partial" || fail "T13b: not delivered"

echo "=== T14: BOTH fail (Codex rc!=0 AND Grok rc!=0) → all degraded, honest, digest still sent ==="
HUB=$(new_hub both-fail)
enable_grok "$HUB"
write_grok "$HUB" "" 3
write_codex "$HUB" "" 5
run_runner "$HUB" "$FIXTURE5" >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "T14: rc=0" || fail "T14: rc=$RC"
[[ "$(mget "$HUB" "m['social_check']")" == "degraded" ]] && ok "T14: social_check=degraded" || fail "T14: social_check"
[[ "$(mget "$HUB" "m['translate_check']")" == "degraded" ]] && ok "T14: translate_check=degraded" || fail "T14: translate_check"
ALL_DEG=$(mget "$HUB" "all(p['social']['x_status']=='degraded' and p['social']['reddit_status']=='degraded' for p in m['selected_papers'])")
[[ "$ALL_DEG" == "True" ]] && ok "T14: all social degraded" || fail "T14: social not all degraded"
NF=$(mget "$HUB" "any('not_found' in (p['social']['x_status'],p['social']['reddit_status']) for p in m['selected_papers'])")
[[ "$NF" == "False" ]] && ok "T14: no invented not_found" || fail "T14: invented not_found"
ABS=$(mget "$HUB" "all(p.get('abstract_source')=='unavailable' and p.get('summary_source')=='fallback_en' for p in m['selected_papers'])")
[[ "$ABS" == "True" ]] && ok "T14: translation all unavailable/fallback_en" || fail "T14: translation provenance"
grep -q "Перевод abstract недоступен" "$HUB/last-digest.txt" && ok "T14: honest unavailable note" || fail "T14: note missing"
grep -q "сбой проверки" "$HUB/last-digest.txt" && ok "T14: degraded social rendered" || fail "T14: social note missing"
[[ "$(mget "$HUB" "m['digest_delivered']")" == "True" ]] && ok "T14: digest still delivered" || fail "T14: not delivered"

echo
echo "=== kb-learning-arxiv tests: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] || exit 1
