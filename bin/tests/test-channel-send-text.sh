#!/usr/bin/env bash
# R6c AC3: typed exact one-part Telegram text transport. All endpoints are a
# local fake HTTP server; no external network or credential is used.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d)
# Hermetic: product code must never reach a real agent CLI (a contributor's
# logged-in Claude Code or Codex would make real, paid calls with test data).
AGENT_STUBS="$TMP/agent-stubs"; mkdir -p "$AGENT_STUBS"
for _cli in claude codex; do
  printf '#!/bin/sh\necho "test stub: no real %s calls" >&2\nexit 1\n' "$_cli" > "$AGENT_STUBS/$_cli"
  chmod +x "$AGENT_STUBS/$_cli"
done
export PATH="$AGENT_STUBS:$PATH" KB_CLAUDE_BIN="$AGENT_STUBS/claude" KB_CODEX_BIN="$AGENT_STUBS/codex"
SERVER_PID=""
trap '[[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true; rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MORNING_FIDELITY_SRC_BIN:-$HOME/knowledge/bin}"
SENDER="$SRC_BIN/kb-channel-send-text"

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

if [[ ! -x "$SENDER" ]]; then
  fail "AC3 kb-channel-send-text exists and is executable"
  echo; echo "PASS=$PASS FAIL=$FAIL"; exit 1
fi

cat > "$TMP/server.py" <<'PY'
import http.server, json, os, socket, socketserver, sys, time
from urllib.parse import parse_qs

root = sys.argv[1]
mode_file = os.path.join(root, "mode")
record_file = os.path.join(root, "record.bin")

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        fields = parse_qs(raw.decode("ascii"), keep_blank_values=True, encoding="utf-8")
        text = fields.get("text", [""])[0]
        with open(record_file, "wb") as f:
            f.write(text.encode("utf-8"))
        mode = open(mode_file, encoding="utf-8").read().strip()
        if mode == "timeout":
            time.sleep(3)
            return
        if mode == "reset":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if mode == "malformed":
            body, status = b'{"ok":true', 200
        elif mode == "reject":
            body, status = json.dumps({"ok": False, "error_code": 400,
                                       "description": "synthetic reject"}).encode(), 400
        elif mode == "string-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": "321"}}).encode(), 200
        elif mode == "zero-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": 0}}).encode(), 200
        elif mode == "bool-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": True}}).encode(), 200
        elif mode == "negative-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": -7}}).encode(), 200
        elif mode == "float-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": 3.5}}).encode(), 200
        elif mode == "object-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": {"id": 7}}}).encode(), 200
        elif mode == "array-id":
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": [7]}}).encode(), 200
        else:
            body, status = json.dumps({"ok": True,
                                       "result": {"message_id": 321}}).encode(), 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

class Server(http.server.ThreadingHTTPServer):
    def server_bind(self):  # skip HTTPServer's reverse-DNS lookup (it can take seconds on CI runners)
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

server = Server(("127.0.0.1", 0), Handler)
with open(os.path.join(root, "port"), "w") as f:
    f.write(str(server.server_port))
server.serve_forever()
PY

echo success > "$TMP/mode"
python3 "$TMP/server.py" "$TMP" & SERVER_PID=$!
for _ in $(seq 1 200); do [[ -s "$TMP/port" ]] && break; sleep 0.05; done
PORT=$(cat "$TMP/port")
API="http://127.0.0.1:$PORT"
PART="$TMP/part.txt"
# Cyrillic and a multi-codepoint emoji on purpose: non-ASCII text must be sent intact.
printf 'Первая строка 👨‍👩‍👧‍👦\n\nФинальная строка\n' > "$PART"
chmod 600 "$PART"

run_sender() {
  local mode="$1"; echo "$mode" > "$TMP/mode"
  KB_HUB="$TMP" TELEGRAM_BOT_TOKEN="secret-test-token" TELEGRAM_CHAT_ID="42" \
    KB_TG_API_BASE="$API" KB_TG_TEXT_TIMEOUT=1 \
    "$SENDER" brief "$PART" 2>"$TMP/stderr"
}

