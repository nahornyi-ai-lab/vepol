#!/usr/bin/env bash
# Tests for the Telegram review surface (people-review-telegram spec 2026-07-05).
#
# Covers (spec-contract:sha256:11703f44…):
#   AC1  push: exactly-once per candidate, cap window, --all flush, dedup
#   AC2  approve button → live card promoted, message edited
#   AC3  reject button → identity blocklisted, staged removed
#   AC4  merge flow → menu, sightings transferred, alias registered, no blacklist
#   AC5  defer → no disk change, re-pushable
#   AC6  enrich button → one-shot Codex search (search-once honored)
#   AC7  unauthorized from.id → refused, no action
#   AC8  unknown/stale cbid → safe ack, no crash
#   AC9  offset watermark → replay processed exactly once
#   +    soft-fail push, resolved-elsewhere race, auto-push next after resolve
#
# All hubs are throwaway temp dirs (KB_HUB) — never the live ~/knowledge.
# Telegram Bot API is faked by a local HTTP server (KB_TG_API_BASE override);
# fakes exist only inside this suite.
# Usage: bash bin/tests/test-people-review-telegram.sh

set -uo pipefail

PASS=0; FAIL=0
TMPDIR_TEST=$(mktemp -d)
BIN="${KB_PEOPLE_SRC_BIN:-$HOME/knowledge/bin}"
export SRC_BIN="$BIN"
PY=python3

SRV="$TMPDIR_TEST/srv"
mkdir -p "$SRV"

cleanup() {
  [ -n "${SRV_PID:-}" ] && kill "$SRV_PID" 2>/dev/null
  rm -rf "$TMPDIR_TEST"
}
trap cleanup EXIT

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# ---------------------------------------------------------------------------
# Fake Telegram Bot API server (test-only)
# ---------------------------------------------------------------------------
cat > "$SRV/fake_tg.py" <<'PYEOF'
import json, os, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SRV = os.path.dirname(os.path.abspath(__file__))
CALLS = os.path.join(SRV, "calls.jsonl")
UPDATES = os.path.join(SRV, "updates.json")
FAILFLAG = os.path.join(SRV, "fail_next")
FAILMETHOD = os.path.join(SRV, "fail_method")
MSGID = os.path.join(SRV, "msgid")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n).decode() if n else "{}"
        try:
            params = json.loads(body)
        except ValueError:
            params = {}
        m = re.match(r"^/bot[^/]+/(\w+)$", self.path)
        method = m.group(1) if m else "unknown"
        with open(CALLS, "a") as f:
            f.write(json.dumps({"method": method, "params": params}) + "\n")
        if os.path.exists(FAILFLAG):
            os.unlink(FAILFLAG)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"ok": false, "description": "boom"}')
            return
        if os.path.exists(FAILMETHOD):
            target = open(FAILMETHOD).read().strip()
            if method == target:
                os.unlink(FAILMETHOD)
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'{"ok": false, "description": "boom"}')
                return
        if method == "sendMessage":
            cur = 0
            if os.path.exists(MSGID):
                cur = int(open(MSGID).read().strip() or 0)
            cur += 1
            open(MSGID, "w").write(str(cur))
            result = {"message_id": cur, "chat": {"id": params.get("chat_id")}}
        elif method == "getUpdates":
            offset = int(params.get("offset", 0) or 0)
            updates = []
            if os.path.exists(UPDATES):
                updates = json.load(open(UPDATES))
            result = [u for u in updates if u["update_id"] >= offset]
        else:
            result = True
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "result": result}).encode())


if __name__ == "__main__":
    port = int(sys.argv[1])
    HTTPServer(("127.0.0.1", port), H).serve_forever()
PYEOF

