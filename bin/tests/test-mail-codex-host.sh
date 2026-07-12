#!/usr/bin/env bash
# CodexHostRunner must never treat a FAILED read as success (Codex stop-review:
# "Codex mail host can silently treat failed reads as successful"). Two guards:
#   1. a non-zero `codex exec` exit is a failure even if stdout carries ok:true;
#   2. the envelope is shape-validated, so a stray {"ok": true} fragment in
#      Codex's noisy guidance/trace is not latched onto as a real read.
#
# Spec: knowledge/decisions/mail-briefing-integration-2026-06-29.md

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MAIL_SRC_BIN:-$HOME/knowledge/bin}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# ── returncode guard: a fake codex that prints ok:true but EXITS 1 ───────────
cat > "$TMP/codex-fail" <<'SH'
#!/bin/sh
echo '{"ok": true, "items": [{"thread_ref": "t"}], "stats": {"n_items": 1}}'
exit 1
SH
chmod +x "$TMP/codex-fail"
cat > "$TMP/codex-ok" <<'SH'
#!/bin/sh
echo 'plugin guidance blah blah'
echo '{"ok": true, "items": [{"thread_ref": "t"}], "stats": {"n_items": 1}}'
echo 'tokens used'
exit 0
SH
chmod +x "$TMP/codex-ok"

KB_MAIL_SRC_BIN="$SRC_BIN" CODEX_FAIL="$TMP/codex-fail" CODEX_OK="$TMP/codex-ok" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["KB_MAIL_SRC_BIN"])
from _kb_mail.host import CodexHostRunner, _extract_envelope, _is_envelope
from _kb_mail.errors import MailUnavailable

P = F = 0
def check(c, m):
    global P, F
    print(("  ✓ " if c else "  ✗ ") + m)
    P += bool(c); F += (not c)

# 1) failed read (exit 1) with ok:true stdout -> MUST raise, not "succeed"
os.environ["KB_CODEX_BIN"] = os.environ["CODEX_FAIL"]
try:
    CodexHostRunner().call("x", timeout_s=10); check(False, "exit 1 + ok:true stdout raised")
except MailUnavailable:
    check(True, "failed read (exit 1) not treated as success")

# 2) clean exit 0 with a valid envelope in noisy output -> returns it
os.environ["KB_CODEX_BIN"] = os.environ["CODEX_OK"]
try:
    env = CodexHostRunner().call("x", timeout_s=10)
    check(env.get("ok") is True and env["stats"]["n_items"] == 1, "clean run returns the real envelope")
except Exception as e:
    check(False, f"clean run raised {e!r}")

# 3) shape validation: a bare {"ok": true} fragment is NOT a real envelope
check(_extract_envelope('{"ok": true}') is None, "bare {ok:true} (no items) rejected by extractor")
check(_is_envelope({"ok": True, "items": []}), "ok:true + items list accepted")
check(not _is_envelope({"ok": True}), "ok:true without items rejected")
check(_is_envelope({"ok": False, "error": "auth"}), "ok:false + error accepted")
check(not _is_envelope({"ok": False}), "ok:false without error rejected")

# 3b) MULTI-LINE / pretty-printed envelope in noisy output must be extracted
ml = ('some guidance\ncodex\n{\n  "ok": true,\n  "items": [{"thread_ref": "t"}],\n'
      '  "stats": {"n_items": 1}\n}\nhook: Stop\ntokens used\n42')
_e = _extract_envelope(ml)
check(_e is not None and _e["stats"]["n_items"] == 1, "multi-line pretty-printed envelope extracted")
two = ml + '\n{\n  "ok": true,\n  "items": [{}, {}],\n  "stats": {"n_items": 2}\n}'
check((_extract_envelope(two) or {}).get("stats", {}).get("n_items") == 2, "last multi-line envelope wins")
check(_extract_envelope('{\n  "ok": true\n}') is None, "multi-line bare {ok:true} still rejected")

# 4) injected runner returning no envelope -> raises
try:
    CodexHostRunner(runner=lambda p, t: "no json here at all").call("x")
    check(False, "no-envelope output raised")
except MailUnavailable:
    check(True, "no-envelope output raises MailUnavailable")

