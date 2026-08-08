#!/usr/bin/env bash
# R6c AC1-AC3 focused tests: prompt-only coverage, mail cap semantics, and the
# private exact multipart planner/state machine. No LLM or real Telegram call.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MORNING_FIDELITY_SRC_BIN:-$HOME/knowledge/bin}"
BRIEF="$SRC_BIN/kb-brief"
MAIL_BLOCK="$SRC_BIN/kb-mail-block"
HELPER="$SRC_BIN/_kb_brief_delivery.py"
DAY=2026-07-13

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
has() { [[ "$1" == *"$2"* ]]; }

make_prompt_hub() {
  local hub="$TMP/hub-$1"
  mkdir -p "$hub"/{personal,briefs,logs,.orchestrator}
  : > "$hub/personal/.secrets"
  cat > "$hub/bin-kb-idea" <<'EOF'
#!/usr/bin/env bash
echo "ready idea marker"
EOF
  cat > "$hub/bin-kb-agenda" <<'EOF'
#!/usr/bin/env bash
echo '{"available":false,"overdue":[],"today":[],"upcoming":[],"errors":["synthetic_unavailable"]}'
EOF
  cat > "$hub/bin-kb-mail-block" <<'EOF'
#!/usr/bin/env bash
cat <<'MAIL'
MAIL morning, 2 item(s):
- [low/newsletter] Sender One — Subject One :: Summary one.
- [normal/receipt] Sender Two — Subject Two :: Summary two. (proposed: none)
MAIL
EOF
  cat > "$hub/bin-kb-brief-preflight" <<'EOF'
#!/usr/bin/env bash
echo '{"projects":[],"warnings":[],"changed_since_yesterday":[],"do_not_surface":[]}'
EOF
  cat > "$hub/bin-kb-orchestrator-run" <<'EOF'
#!/usr/bin/env bash
exit 99
EOF
  chmod +x "$hub"/bin-kb-*
  mkdir -p "$hub/bin"
  ln -s "$hub/bin-kb-idea" "$hub/bin/kb-idea"
  ln -s "$hub/bin-kb-agenda" "$hub/bin/kb-agenda"
  ln -s "$hub/bin-kb-mail-block" "$hub/bin/kb-mail-block"
  ln -s "$hub/bin-kb-brief-preflight" "$hub/bin/kb-brief-preflight"
  ln -s "$hub/bin-kb-orchestrator-run" "$hub/bin/kb-orchestrator-run"
  echo "$hub"
}

echo "=== AC1/AC2: prompt-only RU/EN coverage ==="
HUB=$(make_prompt_hub prompt)
RU=$(KB_HUB="$HUB" KB_LANG=ru KB_BRIEF_PROMPT_ONLY=1 KB_MAIL_NOW="${DAY}T06:15:00+02:00" \
  zsh "$BRIEF" 2>/dev/null)
EN=$(KB_HUB="$HUB" KB_LANG=en KB_BRIEF_PROMPT_ONLY=1 KB_MAIL_NOW="${DAY}T06:15:00+02:00" \
  zsh "$BRIEF" 2>/dev/null)

RU_HEADINGS=(
  "☀️ Сегодня" "🆕 Изменилось со вчера" "🧭 Проекты" "📅 Календарь"
  "📬 Почта" "💡 Идеи" "⚠️ Риски, свежесть и эскалации" "🔥 Действия"
  "❓ Решения от тебя" "🧘 Условие дня"
)
EN_HEADINGS=(
  "☀️ Today" "🆕 Changed since yesterday" "🧭 Projects" "📅 Calendar"
  "📬 Mail" "💡 Ideas" "⚠️ Risks, freshness, and escalations" "🔥 Actions"
  "❓ Decisions from you" "🧘 Day condition"
)
for heading in "${RU_HEADINGS[@]}"; do
  has "$RU" "$heading" && ok "AC1 RU prompt requires $heading" || fail "AC1 RU missing $heading"
done
for heading in "${EN_HEADINGS[@]}"; do
  has "$EN" "$heading" && ok "AC1 EN prompt requires $heading" || fail "AC1 EN missing $heading"
done
if has "$RU" "каждым из пяти" || has "$RU" "каждый логический"; then
  ok "AC1 prompt explicitly covers every logical input"
else
  fail "AC1 no every-logical-input requirement"
fi
if has "$RU" "полное предложение" || has "$RU" "complete sentence"; then
  ok "AC1 every heading requires a sentence"
else
  fail "AC1 no per-heading sentence rule"
fi
has "$RU" "Сегодня писем не было." && has "$RU" "Сегодня были такие письма:" \
  && has "$RU" "Почту сегодня проверить не удалось." \
  && ok "AC2 RU exact mail states" || fail "AC2 RU mail literals missing"
