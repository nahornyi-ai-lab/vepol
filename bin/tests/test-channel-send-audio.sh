#!/usr/bin/env bash
# RED-first acceptance tests for the Telegram sendAudio transport.
# Contract: spec-contract:sha256:4d1e9ea4e8d09c3725739f269407c63200d4d6dd40489f6b35e87533b7467fd4

set -uo pipefail

PASS=0
FAIL=0
TMP=$(mktemp -d)
SENDER="${KB_AUDIO_SENDER:-$HOME/knowledge/bin/kb-channel-send-audio}"
SERVER_PID=""

cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

ok() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
bad() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

expect_rc() {
  local expected="$1" label="$2"; shift 2
  "$@" >"$TMP/stdout" 2>"$TMP/stderr"
  local rc=$?
  if [[ $rc -eq $expected ]]; then ok "$label"; else bad "$label (rc=$rc expected=$expected; $(tail -1 "$TMP/stderr"))"; fi
}

json_assert() {
  local label="$1" expression="$2"
  if python3 - "$TMP/stdout" "$expression" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert eval(sys.argv[2], {"__builtins__": {}}, {"d": d})
PY
  then ok "$label"; else bad "$label"; fi
}

[[ -x "$SENDER" ]] && ok "sender exists and is executable" || bad "sender exists and is executable"

SRV="$TMP/server"
mkdir -p "$SRV"
cat >"$SRV/fake_tg.py" <<'PY'
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

root = Path(sys.argv[1])
port = int(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        (root / "request.json").write_text(json.dumps({
            "path": self.path,
            "content_type": self.headers.get("Content-Type", ""),
            "body_hex": body.hex(),
        }), encoding="utf-8")
        mode = (root / "mode").read_text(encoding="utf-8").strip()
        if mode == "delay":
            time.sleep(2)
        if mode == "disconnect":
            self.connection.shutdown(2)
            self.connection.close()
            return
        if mode == "truncated":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"result":')
            return
        if mode == "http_reject":
            payload = {"ok": False, "error_code": 400, "description": "bad audio"}
            self.send_response(400)
        elif mode == "ok_false":
            payload = {"ok": False, "error_code": 429, "description": "retry later"}
            self.send_response(200)
        elif mode == "bad_schema":
            payload = {"ok": True, "result": {"message_id": [], "audio": {
                "file_id": {}, "file_unique_id": [], "duration": {}}}}
            self.send_response(200)
        elif mode == "echo_token":
            payload = {"ok": True, "result": {"message_id": 4322, "audio": {
                "file_id": "file-echo", "file_unique_id": "unique-echo",
                "duration": 2, "title": "super-secret-token"}}}
            self.send_response(200)
        else:
            payload = {"ok": True, "result": {
                "message_id": 4321,
                "audio": {
                    "file_id": "file-abc", "file_unique_id": "unique-abc",
                    "duration": 17, "file_name": "daily.mp3",
                    "mime_type": "audio/mpeg", "file_size": 12345,
                    "title": "Daily", "performer": "Qwen",
                },
            }}
            self.send_response(200)
        data = json.dumps(payload).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

HTTPServer(("127.0.0.1", port), Handler).serve_forever()
PY

PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
printf 'success' >"$SRV/mode"
python3 "$SRV/fake_tg.py" "$SRV" "$PORT" &
SERVER_PID=$!
for _ in $(seq 1 50); do
  python3 - "$PORT" <<'PY' 2>/dev/null && break
import socket, sys
with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=.2):
    pass
PY
  sleep 0.05
done

API="http://127.0.0.1:$PORT"
TOKEN="super-secret-token"
CHAT="777001"
MP3="$TMP/daily.mp3"
printf 'ID3-exact-test-audio-bytes' >"$MP3"

run_sender() {
  KB_TG_API_BASE="$API" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" \
    "$SENDER" daily_digest "$MP3" "Утренний дайджест — 2026-07-11"
}

if [[ -x "$SENDER" ]]; then
  expect_rc 0 "success exits 0" run_sender
  json_assert "success emits normalized result" 'd["outcome"] == "success" and d["message_id"] == 4321 and d["audio"]["file_id"] == "file-abc" and d["audio"]["file_unique_id"] == "unique-abc" and d["audio"]["duration"] == 17 and d["audio"]["file_size"] == 12345'

  python3 - "$SRV/request.json" "$TOKEN" "$CHAT" "$MP3" <<'PY' \
    && ok "multipart request carries exact chat, caption and MP3 bytes" \
    || bad "multipart request carries exact chat, caption and MP3 bytes"