echo "=== AC3 typed text outcomes ==="
OUT=$(run_sender success); RC=$?
[[ "$RC" == "0" && "$OUT" == *'"outcome": "success"'* && "$OUT" == *'"message_id": 321'* ]] \
  && ok "success => rc0 + message_id" || fail "success classification rc=$RC out=$OUT"
cmp -s "$PART" "$TMP/record.bin" && ok "transport receives exact UTF-8 file bytes" \
  || fail "transport changed text bytes"
if grep -q 'secret-test-token' "$TMP/stderr" \
    || grep -q 'secret-test-token' <<<"$OUT"; then
  fail "secret leaked to output"
else
  ok "secret-free stdout/stderr"
fi

OUT=$(run_sender reject); RC=$?
[[ "$RC" == "20" && "$OUT" == *'"outcome": "known_rejection"'* ]] \
  && ok "complete Telegram rejection => known_rejection" \
  || fail "reject classification rc=$RC out=$OUT"

for mode in malformed reset timeout; do
  OUT=$(run_sender "$mode"); RC=$?
  [[ "$RC" == "21" && "$OUT" == *'"outcome": "ambiguous"'* ]] \
    && ok "$mode after transmission => ambiguous" \
    || fail "$mode classification rc=$RC out=$OUT"
done

for mode in string-id zero-id bool-id negative-id float-id object-id array-id; do
  OUT=$(run_sender "$mode"); RC=$?
  [[ "$RC" == "21" && "$OUT" == *'"outcome": "ambiguous"'* ]] \
    && ok "$mode cannot become false sent evidence" \
    || fail "$mode accepted invalid message_id rc=$RC out=$OUT"
done

# A signal can terminate the transport after the server has received the body.
# The caller has already durably marked the part as `sending`; a restart must
# therefore resolve that state to ambiguous instead of attempting a resend.
rm -f "$TMP/record.bin" "$TMP/interrupted.out" "$TMP/interrupted.err"
echo timeout > "$TMP/mode"
KB_HUB="$TMP" TELEGRAM_BOT_TOKEN="secret-test-token" TELEGRAM_CHAT_ID="42" \
  KB_TG_API_BASE="$API" KB_TG_TEXT_TIMEOUT=10 \
  "$SENDER" brief "$PART" >"$TMP/interrupted.out" 2>"$TMP/interrupted.err" &
INTERRUPTED_PID=$!
for _ in $(seq 1 50); do [[ -s "$TMP/record.bin" ]] && break; sleep 0.05; done
kill -TERM "$INTERRUPTED_PID" 2>/dev/null || true
wait "$INTERRUPTED_PID" 2>/dev/null; IRC=$?
[[ "$IRC" != "0" && -s "$TMP/record.bin" ]] \
  && ok "signal after transmission leaves outcome for caller recovery" \
  || fail "signal fixture did not interrupt post-transmission rc=$IRC"

# Connect failure happens before request transmission and is therefore a known
# rejection, not an ambiguous possibly-delivered message.
OUT=$(KB_HUB="$TMP" TELEGRAM_BOT_TOKEN="secret-test-token" TELEGRAM_CHAT_ID="42" \
  KB_TG_API_BASE="http://127.0.0.1:1" KB_TG_TEXT_TIMEOUT=1 \
  "$SENDER" brief "$PART" 2>"$TMP/stderr"); RC=$?
[[ "$RC" == "20" && "$OUT" == *'"outcome": "known_rejection"'* ]] \
  && ok "pre-transmission connect failure => known_rejection" \
  || fail "connect failure classification rc=$RC out=$OUT"

EMPTY="$TMP/empty.txt"; : > "$EMPTY"; chmod 600 "$EMPTY"
OUT=$(KB_HUB="$TMP" TELEGRAM_BOT_TOKEN=x TELEGRAM_CHAT_ID=42 \
  KB_TG_API_BASE="$API" "$SENDER" brief "$EMPTY" 2>/dev/null); RC=$?
[[ "$RC" == "20" && "$OUT" == *'"known_rejection"'* ]] \
  && ok "empty local part rejected before transport" || fail "empty file rc=$RC out=$OUT"

