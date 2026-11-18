#!/usr/bin/env bash
# kb-channel-send (plain text, used by learning, money radar, research and
# alerts): Telegram-not-configured contract (exit 3, one stderr line, no
# network), the bot token never on a command line, and long messages split on
# line boundaries into as many parts as needed (no "[truncated]").
# All sends go to a local fake Telegram API; no network, no real bot.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d)
SERVER_PID=""
trap '[[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null; rm -rf "$TMP"' EXIT
SRC_BIN="${KB_CHANNEL_SRC_BIN:-$HOME/knowledge/bin}"
SENDER="$SRC_BIN/kb-channel-send"

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# Hermetic: product code must never reach a real agent CLI (a contributor's
# logged-in Claude Code or Codex would make real, paid calls with test data).
AGENT_STUBS="$TMP/agent-stubs"; mkdir -p "$AGENT_STUBS"
for _cli in claude codex; do
  printf '#!/bin/sh\necho "test stub: no real %s calls" >&2\nexit 1\n' "$_cli" > "$AGENT_STUBS/$_cli"
  chmod +x "$AGENT_STUBS/$_cli"
done
export PATH="$AGENT_STUBS:$PATH" KB_CLAUDE_BIN="$AGENT_STUBS/claude" KB_CODEX_BIN="$AGENT_STUBS/codex"

if [[ ! -x "$SENDER" ]]; then
  fail "kb-channel-send exists and is executable"
  echo; echo "PASS=$PASS FAIL=$FAIL"; exit 1
fi

