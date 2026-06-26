#!/usr/bin/env bash
# Tests for calendar-backed follow-up reminders v1.
#
# Spec: knowledge/decisions/calendar-backed-followups-v1-2026-06-25.md
#   (spec-contract:sha256:16543b12f3249e6f338657aa6f361d4071311fb831466f2bd228b41d8174d700)
#
# These tests run with FAKE calendar adapters only. They never touch the real
# Google Calendar, the real ledger, or a live LLM/MCP host (AC9). Isolation is
# via KB_HUB pointed at a temp dir; the fake calendar backend is selected via
# KB_CALENDAR_FAKE_DIR.
#
# Usage:
#   bash ~/knowledge/bin/tests/test-calendar-followups.sh
#   KB_CALENDAR_SRC_BIN=<dir> bash ...   # test a copied/seed distribution

set -uo pipefail   # not -e: a failed assertion must not abort the harness

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

SRC_BIN="${KB_CALENDAR_SRC_BIN:-$HOME/knowledge/bin}"
PY=python3

ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

FUP="$SRC_BIN/kb-followup"
AGENDA="$SRC_BIN/kb-agenda"
TASK="$SRC_BIN/kb-task"

# ---- shared fixtures -------------------------------------------------------

# Build an isolated hub. Calendar scripts resolve the ledger via KB_HUB, so a
# temp hub fully isolates state; the scripts themselves are run straight from
# SRC_BIN (they resolve their own packages). Only kb-board — which kb-task
# invokes as "$KB_HUB/bin/kb-board" — is symlinked so its .resolve() finds the
# real _kb_board package.
make_hub() {
  local hub="$TMP/$1/hub"
  mkdir -p "$hub"/bin "$hub"/personal "$hub"/logs "$hub"/briefs "$hub"/daily
  ln -sf "$SRC_BIN/kb-board" "$hub/bin/kb-board"
  echo "language: en" > "$hub/personal/profile.yaml"
  # minimal valid board so kb-task's `kb-board append` has sections to write to
  cat > "$hub/backlog.md" <<'EOF'
# Backlog

## Backlog

## Ready

## In Progress

## Blocked

## Review

## Done

## Cancelled
EOF
  echo "$hub"
}

# Make a fresh fake-calendar control dir. mode in {ok,fail,uncertain}.
make_fake() {
  local dir="$TMP/$1/fake"
  mkdir -p "$dir"
  echo "${2:-ok}" > "$dir/mode"
  echo "$dir"
}

# count create calls the fake recorded (0 if file absent)
create_calls() {
  local dir="$1"
  [[ -f "$dir/create-calls.jsonl" ]] && grep -c . "$dir/create-calls.jsonl" || echo 0
}
# count distinct events the fake "server" actually stored
distinct_events() {
  local dir="$1"
  [[ -f "$dir/store.jsonl" ]] || { echo 0; return; }
  "$PY" - "$dir/store.jsonl" <<'PY'
import sys, json
keys=set()
for line in open(sys.argv[1]):
    line=line.strip()
    if not line: continue
    keys.add(json.loads(line).get("idempotency_key"))
print(len(keys))
PY
}

ledger_status() {  # ledger_status <hub> <id>
  "$PY" - "$1/personal/calendar-followups.jsonl" "$2" <<'PY'
import sys, json
path, fid = sys.argv[1], sys.argv[2]
state=None
try:
    for line in open(path):
        line=line.strip()
        if not line: continue
        r=json.loads(line)
        if r.get("id")==fid:
            state=r
except FileNotFoundError:
    pass
print((state or {}).get("status","MISSING"))
PY
}

# =============================================================================
echo "== AC1: propose makes zero calendar calls =="
# -----------------------------------------------------------------------------
HUB=$(make_hub ac1); FAKE=$(make_fake ac1 ok)
OUT=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" propose \
  --summary "Check daily brief reads calendar" \
  --when "завтра проверить" --now "2026-06-25T08:00:00+02:00" \
  --project demo-project --kind check --source "chat:test" \
  --reason "owner asked" --json 2>"$TMP/ac1.err")
RC=$?
[[ "$RC" == "0" ]] && ok "AC1: propose exits 0" || { fail "AC1: propose rc=$RC ($(cat "$TMP/ac1.err"))"; }
[[ "$(create_calls "$FAKE")" == "0" ]] && ok "AC1: zero calendar create calls on propose" || fail "AC1: propose made $(create_calls "$FAKE") create calls"
echo "$OUT" | grep -q '"status": *"proposed"' && ok "AC1: ledger record is proposed" || fail "AC1: no proposed record (out: $OUT)"
ID1=$(echo "$OUT" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["id"])' 2>/dev/null || true)
[[ -n "$ID1" ]] && ok "AC1: propose returns an id ($ID1)" || fail "AC1: no id in propose output"

