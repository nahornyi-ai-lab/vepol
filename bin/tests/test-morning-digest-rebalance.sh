#!/usr/bin/env bash
# Morning-digest inputs rebalance (spec morning-digest-inputs-rebalance-2026-07-11,
# v14, Phase A + A2 digest-side): asserts DATA-CORRECTNESS content rules, never sizes.
# Covers D3 (arXiv runner-ups removed, read whole), D7 (log gist = meaningful header
# + first paragraph), D7b (per-project guarantee block), D8 (no daily-research
# block), D9-consumer (money priority + JSON render), D10 (ideas/escalations/state),
# D11 digest-side (missing brief notice + log line), D13 (brief = single
# day-aggregator: NO direct board block, NO direct mail block, same-day brief passes
# through strip_untrusted_spans).
# Uses the KB_DIGEST_PROMPT_ONLY seam (prints the assembled synth input, no LLM).

set -uo pipefail
PASS=0; FAIL=0
SRC_BIN="${KB_MD_SRC_BIN:-$HOME/knowledge/bin}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

if ! [[ -x "$SRC_BIN/kb-morning-digest" ]]; then
  echo "  ✗ kb-morning-digest missing from $SRC_BIN"; echo "PASS=0 FAIL=1"; exit 1
fi

DAY="2026-07-11"

# --- build a fixture hub -----------------------------------------------------
mk_hub() { # $1 = hub dir
  local H="$1"
  mkdir -p "$H/personal" "$H/reports" "$H/.orchestrator" "$H/briefs" "$H/projects"
  ln -s "$SRC_BIN" "$H/bin"
  : > "$H/personal/.secrets"
}

# fixture dev project (state / log / board)
mk_project() { # $1 = project dir
  local P="$1"; mkdir -p "$P/knowledge"
  # state.md: large (>5000 chars) with an end marker → must survive whole (D10)
  { echo "# fixture project state"; echo; python3 - <<'PY'
print(("Строка состояния проекта, наполнитель. " * 4 + "\n") * 140)
PY
    echo "STATE_END_MARKER_KEEP_ME"; } > "$P/knowledge/state.md"
  # log.md: meaningful + junk entries; one entry with big first paragraph (D7)
  cat > "$P/knowledge/log.md" <<'EOF'
# Log — alpha-proj

## [2026-07-01] session | вечерняя авто-запись сессии SESSION_JUNK_MARKER
Details: [[daily/2026-07-01]]

## [2026-07-03] digest | hub | "Утренний дайджест озвучен DIGEST_RECEIPT_MARKER"

## [2026-07-05] fix | alpha-proj | краткий заголовок записи.
FIRST_PARA_MARKER первый абзац тела записи, может быть очень длинным.

SECOND_PARA_MARKER этот второй абзац не должен попасть в gist.

## [2026-07-11] decision | alpha-proj | MEANINGFUL_DECISION_MARKER приняли решение.
Тело решения в первом абзаце.
EOF
  # board
  cat > "$P/knowledge/backlog.md" <<'EOF'
# Backlog — fixture

## Backlog

- [ ] BL_TITLE_1
  plan_item_id: bl-1
- [ ] BL_TITLE_2
  plan_item_id: bl-2
- [ ] BL_TITLE_3
  plan_item_id: bl-3
- [ ] BL_TITLE_4
  plan_item_id: bl-4
- [ ] BL_TITLE_5
  plan_item_id: bl-5
- [ ] BL_TITLE_6_SHOULD_NOT_APPEAR
  plan_item_id: bl-6

## Ready

- [ ] READY_TASK_TITLE
  plan_item_id: rd-1

## In Progress

- [ ] INPROGRESS_TASK_TITLE
  plan_item_id: ip-1

## Review

- [ ] REVIEW_TASK_TITLE
  plan_item_id: rv-1

## Blocked

- [ ] BLOCKED_TASK_TITLE
  plan_item_id: bk-1

## Done

- [x] DONE_TASK_TITLE_HIDDEN
  plan_item_id: dn-1

## Cancelled

- [x] CANCELLED_TASK_TITLE_HIDDEN
  plan_item_id: cn-1
EOF
}

HUB="$TMP/hub"; mk_hub "$HUB"
PROJ="$TMP/alpha-proj"; mk_project "$PROJ"