print(f"\nPASS={P} FAIL={F}")
sys.exit(1 if F else 0)
PY
rc=$?
[[ $rc -eq 0 ]] && ok "codex-host guards all pass" || fail "codex-host guards failed"

# ── process-group timeout: descendant holds inherited pipes ─────────────────
# Old subprocess.run(timeout=...) kills only the leader and then blocks while a
# descendant keeps stdout/stderr open. The fixed runner owns a process group and
# returns a typed timeout within the bounded cleanup grace.
cat > "$TMP/codex-descendant" <<'SH'
#!/bin/sh
(sleep 30) &
echo $! >"$KB_TEST_CHILD_PID_FILE"
sleep 30
SH
chmod +x "$TMP/codex-descendant"

KB_MAIL_SRC_BIN="$SRC_BIN" KB_CODEX_BIN="$TMP/codex-descendant" \
KB_TEST_CHILD_PID_FILE="$TMP/child.pid" \
/usr/bin/perl -e 'alarm shift; exec @ARGV' 6 python3 - <<'PY'
import os, sys, time
sys.path.insert(0, os.environ["KB_MAIL_SRC_BIN"])
from _kb_mail.errors import MailUnavailable
from _kb_mail.host import CodexHostRunner

started = time.monotonic()
try:
    CodexHostRunner().call("x", timeout_s=1)
    raise SystemExit("timeout call unexpectedly succeeded")
except MailUnavailable as exc:
    elapsed = time.monotonic() - started
    assert "timeout after 1s" in str(exc), str(exc)
    assert "process_group_gone=true" in str(exc), str(exc)
    assert elapsed < 5.0, elapsed
PY
timeout_rc=$?
if [[ -s "$TMP/child.pid" ]]; then
  child_pid=$(cat "$TMP/child.pid")
  if kill -0 "$child_pid" 2>/dev/null; then
    child_state=$(ps -o stat= -p "$child_pid" 2>/dev/null | tr -d ' ' || true)
    if [[ "$child_state" == Z* ]]; then
      child_alive=0
    else
      kill -9 "$child_pid" 2>/dev/null || true
      child_alive=1
    fi
  else
    child_alive=0
  fi
else
  child_alive=1
fi
[[ $timeout_rc -eq 0 && $child_alive -eq 0 ]] \
  && ok "timeout kills owned process group and closes descendant-held pipes" \
  || fail "timeout leaked/hung descendant (rc=$timeout_rc child_alive=$child_alive)"

# Runtime budgets are checked through the injectable host seam — the test never
# sleeps 240/300 seconds.
KB_MAIL_SRC_BIN="$SRC_BIN" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["KB_MAIL_SRC_BIN"])
from _kb_mail import adapter

calls = []
class Host:
    def call(self, prompt, *, timeout_s):
        calls.append((prompt, timeout_s))
        if "transcription step" in prompt:
            return {"ok": True, "items": [{"thread_ref":"t", "message_ref":"m",
                    "date":"2026-07-11", "time":"10:00", "sender_label":"x",
                    "sender_email":"x@example.com", "subject":"s", "body_raw":"b"}]}
        return {"ok": True, "items": [{"index":0, "classification":"fyi",
                "urgency":"low", "action_needed":False, "summary":"s",
                "proposed_actions":[], "privacy_flags":[], "confidence":"high"}]}

adapter.ProductionBackend(host=Host()).fetch("morning", {"from":"a", "to":"b"})
assert [timeout for _, timeout in calls] == [240, 300], calls
PY
[[ $? -eq 0 ]] && ok "read/classify budgets are 240s/300s" \
  || fail "mail phase budgets are not 240s/300s"

# Phase attribution remains visible inside the typed MailUnavailable boundary.
KB_MAIL_SRC_BIN="$SRC_BIN" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["KB_MAIL_SRC_BIN"])
from _kb_mail.adapter import ProductionBackend
from _kb_mail.errors import MailUnavailable

class HostRead:
    def call(self, prompt, *, timeout_s):
        raise RuntimeError("boom")

try:
    ProductionBackend(host=HostRead()).fetch("morning", {"from":"a", "to":"b"})
except MailUnavailable as exc:
    assert str(exc).startswith("read:"), str(exc)
else:
    raise AssertionError("read failure was not typed")