# =============================================================================
echo "== AC4: deterministic RU/EN date parsing =="
# -----------------------------------------------------------------------------
parse_start() {  # parse_start <hub> <fake> <when>
  KB_HUB="$1" KB_CALENDAR_FAKE_DIR="$2" "$FUP" propose \
    --summary "x" --when "$3" --now "2026-06-25T08:00:00+02:00" \
    --source "chat:test" --json 2>/dev/null \
    | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["start"])' 2>/dev/null
}
HUB=$(make_hub ac4); FAKE=$(make_fake ac4 ok)
declare -A EXPECT=(
  ["завтра"]="2026-06-26T09:00:00+02:00"
  ["через 10 дней"]="2026-07-05T09:00:00+02:00"
  ["tomorrow"]="2026-06-26T09:00:00+02:00"
  ["in 10 days"]="2026-07-05T09:00:00+02:00"
)
for phrase in "завтра" "через 10 дней" "tomorrow" "in 10 days"; do
  got=$(parse_start "$HUB" "$FAKE" "$phrase")
  [[ "$got" == "${EXPECT[$phrase]}" ]] && ok "AC4: '$phrase' -> ${EXPECT[$phrase]}" || fail "AC4: '$phrase' -> '$got' (want ${EXPECT[$phrase]})"
done
# fail closed (clean error, no traceback, no ledger record) on ambiguous /
# ISO-shaped-but-invalid dates
HUBX=$(make_hub ac4x); FAKEX=$(make_fake ac4x ok)
for bad in "2026-06-31" "2026-02-29" "soon someday"; do
  ERR=$(KB_HUB="$HUBX" KB_CALENDAR_FAKE_DIR="$FAKEX" "$FUP" propose --summary x \
    --when "$bad" --now "2026-06-25T08:00:00+02:00" --source "chat:test" 2>&1 >/dev/null)
  RC=$?
  if [[ "$RC" != "0" ]] && ! echo "$ERR" | grep -qi "Traceback"; then
    ok "AC4: '$bad' fails closed cleanly (rc=$RC, no traceback)"
  else
    fail "AC4: '$bad' did not fail cleanly (rc=$RC, err=$ERR)"
  fi
done
[[ ! -f "$HUBX/personal/calendar-followups.jsonl" ]] && ok "AC4: bad dates wrote no ledger record" || fail "AC4: ledger written for bad date"

# =============================================================================
echo "== AC2: explicit approval creates exactly one event =="
# -----------------------------------------------------------------------------
HUB=$(make_hub ac2); FAKE=$(make_fake ac2 ok)
ID=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" propose --summary "do x" \
  --when "tomorrow 09:00" --now "2026-06-25T08:00:00+02:00" --source "chat:test" --json \
  | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["id"])')
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" approve "$ID" --approval-source "chat:да, поставь" >"$TMP/ac2.out" 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "AC2: approve exits 0" || fail "AC2: approve rc=$RC ($(cat "$TMP/ac2.out"))"
[[ "$(create_calls "$FAKE")" == "1" ]] && ok "AC2: exactly one create call" || fail "AC2: $(create_calls "$FAKE") create calls (want 1)"
[[ "$(ledger_status "$HUB" "$ID")" == "approved" ]] && ok "AC2: ledger marks approved" || fail "AC2: ledger status $(ledger_status "$HUB" "$ID")"

# =============================================================================
echo "== AC3: duplicate approval is idempotent =="
# -----------------------------------------------------------------------------
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" approve "$ID" --approval-source "chat:again" >"$TMP/ac3.out" 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "AC3: re-approve exits 0" || fail "AC3: re-approve rc=$RC ($(cat "$TMP/ac3.out"))"
[[ "$(create_calls "$FAKE")" == "1" ]] && ok "AC3: still exactly one create call (no duplicate)" || fail "AC3: $(create_calls "$FAKE") create calls after re-approve"
[[ "$(distinct_events "$FAKE")" == "1" ]] && ok "AC3: exactly one distinct event on server" || fail "AC3: $(distinct_events "$FAKE") distinct events"