# arXiv report (stale-format) with a runner-ups section that must be dropped (D3)
cat > "$HUB/reports/learning-arxiv-summary-$DAY.md" <<'EOF'
# ArXiv summary

## Статья 1
ARXIV_PICK_MARKER настоящая выбранная статья с полным разбором.

## Не вошли (runner-ups)
RUNNERUP_MARKER_SHOULD_BE_DROPPED — это список не-вошедших статей.
- ещё один runner-up
EOF

# money-radar: same-day digest.txt AND same-day json → digest.txt must win (D9)
cat > "$HUB/.orchestrator/money-radar-$DAY-digest.txt" <<'EOF'
Money radar на сегодня: MONEY_DIGEST_TXT_MARKER — готовая проза дайджеста.
EOF
python3 - "$HUB/.orchestrator/money-radar-$DAY.json" <<'PY'
import json, sys
json.dump({
  "date": "2026-07-11", "attempt_date": "2026-07-11",
  "telegram_delivered": True, "status": "ok",
  "report": {"ranked": ["MONEY_JSON_RANKED_TITLE"], "nogo": ["MONEY_JSON_NOGO_TITLE"],
             "confidence": "low"},
  "agents": {"codex": {"status": "ok", "candidates": [
      {"title": "MONEY_JSON_RANKED_TITLE", "band": "band-x",
       "money_flow": "MONEY_FLOW_MARKER", "risk": "RISK_MARKER",
       "proof_links": ["https://money-secret-url.example/leak"],
       "interest": 9, "_links_withheld": True}]}},
}, open(sys.argv[1], "w"), ensure_ascii=False)
PY

# hub log with a meaningful entry + a digest receipt + a session line
cat > "$HUB/log.md" <<'EOF'
# Hub log

## [2026-07-01 09:00] session | сессия HUBSESSION_JUNK_MARKER
Details: [[daily/2026-07-01]]

## [2026-07-09] digest | hub | "Утренний дайджест HUBDIGEST_RECEIPT_MARKER"

## [2026-07-10] fix | hub | HUB_MEANINGFUL_MARKER важная запись.
Первый абзац тела.
EOF

# escalations: open item present → must show; template comments stripped
cat > "$HUB/escalations.md" <<'EOF'
# Escalations

## Open

<!-- Формат:
- [ ] TEMPLATE_COMMENT_MARKER should be stripped
-->
- [ ] OPEN_ESC_MARKER настоящая открытая эскалация — opened 2026-07-10

## Resolved

- [x] OLD_RESOLVED_MARKER — closed 2026-07-01
EOF

# registry: two live projects (alpha-proj with a log, ghost with no log dir)
cat > "$HUB/registry.md" <<EOF
# Registry