has "$EN" "There were no emails today." && has "$EN" "These emails arrived today:" \
  && has "$EN" "Mail could not be checked today." \
  && ok "AC2 EN exact mail states" || fail "AC2 EN mail literals missing"
has "$RU" "Sender One" && has "$RU" "Subject One" && has "$RU" "Sender Two" \
  && has "$RU" "Subject Two" && ok "AC2 injected low-priority mail remains in prompt" \
  || fail "AC2 injected mail items missing"
has "$RU" "каждое" && has "$RU" "действ" \
  && ok "AC2 prompt requires every item plus action state" \
  || fail "AC2 every-mail-item/action-state rule missing"
if has "$RU" "ноль действий" || has "$RU" "zero actions"; then
  ok "AC1 no-action case is explicit"
else
  fail "AC1 model may invent an action"
fi
if grep -Eq '<=[[:space:]]*\$?\{?BRIEF_CHAR_LIMIT|1500 Unicode|Surface genuinely due/urgent' <<<"$RU"; then
  fail "AC1/AC2 old content cap or urgency-only filter remains"
else
  ok "AC1/AC2 no content cap or urgency-only filter"
fi

echo "=== AC2: 24/25 mail cap modifier ==="
MAIL_HUB="$TMP/mail-hub"; mkdir -p "$MAIL_HUB/personal/mail/briefs" "$MAIL_HUB/personal"
echo "language: ru" > "$MAIL_HUB/personal/profile.yaml"
write_mail_env() {
  local count="$1"
  python3 - "$MAIL_HUB/personal/mail/briefs/${DAY}-morning.json" "$count" <<'PY'
import json, sys
path, count = sys.argv[1], int(sys.argv[2])
items = []
for i in range(count):
    items.append({
        "thread_ref": f"t-{i}", "message_ref": f"m-{i}",
        "date": "2026-07-13", "time": "06:00", "sender_label": f"Sender {i}",
        "subject": f"Subject {i}", "classification": "newsletter",
        "urgency": "low", "action_needed": False, "summary": "No action.",
        "proposed_actions": [{"type": "none", "summary": ""}],
        "privacy_flags": [], "confidence": "high",
    })
env = {
    "schema_version": "mail-brief/v1",
    "generated_at": "2026-07-13T06:15:00+02:00", "period": "morning",
    "window": {"from": "2026-07-12T06:15:00+02:00", "to": "2026-07-13T06:15:00+02:00"},
    "available": True, "account_ref": "primary", "watermark": "synthetic",
    "stats": {"messages_seen": count, "threads_seen": count,
              "threads_included": count, "threads_deferred": 0},
    "items": items, "errors": [],
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(env, f, ensure_ascii=False)
PY
  chmod 600 "$MAIL_HUB/personal/mail/briefs/${DAY}-morning.json"
}
write_mail_env 24
B24=$(KB_HUB="$MAIL_HUB" KB_LANG=ru KB_MAIL_NOW="${DAY}T06:15:00+02:00" \
  "$MAIL_BLOCK" --period morning 2>/dev/null)
write_mail_env 25
B25=$(KB_HUB="$MAIL_HUB" KB_LANG=ru KB_MAIL_NOW="${DAY}T06:15:00+02:00" \
  "$MAIL_BLOCK" --period morning 2>/dev/null)
[[ "$B24" != *"Показаны последние 25 писем"* ]] \
  && ok "AC2 24 items has no cap warning" || fail "AC2 false cap warning at 24"
COUNT25=$(grep -o "Показаны последние 25 писем; список может быть неполным\." <<<"$B25" | wc -l | tr -d ' ')
[[ "$COUNT25" == "1" ]] && ok "AC2 25 items has exact warning once" \
  || fail "AC2 25-item cap warning count=$COUNT25"

echo "=== AC3: pure split and private plan modes ==="
if [[ ! -f "$HELPER" ]]; then
  fail "AC3 delivery helper exists"
else
  python3 - "$HELPER" "$TMP" <<'PY' && ok "AC3 split/hash/mode contract" || fail "AC3 split/hash/mode contract"
import importlib.util, json, os, pathlib, sys
path, tmp = sys.argv[1], pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("brief_delivery", path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
text = ("абзац 👨‍👩‍👧‍👦 e\u0301 🇺🇦 строка\n\n" * 20).strip()
parts = mod.split_text(text, 45)
assert len(parts) > 3
assert "".join(parts) == text
assert all(mod.utf16_units(p) <= 45 for p in parts)
for cluster in ("👨‍👩‍👧‍👦", "e\u0301", "🇺🇦"):
    assert sum(p.count(cluster) for p in parts) == text.count(cluster)
for bad in ("0", "-1", "3501", "oops"):
    try: mod.validate_limit(bad)
    except ValueError: pass
    else: raise AssertionError(bad)
assert mod.validate_limit("1") == 1 and mod.validate_limit("3500") == 3500
try: mod.split_text("x" * 50, 10)
except ValueError: pass
else: raise AssertionError("oversized token was split")
private = tmp / "private"
sidecar = private / "brief-delivery-2026-07-13.json"
mod.atomic_json(sidecar, {"schema": "test"})
assert (private.stat().st_mode & 0o777) == 0o700
assert (sidecar.stat().st_mode & 0o777) == 0o600
PY

  echo "=== AC3: durable begin/finish/restart/reconcile state ==="
  STATE_DIR="$TMP/state"; mkdir -p "$STATE_DIR"
  DAY_FILE="$STATE_DIR/day.md"; SIDE="$STATE_DIR/private/brief-delivery-$DAY.json"
  cat > "$DAY_FILE" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

PART-ONE alpha beta gamma

PART-TWO delta epsilon zeta

PART-THREE eta theta omega
EOF
  python3 "$HELPER" plan --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --date "$DAY" --language ru --limit 35 >/dev/null 2>&1
  PRC=$?
  [[ "$PRC" == "0" && -s "$SIDE" ]] && ok "AC3 immutable plan created" \
    || fail "AC3 plan creation rc=$PRC"
  PART_FILE="$STATE_DIR/private/current-part.txt"
  BEGIN=$(python3 "$HELPER" begin --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --part-file "$PART_FILE" 2>/dev/null); BRC=$?
  [[ "$BRC" == "0" && "$BEGIN" == *'"status": "sending"'* && -s "$PART_FILE" ]] \
    && ok "AC3 begin persists sending before exposing part" \
    || fail "AC3 begin state rc=$BRC out=$BEGIN"
  PMODE=$(stat -f '%Lp' "$PART_FILE" 2>/dev/null || stat -c '%a' "$PART_FILE")
  [[ "$PMODE" == "600" ]] && ok "AC3 temporary part mode 0600" \
    || fail "AC3 part mode=$PMODE"
  python3 "$HELPER" finish --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --outcome success --message-id 101 --part-file "$PART_FILE" >/dev/null 2>&1
  FRC=$?
  [[ "$FRC" == "0" && ! -e "$PART_FILE" ]] && ok "AC3 success persists and removes temp part" \
    || fail "AC3 finish success rc=$FRC"
  BEGIN2=$(python3 "$HELPER" begin --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --part-file "$PART_FILE" 2>/dev/null); B2RC=$?
  [[ "$B2RC" == "0" && "$BEGIN2" == *'"index": 2'* ]] \
    && ok "AC3 retry skips verified part 1" || fail "AC3 did not advance to part 2"
  # A restart while part 2 is `sending` must freeze the delivery ambiguous.
  set +e
  RESTART=$(python3 "$HELPER" plan --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --date "$DAY" --language ru --limit 35 2>/dev/null)
  RRC=$?
  set -e
  [[ "$RRC" != "0" && "$RESTART" == *'"ambiguous"'* ]] \
    && ok "AC3 restart from sending becomes ambiguous" \
    || fail "AC3 sending restart rc=$RRC out=$RESTART"

  # This plan is already terminal ambiguous after restart. Body drift must not
  # rebuild or mutate that terminal evidence.
  printf '\nDRIFT\n' >> "$DAY_FILE"
  BEFORE_SIDE=$(shasum -a 256 "$SIDE" | awk '{print $1}')
  set +e
  python3 "$HELPER" plan --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --date "$DAY" --language ru --limit 35 >/dev/null 2>&1
  DRC=$?
  set -e
  AFTER_SIDE=$(shasum -a 256 "$SIDE" | awk '{print $1}')
  [[ "$DRC" != "0" && "$BEFORE_SIDE" == "$AFTER_SIDE" ]] \
    && ok "AC3 terminal ambiguous plan never recomputes" \
    || fail "AC3 drift recomputed/mutated sidecar"

  # When a sent prefix exists and the remaining plan drifts, the sidecar must
  # durably become ambiguous before returning. A process restart must not leave
  # a merely thrown error with retryable-looking persisted state.
  for drift_kind in body limit language; do
    DRIFT_DIR="$TMP/drift-$drift_kind"; mkdir -p "$DRIFT_DIR"
    DRIFT_DAY="$DRIFT_DIR/day.md"
    DRIFT_SIDE="$DRIFT_DIR/private/brief-delivery-$DAY.json"
    cat > "$DRIFT_DAY" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

FIRST BLOCK alpha beta

SECOND BLOCK gamma delta
EOF
    python3 "$HELPER" plan --day-file "$DRIFT_DAY" --sidecar "$DRIFT_SIDE" \
      --date "$DAY" --language ru --limit 30 >/dev/null 2>&1
    python3 "$HELPER" begin --day-file "$DRIFT_DAY" --sidecar "$DRIFT_SIDE" \
      --part-file "$DRIFT_DIR/private/part.txt" >/dev/null 2>&1
    python3 "$HELPER" finish --day-file "$DRIFT_DAY" --sidecar "$DRIFT_SIDE" \
      --outcome success --message-id 811 --part-file "$DRIFT_DIR/private/part.txt" >/dev/null 2>&1
    if [[ "$drift_kind" == body ]]; then
      printf '\nCHANGED AFTER SENT PREFIX\n' >> "$DRIFT_DAY"
      DRIFT_LIMIT=30
      DRIFT_LANGUAGE=ru
    elif [[ "$drift_kind" == language ]]; then
      DRIFT_LIMIT=30
      DRIFT_LANGUAGE=en
    else
      DRIFT_LIMIT=31
      DRIFT_LANGUAGE=ru
    fi
    set +e
    python3 "$HELPER" plan --day-file "$DRIFT_DAY" --sidecar "$DRIFT_SIDE" \
      --date "$DAY" --language "$DRIFT_LANGUAGE" --limit "$DRIFT_LIMIT" >/dev/null 2>&1
    DRIFT_RC=$?
    set -e
    DRIFT_STATUS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$DRIFT_SIDE")
    DRIFT_PARTS=$(python3 -c 'import json,sys; print(",".join(p["status"] for p in json.load(open(sys.argv[1]))["parts"]))' "$DRIFT_SIDE")
    [[ "$DRIFT_RC" != "0" && "$DRIFT_STATUS" == ambiguous && "$DRIFT_PARTS" == sent,ambiguous* ]] \
      && ok "AC3 $drift_kind drift after sent prefix persists ambiguous" \
      || fail "AC3 $drift_kind drift not durable rc=$DRIFT_RC status=$DRIFT_STATUS parts=$DRIFT_PARTS"
  done

  FAILED_DRIFT_DIR="$TMP/drift-failed"; mkdir -p "$FAILED_DRIFT_DIR"
  FAILED_DRIFT_DAY="$FAILED_DRIFT_DIR/day.md"
  FAILED_DRIFT_SIDE="$FAILED_DRIFT_DIR/private/brief-delivery-$DAY.json"
  cat > "$FAILED_DRIFT_DAY" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

FIRST SENT BLOCK alpha

SECOND REJECTED BLOCK beta
EOF
  python3 "$HELPER" plan --day-file "$FAILED_DRIFT_DAY" --sidecar "$FAILED_DRIFT_SIDE" \
    --date "$DAY" --language ru --limit 30 >/dev/null 2>&1
  python3 "$HELPER" begin --day-file "$FAILED_DRIFT_DAY" --sidecar "$FAILED_DRIFT_SIDE" \
    --part-file "$FAILED_DRIFT_DIR/private/part.txt" >/dev/null 2>&1
  python3 "$HELPER" finish --day-file "$FAILED_DRIFT_DAY" --sidecar "$FAILED_DRIFT_SIDE" \
    --outcome success --message-id 812 \
    --part-file "$FAILED_DRIFT_DIR/private/part.txt" >/dev/null 2>&1
  python3 "$HELPER" begin --day-file "$FAILED_DRIFT_DAY" --sidecar "$FAILED_DRIFT_SIDE" \
    --part-file "$FAILED_DRIFT_DIR/private/part.txt" >/dev/null 2>&1
  set +e
  python3 "$HELPER" finish --day-file "$FAILED_DRIFT_DAY" --sidecar "$FAILED_DRIFT_SIDE" \
    --outcome known_rejection --part-file "$FAILED_DRIFT_DIR/private/part.txt" >/dev/null 2>&1
  python3 "$HELPER" plan --day-file "$FAILED_DRIFT_DAY" --sidecar "$FAILED_DRIFT_SIDE" \
    --date "$DAY" --language en --limit 30 >/dev/null 2>&1
  FAILED_DRIFT_RC=$?
  set -e
  [[ "$FAILED_DRIFT_RC" != "0" \
     && $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$FAILED_DRIFT_SIDE") == ambiguous ]] \
    && ok "AC3 language drift after sent-prefix/failed persists ambiguous" \
    || fail "AC3 sent-prefix/failed drift remained retryable"

  # Even if the caller bypasses the typed transport, a non-positive or
  # non-integer message id can never be committed as sent evidence.
  BAD_ID_DIR="$TMP/bad-message-id"; mkdir -p "$BAD_ID_DIR"
  BAD_ID_DAY="$BAD_ID_DIR/day.md"
  BAD_ID_SIDE="$BAD_ID_DIR/private/brief-delivery-$DAY.json"
  cat > "$BAD_ID_DAY" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

MESSAGE ID DEFENCE
EOF
  python3 "$HELPER" plan --day-file "$BAD_ID_DAY" --sidecar "$BAD_ID_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  python3 "$HELPER" begin --day-file "$BAD_ID_DAY" --sidecar "$BAD_ID_SIDE" \
    --part-file "$BAD_ID_DIR/private/part.txt" >/dev/null 2>&1
  set +e
  python3 "$HELPER" finish --day-file "$BAD_ID_DAY" --sidecar "$BAD_ID_SIDE" \
    --outcome success --message-id not-an-int \
    --part-file "$BAD_ID_DIR/private/part.txt" >/dev/null 2>&1
  BAD_ID_RC=$?
  set -e
  [[ "$BAD_ID_RC" != "0" \
     && $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$BAD_ID_SIDE") == ambiguous \
     && $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["parts"][0]["message_id"])' "$BAD_ID_SIDE") == None ]] \
    && ok "AC3 invalid message_id persists ambiguous, never sent" \
    || fail "AC3 invalid message_id produced false sent evidence"

  # Corrupt attempted sidecars fail closed in place.
  printf '{broken' > "$SIDE"; chmod 600 "$SIDE"
  BROKEN_BEFORE=$(shasum -a 256 "$SIDE" | awk '{print $1}')
  set +e
  python3 "$HELPER" plan --day-file "$DAY_FILE" --sidecar "$SIDE" \
    --date "$DAY" --language ru --limit 35 >/dev/null 2>&1
  CRC=$?
  set -e
  BROKEN_AFTER=$(shasum -a 256 "$SIDE" | awk '{print $1}')
  [[ "$CRC" != "0" && "$BROKEN_BEFORE" == "$BROKEN_AFTER" ]] \
    && ok "AC3 corrupt sidecar fails closed without repair" \
    || fail "AC3 corrupt sidecar was replaced"

  # Completed sidecar is authoritative: stale day frontmatter is repaired with
  # no send, then rollback preflight becomes safe.
  DONE_DIR="$TMP/done"; mkdir -p "$DONE_DIR"
  DONE_DAY="$DONE_DIR/day.md"; DONE_SIDE="$DONE_DIR/private/brief-delivery-$DAY.json"
  cat > "$DONE_DAY" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

ONE COMPLETE PART
EOF
  python3 "$HELPER" plan --day-file "$DONE_DAY" --sidecar "$DONE_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  python3 "$HELPER" begin --day-file "$DONE_DAY" --sidecar "$DONE_SIDE" \
    --part-file "$DONE_DIR/private/part.txt" >/dev/null 2>&1
  python3 "$HELPER" finish --day-file "$DONE_DAY" --sidecar "$DONE_SIDE" \
    --outcome success --message-id 777 --part-file "$DONE_DIR/private/part.txt" >/dev/null 2>&1
  # Simulate crash window after sidecar completion but before frontmatter write.
  python3 - "$DONE_DAY" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); t = p.read_text();
t = t.replace("delivery: telegram_ok", "delivery: pending")
t = "\n".join(line for line in t.splitlines()
              if not line.startswith(("delivery_parts_sent:", "delivery_plan_sha256:"))) + "\n"
p.write_text(t)
PY
  python3 "$HELPER" plan --day-file "$DONE_DAY" --sidecar "$DONE_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  grep -q '^delivery: telegram_ok$' "$DONE_DAY" \
    && grep -q '^delivery_parts_sent: 1$' "$DONE_DAY" \
    && ok "AC3 completed sidecar reconciles stale frontmatter" \
    || fail "AC3 completed frontmatter not reconciled"
  python3 "$HELPER" rollback-preflight --day-file "$DONE_DAY" \
    --sidecar "$DONE_SIDE" >/dev/null 2>&1 \
    && ok "AC3 completed plan is rollback-preflight-safe" \
    || fail "AC3 completed rollback preflight failed"

  # A corrupted sent message id is invalid sidecar evidence even when its plan
  # hash remains intact (delivery outcomes are outside the immutable hash).
  BAD_SENT_DIR="$TMP/bad-sent-sidecar"; mkdir -p "$BAD_SENT_DIR/private"
  BAD_SENT_DAY="$BAD_SENT_DIR/day.md"
  BAD_SENT_SIDE="$BAD_SENT_DIR/private/brief-delivery-$DAY.json"
  cp "$DONE_DAY" "$BAD_SENT_DAY"; cp "$DONE_SIDE" "$BAD_SENT_SIDE"; chmod 600 "$BAD_SENT_SIDE"
  python3 - "$BAD_SENT_SIDE" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text())
d["parts"][0]["message_id"] = "777"
p.write_text(json.dumps(d))
PY
  BAD_SENT_BEFORE=$(shasum -a 256 "$BAD_SENT_SIDE" | awk '{print $1}')
  set +e
  python3 "$HELPER" plan --day-file "$BAD_SENT_DAY" --sidecar "$BAD_SENT_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  BAD_SENT_RC=$?
  set -e
  [[ "$BAD_SENT_RC" != "0" \
     && $(shasum -a 256 "$BAD_SENT_SIDE" | awk '{print $1}') == "$BAD_SENT_BEFORE" ]] \
    && ok "AC3 corrupt sent message_id sidecar fails closed" \
    || fail "AC3 corrupt sent message_id was accepted or rewritten"

  # Top-level status is outside the immutable plan hash, so a mismatch with
  # part states must still fail closed.
  SEM_DIR="$TMP/semantic"; mkdir -p "$SEM_DIR"
  SEM_DAY="$SEM_DIR/day.md"; SEM_SIDE="$SEM_DIR/private/brief-delivery-$DAY.json"
  cat > "$SEM_DAY" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

SEMANTIC SIDECAR BODY
EOF
  python3 "$HELPER" plan --day-file "$SEM_DAY" --sidecar "$SEM_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  python3 - "$SEM_SIDE" <<'PY'
import json, os, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text())
d["status"] = "completed"
p.write_text(json.dumps(d))
os.chmod(p, 0o600)
PY
  SEM_BEFORE=$(shasum -a 256 "$SEM_SIDE" | awk '{print $1}')
  set +e
  python3 "$HELPER" plan --day-file "$SEM_DAY" --sidecar "$SEM_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  SEM_RC=$?
  set -e
  [[ "$SEM_RC" != "0" && $(shasum -a 256 "$SEM_SIDE" | awk '{print $1}') == "$SEM_BEFORE" ]] \
    && ok "AC3 semantically inconsistent sidecar fails closed" \
    || fail "AC3 semantic sidecar corruption was accepted/replaced"

  # A legacy partial delivery without the immutable sidecar cannot infer which
  # bytes Telegram accepted and must not construct a new plan.
  LEG_DIR="$TMP/legacy-partial"; mkdir -p "$LEG_DIR"
  LEG_DAY="$LEG_DIR/day.md"; LEG_SIDE="$LEG_DIR/private/brief-delivery-$DAY.json"
  cat > "$LEG_DAY" <<'EOF'
---
date: 2026-07-13
delivery: telegram_failed
delivery_parts_sent: 1
---

LEGACY PARTIAL BODY
EOF
  set +e
  python3 "$HELPER" plan --day-file "$LEG_DAY" --sidecar "$LEG_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  LEG_RC=$?
  set -e
  [[ "$LEG_RC" != "0" && ! -e "$LEG_SIDE" ]] \
    && ok "AC3 legacy partial delivery refuses reconstruction" \
    || fail "AC3 legacy partial delivery built a new plan"

  # Rollback may discard a zero-attempt pending plan, but not an attempted
  # plan whose transport returned a proven rejection.
  RB_DIR="$TMP/rollback"; mkdir -p "$RB_DIR"
  RB_DAY="$RB_DIR/day.md"; RB_SIDE="$RB_DIR/private/brief-delivery-$DAY.json"
  cat > "$RB_DAY" <<'EOF'
---
date: 2026-07-13
delivery: pending
---

ROLLBACK BODY
EOF
  python3 "$HELPER" plan --day-file "$RB_DAY" --sidecar "$RB_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  python3 "$HELPER" rollback-preflight --day-file "$RB_DAY" --sidecar "$RB_SIDE" >/dev/null 2>&1
  [[ ! -e "$RB_SIDE" ]] && ok "AC3 rollback discards only zero-attempt pending plan" \
    || fail "AC3 rollback retained zero-attempt plan"
  python3 "$HELPER" plan --day-file "$RB_DAY" --sidecar "$RB_SIDE" \
    --date "$DAY" --language ru --limit 3500 >/dev/null 2>&1
  python3 "$HELPER" begin --day-file "$RB_DAY" --sidecar "$RB_SIDE" \
    --part-file "$RB_DIR/private/part.txt" >/dev/null 2>&1
  set +e
  python3 "$HELPER" finish --day-file "$RB_DAY" --sidecar "$RB_SIDE" \
    --outcome known_rejection --part-file "$RB_DIR/private/part.txt" >/dev/null 2>&1
  set -e
  set +e
  python3 "$HELPER" rollback-preflight --day-file "$RB_DAY" --sidecar "$RB_SIDE" >/dev/null 2>&1
  RB_RC=$?
  set -e
  [[ "$RB_RC" != "0" && -e "$RB_SIDE" ]] \
    && ok "AC3 rollback blocks attempted failed plan" \
    || fail "AC3 rollback discarded attempted plan"
fi

echo "=== AC3: generation-error notification uses the same durable sender ==="
if [[ ! -f "$HELPER" || ! -x "$SRC_BIN/kb-channel-send-text" ]] \
    || rg -q 'api\.telegram\.org.*sendMessage|send_tg\(\)' "$BRIEF"; then
  fail "AC3 error notification has no inline sender and uses durable typed delivery"
else
  make_error_hub() {
    local name="$1" hub="$TMP/error-$1"
    mkdir -p "$hub"/{bin,personal,briefs,logs,.orchestrator}
    printf 'language: ru\n' > "$hub/personal/profile.yaml"
    printf 'TELEGRAM_TOKEN=unused\nTELEGRAM_CHAT_ID=42\n' > "$hub/personal/.secrets"
    cat > "$hub/bin/kb-idea" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    cat > "$hub/bin/kb-agenda" <<'EOF'
#!/usr/bin/env bash
echo '{"available":true,"overdue":[],"today":[],"upcoming":[],"errors":[]}'
EOF
    cat > "$hub/bin/kb-mail-block" <<'EOF'
#!/usr/bin/env bash
echo 'MAIL morning, 0 item(s):'
EOF
    cat > "$hub/bin/kb-brief-preflight" <<'EOF'
#!/usr/bin/env bash
echo '{"projects":[],"warnings":[],"changed_since_yesterday":[],"do_not_surface":[]}'
EOF
    cat > "$hub/bin/kb-orchestrator-run" <<'EOF'
#!/usr/bin/env bash
echo synthetic-orchestrator-failure
exit 75
EOF
    cat > "$hub/bin/kb-channel-send-text" <<'EOF'
#!/usr/bin/env bash
set -u
root="${KB_HUB:?}"
mode=$(cat "$root/.mode")
printf '%s\n' "$mode" >> "$root/.calls"
if [[ -f "$root/.expected-token" ]]; then
  expected_token=$(<"$root/.expected-token")
  expected_chat=$(<"$root/.expected-chat")
  if [[ "${TELEGRAM_TOKEN:-}" != "$expected_token" \
     || "${TELEGRAM_CHAT_ID:-}" != "$expected_chat" ]]; then
    printf '{"outcome":"known_rejection","message_id":null,"reason":"credential_env_mismatch"}\n'
    exit 20
  fi
fi
case "$mode" in
  success) printf '{"outcome":"success","message_id":9001}\n'; exit 0 ;;
  known_rejection) printf '{"outcome":"known_rejection","message_id":null}\n'; exit 20 ;;
  interrupt) kill -TERM $$ ;;
  *) printf '{"outcome":"ambiguous","message_id":null}\n'; exit 21 ;;