PORT=$($PY -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
$PY "$SRV/fake_tg.py" "$PORT" &
SRV_PID=$!
for _ in $(seq 1 50); do
  $PY -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/botX/getUpdates', data=b'{}', timeout=1)" 2>/dev/null && break
  sleep 0.1
done

export KB_TG_API_BASE="http://127.0.0.1:$PORT"
export TELEGRAM_TOKEN="test-token"
export TELEGRAM_CHAT_ID="777"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
make_hub() {
  local hub="$1"
  mkdir -p "$hub/people" "$hub/personal/mail/people" "$hub/bin"
  cat > "$hub/bin/kb-channel-send" <<'EOS'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
printf '%s|%s\n' "$1" "$2" >> "$DIR/sent.log"
EOS
  chmod +x "$hub/bin/kb-channel-send"
}

write_envelope() {
  local hub="$1" day="$2" period="$3" senders="$4"
  cat > "$hub/personal/mail/people/$day-$period.json" <<EOF
{"schema": "mail-people/v1", "date": "$day", "period": "$period",
 "generated_at": "${day}T06:15:00+02:00", "available": true,
 "senders": $senders}
EOF
}

run_extract() {
  local hub="$1"; shift
  KB_HUB="$hub" $PY "$BIN/kb-extract-people" --hub "$hub" --no-llm --quiet --no-push "$@" 2>/dev/null
}

# Stage N candidates via a real extractor run (realistic staged files).
stage_senders() {
  local hub="$1" day="$2" senders="$3"
  write_envelope "$hub" "$day" "morning" "$senders"
  run_extract "$hub"
}

run_push() {
  local hub="$1"; shift
  KB_HUB="$hub" $PY "$BIN/kb-contact" push "$@" 2>&1
}

run_listener_once() {
  local hub="$1"; shift
  KB_HUB="$hub" $PY "$BIN/kb-people-review-bot" --once "$@" 2>&1
}

reset_srv() {
  : > "$SRV/calls.jsonl"
  echo "[]" > "$SRV/updates.json"
  rm -f "$SRV/fail_next" "$SRV/fail_method"
}

calls_of() { grep '"method": "'"$1"'"' "$SRV/calls.jsonl" 2>/dev/null | wc -l | tr -d ' '; }

# Read a field from the outbox with python (json).
outbox_get() {
  local hub="$1" expr="$2"
  $PY -c "
import json
d = json.load(open('$hub/people/.review-outbox.json'))
print($expr)
" 2>/dev/null
}

# cbid of the outbox item for a slug (state filter optional).
cbid_for() {
  local hub="$1" slug="$2"
  $PY -c "
import json
d = json.load(open('$hub/people/.review-outbox.json'))
for cbid, it in d['items'].items():
    if it['slug'] == '$slug' and it['state'] == 'pending':
        print(cbid); break
"
}

# message_id stored in the outbox for a cbid (buttons are bound to it).
msgid_for() {
  local hub="$1" cbid="$2"
  outbox_get "$hub" "d['items']['$cbid']['message_id']"
}

# Queue a callback_query update bound to the item's real message.
# args: hub, update_id, data, cbid, [from_id]
queue_callback() {
  local hub="$1" upd="$2" data="$3" cbid="$4" from_id="${5:-777}"
  local mid
  mid=$(msgid_for "$hub" "$cbid" 2>/dev/null)
  [ -n "$mid" ] || mid=1
  $PY -c "
import json
p = '$SRV/updates.json'
u = json.load(open(p))
u.append({'update_id': $upd, 'callback_query': {
    'id': 'cbq$upd', 'from': {'id': $from_id},
    'message': {'message_id': $mid, 'chat': {'id': 777}},
    'data': '$data'}})
json.dump(u, open(p, 'w'))
"
}

echo "=== People review over Telegram tests ==="

# ---------------------------------------------------------------------------
# T1 (AC1): push sends one message per staged candidate with the keyboard
# ---------------------------------------------------------------------------
HUB1="$TMPDIR_TEST/hub1"; make_hub "$HUB1"; reset_srv
stage_senders "$HUB1" "2026-07-05" '[
  {"name": "Alice Wonder", "address": "alice@wonder.example", "domain": "wonder.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1},
  {"name": "Bob Builder", "address": "bob@builder.example", "domain": "builder.example",
   "first_ts": "2026-07-05T05:00:00Z", "last_ts": "2026-07-05T05:00:00Z", "count": 2}]'
STAGED_N=$(ls "$HUB1"/people/*.staged.md 2>/dev/null | wc -l | tr -d ' ')
[ "$STAGED_N" = "2" ] && ok "T1a: fixture staged 2 candidates" || fail "T1a: expected 2 staged, got $STAGED_N"

run_push "$HUB1" >/dev/null
[ "$(calls_of sendMessage)" = "2" ] && ok "T1b: push sent 2 messages" || fail "T1b: expected 2 sendMessage, got $(calls_of sendMessage)"

KB_OK=$($PY -c "
import json
lines = [json.loads(l) for l in open('$SRV/calls.jsonl')]
sends = [l for l in lines if l['method'] == 'sendMessage']
kb = sends[0]['params'].get('reply_markup', {}).get('inline_keyboard', [])
flat = [b for row in kb for b in row]
datas = [b.get('callback_data', '') for b in flat]
import re
grammar = all(re.match(r'^pn:[a-z]+:[a-z0-9]+$', d) for d in datas)
print('OK' if len(flat) == 4 and grammar and sends[0]['params'].get('chat_id') == 777 else 'BAD', len(flat))
")
[ "${KB_OK%% *}" = "OK" ] && ok "T1c: message has 4-button pn:* keyboard to owner chat" || fail "T1c: keyboard wrong: $KB_OK"

TEXT_OK=$($PY -c "
import json
lines = [json.loads(l) for l in open('$SRV/calls.jsonl')]
sends = [l for l in lines if l['method'] == 'sendMessage']
texts = ' '.join(s['params'].get('text', '') for s in sends)
print('OK' if 'alice@wonder.example' in texts and 'Alice Wonder' in texts else 'BAD')
")
[ "$TEXT_OK" = "OK" ] && ok "T1d: message text carries name + address" || fail "T1d: identity missing from text"

# ---------------------------------------------------------------------------
# T2 (AC1): second push run sends nothing (dedup via outbox)
# ---------------------------------------------------------------------------
run_push "$HUB1" >/dev/null
[ "$(calls_of sendMessage)" = "2" ] && ok "T2: re-push sends 0 new messages" || fail "T2: dedup broken, $(calls_of sendMessage) sends"

# ---------------------------------------------------------------------------
# T3 (AC1): cap window 8; --all flushes everything
# ---------------------------------------------------------------------------
HUB3="$TMPDIR_TEST/hub3"; make_hub "$HUB3"; reset_srv
SENDERS=$($PY -c "
import json
print(json.dumps([{'name': f'Person Num{i}', 'address': f'p{i}@ex{i}.example',
                   'domain': f'ex{i}.example', 'first_ts': '2026-07-05T04:00:00Z',
                   'last_ts': '2026-07-05T04:00:00Z', 'count': 1} for i in range(10)]))
")
stage_senders "$HUB3" "2026-07-05" "$SENDERS"
run_push "$HUB3" >/dev/null
[ "$(calls_of sendMessage)" = "8" ] && ok "T3a: cap holds pending window at 8" || fail "T3a: expected 8 sends, got $(calls_of sendMessage)"
run_push "$HUB3" --all >/dev/null
[ "$(calls_of sendMessage)" = "10" ] && ok "T3b: --all flushes the rest" || fail "T3b: expected 10 total, got $(calls_of sendMessage)"

# ---------------------------------------------------------------------------
# T4 (AC2): approve button promotes the staged card to live
# ---------------------------------------------------------------------------
reset_srv
CBID=$(cbid_for "$HUB1" "alice-wonder")
[ -n "$CBID" ] && ok "T4a: outbox has cbid for alice-wonder" || fail "T4a: no cbid found"
queue_callback "$HUB1" 100 "pn:a:$CBID" "$CBID"
run_listener_once "$HUB1" >/dev/null
if [ -f "$HUB1/people/alice-wonder.md" ] && [ ! -f "$HUB1/people/alice-wonder.staged.md" ]; then
  ok "T4b: approve promoted card to live"
else
  fail "T4b: staged not promoted (live=$([ -f "$HUB1/people/alice-wonder.md" ] && echo y || echo n))"
fi
[ "$(calls_of answerCallbackQuery)" -ge 1 ] && ok "T4c: callback answered" || fail "T4c: no answerCallbackQuery"
[ "$(calls_of editMessageText)" -ge 1 ] && ok "T4d: message edited with outcome" || fail "T4d: no editMessageText"
STATE=$(outbox_get "$HUB1" "d['items']['$CBID']['state']")
[ "$STATE" = "approved" ] && ok "T4e: outbox state=approved" || fail "T4e: outbox state=$STATE"

# ---------------------------------------------------------------------------
# T5 (AC3): reject button blocklists identity and removes staged
# ---------------------------------------------------------------------------
reset_srv
CBID=$(cbid_for "$HUB1" "bob-builder")
queue_callback "$HUB1" 200 "pn:r:$CBID" "$CBID"
run_listener_once "$HUB1" >/dev/null
if [ ! -f "$HUB1/people/bob-builder.staged.md" ] && grep -q "bob@builder.example" "$HUB1/people/.rejected.yaml" 2>/dev/null; then
  ok "T5: reject removed staged + blocklisted email"
else
  fail "T5: reject incomplete"
fi

# ---------------------------------------------------------------------------
# T6 (AC5): defer keeps staged intact; candidate re-pushable afterwards
# ---------------------------------------------------------------------------
HUB6="$TMPDIR_TEST/hub6"; make_hub "$HUB6"; reset_srv
stage_senders "$HUB6" "2026-07-05" '[
  {"name": "Carol Deep", "address": "carol@deep.example", "domain": "deep.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB6" >/dev/null
CBID=$(cbid_for "$HUB6" "carol-deep")
queue_callback "$HUB6" 300 "pn:d:$CBID" "$CBID"
run_listener_once "$HUB6" >/dev/null
[ -f "$HUB6/people/carol-deep.staged.md" ] && ok "T6a: defer keeps staged file" || fail "T6a: staged gone after defer"
STATE=$(outbox_get "$HUB6" "d['items']['$CBID']['state']")
[ "$STATE" = "deferred" ] && ok "T6b: outbox state=deferred" || fail "T6b: state=$STATE"
reset_srv
run_push "$HUB6" >/dev/null
[ "$(calls_of sendMessage)" = "1" ] && ok "T6c: deferred candidate re-pushed" || fail "T6c: not re-pushed"

# ---------------------------------------------------------------------------
# T7+T8 (AC4): merge menu + merge into target
# ---------------------------------------------------------------------------
HUB7="$TMPDIR_TEST/hub7"; make_hub "$HUB7"; reset_srv
# Seed a live card the staged one should merge into.
stage_senders "$HUB7" "2026-07-04" '[
  {"name": "Jane Doe", "address": "jane@acme.example", "domain": "acme.example",
   "first_ts": "2026-07-04T04:00:00Z", "last_ts": "2026-07-04T04:00:00Z", "count": 1}]'
KB_HUB="$HUB7" $PY "$BIN/kb-extract-people" --hub "$HUB7" --approve jane-doe >/dev/null 2>&1
# New staged person that is actually the same Jane on a personal address.
stage_senders "$HUB7" "2026-07-05" '[
  {"name": "Jane Doe", "address": "jane.personal@mail.example", "domain": "mail.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
STAGED7=$(basename "$(ls "$HUB7"/people/*.staged.md | head -1)" .staged.md)
run_push "$HUB7" >/dev/null
CBID=$(cbid_for "$HUB7" "$STAGED7")
queue_callback "$HUB7" 400 "pn:m:$CBID" "$CBID"
run_listener_once "$HUB7" >/dev/null
MENU_OK=$($PY -c "
import json
lines = [json.loads(l) for l in open('$SRV/calls.jsonl')]
edits = [l for l in lines if l['method'] == 'editMessageText']
if not edits:
    print('NOEDIT'); raise SystemExit
kb = edits[-1]['params'].get('reply_markup', {}).get('inline_keyboard', [])
datas = [b.get('callback_data', '') for row in kb for b in row]
has_target = any(d.startswith('pn:mt:') for d in datas)
has_back = any(d.startswith('pn:b:') for d in datas)
print('OK' if has_target and has_back else f'BAD {datas}')
")
[ "$MENU_OK" = "OK" ] && ok "T7: merge menu with target + back buttons" || fail "T7: merge menu wrong: $MENU_OK"

queue_callback "$HUB7" 401 "pn:mt:$CBID:0" "$CBID"
run_listener_once "$HUB7" >/dev/null
if [ ! -f "$HUB7/people/$STAGED7.staged.md" ] \
   && grep -q "mail:morning-2026-07-05" "$HUB7/people/jane-doe.md" 2>/dev/null; then
  ok "T8a: merge transferred sightings into target"
else
  fail "T8a: merge did not land on target"
fi
if grep -q "jane.personal@mail.example" "$HUB7/people/.rejected.yaml" 2>/dev/null; then
  fail "T8b: merged identity wrongly blacklisted"
else
  ok "T8b: merged identity NOT blacklisted"
fi
ALIAS_OK=$($PY -c "
import sys
from pathlib import Path
sys.path.insert(0, '$BIN')
from _kb_people import index
index.INDEX_PATH = Path('$HUB7/people/_index.yaml')
idx = index._load()
hits = [e for e in idx.values()
        if isinstance(e, dict) and 'jane.personal@mail.example' in str(e.get('locators', ''))]
print('OK' if hits else 'MISS')
" 2>/dev/null)
[ "$ALIAS_OK" = "OK" ] && ok "T8c: alias registered in index" || fail "T8c: alias missing from index ($ALIAS_OK)"

# ---------------------------------------------------------------------------
# T9 (AC7): unauthorized from.id → no action
# ---------------------------------------------------------------------------
HUB9="$TMPDIR_TEST/hub9"; make_hub "$HUB9"; reset_srv
stage_senders "$HUB9" "2026-07-05" '[
  {"name": "Eve Mallory", "address": "eve@mallory.example", "domain": "mallory.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB9" >/dev/null
CBID=$(cbid_for "$HUB9" "eve-mallory")
queue_callback "$HUB9" 500 "pn:a:$CBID" "$CBID" 31337
run_listener_once "$HUB9" >/dev/null
if [ -f "$HUB9/people/eve-mallory.staged.md" ] && [ ! -f "$HUB9/people/eve-mallory.md" ]; then
  ok "T9a: unauthorized press performed no action"
else
  fail "T9a: unauthorized press mutated state"
fi
[ "$(calls_of answerCallbackQuery)" -ge 1 ] && ok "T9b: unauthorized press answered politely" || fail "T9b: no answer"

# T9c: right user but button not bound to the outbox message (forwarded copy)
reset_srv
$PY -c "
import json
p = '$SRV/updates.json'
u = json.load(open(p))
u.append({'update_id': 550, 'callback_query': {
    'id': 'cbq550', 'from': {'id': 777},
    'message': {'message_id': 99999, 'chat': {'id': 777}},
    'data': 'pn:a:$CBID'}})
json.dump(u, open(p, 'w'))
"
run_listener_once "$HUB9" >/dev/null
if [ -f "$HUB9/people/eve-mallory.staged.md" ] && [ ! -f "$HUB9/people/eve-mallory.md" ]; then
  ok "T9c: unbound message_id performed no action"
else
  fail "T9c: forwarded-button callback mutated state"
fi

# ---------------------------------------------------------------------------
# T10 (AC8): unknown/stale cbid → safe ack, no crash
# ---------------------------------------------------------------------------
reset_srv
queue_callback "$HUB9" 600 "pn:a:zzzzzzzzzz" "zzzzzzzzzz"
OUT=$(run_listener_once "$HUB9"; echo "rc=$?")
echo "$OUT" | grep -q "rc=0" && ok "T10a: unknown cbid exits 0" || fail "T10a: crashed: $OUT"
[ "$(calls_of answerCallbackQuery)" -ge 1 ] && ok "T10b: unknown cbid safely acked" || fail "T10b: no ack"

# ---------------------------------------------------------------------------
# T11 (AC9): offset watermark — replay processed exactly once
# ---------------------------------------------------------------------------
reset_srv
CBID=$(cbid_for "$HUB9" "eve-mallory")
queue_callback "$HUB9" 700 "pn:a:$CBID" "$CBID"
run_listener_once "$HUB9" >/dev/null
[ -f "$HUB9/people/eve-mallory.md" ] && ok "T11a: approve applied" || fail "T11a: approve failed"
N_EDITS=$(calls_of editMessageText)
run_listener_once "$HUB9" >/dev/null
# Same updates file still contains update 700, but offset must skip it.
[ "$(calls_of editMessageText)" = "$N_EDITS" ] && ok "T11b: watermark prevents double-processing" || fail "T11b: replayed update re-processed"
OFFSET=$(outbox_get "$HUB9" "d['offset']")
[ "$OFFSET" = "701" ] && ok "T11c: offset advanced to 701" || fail "T11c: offset=$OFFSET"

# ---------------------------------------------------------------------------
# T12 (AC6): post-approve enrich offer + search-once via fake codex
# ---------------------------------------------------------------------------
HUB12="$TMPDIR_TEST/hub12"; make_hub "$HUB12"; reset_srv
stage_senders "$HUB12" "2026-07-05" '[
  {"name": "Grace Hopper", "address": "grace@navy.example", "domain": "navy.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB12" >/dev/null
CBID=$(cbid_for "$HUB12" "grace-hopper")
queue_callback "$HUB12" 800 "pn:a:$CBID" "$CBID"
run_listener_once "$HUB12" >/dev/null
OFFER_OK=$($PY -c "
import json
lines = [json.loads(l) for l in open('$SRV/calls.jsonl')]
kbs = []
for l in lines:
    if l['method'] in ('editMessageText', 'sendMessage'):
        kb = l['params'].get('reply_markup', {}).get('inline_keyboard', [])
        kbs += [b.get('callback_data', '') for row in kb for b in row]
has_e = any(d.startswith('pn:e:') for d in kbs)
has_x = any(d.startswith('pn:x:') for d in kbs)
print('OK' if has_e and has_x else f'BAD {kbs}')
")
[ "$OFFER_OK" = "OK" ] && ok "T12a: approve offers enrich keyboard" || fail "T12a: no enrich offer: $OFFER_OK"

FAKE_CODEX="$TMPDIR_TEST/fake-codex"
cat > "$FAKE_CODEX" <<'EOS'
#!/usr/bin/env bash
OUT=""
prev=""
for a in "$@"; do
  [ "$prev" = "--output-last-message" ] && OUT="$a"
  prev="$a"
done
echo "$KB_FAKE_CODEX_CALLS_FILE" >> /dev/null
echo "x" >> "$KB_FAKE_CODEX_CALLS_FILE"
cat > "$OUT" <<'JSON'
{"found": true, "profiles": [{"url": "https://www.linkedin.com/in/grace-hopper",
 "confidence": "high", "evidence": "navy.example engineer Grace"}]}
JSON
EOS
chmod +x "$FAKE_CODEX"
export KB_FAKE_CODEX_CALLS_FILE="$TMPDIR_TEST/codex-calls"
: > "$KB_FAKE_CODEX_CALLS_FILE"

queue_callback "$HUB12" 801 "pn:e:$CBID" "$CBID"
KB_CODEX_BIN="$FAKE_CODEX" run_listener_once "$HUB12" >/dev/null
grep -q "linkedin.com/in/grace-hopper" "$HUB12/people/grace-hopper.md" 2>/dev/null \
  && ok "T12b: enrich wrote profile to live card" || fail "T12b: profile missing"
CALLS1=$(wc -l < "$KB_FAKE_CODEX_CALLS_FILE" | tr -d ' ')
queue_callback "$HUB12" 802 "pn:e:$CBID" "$CBID"
KB_CODEX_BIN="$FAKE_CODEX" run_listener_once "$HUB12" >/dev/null
CALLS2=$(wc -l < "$KB_FAKE_CODEX_CALLS_FILE" | tr -d ' ')
[ "$CALLS1" = "$CALLS2" ] && ok "T12c: second enrich press skipped (search-once)" || fail "T12c: codex called again ($CALLS1→$CALLS2)"

# ---------------------------------------------------------------------------
# T13: candidate resolved elsewhere (CLI) while pending → safe answer
# ---------------------------------------------------------------------------
HUB13="$TMPDIR_TEST/hub13"; make_hub "$HUB13"; reset_srv
stage_senders "$HUB13" "2026-07-05" '[
  {"name": "Hank Solo", "address": "hank@solo.example", "domain": "solo.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB13" >/dev/null
CBID=$(cbid_for "$HUB13" "hank-solo")
KB_HUB="$HUB13" $PY "$BIN/kb-extract-people" --hub "$HUB13" --reject hank-solo >/dev/null 2>&1
queue_callback "$HUB13" 900 "pn:a:$CBID" "$CBID"
OUT=$(run_listener_once "$HUB13"; echo "rc=$?")
echo "$OUT" | grep -q "rc=0" && ok "T13a: resolved-elsewhere handled without crash" || fail "T13a: $OUT"
[ ! -f "$HUB13/people/hank-solo.md" ] && ok "T13b: no zombie card created" || fail "T13b: card resurrected"

# ---------------------------------------------------------------------------
# T14: Telegram API failure → push soft-fails, staged intact
# ---------------------------------------------------------------------------
HUB14="$TMPDIR_TEST/hub14"; make_hub "$HUB14"; reset_srv
stage_senders "$HUB14" "2026-07-05" '[
  {"name": "Ivy Fault", "address": "ivy@fault.example", "domain": "fault.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
touch "$SRV/fail_next"
OUT=$(run_push "$HUB14"; echo "rc=$?")
echo "$OUT" | grep -q "rc=0" && ok "T14a: push soft-fails (exit 0)" || fail "T14a: $OUT"
[ -f "$HUB14/people/ivy-fault.staged.md" ] && ok "T14b: staged intact after failure" || fail "T14b: staged lost"
PENDING=$(outbox_get "$HUB14" "sum(1 for i in d['items'].values() if i['state'] == 'pending')" 2>/dev/null || echo 0)
[ "${PENDING:-0}" = "0" ] && ok "T14c: failed send not recorded as pending" || fail "T14c: phantom pending=$PENDING"

# ---------------------------------------------------------------------------
# T15: resolution below cap → next staged candidate auto-pushed
# ---------------------------------------------------------------------------
HUB15="$TMPDIR_TEST/hub15"; make_hub "$HUB15"; reset_srv
SENDERS=$($PY -c "
import json
print(json.dumps([{'name': f'Queue Person{i}', 'address': f'q{i}@queue{i}.example',
                   'domain': f'queue{i}.example', 'first_ts': '2026-07-05T04:00:00Z',
                   'last_ts': '2026-07-05T04:00:00Z', 'count': 1} for i in range(9)]))
")
stage_senders "$HUB15" "2026-07-05" "$SENDERS"
run_push "$HUB15" >/dev/null
[ "$(calls_of sendMessage)" = "8" ] || fail "T15-pre: expected 8 initial sends"
CBID=$(cbid_for "$HUB15" "queue-person0")
queue_callback "$HUB15" 1000 "pn:a:$CBID" "$CBID"
run_listener_once "$HUB15" >/dev/null
[ "$(calls_of sendMessage)" = "9" ] && ok "T15: resolving one auto-pushed the 9th" || fail "T15: no auto-push ($(calls_of sendMessage) sends)"

# ---------------------------------------------------------------------------
# T16: extractor auto-push fires under KB_PROCESS_OUTPUTS=telegram,
#      stays silent with --no-push
# ---------------------------------------------------------------------------
HUB16="$TMPDIR_TEST/hub16"; make_hub "$HUB16"; reset_srv
write_envelope "$HUB16" "2026-07-05" "morning" '[
  {"name": "Kim Wire", "address": "kim@wire.example", "domain": "wire.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
KB_HUB="$HUB16" KB_PROCESS_OUTPUTS=telegram $PY "$BIN/kb-extract-people" \
  --hub "$HUB16" --no-llm --quiet >/dev/null 2>&1
[ "$(calls_of sendMessage)" = "1" ] && ok "T16a: cycle auto-pushed the new candidate" || fail "T16a: expected 1 send, got $(calls_of sendMessage)"

HUB16B="$TMPDIR_TEST/hub16b"; make_hub "$HUB16B"; reset_srv
write_envelope "$HUB16B" "2026-07-05" "morning" '[
  {"name": "Lea Quiet", "address": "lea@quiet.example", "domain": "quiet.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
KB_HUB="$HUB16B" KB_PROCESS_OUTPUTS=telegram $PY "$BIN/kb-extract-people" \
  --hub "$HUB16B" --no-llm --quiet --no-push >/dev/null 2>&1
[ "$(calls_of sendMessage)" = "0" ] && ok "T16b: --no-push suppresses auto-push" || fail "T16b: pushed despite --no-push"

# ---------------------------------------------------------------------------
# T17 (AC12): pending older than 7 days auto-defers, freeing the window
# ---------------------------------------------------------------------------
HUB17="$TMPDIR_TEST/hub17"; make_hub "$HUB17"; reset_srv
SENDERS=$($PY -c "
import json
print(json.dumps([{'name': f'Old Timer{i}', 'address': f'ot{i}@old{i}.example',
                   'domain': f'old{i}.example', 'first_ts': '2026-07-05T04:00:00Z',
                   'last_ts': '2026-07-05T04:00:00Z', 'count': 1} for i in range(10)]))
")
stage_senders "$HUB17" "2026-07-05" "$SENDERS"
run_push "$HUB17" >/dev/null
[ "$(calls_of sendMessage)" = "8" ] || fail "T17-pre: expected 8 initial sends"
$PY -c "
import json
p = '$HUB17/people/.review-outbox.json'
d = json.load(open(p))
for it in d['items'].values():
    it['sent_at'] = '2026-06-20T00:00:00+00:00'
json.dump(d, open(p, 'w'))
"
run_push "$HUB17" >/dev/null
# Expiry frees all 8 slots; the 2 NEVER-SENT candidates must win the
# window ahead of the re-pushable deferred backlog (anti-starvation).
[ "$(calls_of sendMessage)" = "16" ] && ok "T17a: freed window refilled (8 more sent)" || fail "T17a: expected 16 total, got $(calls_of sendMessage)"
FRESH_OK=$($PY -c "
import json
d = json.load(open('$HUB17/people/.review-outbox.json'))
pend = {i['slug'] for i in d['items'].values() if i['state'] == 'pending'}
print('OK' if {'old-timer8', 'old-timer9'} <= pend else f'MISS {sorted(pend)}')
")
[ "$FRESH_OK" = "OK" ] && ok "T17b: fresh candidates got slots ahead of deferred" || fail "T17b: $FRESH_OK"
NDEF=$(outbox_get "$HUB17" "sum(1 for i in d['items'].values() if i['state'] == 'deferred')")
[ "$NDEF" = "8" ] && ok "T17c: 8 stale pendings auto-deferred" || fail "T17c: deferred=$NDEF"

# ---------------------------------------------------------------------------
# T18 (AC13): outcome edit fails → action durable + keyboard-removal fallback
# ---------------------------------------------------------------------------
HUB18="$TMPDIR_TEST/hub18"; make_hub "$HUB18"; reset_srv
stage_senders "$HUB18" "2026-07-05" '[
  {"name": "Mia Render", "address": "mia@render.example", "domain": "render.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB18" >/dev/null
CBID=$(cbid_for "$HUB18" "mia-render")
queue_callback "$HUB18" 1100 "pn:a:$CBID" "$CBID"
echo "editMessageText" > "$SRV/fail_method"
OUT=$(run_listener_once "$HUB18"; echo "rc=$?")
echo "$OUT" | grep -q "rc=0" && ok "T18a: edit failure did not crash listener" || fail "T18a: $OUT"
[ -f "$HUB18/people/mia-render.md" ] && ok "T18b: disk action durable despite render failure" || fail "T18b: approve rolled back"
[ "$(calls_of editMessageReplyMarkup)" -ge 1 ] && ok "T18c: keyboard-removal fallback attempted" || fail "T18c: no editMessageReplyMarkup fallback"

# ---------------------------------------------------------------------------
# T19 (AC13): non-callback updates skipped with offset advance
# ---------------------------------------------------------------------------
HUB19="$TMPDIR_TEST/hub19"; make_hub "$HUB19"; reset_srv
stage_senders "$HUB19" "2026-07-05" '[
  {"name": "Ned Mixed", "address": "ned@mixed.example", "domain": "mixed.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB19" >/dev/null
CBID=$(cbid_for "$HUB19" "ned-mixed")
$PY -c "
import json
p = '$SRV/updates.json'
u = json.load(open(p))
u.append({'update_id': 1200, 'message': {'message_id': 5, 'chat': {'id': 777}, 'text': 'hi'}})
json.dump(u, open(p, 'w'))
"
queue_callback "$HUB19" 1201 "pn:a:$CBID" "$CBID"
OUT=$(run_listener_once "$HUB19"; echo "rc=$?")
echo "$OUT" | grep -q "rc=0" && ok "T19a: mixed update batch processed without crash" || fail "T19a: $OUT"
[ -f "$HUB19/people/ned-mixed.md" ] && ok "T19b: callback in mixed batch applied" || fail "T19b: approve lost"
OFFSET=$(outbox_get "$HUB19" "d['offset']")
[ "$OFFSET" = "1202" ] && ok "T19c: offset advanced past non-callback update" || fail "T19c: offset=$OFFSET"

# ---------------------------------------------------------------------------
# T20 (AC9): replayed approve callback converges, never clobbers state
# ---------------------------------------------------------------------------
HUB20="$TMPDIR_TEST/hub20"; make_hub "$HUB20"; reset_srv
stage_senders "$HUB20" "2026-07-05" '[
  {"name": "Rea Play", "address": "rea@play.example", "domain": "play.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB20" >/dev/null
CBID=$(cbid_for "$HUB20" "rea-play")
queue_callback "$HUB20" 1300 "pn:a:$CBID" "$CBID"
run_listener_once "$HUB20" >/dev/null
# Simulate crash-before-offset-save: rewind the watermark and replay.
$PY -c "
import json
p = '$HUB20/people/.review-outbox.json'
d = json.load(open(p)); d['offset'] = 1300
json.dump(d, open(p, 'w'))
"
run_listener_once "$HUB20" >/dev/null
STATE=$(outbox_get "$HUB20" "d['items']['$CBID']['state']")
[ "$STATE" = "approved" ] && ok "T20a: replay kept state=approved (not closed)" || fail "T20a: state=$STATE"
REKB=$($PY -c "
import json
lines = [json.loads(l) for l in open('$SRV/calls.jsonl')]
edits = [l for l in lines if l['method'] == 'editMessageText']
kb = edits[-1]['params'].get('reply_markup', {}).get('inline_keyboard', []) if edits else []
datas = [b.get('callback_data', '') for row in kb for b in row]
print('OK' if any(d.startswith('pn:e:') for d in datas) else f'BAD {datas}')
")
[ "$REKB" = "OK" ] && ok "T20b: replay re-offered the enrich keyboard" || fail "T20b: $REKB"

# ---------------------------------------------------------------------------
# T21: dead `sending` reservation (crashed mid-send) is purged, slot reused
# ---------------------------------------------------------------------------
HUB21="$TMPDIR_TEST/hub21"; make_hub "$HUB21"; reset_srv
stage_senders "$HUB21" "2026-07-05" '[
  {"name": "Sam Stuck", "address": "sam@stuck.example", "domain": "stuck.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
$PY -c "
import json
p = '$HUB21/people/.review-outbox.json'
d = {'schema_version': 1, 'offset': 0, 'items': {
    'deadbeef01': {'slug': 'sam-stuck', 'kind': 'new-card', 'chat_id': 777,
                   'message_id': None, 'state': 'sending',
                   'sent_at': '2026-07-05T00:00:00+00:00'}}}
json.dump(d, open(p, 'w'))
"
run_push "$HUB21" >/dev/null
[ "$(calls_of sendMessage)" = "1" ] && ok "T21a: dead reservation did not block the send" || fail "T21a: $(calls_of sendMessage) sends"
GONE=$(outbox_get "$HUB21" "'deadbeef01' in d['items']")
[ "$GONE" = "False" ] && ok "T21b: dead sending reservation purged" || fail "T21b: still present"

# ---------------------------------------------------------------------------
# T22: enrich worker is single-slot GLOBALLY (one Codex search at a time)
# ---------------------------------------------------------------------------
HUB22="$TMPDIR_TEST/hub22"; make_hub "$HUB22"; reset_srv
stage_senders "$HUB22" "2026-07-05" '[
  {"name": "Tia One", "address": "tia@one.example", "domain": "one.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1},
  {"name": "Uma Two", "address": "uma@two.example", "domain": "two.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB22" >/dev/null
CB_T=$(cbid_for "$HUB22" "tia-one"); CB_U=$(cbid_for "$HUB22" "uma-two")
queue_callback "$HUB22" 1400 "pn:a:$CB_T" "$CB_T"
queue_callback "$HUB22" 1401 "pn:a:$CB_U" "$CB_U"
run_listener_once "$HUB22" >/dev/null
SLOW_CODEX="$TMPDIR_TEST/slow-codex"
cat > "$SLOW_CODEX" <<'EOS'
#!/usr/bin/env bash
OUT=""
prev=""
for a in "$@"; do
  [ "$prev" = "--output-last-message" ] && OUT="$a"
  prev="$a"
done
echo "x" >> "$KB_FAKE_CODEX_CALLS_FILE"
sleep 1.5
cat > "$OUT" <<'JSON'
{"found": false, "profiles": []}
JSON
EOS
chmod +x "$SLOW_CODEX"
: > "$KB_FAKE_CODEX_CALLS_FILE"
queue_callback "$HUB22" 1402 "pn:e:$CB_T" "$CB_T"
queue_callback "$HUB22" 1403 "pn:e:$CB_U" "$CB_U"
KB_CODEX_BIN="$SLOW_CODEX" run_listener_once "$HUB22" >/dev/null
CALLS=$(wc -l < "$KB_FAKE_CODEX_CALLS_FILE" | tr -d ' ')
[ "$CALLS" = "1" ] && ok "T22a: only one Codex search ran (global single slot)" || fail "T22a: $CALLS codex calls"
STATE_U=$(outbox_get "$HUB22" "d['items']['$CB_U']['state']")
[ "$STATE_U" = "approved" ] && ok "T22b: busy candidate stays re-tappable (approved)" || fail "T22b: state=$STATE_U"

# ---------------------------------------------------------------------------
# T23: interrupted search (state=enriching, card still `manual`) is re-offered
# ---------------------------------------------------------------------------
HUB23="$TMPDIR_TEST/hub23"; make_hub "$HUB23"; reset_srv
stage_senders "$HUB23" "2026-07-05" '[
  {"name": "Vic Crash", "address": "vic@crash.example", "domain": "crash.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB23" >/dev/null
CBID=$(cbid_for "$HUB23" "vic-crash")
queue_callback "$HUB23" 1500 "pn:a:$CBID" "$CBID"
run_listener_once "$HUB23" >/dev/null
# Simulate a crash mid-search: state stuck at `enriching`, card untouched
# (enrichment_status stays the default `manual` = never searched).
$PY -c "
import json
p = '$HUB23/people/.review-outbox.json'
d = json.load(open(p)); d['items']['$CBID']['state'] = 'enriching'
json.dump(d, open(p, 'w'))
"
reset_srv
run_listener_once "$HUB23" >/dev/null
STATE=$(outbox_get "$HUB23" "d['items']['$CBID']['state']")
[ "$STATE" = "approved" ] && ok "T23a: interrupted search reset to approved (manual ≠ done)" || fail "T23a: state=$STATE"
REKB=$($PY -c "
import json
lines = [json.loads(l) for l in open('$SRV/calls.jsonl')]
edits = [l for l in lines if l['method'] == 'editMessageText']
kb = edits[-1]['params'].get('reply_markup', {}).get('inline_keyboard', []) if edits else []
datas = [b.get('callback_data', '') for row in kb for b in row]
print('OK' if any(d.startswith('pn:e:') for d in datas) else f'BAD {datas}')
")
[ "$REKB" = "OK" ] && ok "T23b: reconcile re-offered the search keyboard" || fail "T23b: $REKB"

# ---------------------------------------------------------------------------
# T24: stale search callback cannot override an explicit «без поиска»
# ---------------------------------------------------------------------------
HUB24="$TMPDIR_TEST/hub24"; make_hub "$HUB24"; reset_srv
stage_senders "$HUB24" "2026-07-05" '[
  {"name": "Wes Skip", "address": "wes@skip.example", "domain": "skip.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
run_push "$HUB24" >/dev/null
CBID=$(cbid_for "$HUB24" "wes-skip")
queue_callback "$HUB24" 1600 "pn:a:$CBID" "$CBID"
queue_callback "$HUB24" 1601 "pn:x:$CBID" "$CBID"
run_listener_once "$HUB24" >/dev/null
STATE=$(outbox_get "$HUB24" "d['items']['$CBID']['state']")
[ "$STATE" = "closed" ] && ok "T24a: skip-search closed the offer" || fail "T24a: state=$STATE"
: > "$KB_FAKE_CODEX_CALLS_FILE"
queue_callback "$HUB24" 1602 "pn:e:$CBID" "$CBID"
KB_CODEX_BIN="$FAKE_CODEX" run_listener_once "$HUB24" >/dev/null
CALLS=$(wc -l < "$KB_FAKE_CODEX_CALLS_FILE" | tr -d ' ')
STATE=$(outbox_get "$HUB24" "d['items']['$CBID']['state']")
if [ "$CALLS" = "0" ] && [ "$STATE" = "closed" ]; then
  ok "T24b: stale search press did not override skip (no codex, state=closed)"
else
  fail "T24b: codex_calls=$CALLS state=$STATE"
fi
# Reverse guard: stale skip press must not clobber a completed search.
$PY -c "
import json
p = '$HUB24/people/.review-outbox.json'
d = json.load(open(p)); d['items']['$CBID']['state'] = 'enriched'
json.dump(d, open(p, 'w'))
"
queue_callback "$HUB24" 1603 "pn:x:$CBID" "$CBID"
run_listener_once "$HUB24" >/dev/null
STATE=$(outbox_get "$HUB24" "d['items']['$CBID']['state']")
[ "$STATE" = "enriched" ] && ok "T24c: stale skip did not clobber enriched" || fail "T24c: state=$STATE"

# ---------------------------------------------------------------------------
# T25: bots are never people — push auto-rejects bot-identity staged
# ---------------------------------------------------------------------------
HUB25="$TMPDIR_TEST/hub25"; make_hub "$HUB25"; reset_srv
cat > "$HUB25/people/fixbot.staged.md" <<'EOF'
---
name: fixbot
telegram: '@fixbot'
draft: true
slug: fixbot
---
<!-- DERIVED-SIGHTINGS-BEGIN -->
| Date | Source | Summary |
|---|---|---|
| 2026-07-05 | project-source | seen in log |
<!-- DERIVED-SIGHTINGS-END -->
EOF
run_push "$HUB25" >/dev/null
[ "$(calls_of sendMessage)" = "0" ] && ok "T25a: bot candidate never pushed" || fail "T25a: bot was pushed"
[ ! -f "$HUB25/people/fixbot.staged.md" ] && ok "T25b: bot staged auto-rejected" || fail "T25b: staged remains"
grep -q "fixbot" "$HUB25/people/.rejected.yaml" 2>/dev/null && ok "T25c: bot identity blocklisted" || fail "T25c: not in .rejected.yaml"

# T25d: predicate unit checks (incl. the documented Talbot tradeoffs)
UNIT_OK=$($PY -c "
import sys
from pathlib import Path
sys.path.insert(0, '$BIN')
from _kb_people.filters import is_bot_identity as bot
checks = [
    (bot(telegram='@fitness_tracker_bot'), True),
    (bot(name='weather_alerts_bot'), True),
    (bot(name='fitness_tracker_bot'), True),
    (bot(name='John Talbot', email='john@talbot.example'), False),
    (bot(name='Talbot'), True),
    (bot(name='Jane Doe', email='jane@acme.example'), False),
    (bot(telegram='@moon0blossom'), False),
]
bad = [i for i, (got, want) in enumerate(checks) if got != want]
print('OK' if not bad else f'BAD {bad}')
")
[ "$UNIT_OK" = "OK" ] && ok "T25d: is_bot_identity predicate matrix" || fail "T25d: $UNIT_OK"

# T25f: bot pushed BEFORE the filter existed → its pending outbox entry
#       is closed and the chat keyboard stripped during push auto-reject
HUB25F="$TMPDIR_TEST/hub25f"; make_hub "$HUB25F"; reset_srv
cat > "$HUB25F/people/oldbot.staged.md" <<'EOF'
---
name: oldbot
telegram: '@oldbot'
draft: true
slug: oldbot
---
EOF
$PY -c "
import json
p = '$HUB25F/people/.review-outbox.json'
d = {'schema_version': 1, 'offset': 0, 'items': {
    'cafebabe01': {'slug': 'oldbot', 'kind': 'new-card', 'chat_id': 777,
                   'message_id': 42, 'state': 'pending',
                   'sent_at': '2026-07-05T00:00:00+00:00'}}}
json.dump(d, open(p, 'w'))
"
run_push "$HUB25F" >/dev/null
STATE=$(outbox_get "$HUB25F" "d['items']['cafebabe01']['state']")
[ "$STATE" = "rejected" ] && ok "T25f: stale bot outbox entry closed" || fail "T25f: state=$STATE"
[ "$(calls_of editMessageText)" -ge 1 ] && ok "T25g: stale bot chat message edited" || fail "T25g: keyboard left live"
[ ! -f "$HUB25F/people/oldbot.staged.md" ] && ok "T25h: bot staged rejected" || fail "T25h: staged remains"

# T25i: bot cleanup runs even when the review window is already full
HUB25I="$TMPDIR_TEST/hub25i"; make_hub "$HUB25I"; reset_srv
cat > "$HUB25I/people/aaa-human.staged.md" <<'EOF'
---
name: Aaa Human
email: aaa@human.example
draft: true
slug: aaa-human
---
EOF
cat > "$HUB25I/people/zzzbot.staged.md" <<'EOF'
---
name: zzzbot
telegram: '@zzzbot'
draft: true
slug: zzzbot
---
EOF
$PY -c "
import json
from datetime import datetime, timedelta, timezone
# sent_at must be RECENT: pending entries older than PENDING_TTL_DAYS are
# deferred (anti-starvation) and would free the window — a hardcoded date
# here made the whole test rot after 7 calendar days (broke 2026-07-12).
recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
items = {}
for i in range(8):
    items[f'full{i:06d}'] = {'slug': f'p{i}', 'kind': 'new-card', 'chat_id': 777,
                             'message_id': 100 + i, 'state': 'pending',
                             'sent_at': recent}
json.dump({'schema_version': 1, 'offset': 0, 'items': items},
          open('$HUB25I/people/.review-outbox.json', 'w'))
"
run_push "$HUB25I" >/dev/null
[ "$(calls_of sendMessage)" = "0" ] || fail "T25i-pre: window full but something was sent"
if [ ! -f "$HUB25I/people/zzzbot.staged.md" ] \
   && grep -q "zzzbot" "$HUB25I/people/.rejected.yaml" 2>/dev/null \
   && [ -f "$HUB25I/people/aaa-human.staged.md" ]; then
  ok "T25i: full window still sweeps bots (human untouched)"
else
  fail "T25i: bot survived a full window"
fi

# T25j: sightings-only staged for a live human whose SLUG ends in "bot"
#       is never swept — it is pushed like any human candidate
HUB25J="$TMPDIR_TEST/hub25j"; make_hub "$HUB25J"; reset_srv
stage_senders "$HUB25J" "2026-07-05" '[
  {"name": "John Talbot", "address": "john@talbot.example", "domain": "talbot.example",
   "first_ts": "2026-07-05T04:00:00Z", "last_ts": "2026-07-05T04:00:00Z", "count": 1}]'
KB_HUB="$HUB25J" $PY "$BIN/kb-extract-people" --hub "$HUB25J" --approve john-talbot >/dev/null 2>&1
cat > "$HUB25J/people/john-talbot.staged-sightings.md" <<'EOF'
| Date | Source | Summary |
|---|---|---|
| 2026-07-05 | demo/log.md:3 | mentioned in standup |
EOF
run_push "$HUB25J" >/dev/null
if [ -f "$HUB25J/people/john-talbot.staged-sightings.md" ] \
   && [ "$(calls_of sendMessage)" = "1" ] \
   && ! grep -q "john-talbot" "$HUB25J/people/.rejected.yaml" 2>/dev/null; then
  ok "T25j: live-human sightings survived the bot sweep and were pushed"
else
  fail "T25j: sightings swept (file=$([ -f "$HUB25J/people/john-talbot.staged-sightings.md" ] && echo y || echo n), sends=$(calls_of sendMessage))"
fi

# T25e: extractor drops bot hits at the dedup-loop chokepoint
HUB25E="$TMPDIR_TEST/hub25e"; make_hub "$HUB25E"
mkdir -p "$HUB25E/projects/demo/knowledge"
cat > "$HUB25E/registry.md" <<EOF
| slug | path | status |
|---|---|---|
| demo | $HUB25E/projects/demo | live |
EOF
cat > "$HUB25E/projects/demo/knowledge/log.md" <<'EOF'
## [2026-07-05] person | created | demo | met new contact @helperbot in the chat
EOF
KB_HUB="$HUB25E" $PY "$BIN/kb-extract-people" --hub "$HUB25E" --init-watermarks >/dev/null 2>&1
cat >> "$HUB25E/projects/demo/knowledge/log.md" <<'EOF'
## [2026-07-05] person | created | demo | intro call with @cleverbot went well
EOF
run_extract "$HUB25E"
if ls "$HUB25E"/people/*bot*.staged.md >/dev/null 2>&1; then
  fail "T25e: extractor staged a bot"
else
  ok "T25e: extractor dropped bot hits"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" = "0" ] || exit 1