# =============================================================================
echo "== AC5: KB_CALENDAR_DISABLE=1 fails closed =="
# -----------------------------------------------------------------------------
HUB=$(make_hub ac5); FAKE=$(make_fake ac5 ok)
ID=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" propose --summary "y" \
  --when "tomorrow" --now "2026-06-25T08:00:00+02:00" --source "chat:test" --json \
  | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["id"])')
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" KB_CALENDAR_DISABLE=1 "$FUP" approve "$ID" --approval-source "chat:x" >"$TMP/ac5.out" 2>&1
RC=$?
[[ "$RC" != "0" ]] && ok "AC5: approve under disable exits nonzero" || fail "AC5: approve under disable exited 0"
[[ "$(create_calls "$FAKE")" == "0" ]] && ok "AC5: zero create calls under disable" || fail "AC5: $(create_calls "$FAKE") create calls under disable"
[[ "$(ledger_status "$HUB" "$ID")" != "approved" ]] && ok "AC5: proposal not marked approved" || fail "AC5: proposal wrongly approved under disable"
# kb-agenda disabled envelope
AG=$(KB_HUB="$HUB" KB_CALENDAR_DISABLE=1 "$AGENDA" --from today --days 8 --json --now "2026-06-26T08:00:00+02:00" 2>"$TMP/ac5ag.err")
RC=$?
echo "$AG" | "$PY" -c 'import sys,json;d=json.load(sys.stdin);assert d["available"] is False' 2>/dev/null \
  && ok "AC5: kb-agenda returns valid unavailable JSON (available=false)" \
  || fail "AC5: kb-agenda disabled envelope invalid (rc=$RC out=$AG err=$(cat "$TMP/ac5ag.err"))"

# =============================================================================
echo "== AC10: write failure / uncertain state does not duplicate events =="
# -----------------------------------------------------------------------------
# 10a: hard failure -> proposal stays retryable, no event id, no event stored
HUB=$(make_hub ac10a); FAKE=$(make_fake ac10a fail)
ID=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" propose --summary "z" \
  --when "tomorrow" --now "2026-06-25T08:00:00+02:00" --source "chat:test" --json \
  | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["id"])')
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" approve "$ID" --approval-source "chat:x" >/dev/null 2>&1
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" approve "$ID" --approval-source "chat:x" >/dev/null 2>&1
[[ "$(ledger_status "$HUB" "$ID")" != "approved" ]] && ok "AC10a: failed write leaves proposal unapproved" || fail "AC10a: proposal approved despite write failure"
[[ "$(distinct_events "$FAKE")" == "0" ]] && ok "AC10a: no event stored after failed writes" || fail "AC10a: $(distinct_events "$FAKE") events stored after failure"
# 10b: uncertain (create succeeded server-side, response lost) -> retry dedupes
HUB=$(make_hub ac10b); FAKE=$(make_fake ac10b uncertain)
ID=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" propose --summary "z2" \
  --when "tomorrow" --now "2026-06-25T08:00:00+02:00" --source "chat:test" --json \
  | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["id"])')
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" approve "$ID" --approval-source "chat:x" >/dev/null 2>&1
KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$FUP" approve "$ID" --approval-source "chat:x" >/dev/null 2>&1
calls=$(create_calls "$FAKE"); evs=$(distinct_events "$FAKE")
[[ "$calls" -ge "1" ]] && ok "AC10b: uncertain retry re-attempts via idempotency key (calls=$calls)" || fail "AC10b: no create attempts recorded"
[[ "$evs" == "1" ]] && ok "AC10b: at most one distinct event despite uncertain retries" || fail "AC10b: $evs distinct events (want 1, no blind duplicate)"
[[ "$(ledger_status "$HUB" "$ID")" != "approved" ]] && ok "AC10b: uncertain state not silently marked approved" || fail "AC10b: uncertain wrongly marked approved"

# =============================================================================
echo "== AC8: kb-agenda returns minimized agenda JSON =="
# -----------------------------------------------------------------------------
HUB=$(make_hub ac8); FAKE=$(make_fake ac8 ok)
# a rich calendar meeting the reader must minimize (attendees/emails/link/desc)
cat > "$FAKE/list-events.json" <<'JSON'
[
  {
    "id": "evt-meeting-1",
    "title": "Sync with client",
    "start": "2026-06-26T11:00:00+02:00",
    "end": "2026-06-26T11:30:00+02:00",
    "attendees": ["secret.person@example.com", "another@example.com"],
    "hangoutLink": "https://meet.google.com/abc-defg-hij",
    "description": "Private notes: budget 50000 EUR, password hunter2"
  }
]
JSON
AG=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" "$AGENDA" --from today --days 8 --json --now "2026-06-26T08:00:00+02:00" 2>"$TMP/ac8.err")
RC=$?
[[ "$RC" == "0" ]] && ok "AC8: kb-agenda exits 0" || fail "AC8: kb-agenda rc=$RC ($(cat "$TMP/ac8.err"))"
echo "$AG" | "$PY" -c 'import sys,json;json.load(sys.stdin)' 2>/dev/null && ok "AC8: kb-agenda emits valid JSON" || fail "AC8: invalid JSON ($AG)"
echo "$AG" | grep -q "Sync with client" && ok "AC8: meeting title present (minimized item)" || fail "AC8: meeting title missing"
if echo "$AG" | grep -Eq "example.com|meet.google.com|hunter2|budget 50000"; then
  fail "AC8: agenda leaked attendee email / link / description"