class HostClassify:
    calls = 0
    def call(self, prompt, *, timeout_s):
        self.calls += 1
        if self.calls == 1:
            return {"ok": True, "items": [{"thread_ref":"t", "message_ref":"m",
                    "date":"2026-07-11", "time":"10:00", "sender_label":"x",
                    "sender_email":"x@example.com", "subject":"s", "body_raw":"b"}]}
        raise RuntimeError("boom")

try:
    ProductionBackend(host=HostClassify()).fetch("morning", {"from":"a", "to":"b"})
except MailUnavailable as exc:
    assert str(exc).startswith("classify:"), str(exc)
else:
    raise AssertionError("classify failure was not typed")
PY
[[ $? -eq 0 ]] && ok "mail failures record read/classify phase attribution" \
  || fail "mail phase attribution missing"

# Cleanup race seams: an already-exited leader/group and a second communicate
# timeout remain bounded, close inherited pipes, and report the saved PGID gone.
KB_MAIL_SRC_BIN="$SRC_BIN" python3 - <<'PY'
import os, signal, subprocess, sys
sys.path.insert(0, os.environ["KB_MAIL_SRC_BIN"])
import _kb_mail.host as host

class Pipe:
    def __init__(self): self.closed = False
    def close(self): self.closed = True

class Proc:
    def __init__(self):
        self.stdout, self.stderr = Pipe(), Pipe()
        self.calls = 0
        self.killed = False
    def communicate(self, timeout):
        self.calls += 1
        raise subprocess.TimeoutExpired("fake", timeout)
    def kill(self): self.killed = True
    def wait(self, timeout): return 0

proc = Proc()
orig = host.os.killpg
def gone(pgid, sig):
    raise ProcessLookupError
host.os.killpg = gone
try:
    assert host._best_effort_kill_group(proc, 424242) is True
finally:
    host.os.killpg = orig
assert proc.killed and proc.stdout.closed and proc.stderr.closed

proc = Proc()
def denied(pgid, sig):
    raise PermissionError("denied")
host.os.killpg = denied
try:
    assert host._best_effort_kill_group(proc, 424243) is False
finally:
    host.os.killpg = orig
assert proc.killed and proc.stdout.closed and proc.stderr.closed
PY
[[ $? -eq 0 ]] && ok "cleanup races stay bounded and probe the saved process group" \
  || fail "cleanup race/probe contract failed"

# A timeout envelope must not advance either watermark byte; the next clean run
# catches up from the same lower bound and advances only after durable success.
WM_HUB="$TMP/watermark-hub"; WM_FAKE="$TMP/watermark-fake"
mkdir -p "$WM_HUB/personal/mail" "$WM_FAKE"
printf '{"morning":"2026-07-09T06:00:00+02:00","evening":"2026-07-09T20:00:00+02:00"}\n' \
  > "$WM_HUB/personal/mail/watermarks.json"
cp "$WM_HUB/personal/mail/watermarks.json" "$TMP/watermarks.before"
WM_OUT=$(KB_HUB="$WM_HUB" KB_CODEX_BIN="$TMP/codex-descendant" \
  KB_TEST_CHILD_PID_FILE="$TMP/wm-child.pid" \
  KB_MAIL_NOW="2026-07-11T12:00:00+02:00" \
  python3 - "$SRC_BIN" <<'PY'
import importlib.machinery, importlib.util, pathlib, sys
src = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(src))
from _kb_mail import adapter
adapter._READ_TIMEOUT_S = 1
loader = importlib.machinery.SourceFileLoader("mail_timeout_e2e", str(src / "kb-mail-brief"))
spec = importlib.util.spec_from_loader("mail_timeout_e2e", loader)
brief = importlib.util.module_from_spec(spec)
sys.modules["mail_timeout_e2e"] = brief
loader.exec_module(brief)
sys.argv = ["kb-mail-brief", "--period", "morning", "--write", "--json"]
raise SystemExit(brief.main())
PY
)
cmp -s "$TMP/watermarks.before" "$WM_HUB/personal/mail/watermarks.json"
wm_timeout_rc=$?
printf 'ok\n' > "$WM_FAKE/mode"
printf '[]\n' > "$WM_FAKE/threads.json"
WM_OK=$(KB_HUB="$WM_HUB" KB_MAIL_FAKE_DIR="$WM_FAKE" \
  KB_MAIL_NOW="2026-07-11T12:05:00+02:00" \
  "$SRC_BIN/kb-mail-brief" --period morning --write --json)
