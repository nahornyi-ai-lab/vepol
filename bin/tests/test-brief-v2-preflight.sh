#!/usr/bin/env bash
# Tests for Daily brief v2 control surface.
#
# Spec: daily-brief-v2-control-surface-2026-06-25.md
#
# Usage:
#   bash ~/knowledge/bin/tests/test-brief-v2-preflight.sh
#   KB_BRIEF_V2_SRC_BIN=<dir> bash ...   # test a copied distribution

set -uo pipefail

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

SRC_BIN="${KB_BRIEF_V2_SRC_BIN:-$HOME/knowledge/bin}"
HELPER="$SRC_BIN/kb-brief-preflight"
BRIEF="$SRC_BIN/kb-brief"
PY=python3

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

write_registry() {
  local hub="$1" slug="$2" status="$3" project="$4" desc="$5"
  cat > "$hub/registry.md" <<EOF
# Registry fixture

| slug | статус | категория | parent | путь | описание |
|---|---|---|---|---|---|
| $slug | $status | personal | hub | \`$project\` | $desc |
EOF
}

make_hub() {
  local name="$1"
  local hub="$TMP/$name/hub"
  mkdir -p "$hub"/{bin,logs,briefs,daily,personal/daily-inbox}
  cat > "$hub/personal/.secrets" <<'EOF'
TELEGRAM_TOKEN=test-token
TELEGRAM_CHAT_ID=42
EOF
  echo "language: ru" > "$hub/personal/profile.yaml"
  if [[ -f "$SRC_BIN/_kb_profile.py" ]]; then
    cp "$SRC_BIN/_kb_profile.py" "$hub/bin/_kb_profile.py"
  fi
  cat > "$hub/bin/kb-idea" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$hub/bin/kb-idea"
  echo "$hub"
}

make_project() {
  local root="$1" canonical_log="$2" child_log="$3" backlog="$4" child_state="${5:-}"
  mkdir -p "$root/knowledge" "$root/casanueva/knowledge"
  cat > "$root/knowledge/state.md" <<'EOF'
# State

Rental is not current here yet.
EOF
  cat > "$root/knowledge/log.md" <<EOF
# Log

## [$canonical_log] older canonical note
Canonical state before update.
EOF
  cat > "$root/knowledge/backlog.md" <<EOF
# Backlog

## Open

$backlog
EOF
  cat > "$root/casanueva/knowledge/log.md" <<EOF
# Log

## [$child_log] child update
$child_state
EOF
  cat > "$root/casanueva/knowledge/state.md" <<EOF
# State

$child_state
EOF
}

run_preflight_json() {
  local hub="$1"
  if [[ ! -x "$HELPER" ]]; then
    echo '{}'
    return 127
  fi
  KB_HUB="$hub" "$HELPER"
}

assert_json_has_warning() {
  local json="$1" label="$2"
  JSON_PAYLOAD="$json" "$PY" - <<'PY'
import json, os
data = json.loads(os.environ["JSON_PAYLOAD"])
warnings = data.get("warnings", [])
do_not = data.get("do_not_surface", [])
ok = any(w.get("type") == "child_split_brain_stale_backlog" for w in warnings)
ok = ok and bool(do_not)
raise SystemExit(0 if ok else 1)
PY
  [[ "$?" == "0" ]] && ok "$label" || fail "$label"
}

assert_json_no_stale_warning() {
  local json="$1" label="$2"
  JSON_PAYLOAD="$json" "$PY" - <<'PY'
import json, os
data = json.loads(os.environ["JSON_PAYLOAD"])
warnings = data.get("warnings", [])
ok = not any(w.get("type") == "child_split_brain_stale_backlog" for w in warnings)
raise SystemExit(0 if ok else 1)
PY
  [[ "$?" == "0" ]] && ok "$label" || fail "$label"
}

echo "=== P1: kb-brief-preflight detects RU split-brain stale rental ==="
HUB=$(make_hub ru-case)
PROJECT="$TMP/ru-case/Family"
make_project "$PROJECT" "2026-06-23" "2026-06-24" \
  "- [ ] César — дожать договор аренды C/ Saragossa 5 — plan_item_id: stale-rental" \
  "договор подписали, переезжаем, перевозим вещи понемногу, заказали Starlink."
write_registry "$HUB" family live "$PROJECT" "Family"
BEFORE="$TMP/ru-before.txt"
AFTER="$TMP/ru-after.txt"
find "$PROJECT" -type f -exec shasum -a 256 {} \; | sort > "$BEFORE"
RU_JSON=$(run_preflight_json "$HUB")
RC=$?
if [[ "$RC" == "0" ]]; then
  assert_json_has_warning "$RU_JSON" "P1: RU fixture emits stale split-brain warning + do_not_surface"
else
  fail "P1: kb-brief-preflight executable exists and runs"
fi
find "$PROJECT" -type f -exec shasum -a 256 {} \; | sort > "$AFTER"
cmp -s "$BEFORE" "$AFTER" && ok "P1: preflight performs no project-KB writes" || fail "P1: preflight changed project files"

echo "=== P2: kb-brief-preflight detects EN split-brain stale rental ==="
HUB=$(make_hub en-case)
PROJECT="$TMP/en-case/Family"
make_project "$PROJECT" "2026-06-23" "2026-06-24" \
  "- [ ] Secure/sign rental contract for C/ Saragossa 5 — plan_item_id: stale-rental" \
  "Lease signed, move-in started, belongings are moving, Starlink ordered."
write_registry "$HUB" family live "$PROJECT" "Family"
EN_JSON=$(run_preflight_json "$HUB")
[[ "$?" == "0" ]] && assert_json_has_warning "$EN_JSON" "P2: EN fixture emits stale split-brain warning + do_not_surface" || fail "P2: kb-brief-preflight executable exists and runs"

echo "=== P3: older child wiki does not warn ==="
HUB=$(make_hub older-child)
PROJECT="$TMP/older-child/Family"
make_project "$PROJECT" "2026-06-24" "2026-06-22" \
  "- [ ] Secure/sign rental contract for C/ Saragossa 5 — plan_item_id: stale-rental" \
  "Lease signed, move-in started, Starlink ordered."
write_registry "$HUB" family live "$PROJECT" "Family"
OLDER_JSON=$(run_preflight_json "$HUB")
[[ "$?" == "0" ]] && assert_json_no_stale_warning "$OLDER_JSON" "P3: older child fixture has no stale split-brain warning" || fail "P3: kb-brief-preflight executable exists and runs"

echo "=== P4: documented 5-column demo registry layout parses ==="
HUB=$(make_hub demo-layout)
PROJECT="$TMP/demo-layout/Family"
make_project "$PROJECT" "2026-06-23" "2026-06-24" \
  "- [ ] Secure/sign rental contract for C/ Saragossa 5 — plan_item_id: stale-rental" \
  "Lease signed, move-in started, Starlink ordered."
cat > "$HUB/registry.md" <<EOF
# Registry fixture (documented demo/template layout, no parent column)

| slug | status | category | path | description |
|---|---|---|---|---|
| family | live | personal | \`$PROJECT\` | Family |
EOF
DEMO_JSON=$(run_preflight_json "$HUB")
if [[ "$?" == "0" ]]; then
  JSON_PAYLOAD="$DEMO_JSON" "$PY" - <<'PY'
import json, os
data = json.loads(os.environ["JSON_PAYLOAD"])
slugs = [p.get("slug") for p in data.get("projects", [])]
raise SystemExit(0 if "family" in slugs else 1)
PY
  [[ "$?" == "0" ]] && ok "P4: 5-column demo registry parses and finds project" || fail "P4: 5-column demo registry not parsed"
  assert_json_has_warning "$DEMO_JSON" "P4: demo-layout fixture still detects split-brain"
else
  fail "P4: kb-brief-preflight executable exists and runs"
fi

echo "=== B1: kb-brief injects preflight JSON and v2 prompt contract ==="
HUB=$(make_hub prompt)
PROJECT="$TMP/prompt/Family"
make_project "$PROJECT" "2026-06-23" "2026-06-24" \
  "- [ ] César — дожать договор аренды C/ Saragossa 5 — plan_item_id: stale-rental" \
  "договор подписали, переезжаем, заказали Starlink."
write_registry "$HUB" family live "$PROJECT" "Family"
cat > "$HUB/bin/kb-brief-preflight" <<'EOF'
#!/usr/bin/env bash
cat <<'JSON'
{
  "generated_at": "2026-06-25T07:30:00+02:00",
  "projects": [{"slug": "family", "child_knowledge_newer": true}],
  "warnings": [{"type": "child_split_brain_stale_backlog", "slug": "family", "summary": "stale rental"}],
  "changed_since_yesterday": ["Family: договор подписан, переезд начат, Starlink заказан."],
  "do_not_surface": [{"slug": "family", "reason": "lease already signed", "match": "дожать договор аренды"}]
}
JSON
EOF
chmod +x "$HUB/bin/kb-brief-preflight"
cat > "$HUB/bin/kb-orchestrator-run" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do LAST="\$a"; done
printf '%s' "\$LAST" > "$HUB/captured-prompt.txt"
cat <<'OUT'
| project | status |
---BRIEF---
☀️ Сегодня 2026-06-25 07:30

🆕 Изменилось со вчера
- Семья: договор подписан, переезд начат, Starlink заказан.

🔥 3 действия
1. Семья / жильё: собрать move-in evidence package.
   Готово: фото/видео, счётчики и дефекты сохранены.

⚠️ Проверить свежесть
- Есть child-KB split-brain по Family; не брифить старую задачу про договор.

📅 Жёсткие дедлайны недели
- 2026-06-26: проверить подключение Starlink.

🧘 Условие дня
Держать день коротким и практичным.
OUT
EOF
chmod +x "$HUB/bin/kb-orchestrator-run"
cat > "$HUB/bin/kb-channel-send-text" <<EOF
#!/usr/bin/env bash
echo "typed-sender-called" >> "$TMP/curl-called.txt"
exit 91
EOF
chmod +x "$HUB/bin/kb-channel-send-text"
FAKEBIN="$TMP/fakebin"; mkdir -p "$FAKEBIN"
cat > "$FAKEBIN/curl" <<EOF
#!/usr/bin/env bash
echo "curl-called" >> "$TMP/curl-called.txt"
exit 91
EOF
chmod +x "$FAKEBIN/curl"
OUT=$(PATH="$FAKEBIN:$PATH" KB_HUB="$HUB" KB_BRIEF_DRY=1 zsh "$BRIEF" 2>/dev/null)
RC=$?
PROMPT=$(cat "$HUB/captured-prompt.txt" 2>/dev/null || true)
[[ "$RC" == "0" ]] && ok "B1: kb-brief dry-run exits 0" || fail "B1: kb-brief dry-run rc=$RC"
[[ ! -f "$TMP/curl-called.txt" ]] && ok "B1: dry-run does not call Telegram curl" || fail "B1: dry-run invoked curl"
grep -q '"child_split_brain_stale_backlog"' <<<"$PROMPT" && ok "B1: prompt includes preflight JSON warning" || fail "B1: prompt missing preflight JSON warning"
grep -q '"do_not_surface"' <<<"$PROMPT" && ok "B1: prompt includes do_not_surface hints" || fail "B1: prompt missing do_not_surface"
grep -q "🆕 Изменилось со вчера" <<<"$PROMPT" && ok "B1: prompt requires changed-since-yesterday section" || fail "B1: missing changed section"
grep -q "🔥 Действия" <<<"$PROMPT" && ok "B1: prompt requires actions section" || fail "B1: missing actions section"
grep -q "Готово:" <<<"$PROMPT" && ok "B1: prompt requires localized completion label" || fail "B1: missing Готово label"
grep -Eqi "1-3|1–3|one to three|не больше тр[её]х|at most three" <<<"$PROMPT" && ok "B1: prompt contains 1-3 action cap" || fail "B1: no 1-3 action cap"
grep -qiE "backlog.*queue|backlog.*очеред|очеред.*backlog|not factual truth" <<<"$PROMPT" && ok "B1: prompt says backlog is queue, not truth" || fail "B1: no backlog precedence rule"
grep -q "plan_item_id" <<<"$PROMPT" && grep -q "claim_id" <<<"$PROMPT" && ok "B1: prompt bans raw internal ids" || fail "B1: missing internal-id ban"
grep -q "дожать договор аренды" <<<"$OUT" && fail "B1: dry-run brief surfaced stale rental task" || ok "B1: dry-run brief does not surface stale rental task"
grep -q "Готово:" <<<"$OUT" && ok "B1: dry-run brief has localized completion line" || fail "B1: dry-run brief lacks completion line"
grep -q "⚠️ Проверить свежесть" <<<"$OUT" && ok "B1: dry-run brief has freshness warning" || fail "B1: dry-run brief lacks freshness warning"

echo "=== D1: managed distribution hooks include preflight helper ==="
if [[ ! -f "$SRC_BIN/kb-seed-sync" ]]; then
  # Distribution hook is a hub tool; shipped trees don't carry it.
  ok "D1: kb-seed-sync not in this tree — distribution hook check skipped"
elif grep -q "kb-brief-preflight" "$SRC_BIN/kb-seed-sync"; then
  ok "D1: kb-seed-sync copies kb-brief-preflight"
else
  fail "D1: kb-seed-sync does not mention kb-brief-preflight"
fi
if [[ -d "$HOME/knowledge/orchestrator-seed/knowledge/bin" ]]; then
  [[ -f "$HOME/knowledge/orchestrator-seed/knowledge/bin/kb-brief-preflight" ]] \
    && ok "D1: orchestrator-seed has kb-brief-preflight" \
    || fail "D1: orchestrator-seed missing kb-brief-preflight"
fi
PREP_DIR="${VEPOL_PREP_DIR:-}"
if [[ -z "$PREP_DIR" && -d "$PWD/vepol-prep/bin" ]]; then
  PREP_DIR="$PWD/vepol-prep"
fi
if [[ -n "$PREP_DIR" && -d "$PREP_DIR/bin" ]]; then
  [[ -f "$PREP_DIR/bin/kb-brief-preflight" ]] \
    && ok "D1: vepol-prep has kb-brief-preflight" \
    || fail "D1: vepol-prep missing kb-brief-preflight"
fi

echo
echo "=== brief-v2 tests: $PASS passed, $FAIL failed ==="
[[ "$FAIL" == "0" ]]