import json, pathlib, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
body = bytes.fromhex(d["body_hex"])
assert d["path"] == f"/bot{sys.argv[2]}/sendAudio"
assert d["content_type"].startswith("multipart/form-data; boundary=")
assert b'name="chat_id"' in body and sys.argv[3].encode() in body
assert b'name="caption"' in body and "Утренний дайджест — 2026-07-11".encode() in body
assert b'name="audio"' in body and b'filename="daily.mp3"' in body
assert pathlib.Path(sys.argv[4]).read_bytes() in body
PY

  if grep -Fq "$TOKEN" "$TMP/stdout" "$TMP/stderr"; then bad "success output keeps token secret"; else ok "success output keeps token secret"; fi

  printf 'ok_false' >"$SRV/mode"
  expect_rc 20 "complete Telegram ok:false is known rejection" run_sender
  json_assert "known rejection has structured outcome" 'd["outcome"] == "known_rejection"'

  printf 'http_reject' >"$SRV/mode"
  expect_rc 20 "complete HTTP rejection is known rejection" run_sender
  json_assert "HTTP rejection is structured" 'd["outcome"] == "known_rejection"'

  printf 'disconnect' >"$SRV/mode"
  expect_rc 21 "disconnect after transmission is ambiguous" run_sender
  json_assert "disconnect has ambiguous outcome" 'd["outcome"] == "ambiguous"'

  printf 'truncated' >"$SRV/mode"
  expect_rc 21 "truncated success response is ambiguous" run_sender
  json_assert "truncated response has ambiguous outcome" 'd["outcome"] == "ambiguous"'

  printf 'bad_schema' >"$SRV/mode"
  expect_rc 21 "ok:true with invalid Telegram field types is ambiguous" run_sender
  json_assert "invalid success schema is not accepted" 'd["outcome"] == "ambiguous"'

  printf 'echo_token' >"$SRV/mode"
  expect_rc 0 "valid success with reflected text still succeeds" run_sender
  if grep -Fq "$TOKEN" "$TMP/stdout" "$TMP/stderr"; then bad "all success metadata is token-redacted"; else ok "all success metadata is token-redacted"; fi
  cp "$MP3" "$TMP/$TOKEN.mp3"
  expect_rc 0 "secret-like message type and filename still send" env KB_TG_API_BASE="$API" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" "$TOKEN" "$TMP/$TOKEN.mp3"
  if grep -Fq "$TOKEN" "$TMP/stdout" "$TMP/stderr"; then bad "stderr labels and filename are token-redacted"; else ok "stderr labels and filename are token-redacted"; fi

  expect_rc 20 "missing file is known rejection" env KB_TG_API_BASE="$API" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" daily_digest "$TMP/missing.mp3"
  : >"$TMP/empty.mp3"
  expect_rc 20 "empty file is known rejection" env KB_TG_API_BASE="$API" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" daily_digest "$TMP/empty.mp3"
  printf 'RIFF-not-an-mp3' >"$TMP/audio.wav"
  expect_rc 20 "non-MP3 input is known rejection" env KB_TG_API_BASE="$API" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" daily_digest "$TMP/audio.wav"
  expect_rc 20 "missing credentials are known rejection" env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$TMP/no-secrets" KB_TG_API_BASE="$API" "$SENDER" daily_digest "$MP3"
  expect_rc 20 "malformed API base is local known rejection" env KB_TG_API_BASE="http://127.0.0.1:notaport" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" daily_digest "$MP3"

  mkdir -p "$TMP/hub/personal"
  printf '%s\n' 'TELEGRAM_TOKEN=secret-file-token' 'TELEGRAM_CHAT_ID=111' >"$TMP/hub/personal/.secrets"
  printf 'success' >"$SRV/mode"
  expect_rc 0 "TELEGRAM_TOKEN secrets alias works" env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_TOKEN -u TELEGRAM_CHAT_ID KB_HUB="$TMP/hub" KB_TG_API_BASE="$API" "$SENDER" daily_digest "$MP3"
  python3 - "$SRV/request.json" <<'PY' && ok "secrets alias values reach request" || bad "secrets alias values reach request"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); b = bytes.fromhex(d["body_hex"])
assert d["path"] == "/botsecret-file-token/sendAudio" and b"111" in b
PY

  expect_rc 0 "environment credentials override secrets" env KB_HUB="$TMP/hub" KB_TG_API_BASE="$API" TELEGRAM_BOT_TOKEN="$TOKEN" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" daily_digest "$MP3"
  python3 - "$SRV/request.json" "$TOKEN" "$CHAT" <<'PY' && ok "per-variable env precedence is preserved" || bad "per-variable env precedence is preserved"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); b = bytes.fromhex(d["body_hex"])
assert d["path"] == f"/bot{sys.argv[2]}/sendAudio" and sys.argv[3].encode() in b
PY

  printf '%s\n' 'TELEGRAM_BOT_TOKEN=file-primary-token' 'TELEGRAM_CHAT_ID=111' >"$TMP/hub/personal/.secrets"
  expect_rc 0 "environment alias wins over primary secret" env -u TELEGRAM_BOT_TOKEN KB_HUB="$TMP/hub" KB_TG_API_BASE="$API" TELEGRAM_TOKEN="env-alias-token" TELEGRAM_CHAT_ID="$CHAT" "$SENDER" daily_digest "$MP3"
  python3 - "$SRV/request.json" "$CHAT" <<'PY' && ok "environment-first precedence covers compatibility alias" || bad "environment-first precedence covers compatibility alias"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); b = bytes.fromhex(d["body_hex"])
assert d["path"] == "/botenv-alias-token/sendAudio" and sys.argv[2].encode() in b
PY

  printf 'delay' >"$SRV/mode"
  run_sender >"$TMP/delay-out" 2>"$TMP/delay-err" & sender_pid=$!
  sleep 0.15
  argv=$(ps -o command= -p "$sender_pid" 2>/dev/null || true)
  wait "$sender_pid" 2>/dev/null || true
  if [[ "$argv" == *"$TOKEN"* ]]; then bad "token absent from sender/child argv"; else ok "token absent from sender/child argv"; fi
fi

echo
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
