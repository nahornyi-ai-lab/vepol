#!/usr/bin/env bash
# Tests for the mail-people/v1 senders-identity envelope (People Notebook C1).
#
# The same single kb-mail-brief run that writes the brief envelope additionally
# writes $HUB/personal/mail/people/<date>-<period>.json: per unique sender
# (lowercased address) ONLY identity fields — never subjects/bodies/snippets.
# The brief envelope must remain byte-identical to the pre-change golden.
#
# Spec: the People Notebook v1 spec (dev KB, decisions/people-notebook-spec-2026-07-04.md) (D2)
# Plan: its build plan (decisions/people-notebook-build-plan-2026-07-05.md) (C1)
#
# Usage:
#   bash ~/knowledge/bin/tests/test-mail-people-envelope.sh
#   KB_MAIL_SRC_BIN=<dir> bash ...   # test a copied/seed distribution

set -uo pipefail

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

SRC_BIN="${KB_MAIL_SRC_BIN:-$HOME/knowledge/bin}"
BRIEF="$SRC_BIN/kb-mail-brief"
FIXTURES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fixtures/mail-people"
NOW="2026-07-05T06:15:00+02:00"
DAY="2026-07-05"

ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

make_hub()  { local h="$TMP/hub-$1"; mkdir -p "$h/personal"; echo "$h"; }
make_fake() {
  local d="$TMP/fake-$1"; mkdir -p "$d"; echo "$2" > "$d/mode"
  cp "$FIXTURES/threads.json" "$d/threads.json"
  echo "$d"
}

# ── P1: single run writes both envelopes; people envelope per schema ─────────
HUB=$(make_hub p1); FAKE=$(make_fake p1 ok)
KB_HUB="$HUB" KB_MAIL_FAKE_DIR="$FAKE" KB_MAIL_NOW="$NOW" \
  "$BRIEF" --period morning --write >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" ]] && ok "P1: exit 0" || fail "P1: exit $RC"

PF="$HUB/personal/mail/people/$DAY-morning.json"
BF="$HUB/personal/mail/briefs/$DAY-morning.json"
[[ -f "$PF" ]] && ok "P1: people envelope written by the same run" || fail "P1: no people envelope file"
[[ -f "$BF" ]] && ok "P1: brief envelope still written" || fail "P1: brief envelope missing"

MODE=$(stat -f "%Lp" "$PF" 2>/dev/null || stat -c "%a" "$PF" 2>/dev/null)
[[ "$MODE" == "600" ]] && ok "P1: people file mode 0600" || fail "P1: people file mode $MODE"

python3 - "$PF" <<'PY' && ok "P1: schema + sender aggregation correct" || fail "P1: people envelope assertions"
import json, sys
env = json.load(open(sys.argv[1]))
assert set(env.keys()) == {"schema", "date", "period", "generated_at", "available", "senders"}, env.keys()
assert env["schema"] == "mail-people/v1"
assert env["date"] == "2026-07-05" and env["period"] == "morning"
assert env["available"] is True
# t-1 + t-2 are the same person by lowercased address; t-4 has no address.
assert len(env["senders"]) == 2, [s["address"] for s in env["senders"]]
by_addr = {s["address"]: s for s in env["senders"]}
jane = by_addr["jane@example.com"]
assert jane["count"] == 2
assert jane["name"] == "Jane Doe"
assert jane["domain"] == "example.com"
assert jane["first_ts"] == "2026-07-05T04:11:00"
assert jane["last_ts"] == "2026-07-05T05:50:00"
news = by_addr["noreply@newsletter.example"]
assert news["count"] == 1 and news["domain"] == "newsletter.example"
for s in env["senders"]:
    assert set(s.keys()) == {"name", "address", "domain", "first_ts", "last_ts", "count"}, s.keys()
print("ok")
PY

# no message content in the people envelope, ever
if grep -q "SECRET-TOKEN\|Intro from the conference\|weekly digest\|subject" "$PF" 2>/dev/null; then
  fail "P1: message content/subject leaked into people envelope"
else
  ok "P1: no subject/body content in people envelope"
fi

# ── P2: brief envelope byte-identical to the pre-change golden ───────────────
if cmp -s "$BF" "$FIXTURES/golden-brief-$DAY-morning.json"; then
  ok "P2: brief envelope byte-identical to pre-change golden"
else
  fail "P2: brief envelope bytes changed vs golden"
fi

# sender addresses still never leak into the BRIEF envelope
if grep -qi "jane@example.com\|noreply@newsletter.example" "$BF" 2>/dev/null; then
  fail "P2: sender address leaked into brief envelope"
else
  ok "P2: no sender address in brief envelope"
fi

# ── P3: Gmail unavailable → available:false, senders [], exit 0 ──────────────
HUB=$(make_hub p3); FAKE=$(make_fake p3 unavailable)
KB_HUB="$HUB" KB_MAIL_FAKE_DIR="$FAKE" KB_MAIL_NOW="$NOW" \
  "$BRIEF" --period evening --write >/dev/null 2>&1
RC=$?
PF="$HUB/personal/mail/people/$DAY-evening.json"
[[ "$RC" == "0" ]] && ok "P3: unavailable run exits 0" || fail "P3: exit $RC"
python3 - "$PF" <<'PY' && ok "P3: unavailable → available:false, senders []" || fail "P3: unavailable people envelope"
import json, sys
env = json.load(open(sys.argv[1]))
assert env["available"] is False
assert env["senders"] == []
assert env["period"] == "evening"
print("ok")
PY