else
  ok "AC8: no attendee emails, meeting links, or full descriptions in agenda JSON"
fi

# =============================================================================
echo "== AC7: kb-task --calendar no longer writes directly =="
# -----------------------------------------------------------------------------
HUB=$(make_hub ac7); FAKE=$(make_fake ac7 ok)
# kb-task must NOT shell out to a live writer. Plant a tripwire `claude` on PATH
# that records any invocation; the gated path must never call it.
TRIP="$TMP/trip"; mkdir -p "$TRIP"
cat > "$TRIP/claude" <<EOF
#!/usr/bin/env bash
echo "CLAUDE_CALLED" >> "$TMP/claude-calls.log"
echo "fake-event-url"
EOF
chmod +x "$TRIP/claude"
rm -f "$TMP/claude-calls.log"
OUT=$(KB_HUB="$HUB" KB_CALENDAR_FAKE_DIR="$FAKE" PATH="$TRIP:$PATH" "$TASK" \
  "Follow up on launch" --due "2026-06-27T09:00" --calendar 2>"$TMP/ac7.err")
RC=$?
[[ "$RC" == "0" ]] && ok "AC7: kb-task --calendar exits 0" || fail "AC7: kb-task rc=$RC ($(cat "$TMP/ac7.err"))"
[[ ! -f "$TMP/claude-calls.log" ]] && ok "AC7: kb-task --calendar did not invoke a direct claude calendar write" || fail "AC7: kb-task still called claude directly"
[[ "$(create_calls "$FAKE")" == "0" ]] && ok "AC7: kb-task --calendar created no calendar event without approval" || fail "AC7: kb-task wrote $(create_calls "$FAKE") events directly"
# it should instead leave a pending follow-up proposal + print the approval command
if echo "$OUT" | grep -qi "approve"; then ok "AC7: kb-task prints an approval command/instruction"; else fail "AC7: kb-task gave no approval path (out: $OUT)"; fi

# =============================================================================
echo "== AC7b: kb-idea routes through shared adapter without collapsing reminders =="
# -----------------------------------------------------------------------------
# A calendar proposal_id (cal-<date>-01) is only unique WITHIN one idea card, so
# two different ideas can share it. The single-writer routing must still produce
# two DISTINCT calendar events, not collapse them onto one idempotency key.
if [[ ! -f "$SRC_BIN/_kb_ideas/card.py" ]]; then
  echo "  - SKIP AC7b (_kb_ideas/card.py not in $SRC_BIN)"
else
  FAKE=$(make_fake ac7b ok)
  RES=$(KB_CALENDAR_FAKE_DIR="$FAKE" "$PY" - "$SRC_BIN" <<'PY'
import sys, json, importlib
sys.path.insert(0, sys.argv[1])
card = importlib.import_module("_kb_ideas.card")
prop = lambda: {"proposal_id": "cal-20260626-01", "title": "t",
                "start": "2026-06-26T09:00:00+02:00", "end": "2026-06-26T09:15:00+02:00",
                "timezone": "Europe/Madrid"}
a1 = card._create_google_calendar_event(prop(), "idea-aaa")
b1 = card._create_google_calendar_event(prop(), "idea-bbb")   # different idea, same proposal_id
a2 = card._create_google_calendar_event(prop(), "idea-aaa")   # same idea+proposal → idempotent
# no-id proposal must fail closed, not collapse
try:
    card._create_google_calendar_event({"title": "x", "start": "2026-06-26T09:00:00+02:00",
                                         "end": "2026-06-26T09:15:00+02:00"}, "idea-ccc")
    raised = False
except Exception:
    raised = True
print(json.dumps({"a1": a1, "b1": b1, "a2": a2, "raised": raised}))
PY
)
  RC=$?
  if [[ "$RC" != "0" ]]; then
    fail "AC7b: kb-idea adapter routing crashed ($RES)"
  else
    A1=$(echo "$RES" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["a1"])')
    B1=$(echo "$RES" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["b1"])')
    A2=$(echo "$RES" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["a2"])')
    RAISED=$(echo "$RES" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["raised"])')
    [[ "$A1" != "$B1" ]] && ok "AC7b: distinct ideas with same proposal_id → distinct events" || fail "AC7b: distinct ideas COLLAPSED to one event ($A1)"
    [[ "$A1" == "$A2" ]] && ok "AC7b: same idea+proposal re-approve is idempotent" || fail "AC7b: same idea+proposal produced two events"
    [[ "$(distinct_events "$FAKE")" == "2" ]] && ok "AC7b: exactly two distinct events stored" || fail "AC7b: $(distinct_events "$FAKE") distinct events (want 2)"
    [[ "$RAISED" == "True" ]] && ok "AC7b: id-less proposal fails closed (no constant-id collapse)" || fail "AC7b: id-less proposal did not fail closed"
  fi