WM_OUT="$WM_OUT" WM_OK="$WM_OK" python3 - <<'PY'
import json, os
bad = json.loads(os.environ["WM_OUT"])
good = json.loads(os.environ["WM_OK"])
assert bad["available"] is False and bad["watermark"] is None
assert bad["errors"] == ["gmail_unavailable:timeout"], bad
assert good["available"] is True
assert good["window"]["from"] == "2026-07-09T20:00:00+02:00", good
assert good["watermark"] == "2026-07-11T12:05:00+02:00", good
PY
wm_catchup_rc=$?
[[ $wm_timeout_rc -eq 0 && $wm_catchup_rc -eq 0 ]] \
  && ok "timeout preserves watermark; next success catches up and advances" \
  || fail "timeout/catch-up watermark contract failed"

# ── kb-mail-brief must NEVER exit non-zero on bad mail-host output ────────────
# A malformed / junk Codex response must degrade to available:false (exit 0), so
# it can never block daily/retro (which run after:mail-*).
HUB="$TMP/hub"; mkdir -p "$HUB/personal"
BRIEF="$SRC_BIN/kb-mail-brief"

cat > "$TMP/codex-garbage" <<'SH'
#!/bin/sh
echo "totally not json — a confused model just wrote prose"
exit 0
SH
chmod +x "$TMP/codex-garbage"
OUT=$(KB_HUB="$HUB" KB_CODEX_BIN="$TMP/codex-garbage" KB_MAIL_NOW="2026-07-02T06:15:00+02:00" \
      "$BRIEF" --period morning --write --json 2>/dev/null); RC=$?
python3 -c "import json,sys;e=json.loads(sys.argv[1]);sys.exit(0 if (sys.argv[2]=='0' and e['available'] is False) else 1)" "$OUT" "$RC" \
  && ok "garbage host output -> available:false, exit 0 (morning not blocked)" \
  || fail "garbage host output blocked/crashed (rc=$RC)"

cat > "$TMP/codex-junk-items" <<'SH'
#!/bin/sh
echo '{"ok": true, "items": ["stray", 5, {"thread_ref": "t", "subject": "s", "date": "2026-07-02", "time": "06:00"}], "stats": {"n_items": 3}}'
exit 0
SH
chmod +x "$TMP/codex-junk-items"
OUT=$(KB_HUB="$HUB" KB_CODEX_BIN="$TMP/codex-junk-items" KB_MAIL_NOW="2026-07-02T06:16:00+02:00" \
      "$BRIEF" --period morning --write --json 2>/dev/null); RC=$?
python3 -c "import json,sys;e=json.loads(sys.argv[1]);sys.exit(0 if (sys.argv[2]=='0' and e['available'] is False) else 1)" "$OUT" "$RC" \
  && ok "mixed junk+good items -> available:false, exit 0 (malformed read not trusted)" \
  || fail "mixed junk items accepted as available:true or blocked (rc=$RC)"

cat > "$TMP/codex-exit1" <<'SH'
#!/bin/sh
echo '{"ok": true, "items": [{"thread_ref":"t"}], "stats": {"n_items": 1}}'
exit 1
SH
chmod +x "$TMP/codex-exit1"
OUT=$(KB_HUB="$HUB" KB_CODEX_BIN="$TMP/codex-exit1" KB_MAIL_NOW="2026-07-02T06:17:00+02:00" \
      "$BRIEF" --period morning --write --json 2>/dev/null); RC=$?
python3 -c "import json,sys;e=json.loads(sys.argv[1]);sys.exit(0 if (sys.argv[2]=='0' and e['available'] is False) else 1)" "$OUT" "$RC" \
  && ok "host exit 1 (with ok:true stdout) -> available:false, exit 0" \
  || fail "host exit 1 blocked/crashed (rc=$RC)"

# A CLEAN read but a JUNK classify must also fail closed (symmetry). The fake
# codex answers the read phase (prompt contains "transcription step") with a
# valid dict, and the classify phase with non-dict junk.
cat > "$TMP/codex-classify-junk" <<'SH'
#!/bin/sh
case "$*" in
  *"transcription step"*)
    echo '{"ok": true, "items": [{"thread_ref": "t", "subject": "s", "date": "2026-07-02", "time": "06:00", "body_raw": "hi"}], "stats": {"n_items": 1}}' ;;
  *)
    echo '{"ok": true, "items": ["junk-classify-row", 7], "stats": {"n_items": 2}}' ;;