# ── P4: strict validation mirrors validate_envelope strictness ───────────────
python3 - "$SRC_BIN" <<'PY' && ok "P4: validate_people_envelope strictness" || fail "P4: validation strictness"
import sys, copy
sys.path.insert(0, sys.argv[1])
from _kb_mail.people import build_people_envelope, validate_people_envelope

def base():
    return build_people_envelope(
        period="morning", day="2026-07-05",
        generated_at="2026-07-05T06:15:00+02:00",
        senders=[{"name": "Jane Doe", "address": "jane@example.com",
                  "domain": "example.com", "first_ts": "2026-07-05T04:11:00",
                  "last_ts": "2026-07-05T05:50:00", "count": 2}],
        available=True)

assert validate_people_envelope(base()), "clean envelope must validate"

def broken(mut):
    env = copy.deepcopy(base()); mut(env)
    return not validate_people_envelope(env)

# unknown keys rejected at both levels
assert broken(lambda e: e.update(extra=1)), "unknown top-level key accepted"
assert broken(lambda e: e["senders"][0].update(subject="hi")), "subject field accepted"
assert broken(lambda e: e["senders"][0].update(body="hi")), "body field accepted"
assert broken(lambda e: e["senders"][0].update(snippet="hi")), "snippet field accepted"
# missing keys rejected
assert broken(lambda e: e.pop("available")), "missing key accepted"
assert broken(lambda e: e["senders"][0].pop("domain")), "missing sender key accepted"
# type/shape strictness
assert broken(lambda e: e.update(schema="mail-brief/v1")), "wrong schema accepted"
assert broken(lambda e: e.update(period="noon")), "bad period accepted"
assert broken(lambda e: e.update(date="07/05/2026")), "bad date accepted"
assert broken(lambda e: e.update(available="yes")), "non-bool available accepted"
assert broken(lambda e: e.update(senders={})), "non-list senders accepted"
assert broken(lambda e: e["senders"][0].update(count=0)), "count 0 accepted"
assert broken(lambda e: e["senders"][0].update(count=True)), "bool count accepted"
# address discipline
assert broken(lambda e: e["senders"][0].update(address="Jane@Example.com")), "non-lowercase address accepted"
assert broken(lambda e: e["senders"][0].update(address="not-an-address")), "junk address accepted"
assert broken(lambda e: e["senders"][0].update(domain="other.com")), "domain/address mismatch accepted"
# duplicate lowercased addresses rejected
def dup(e):
    e["senders"].append(dict(e["senders"][0]))
assert broken(dup), "duplicate address accepted"
# name discipline: bounded, no markup, no embedded address
assert broken(lambda e: e["senders"][0].update(name="x" * 201)), "oversized name accepted"
assert broken(lambda e: e["senders"][0].update(name="<script>")), "markup name accepted"
assert broken(lambda e: e["senders"][0].update(name="jane jane@example.com")), "address inside name accepted"
# available:false must carry zero senders
def unavail(e):
    e["available"] = False
assert broken(unavail), "available:false with senders accepted"
print("ok")
PY

# ── P5: collector sanitizes hostile sender fields before they persist ────────
HUB=$(make_hub p5); FAKE="$TMP/fake-p5"; mkdir -p "$FAKE"; echo ok > "$FAKE/mode"
cat > "$FAKE/threads.json" <<'JSON'
[
  {
    "thread_ref": "t-h", "message_ref": "m-h",
    "date": "2026-07-05", "time": "05:00",
    "sender_label": "Evil <b>Bold</b> evil@attacker.example person",
    "sender_email": "EVIL@Attacker.Example",
    "subject": "hi", "body": "x",
    "classification": "unknown", "urgency": "normal", "action_needed": false,
    "summary": "s", "proposed_actions": [], "privacy_flags": [], "confidence": "low"
  },
  {
    "thread_ref": "t-j", "message_ref": "m-j",
    "date": "2026-07-05", "time": "05:01",
    "sender_label": "No Address Junk", "sender_email": "not an address",
    "subject": "hi", "body": "x",
    "classification": "unknown", "urgency": "normal", "action_needed": false,
    "summary": "s", "proposed_actions": [], "privacy_flags": [], "confidence": "low"
  }
]
JSON
KB_HUB="$HUB" KB_MAIL_FAKE_DIR="$FAKE" KB_MAIL_NOW="$NOW" \
  "$BRIEF" --period morning --write >/dev/null 2>&1
RC=$?
PF="$HUB/personal/mail/people/$DAY-morning.json"
[[ "$RC" == "0" ]] && ok "P5: hostile fixture run exits 0" || fail "P5: exit $RC"
python3 - "$PF" <<'PY' && ok "P5: hostile name sanitized, junk address dropped, address lowercased" || fail "P5: sanitization"
import json, sys
env = json.load(open(sys.argv[1]))
assert env["available"] is True
assert len(env["senders"]) == 1, [s["address"] for s in env["senders"]]
s = env["senders"][0]
assert s["address"] == "evil@attacker.example", s["address"]
assert "<" not in s["name"] and ">" not in s["name"], s["name"]
assert "@" not in s["name"], s["name"]
print("ok")
PY

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