fi

# =============================================================================
echo "== AC6: daily brief reads agenda input =="
# -----------------------------------------------------------------------------
if ! command -v zsh >/dev/null 2>&1; then
  echo "  - SKIP AC6 (zsh not available)"
elif [[ ! -f "$SRC_BIN/kb-brief" ]]; then
  echo "  - SKIP AC6 (kb-brief not in $SRC_BIN)"
else
  HUB=$(make_hub ac6)
  # brief deps: symlink the real scripts (kb-brief resolves _kb_profile.py and
  # kb-agenda resolves _kb_calendar via their real dir after .resolve()).
  ln -sf "$SRC_BIN/kb-brief" "$HUB/bin/kb-brief"
  ln -sf "$SRC_BIN/kb-agenda" "$HUB/bin/kb-agenda"
  cat > "$HUB/personal/.secrets" <<'EOF'
TELEGRAM_TOKEN=test-token
TELEGRAM_CHAT_ID=42
EOF
  # stub the other helpers kb-brief shells out to
  printf '#!/usr/bin/env bash\nprintf ""\n' > "$HUB/bin/kb-idea"; chmod +x "$HUB/bin/kb-idea"
  printf '#!/usr/bin/env bash\nprintf "%%s" "{\\"generated_at\\":null,\\"projects\\":[],\\"warnings\\":[],\\"changed_since_yesterday\\":[],\\"do_not_surface\\":[]}"\n' > "$HUB/bin/kb-brief-preflight"; chmod +x "$HUB/bin/kb-brief-preflight"
  # capture-mock the orchestrator: write the PROMPT (last arg) to a file
  cat > "$HUB/bin/kb-orchestrator-run" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do LAST="\$a"; done
printf '%s' "\$LAST" > "$HUB/captured-prompt.txt"
cat <<'OUT'
| project | status |
---BRIEF---
brief body
OUT
EOF
  chmod +x "$HUB/bin/kb-orchestrator-run"
  # ledger fixture: one approved follow-up due today
  TODAY=$(date +%Y-%m-%d)
  UNIQ="ZZ-followup-marker-7421"
  cat > "$HUB/personal/calendar-followups.jsonl" <<EOF
{"id":"fup-fixture-001","status":"approved","summary":"$UNIQ check brief reads calendar","start":"${TODAY}T09:00:00+02:00","end":"${TODAY}T09:15:00+02:00","timezone":"Europe/Madrid","project_slug":"demo-project","kind":"check","source":"chat:test","calendar_event_id":"evt-fixture"}
EOF
  # calendar connector disabled: the approved follow-up still comes from the local ledger
  KB_HUB="$HUB" KB_BRIEF_DRY=1 KB_CALENDAR_DISABLE=1 zsh "$HUB/bin/kb-brief" >/dev/null 2>"$TMP/ac6.err"
  RC=$?
  PROMPT=$(cat "$HUB/captured-prompt.txt" 2>/dev/null || true)
  [[ "$RC" == "0" ]] && ok "AC6: kb-brief dry-run exits 0" || fail "AC6: kb-brief rc=$RC ($(cat "$TMP/ac6.err"))"
  echo "$PROMPT" | grep -q "$UNIQ" && ok "AC6: approved follow-up reaches the brief prompt/input" || fail "AC6: agenda follow-up missing from brief prompt"
  # privacy: even surfaced agenda must not carry connector raw fields
  if echo "$PROMPT" | grep -Eq "example.com|meet.google.com|hunter2"; then
    fail "AC6: brief prompt leaked attendee/link/description"
  else
    ok "AC6: brief prompt carries no attendee emails / links / descriptions"
  fi
fi

echo
echo "=== calendar-followups tests: $PASS passed, $FAIL failed ==="
[[ "$FAIL" == "0" ]]