# Fake Telegram: records every sendMessage text (one JSON line per request);
# mode file: ok | reject | reject-second.
cat > "$TMP/server.py" <<'PY'
import http.server, json, os, socketserver, sys
from urllib.parse import parse_qs
root = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        fields = parse_qs(raw.decode("ascii"), keep_blank_values=True)
        rec = {"path": self.path, "chat": fields.get("chat_id", [""])[0],
               "text": fields.get("text", [""])[0]}
        with open(os.path.join(root, "requests.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        n = sum(1 for _ in open(os.path.join(root, "requests.jsonl"), encoding="utf-8"))
        mode = open(os.path.join(root, "mode"), encoding="utf-8").read().strip()
        bad = mode == "reject" or (mode == "reject-second" and n == 2)
        body = json.dumps({"ok": False, "description": "synthetic reject"} if bad
                          else {"ok": True, "result": {"message_id": n}}).encode()
        self.send_response(400 if bad else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
class Server(http.server.ThreadingHTTPServer):
    def server_bind(self):  # skip HTTPServer's reverse-DNS lookup (it can take seconds on CI runners)
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
s = Server(("127.0.0.1", 0), H)
open(os.path.join(root, "port"), "w").write(str(s.server_port))
s.serve_forever()
PY
echo ok > "$TMP/mode"
python3 "$TMP/server.py" "$TMP" & SERVER_PID=$!
for _ in $(seq 1 200); do [[ -s "$TMP/port" ]] && break; sleep 0.05; done
API="http://127.0.0.1:$(cat "$TMP/port")"

# curl wrapper first on PATH: records every curl argv, so a token on the
# command line (visible in ps) is caught.
REAL_CURL="$(command -v curl)"
mkdir -p "$TMP/wrap"
cat > "$TMP/wrap/curl" <<EOF
#!/bin/sh
printf '%s\n' "\$*" >> "$TMP/curl-argv.log"
exec "$REAL_CURL" "\$@"
EOF
chmod +x "$TMP/wrap/curl"

HUB="$TMP/hub"; mkdir -p "$HUB/personal"
TOKEN="123456:secret-plain-token"
send() { # send <message> → rc; env credentials, fake API
  : > "$TMP/requests.jsonl"
  env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID \
    PATH="$TMP/wrap:$PATH" KB_HUB="$HUB" KB_TG_API_BASE="$API" \
    TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID=42 \
    "$SENDER" test_type "$1" 2>"$TMP/stderr"
}
count() { [[ -f "$TMP/requests.jsonl" ]] && wc -l < "$TMP/requests.jsonl" | tr -d ' ' || echo 0; }

echo "=== Telegram not configured: exit 3, no network ==="
printf '# installer template\nTELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\n' > "$HUB/personal/.secrets"
: > "$TMP/requests.jsonl"
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$HUB" KB_TG_API_BASE="$API" \
  "$SENDER" test_type "hello" >/dev/null 2>"$TMP/stderr"; RC=$?
[[ "$RC" == "3" ]] && ok "empty token and chat id => exit 3" || fail "not configured rc=$RC"
[[ "$(cat "$TMP/stderr")" == "telegram not configured" ]] \
  && ok "one stderr line: telegram not configured" || fail "stderr: $(cat "$TMP/stderr")"
[[ "$(count)" == "0" ]] && ok "no request when not configured" || fail "not configured reached the server"
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$HUB" KB_TG_API_BASE="$API" \
  TELEGRAM_BOT_TOKEN="$TOKEN" "$SENDER" test_type "hello" >/dev/null 2>&1; RC=$?
[[ "$RC" == "3" ]] && ok "token without chat id => exit 3" || fail "token-only rc=$RC"
"$SENDER" only-one-arg >/dev/null 2>&1; RC=$?
[[ "$RC" == "1" ]] && ok "bad args => exit 1" || fail "bad args rc=$RC"

echo "=== credentials from .secrets (data, legacy alias) ==="
printf 'TELEGRAM_TOKEN="%s"\nexport TELEGRAM_CHAT_ID=77\n' "$TOKEN" > "$HUB/personal/.secrets"
: > "$TMP/requests.jsonl"
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$HUB" KB_TG_API_BASE="$API" \
  "$SENDER" test_type "from secrets" >/dev/null 2>&1; RC=$?
python3 - "$TMP/requests.jsonl" "$TOKEN" <<'PY' && [[ "$RC" == "0" ]] \
  && ok "legacy TELEGRAM_TOKEN + export line in .secrets are used" || fail "secrets fallback rc=$RC"
import json, sys
r = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
assert len(r) == 1 and r[0]["path"] == f"/bot{sys.argv[2]}/sendMessage" and r[0]["chat"] == "77"
PY

echo "=== short message: one verbatim part, token not in argv ==="
: > "$TMP/curl-argv.log"
MSG=$'Первая строка 👨‍👩‍👧‍👦\n\nsecond line'
send "$MSG"; RC=$?
python3 - "$TMP/requests.jsonl" "$MSG" <<'PY' && [[ "$RC" == "0" ]] \
  && ok "short message sent once, byte for byte" || fail "short message rc=$RC"
import json, sys
r = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
assert len(r) == 1 and r[0]["text"] == sys.argv[2], r
PY
[[ -s "$TMP/curl-argv.log" ]] && ok "curl was called through the recording wrapper" || fail "curl wrapper not used"
grep -qF "$TOKEN" "$TMP/curl-argv.log" && fail "bot token appeared on the curl command line" \
  || ok "bot token never on the curl command line"
grep -qF "$TOKEN" "$TMP/stderr" && fail "bot token in stderr" || ok "bot token not in stderr"
# A non-UTF-8 locale (launchd or a user shell) must not break non-Latin text.
LC_ALL=en_US.ISO8859-1 send "$MSG"; RC=$?
python3 - "$TMP/requests.jsonl" "$MSG" <<'PY' && [[ "$RC" == "0" ]] \
  && ok "non-UTF-8 locale: the message is still sent intact" || fail "non-UTF-8 locale rc=$RC"
import json, sys
r = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
assert len(r) == 1 and r[0]["text"] == sys.argv[2], r
PY

echo "=== long message: as many parts as needed, on line boundaries ==="
LONG=$(python3 - <<'PY'
# 30 lines of 500 characters (Cyrillic + one emoji each): ~15000 characters.
print("\n".join(f"{i:02d} " + "ж" * 494 + " 🙂" for i in range(30)), end="")
PY
)
send "$LONG"; RC=$?
python3 - "$TMP/requests.jsonl" "$LONG" <<'PY' && [[ "$RC" == "0" ]] \
  && ok "long message: >2 parts, each <= 4096 UTF-16 units, whole lines, nothing lost" \
  || fail "long message split rc=$RC"
import json, sys
parts = [json.loads(l)["text"] for l in open(sys.argv[1], encoding="utf-8")]
units = lambda s: len(s.encode("utf-16-le")) // 2
assert len(parts) > 2, len(parts)
assert all(units(p) <= 4096 for p in parts), [units(p) for p in parts]
assert "\n".join(parts) == sys.argv[2], "lines lost or reordered"
assert not any("[truncated]" in p for p in parts)
PY

ONE_LINE=$(python3 -c 'print("x" * 10000, end="")')
send "$ONE_LINE"; RC=$?
python3 - "$TMP/requests.jsonl" <<'PY' && [[ "$RC" == "0" ]] \
  && ok "a single 10000-char line is cut into 3 parts" || fail "single long line rc=$RC"
import json, sys
parts = [json.loads(l)["text"] for l in open(sys.argv[1], encoding="utf-8")]
assert [len(p) for p in parts] == [4096, 4096, 1808], [len(p) for p in parts]
PY

echo "=== send failures exit 4 and stop ==="
echo reject > "$TMP/mode"
send "hello"; RC=$?
[[ "$RC" == "4" ]] && ok "Telegram rejection => exit 4" || fail "reject rc=$RC"
echo reject-second > "$TMP/mode"
send "$LONG"; RC=$?
[[ "$RC" == "4" && "$(count)" == "2" ]] && ok "failed part stops the send (no parts after it)" \
  || fail "partial failure rc=$RC requests=$(count)"
echo ok > "$TMP/mode"
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$HUB" \
  KB_TG_API_BASE="http://127.0.0.1:9" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID=42 \
  "$SENDER" test_type "hello" >/dev/null 2>&1; RC=$?
[[ "$RC" == "4" ]] && ok "network failure => exit 4 (not 3)" || fail "network failure rc=$RC"

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