echo "=== Telegram not configured (exit 3, no network) ==="
rm -f "$TMP/record.bin"; echo success > "$TMP/mode"
mkdir -p "$TMP/nocfg/personal"
printf '%s\n' '# installer template' 'TELEGRAM_BOT_TOKEN=' 'TELEGRAM_CHAT_ID=' > "$TMP/nocfg/personal/.secrets"
OUT=$(env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$TMP/nocfg" \
  KB_TG_API_BASE="$API" "$SENDER" brief "$PART" 2>"$TMP/stderr"); RC=$?
[[ "$RC" == "3" && "$OUT" == *'"outcome": "not_configured"'* ]] \
  && ok "empty token/chat id => exit 3 not_configured" || fail "not configured rc=$RC out=$OUT"
[[ "$(cat "$TMP/stderr")" == "telegram not configured" ]] \
  && ok "not configured prints one stderr line" || fail "not configured stderr: $(cat "$TMP/stderr")"
[[ ! -e "$TMP/record.bin" ]] && ok "not configured makes no request" || fail "not configured reached the server"
OUT=$(env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID TELEGRAM_BOT_TOKEN="secret-test-token" \
  KB_HUB="$TMP/nocfg" KB_TG_API_BASE="$API" "$SENDER" brief "$PART" 2>/dev/null); RC=$?
[[ "$RC" == "3" ]] && ok "token without chat id => exit 3" || fail "token-only rc=$RC out=$OUT"

# .secrets is read as data when the environment has no credentials.
printf '%s\n' 'export TELEGRAM_BOT_TOKEN="secret-test-token"' "TELEGRAM_CHAT_ID='42'" > "$TMP/nocfg/personal/.secrets"
OUT=$(env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$TMP/nocfg" \
  KB_TG_API_BASE="$API" "$SENDER" brief "$PART" 2>/dev/null); RC=$?
[[ "$RC" == "0" && "$OUT" == *'"outcome": "success"'* ]] \
  && ok ".secrets credentials (export + quotes) are used" || fail ".secrets fallback rc=$RC out=$OUT"
printf '%s\n' 'TELEGRAM_TOKEN=secret-test-token' 'TELEGRAM_CHAT_ID=42' > "$TMP/nocfg/personal/.secrets"
OUT=$(env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$TMP/nocfg" \
  KB_TG_API_BASE="$API" "$SENDER" retro "$PART" 2>/dev/null); RC=$?
[[ "$RC" == "0" ]] && ok "legacy TELEGRAM_TOKEN in .secrets + retro message type" || fail "legacy alias rc=$RC out=$OUT"

echo "=== per-type length limit: brief parts 3500, the unsplit retro 4096 ==="
LONG="$TMP/long.txt"
python3 -c 'import sys; open(sys.argv[1], "w", encoding="utf-8").write("р" * 3800)' "$LONG"
chmod 600 "$LONG"
OUT=$(KB_HUB="$TMP" TELEGRAM_BOT_TOKEN="secret-test-token" TELEGRAM_CHAT_ID="42" \
  KB_TG_API_BASE="$API" "$SENDER" retro "$LONG" 2>/dev/null); RC=$?
[[ "$RC" == "0" && "$OUT" == *'"outcome": "success"'* ]] \
  && ok "retro of 3800 units (under Telegram's 4096) is sent" || fail "long retro rc=$RC out=$OUT"
OUT=$(KB_HUB="$TMP" TELEGRAM_BOT_TOKEN="secret-test-token" TELEGRAM_CHAT_ID="42" \
  KB_TG_API_BASE="$API" "$SENDER" brief "$LONG" 2>/dev/null); RC=$?
[[ "$RC" == "20" ]] && ok "brief part over 3500 units is still rejected locally" || fail "long brief part rc=$RC out=$OUT"
python3 -c 'import sys; open(sys.argv[1], "w", encoding="utf-8").write("р" * 4097)' "$LONG"
OUT=$(KB_HUB="$TMP" TELEGRAM_BOT_TOKEN="secret-test-token" TELEGRAM_CHAT_ID="42" \
  KB_TG_API_BASE="$API" "$SENDER" retro "$LONG" 2>/dev/null); RC=$?
[[ "$RC" == "20" ]] && ok "retro over Telegram's 4096 units is rejected locally" || fail "too long retro rc=$RC out=$OUT"

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