| slug | статус | категория | parent | путь | описание |
|---|---|---|---|---|---|
| alpha-proj | live | lab | hub | \`~/alpha-proj\` | dev workspace |
| ghost-proj | live | lab | hub | \`~/ghost\` | no log project |
| sleepy | seeded | lab | hub | \`~/sleepy\` | not live, skip |
EOF
ln -s "$PROJ/knowledge" "$HUB/projects/alpha-proj"
mkdir -p "$TMP/ghost/knowledge"
ln -s "$TMP/ghost/knowledge" "$HUB/projects/ghost-proj"

run_digest() { # $1 = hub, rest = extra env "VAR=val"
  local H="$1"; shift
  env "$@" KB_HUB="$H" KB_VEPOL_DEV="$PROJ" KB_DIGEST_PROMPT_ONLY=1 \
    "$SRC_BIN/kb-morning-digest" --date "$DAY" 2>/dev/null
}

# =============== Case 1: brief MISSING (D11) + everything above ===============
P=$(run_digest "$HUB")
if [[ -z "$P" ]]; then
  fail "produced no output"
else
  # D3 arXiv
  [[ "$P" == *"ARXIV_PICK_MARKER"* ]] && ok "D3: arXiv pick present" || fail "D3: arXiv pick missing"
  [[ "$P" != *"RUNNERUP_MARKER_SHOULD_BE_DROPPED"* ]] && ok "D3: runner-ups dropped" || fail "D3: runner-ups leaked"

  # D13: the direct board block is GONE — no block name, no task titles from the
  # board file, no counts summary, no repr/JSON dump (backlog.md exists in the
  # fixture, so absence proves the block is not gathered, not that data is empty).
  [[ "$P" != *"доска задач"* ]] \
    && ok "D13: board block name absent" || fail "D13: board block name present"
  [[ "$P" != *"READY_TASK_TITLE"* && "$P" != *"INPROGRESS_TASK_TITLE"* \
     && "$P" != *"REVIEW_TASK_TITLE"* && "$P" != *"BLOCKED_TASK_TITLE"* \
     && "$P" != *"BL_TITLE_1"* ]] \
    && ok "D13: no board task lines outside the brief" || fail "D13: board task line leaked"
  [[ "$P" != *"DONE_TASK_TITLE_HIDDEN"* && "$P" != *"CANCELLED_TASK_TITLE_HIDDEN"* \
     && "$P" != *"claim_owner"* && "$P" != *"plan_item_id"* ]] \
    && ok "D13: no Done/Cancelled/repr leakage" || fail "D13: board dump leaked"
  [[ "$P" != *"Ready=1"* ]] \
    && ok "D13: no counts summary line" || fail "D13: counts summary present"
  # D13: the direct mail block is GONE — no section, no freshness note, no wrapper.
  [[ "$P" != *"Утренняя почта"* && "$P" != *"no fresh mail brief"* \
     && "$P" != *"untrusted-source"* ]] \
    && ok "D13: no direct mail block / wrapper in packet" || fail "D13: mail block present"
  # D13: synth fallback wording — project-context inference, not a board feed.
  [[ "$P" == *"действия только из состояния проектов и последних следов проектов"* ]] \
    && ok "D13: v13 missing-brief fallback wording" || fail "D13: fallback wording stale"
  [[ "$P" != *"действия только из доски"* ]] \
    && ok "D13: old board-referencing fallback gone" || fail "D13: old fallback wording present"

  # D7 log gist
  [[ "$P" == *"FIRST_PARA_MARKER"* && "$P" != *"SECOND_PARA_MARKER"* ]] \
    && ok "D7: entry gist = first paragraph only" || fail "D7: gist absorbed 2nd paragraph"
  [[ "$P" != *"SESSION_JUNK_MARKER"* && "$P" != *"HUBSESSION_JUNK_MARKER"* ]] \
    && ok "D7: session lines excluded" || fail "D7: session line leaked"
  [[ "$P" != *"DIGEST_RECEIPT_MARKER"* && "$P" != *"HUBDIGEST_RECEIPT_MARKER"* ]] \
    && ok "D7: digest receipts excluded" || fail "D7: digest receipt leaked"
  [[ "$P" == *"HUB_MEANINGFUL_MARKER"* && "$P" == *"MEANINGFUL_DECISION_MARKER"* ]] \
    && ok "D7: meaningful entries kept" || fail "D7: meaningful entry dropped"

  # D7b per-project guarantee
  [[ "$P" == *"alpha-proj: [2026-07-11]"* ]] \
    && ok "D7b: live project latest header (date once)" || fail "D7b: project header wrong"
  [[ "$P" == *"ghost-proj: (записей нет)"* ]] \
    && ok "D7b: missing-log project degraded line" || fail "D7b: missing-log line wrong"
  [[ "$P" != *"sleepy"* ]] && ok "D7b: non-live project skipped" || fail "D7b: non-live leaked"

  # D8 daily research gone
  [[ "$P" != *"Daily research"* ]] && ok "D8: daily-research block removed" || fail "D8: daily-research present"

  # D9 money priority: same-day digest.txt beats same-day JSON
  [[ "$P" == *"MONEY_DIGEST_TXT_MARKER"* ]] \
    && ok "D9: same-day digest.txt wins" || fail "D9: digest.txt did not win"
  [[ "$P" != *"MONEY_FLOW_MARKER"* ]] \
    && ok "D9: JSON not rendered when digest.txt present" || fail "D9: JSON leaked over digest.txt"

  # D10 escalations + state
  [[ "$P" == *"OPEN_ESC_MARKER"* ]] && ok "D10: open escalation shown" || fail "D10: open escalation missing"
  [[ "$P" != *"TEMPLATE_COMMENT_MARKER"* && "$P" != *"OLD_RESOLVED_MARKER"* ]] \
    && ok "D10: template comments + resolved stripped" || fail "D10: template/resolved leaked"
  [[ "$P" == *"STATE_END_MARKER_KEEP_ME"* && "$P" != *"обрезано"* ]] \
    && ok "D10: state.md passed whole (no cap)" || fail "D10: state.md truncated"

  # D11 missing brief
  [[ "$P" == *"утренний бриф за сегодня не создан — инцидент в работе"* ]] \
    && ok "D11: missing-brief notice line" || fail "D11: missing-brief notice absent"
  grep -q 'morning brief missing — digest built without it' "$HUB/log.md" \
    && ok "D11: log.md gets the missing-brief line" || fail "D11: log.md line not appended"
fi

# D11 dedup: second run must not append a second line for the same date
run_digest "$HUB" >/dev/null
N=$(grep -c 'morning brief missing — digest built without it' "$HUB/log.md")
[[ "$N" == "1" ]] && ok "D11: missing-brief log line deduped per date" || fail "D11: log line duplicated ($N)"

# =============== Case 2: brief PRESENT → no notice, no historical text ========
HUB2="$TMP/hub2"; mk_hub "$HUB2"
cp "$HUB/registry.md" "$HUB2/registry.md"; ln -s "$PROJ/knowledge" "$HUB2/projects/alpha-proj"
mkdir -p "$TMP/ghost2/knowledge"; ln -s "$TMP/ghost2/knowledge" "$HUB2/projects/ghost-proj"
cat > "$HUB2/briefs/$DAY.md" <<'EOF'
TODAY_BRIEF_MARKER свежий утренний бриф.

🔥 3 действия
1. BRIEF_TASK_PROSE_MARKER задача дня из доски, курированная брифом.
EOF
echo "YESTERDAY_BRIEF_MARKER вчерашний бриф." > "$HUB2/briefs/2026-07-10.md"
P2=$(run_digest "$HUB2")
[[ "$P2" == *"TODAY_BRIEF_MARKER"* ]] && ok "D11: today's brief present" || fail "D11: today's brief missing"
[[ "$P2" != *"YESTERDAY_BRIEF_MARKER"* && "$P2" != *"инцидент в работе"* ]] \
  && ok "D11: no historical brief / no notice when today's brief exists" \
  || fail "D11: historical brief or notice leaked with a present brief"
# AC-1 (v14): task/action PROSE inside the brief is expected and permitted —
# that is exactly how tasks arrive under D13.
[[ "$P2" == *"BRIEF_TASK_PROSE_MARKER"* ]] \
  && ok "D13: task prose inside the brief permitted" || fail "D13: brief task prose dropped"

# =============== Case 3: money JSON fallback (no digest.txt) ==================
HUB3="$TMP/hub3"; mk_hub "$HUB3"
cp "$HUB/registry.md" "$HUB3/registry.md"; ln -s "$PROJ/knowledge" "$HUB3/projects/alpha-proj"
mkdir -p "$TMP/ghost3/knowledge"; ln -s "$TMP/ghost3/knowledge" "$HUB3/projects/ghost-proj"
cp "$HUB/.orchestrator/money-radar-$DAY.json" "$HUB3/.orchestrator/money-radar-$DAY.json"
P3=$(run_digest "$HUB3")
[[ "$P3" == *"MONEY_JSON_RANKED_TITLE"* && "$P3" == *"MONEY_JSON_NOGO_TITLE"* && "$P3" == *"low"* ]] \
  && ok "D9: JSON render shows ranked/nogo/confidence" || fail "D9: JSON ranked/nogo/confidence missing"
[[ "$P3" == *"MONEY_FLOW_MARKER"* && "$P3" == *"RISK_MARKER"* ]] \
  && ok "D9: JSON candidate prose fields rendered" || fail "D9: candidate prose fields missing"
[[ "$P3" != *"money-secret-url"* && "$P3" != *"_links_withheld"* && "$P3" != *"telegram_delivered"* ]] \
  && ok "D9: URLs/scores/run-metadata dropped" || fail "D9: metadata/URLs leaked"

# =============== Case 4: registry unavailable degradation (D7b) ==============
HUB4="$TMP/hub4"; mk_hub "$HUB4"
mkdir -p "$HUB4/registry.md"   # a directory where a file is expected → unreadable
P4=$(run_digest "$HUB4")
[[ "$P4" == *"(registry unavailable)"* ]] \
  && ok "D7b: unreadable registry degrades to one line" || fail "D7b: registry-unavailable line missing"
[[ -n "$P4" ]] && ok "D7b: digest still produced with bad registry" || fail "D7b: bad registry blocked digest"

# =============== Case 5: evening path unchanged (AC-8) =======================
mkdir -p "$TMP/hub5/personal" "$TMP/hub5/briefs"; ln -s "$SRC_BIN" "$TMP/hub5/bin"
: > "$TMP/hub5/personal/.secrets"
cat > "$TMP/hub5/briefs/$DAY.md" <<'EOF'
## Morning brief
morning text
## Retro (20:00)
EVENING_RETRO_MARKER ретро дня.
EOF
PE=$(env KB_HUB="$TMP/hub5" KB_VEPOL_DEV="$PROJ" KB_DIGEST_PROMPT_ONLY=1 \
     "$SRC_BIN/kb-morning-digest" --date "$DAY" --period evening 2>/dev/null)
[[ "$PE" == *"EVENING_RETRO_MARKER"* ]] && ok "AC-8: evening retro still voiced" || fail "AC-8: evening retro missing"
[[ "$PE" != *"Проекты: последний след"* && "$PE" != *"READY_TASK_TITLE"* ]] \
  && ok "AC-8: morning-only blocks absent from evening" || fail "AC-8: morning block leaked into evening"

# =============== Case 6: day-file untrusted markers stripped (AC-14) =========
# Fixtures follow the strip_untrusted_spans() contract matrix: (i) paired span →
# content removed, placeholder kept; (ii) orphan CLOSING marker → dropped alone,
# surrounding text kept; (iii) unclosed opening → tail dropped. In every case the
# packet must contain zero untrusted-source markers.
HUB6="$TMP/hub6"; mk_hub "$HUB6"
cp "$HUB/registry.md" "$HUB6/registry.md"; ln -s "$PROJ/knowledge" "$HUB6/projects/alpha-proj"
mkdir -p "$TMP/ghost6/knowledge"; ln -s "$TMP/ghost6/knowledge" "$HUB6/projects/ghost-proj"
cat > "$HUB6/briefs/$DAY.md" <<'EOF'
TRUSTED_HEAD_MARKER начало брифа.
<untrusted-source-abc123>
PAIRED_SPAN_SECRET сырое письмо внутри парного блока.
</untrusted-source-abc123>
TRUSTED_MID_MARKER середина брифа.
</untrusted-source-orphan>
TRUSTED_AFTER_ORPHAN_MARKER текст после сиротской закрывашки.
<untrusted-source-unclosed>
UNCLOSED_TAIL_SECRET хвост после незакрытого маркера.
EOF
P6=$(run_digest "$HUB6")
[[ "$P6" == *"TRUSTED_HEAD_MARKER"* && "$P6" == *"TRUSTED_MID_MARKER"* \
   && "$P6" == *"TRUSTED_AFTER_ORPHAN_MARKER"* ]] \
  && ok "AC-14: trusted brief text survives the strip" || fail "AC-14: trusted text lost"
[[ "$P6" != *"PAIRED_SPAN_SECRET"* ]] \
  && ok "AC-14: paired span content removed" || fail "AC-14: paired span leaked"
[[ "$P6" != *"UNCLOSED_TAIL_SECRET"* ]] \
  && ok "AC-14: unclosed-marker tail dropped" || fail "AC-14: unclosed tail leaked"
[[ "$P6" != *"untrusted-source"* ]] \
  && ok "AC-14: zero untrusted-source markers in packet" || fail "AC-14: marker leaked"
[[ "$P6" == *"(untrusted block removed)"* ]] \
  && ok "AC-14: placeholder marks removed spans" || fail "AC-14: placeholder missing"

echo; echo "PASS=$PASS FAIL=$FAIL"; [[ "$FAIL" == "0" ]]