esac
EOF
    chmod +x "$hub/bin/"*
    ln -s "$HELPER" "$hub/bin/_kb_brief_delivery.py"
    echo "$hub"
  }

  run_error_case() {
    local hub="$1" mode="$2"
    printf '%s\n' "$mode" > "$hub/.mode"
    KB_HUB="$hub" BRIEF_TIMEOUT=1 zsh "$BRIEF" >/dev/null 2>&1
    return $?
  }

  ERR_DAY=$(date +%Y-%m-%d)
  SUCCESS_HUB=$(make_error_hub success)
  set +e; run_error_case "$SUCCESS_HUB" success; SRC=$?; set -e
  SUCCESS_SIDE="$SUCCESS_HUB/.orchestrator/brief-error-delivery-$ERR_DAY.json"
  SUCCESS_CALLS=$(wc -l < "$SUCCESS_HUB/.calls" | tr -d ' ')
  set +e; run_error_case "$SUCCESS_HUB" success; SRRC=$?; set -e
  SUCCESS_CALLS_2=$(wc -l < "$SUCCESS_HUB/.calls" | tr -d ' ')
  [[ "$SRC" != "0" && "$SRRC" != "0" && "$SUCCESS_CALLS" == "1" \
     && "$SUCCESS_CALLS_2" == "1" \
     && $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$SUCCESS_SIDE") == completed ]] \
    && ok "AC3 successful error notice is delivered once" \
    || fail "AC3 successful error notice was repeated or lacked evidence"

  RETRY_HUB=$(make_error_hub retry)
  set +e; run_error_case "$RETRY_HUB" known_rejection; R1=$?; set -e
  printf 'success\n' > "$RETRY_HUB/.mode"
  set +e; run_error_case "$RETRY_HUB" success; R2=$?; set -e
  [[ "$R1" != "0" && "$R2" != "0" \
     && $(wc -l < "$RETRY_HUB/.calls" | tr -d ' ') == "2" ]] \
    && ok "AC3 proven-unsent error notice alone is retryable" \
    || fail "AC3 known rejection retry semantics wrong"

  for mode in timeout reset malformed; do
    AMB_HUB=$(make_error_hub "$mode")
    set +e; run_error_case "$AMB_HUB" "$mode"; A1=$?; set -e
    printf 'success\n' > "$AMB_HUB/.mode"
    set +e; run_error_case "$AMB_HUB" success; A2=$?; set -e
    AMB_SIDE="$AMB_HUB/.orchestrator/brief-error-delivery-$ERR_DAY.json"
    [[ "$A1" != "0" && "$A2" != "0" \
       && $(wc -l < "$AMB_HUB/.calls" | tr -d ' ') == "1" \
       && $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$AMB_SIDE") == ambiguous ]] \
      && ok "AC3 $mode error-notice outcome is terminal ambiguous" \
      || fail "AC3 $mode error-notice outcome retried or lost evidence"
  done

  INT_HUB=$(make_error_hub interrupt)
  set +e; run_error_case "$INT_HUB" interrupt; I1=$?; set -e
  printf 'success\n' > "$INT_HUB/.mode"
  set +e; run_error_case "$INT_HUB" success; I2=$?; set -e
  INT_SIDE="$INT_HUB/.orchestrator/brief-error-delivery-$ERR_DAY.json"
  [[ "$I1" != "0" && "$I2" != "0" \
     && $(wc -l < "$INT_HUB/.calls" | tr -d ' ') == "1" \
     && $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$INT_SIDE") == ambiguous ]] \
    && ok "AC3 interrupted error notice resolves sending to ambiguous" \
    || fail "AC3 interrupted error notice was automatically retried"

  echo "=== AC3: real secret-file syntax reaches the typed sender ==="
  for style in bare export-space export-tab; do
    SECRET_HUB=$(make_error_hub "secret-$style")
    printf 'fixture-%s-token\n' "$style" > "$SECRET_HUB/.expected-token"
    printf '424242\n' > "$SECRET_HUB/.expected-chat"
    case "$style" in
      bare)
        printf 'TELEGRAM_TOKEN=fixture-%s-token\nTELEGRAM_CHAT_ID=424242\n' \
          "$style" > "$SECRET_HUB/personal/.secrets"
        ;;
      export-space)
        printf 'export TELEGRAM_TOKEN=fixture-%s-token\nexport TELEGRAM_CHAT_ID=424242\n' \
          "$style" > "$SECRET_HUB/personal/.secrets"
        ;;
      export-tab)
        printf 'export\tTELEGRAM_TOKEN=fixture-%s-token\nexport\tTELEGRAM_CHAT_ID=424242\n' \
          "$style" > "$SECRET_HUB/personal/.secrets"
        ;;
    esac
    printf 'success\n' > "$SECRET_HUB/.mode"
    set +e
    KB_HUB="$SECRET_HUB" BRIEF_TIMEOUT=1 zsh "$BRIEF" \
      >"$SECRET_HUB/stdout" 2>"$SECRET_HUB/stderr"
    SECRET_RC=$?
    set -e
    SECRET_SIDE="$SECRET_HUB/.orchestrator/brief-error-delivery-$ERR_DAY.json"
    SECRET_STATUS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' \
      "$SECRET_SIDE" 2>/dev/null || true)
    [[ "$SECRET_RC" != "0" && "$SECRET_STATUS" == completed \
       && $(wc -l < "$SECRET_HUB/.calls" | tr -d ' ') == "1" ]] \
      && ok "AC3 $style secret syntax reaches sender environment" \
      || fail "AC3 $style secret syntax did not reach sender environment"
    if rg -q "fixture-$style-token|424242" \
        "$SECRET_HUB/stdout" "$SECRET_HUB/stderr" \
        "$SECRET_HUB/logs/brief.log" "$SECRET_SIDE" 2>/dev/null; then
      fail "AC3 $style credential leaked to delivery evidence"
    else
      ok "AC3 $style credential remains absent from output and evidence"
    fi
  done
fi

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