esac
exit 0
SH
chmod +x "$TMP/codex-classify-junk"
OUT=$(KB_HUB="$HUB" KB_CODEX_BIN="$TMP/codex-classify-junk" KB_MAIL_NOW="2026-07-02T06:18:00+02:00" \
      "$BRIEF" --period morning --write --json 2>/dev/null); RC=$?
python3 -c "import json,sys;e=json.loads(sys.argv[1]);sys.exit(0 if (sys.argv[2]=='0' and e['available'] is False) else 1)" "$OUT" "$RC" \
  && ok "clean read + junk classify -> available:false, exit 0 (classify fails closed)" \
  || fail "junk classify failed open (rc=$RC, available not false)"

# A clean read + a classify with VALID dict rows but WRONG indexes (not matching
# the read items 0..N-1) must also fail closed — no defaulting unmatched items.
cat > "$TMP/codex-badindex" <<'SH'
#!/bin/sh
case "$*" in
  *"transcription step"*)
    echo '{"ok": true, "items": [{"thread_ref": "t", "subject": "s", "date": "2026-07-02", "time": "06:00", "body_raw": "hi"}], "stats": {"n_items": 1}}' ;;
  *)
    echo '{"ok": true, "items": [{"index": 99, "classification": "fyi", "urgency": "low", "action_needed": false, "summary": "x", "proposed_actions": [], "privacy_flags": [], "confidence": "low"}], "stats": {"n_items": 1}}' ;;
esac
exit 0
SH
chmod +x "$TMP/codex-badindex"
OUT=$(KB_HUB="$HUB" KB_CODEX_BIN="$TMP/codex-badindex" KB_MAIL_NOW="2026-07-02T06:19:00+02:00" \
      "$BRIEF" --period morning --write --json 2>/dev/null); RC=$?
python3 -c "import json,sys;e=json.loads(sys.argv[1]);sys.exit(0 if (sys.argv[2]=='0' and e['available'] is False) else 1)" "$OUT" "$RC" \
  && ok "classify with wrong indexes -> available:false, exit 0 (no default-fill)" \
  || fail "classify wrong-index failed open (rc=$RC)"

# A clean 2-item read + a classify with DUPLICATE indices (two rows both index=0)
# must fail closed — a plain set would swallow the duplicate and pass.
cat > "$TMP/codex-dupindex" <<'SH'
#!/bin/sh
case "$*" in
  *"transcription step"*)
    echo '{"ok": true, "items": [{"thread_ref": "t1", "subject": "a", "date": "2026-07-02", "time": "06:00", "body_raw": "x"}, {"thread_ref": "t2", "subject": "b", "date": "2026-07-02", "time": "06:01", "body_raw": "y"}], "stats": {"n_items": 2}}' ;;
  *)
    echo '{"ok": true, "items": [{"index": 0, "classification": "fyi", "urgency": "low", "action_needed": false, "summary": "a", "proposed_actions": [], "privacy_flags": [], "confidence": "low"}, {"index": 0, "classification": "noise", "urgency": "low", "action_needed": false, "summary": "b", "proposed_actions": [], "privacy_flags": [], "confidence": "low"}], "stats": {"n_items": 2}}' ;;
esac
exit 0
SH
chmod +x "$TMP/codex-dupindex"
OUT=$(KB_HUB="$HUB" KB_CODEX_BIN="$TMP/codex-dupindex" KB_MAIL_NOW="2026-07-02T06:20:00+02:00" \
      "$BRIEF" --period morning --write --json 2>/dev/null); RC=$?
python3 -c "import json,sys;e=json.loads(sys.argv[1]);sys.exit(0 if (sys.argv[2]=='0' and e['available'] is False) else 1)" "$OUT" "$RC" \
  && ok "classify with duplicate indexes -> available:false, exit 0" \
  || fail "classify duplicate-index failed open (rc=$RC)"

echo; echo "PASS=$PASS FAIL=$FAIL"; [[ "$FAIL" == "0" ]]
