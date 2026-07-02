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
