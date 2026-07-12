#!/usr/bin/env bash
# Tests for MailSource (mail-people/v1 envelopes) + kb-extract-people wiring.
#
# Covers (people-notebook build plan 2026-07-05, component C2):
#   - strict mail-people/v1 envelope validation (unknown keys rejected)
#   - per-envelope processed-watermark idempotency
#   - sender filters (bot/noreply, resource-calendar, owner-emails, .rejected.yaml)
#   - policy: known address → live sighting; new/ambiguous → staged
#   - run-level people-extraction.lock (exit code 2 on contention)
#   - digest D1 firing rule (new → send; pending-only → weekly nudge; none → nothing)
#   - --no-mail opt-out; stale --llm help text fixed
#
# All hubs are throwaway temp dirs (KB_HUB) — never the live ~/knowledge.
# Usage: bash bin/tests/test-people-mail-source.sh

set -uo pipefail

PASS=0; FAIL=0
TMPDIR_TEST=$(mktemp -d)
BIN="${KB_PEOPLE_SRC_BIN:-$HOME/knowledge/bin}"
export SRC_BIN="$BIN"
PY=python3

cleanup() { rm -rf "$TMPDIR_TEST"; }
trap cleanup EXIT

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# Build a fresh isolated hub with a fake channel binary capturing digests.
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

# Write a mail-people/v1 envelope. args: hub date period senders_json
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
  KB_HUB="$hub" $PY "$BIN/kb-extract-people" --hub "$hub" --no-llm --quiet "$@" 2>/dev/null
}

echo "=== MailSource + kb-extract-people mail wiring tests ==="

# ---------------------------------------------------------------------------
# T1: strict envelope validation
# ---------------------------------------------------------------------------
$PY - <<PYEOF
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
from _kb_people.sources import mail_source as ms

GOOD = {
    "schema": "mail-people/v1", "date": "2026-07-05", "period": "morning",
    "generated_at": "2026-07-05T06:15:00+02:00", "available": True,
    "senders": [{"name": "Jane Doe", "address": "jane@acme.com",
                 "domain": "acme.com", "first_ts": "2026-07-05T04:11:00Z",
                 "last_ts": "2026-07-05T05:50:00Z", "count": 2}],
}
assert ms.validate_envelope(GOOD) is True, "valid envelope must pass"

import copy
def bad(mut):
    env = copy.deepcopy(GOOD)
    mut(env)
    assert ms.validate_envelope(env) is False, f"must reject: {env}"

bad(lambda e: e.__setitem__("schema", "mail-brief/v1"))
bad(lambda e: e.__setitem__("extra", 1))                       # unknown top-level key
bad(lambda e: e["senders"][0].__setitem__("subject", "hi"))    # content smuggling
bad(lambda e: e["senders"][0].pop("count"))                    # missing sender key
bad(lambda e: e["senders"][0].__setitem__("count", -1))
bad(lambda e: e["senders"][0].__setitem__("count", True))      # bool is not an int count
bad(lambda e: e["senders"][0].__setitem__("name", "x" * 201))  # name cap 200
bad(lambda e: e["senders"][0].__setitem__("address", "not-an-email"))
bad(lambda e: e.__setitem__("period", "noon"))
bad(lambda e: e.__setitem__("date", "05.07.2026"))
bad(lambda e: e.__setitem__("available", "yes"))
# available:false must carry no senders
bad(lambda e: e.__setitem__("available", False))
env = copy.deepcopy(GOOD); env["available"] = False; env["senders"] = []
assert ms.validate_envelope(env) is True, "available:false with [] must pass"
# duplicate addresses (case-insensitive) rejected
env = copy.deepcopy(GOOD)
dup = dict(env["senders"][0]); dup["address"] = "JANE@acme.com"
env["senders"].append(dup)
assert ms.validate_envelope(env) is False, "dup lowercased address must fail"
print("T1_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T1: strict mail-people/v1 validation (unknown keys, bounds, dups)" || fail "T1: envelope validation"

# ---------------------------------------------------------------------------
# T2: pending_envelopes + processed-watermark
# ---------------------------------------------------------------------------
HUB2="$TMPDIR_TEST/hub-t2"; make_hub "$HUB2"
write_envelope "$HUB2" 2026-07-05 morning '[{"name": "Jane Doe", "address": "jane@acme.com", "domain": "acme.com", "first_ts": "t", "last_ts": "t", "count": 1}]'
$PY - "$HUB2" <<'PYEOF'
import json, sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
from _kb_people.sources import mail_source as ms

hub = Path(sys.argv[1])
src = ms.MailSource(hub)
pending, warnings = src.pending_envelopes()
assert len(pending) == 1, f"expected 1 pending, got {len(pending)}"
item = pending[0]
assert item["key"] == "2026-07-05-morning", item["key"]
assert len(item["sha"]) == 64

# Mark processed → gone from pending.
ms.mark_processed(hub, item["key"], item["sha"])
wm = json.loads(ms.processed_path(hub).read_text())
assert wm["schema_version"] == 1
assert wm["processed"]["2026-07-05-morning"] == item["sha"]
pending2, _ = src.pending_envelopes()
assert pending2 == [], f"processed envelope must not be pending: {pending2}"

# Rewritten envelope content (new sha) → pending again.
p = item["path"]
env = json.loads(p.read_text())
env["senders"][0]["count"] = 5
p.write_text(json.dumps(env))
pending3, _ = src.pending_envelopes()
assert len(pending3) == 1, "changed content must re-pend"

# Corrupt / invalid envelopes are warned about, never pending.
(hub / "personal/mail/people/2026-07-04-evening.json").write_text("{not json")
pending4, warn4 = src.pending_envelopes()
assert len(pending4) == 1 and warn4, "invalid file must warn, not crash"
print("T2_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T2: pending_envelopes + processed-watermark (sha-keyed, invalid warned)" || fail "T2: watermark plumbing"

# ---------------------------------------------------------------------------
# T3: sender filters (bot/noreply, resource-calendar, owner-emails)
# ---------------------------------------------------------------------------
HUB3="$TMPDIR_TEST/hub-t3"; make_hub "$HUB3"
echo "owner-self@corp.io" > "$HUB3/people/.owner-emails.txt"
$PY - "$HUB3" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
from _kb_people.sources import mail_source as ms

hub = Path(sys.argv[1])
card.PEOPLE_DIR = hub / "people"

def s(addr, name="X"):
    return {"name": name, "address": addr, "domain": addr.split("@")[1],
            "first_ts": "t", "last_ts": "t", "count": 1}

senders = [
    s("jane@acme.com", "Jane Doe"),
    s("noreply@vendor.io"),
    s("notifications@github.com"),
    s("info@somecorp.com"),
    s("room.a@resource.calendar.google.com"),
    s("owner-self@corp.io"),          # owner-self
    s("receipts@vendor.io"),          # role mailbox, not a person
    s("demo@example.com"),            # RFC-reserved doc domain — a fixture
    s("JANE.SMITH@Client.ORG", "Jane Smith"),  # lowercased on keep
]
kept, dropped = ms.MailSource(hub).filter_senders(senders)
emails = [k["email"] for k in kept]
assert emails == ["jane@acme.com", "jane.smith@client.org"], emails
assert dropped == 7, f"expected 7 dropped, got {dropped}"
assert kept[0]["name"] == "Jane Doe"
print("T3_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T3: filters drop bot/noreply/role/example-domain/resource/owner, keep + lowercase real senders" || fail "T3: sender filters"

# ---------------------------------------------------------------------------
# T4: new sender → staged card (never live), watermark written
# ---------------------------------------------------------------------------
HUB4="$TMPDIR_TEST/hub-t4"; make_hub "$HUB4"
write_envelope "$HUB4" 2026-07-05 morning '[{"name": "New Person", "address": "new.person@startup.io", "domain": "startup.io", "first_ts": "t", "last_ts": "t", "count": 3}]'
run_extract "$HUB4"
RC=$?
STAGED="$HUB4/people/new-person.staged.md"
if [[ $RC -eq 0 && -f "$STAGED" && ! -f "$HUB4/people/new-person.md" ]] \
   && grep -q "mail:morning-2026-07-05" "$STAGED" \
   && grep -q "source: mail" "$STAGED" \
   && grep -q "draft: true" "$STAGED" \
   && grep -q "2026-07-05-morning" "$HUB4/people/.mail-envelopes-processed.json"; then
  ok "T4: new sender → staged card with mail:<period>-<date> ref, no live card, watermark set"
else
  fail "T4: new sender staging (rc=$RC, staged=$(ls "$HUB4/people" 2>/dev/null | tr '\n' ' '))"
fi

# ---------------------------------------------------------------------------
# T5: known sender (address matches live card) → live sighting, no staged
# ---------------------------------------------------------------------------
HUB5="$TMPDIR_TEST/hub-t5"; make_hub "$HUB5"
$PY - "$HUB5" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
import _kb_people.index as idx
hub = Path(sys.argv[1])
card.PEOPLE_DIR = hub / "people"
idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Alice Johnson", email="alice@acme.com", source="manual", draft=False,
                first_met="2026-07-01", last_seen="2026-07-01")
post = card.load(p.stem)
idx.register(post["id"], p.stem, "Alice Johnson", {"email": "alice@acme.com"})
PYEOF
write_envelope "$HUB5" 2026-07-05 morning '[{"name": "Alice Johnson", "address": "alice@acme.com", "domain": "acme.com", "first_ts": "t", "last_ts": "t", "count": 2}]'
run_extract "$HUB5"
RC=$?
CARD5="$HUB5/people/alice-johnson.md"
if [[ $RC -eq 0 ]] && grep -q "mail:morning-2026-07-05" "$CARD5" \
   && ! ls "$HUB5/people/"*.staged*.md >/dev/null 2>&1 \
   && grep -q "last_seen: '2026-07-05'\|last_seen: 2026-07-05" "$CARD5"; then
  ok "T5: known address → live sighting upsert (mail:<period>-<date>), nothing staged"
else
  fail "T5: known-sender live sighting (rc=$RC)"
fi
# No message content anywhere: card must not contain subject-like text, only counts
if grep -q "2 messages" "$CARD5" 2>/dev/null; then
  ok "T5b: sighting summary is count metadata only"
else
  fail "T5b: sighting summary metadata (got: $(grep 'mail:' "$CARD5" 2>/dev/null))"
fi

# ---------------------------------------------------------------------------
# T6: idempotency — reprocessing the same envelope proposes nothing
# ---------------------------------------------------------------------------
HUB6="$TMPDIR_TEST/hub-t6"; make_hub "$HUB6"
write_envelope "$HUB6" 2026-07-05 morning '[{"name": "Repeat Person", "address": "repeat@corp.io", "domain": "corp.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB6"
KB_HUB="$HUB6" $PY "$BIN/kb-extract-people" --hub "$HUB6" --approve repeat-person >/dev/null 2>&1
# Live card now exists; staged is gone. Re-run: same envelope must NOT re-propose,
# and must NOT add a live sighting either (watermark short-circuits the envelope).
BEFORE=$(cat "$HUB6/people/repeat-person.md" 2>/dev/null)
run_extract "$HUB6"
RC=$?
AFTER=$(cat "$HUB6/people/repeat-person.md" 2>/dev/null)
if [[ $RC -eq 0 && -f "$HUB6/people/repeat-person.md" && "$BEFORE" == "$AFTER" ]] \
   && ! ls "$HUB6/people/"*.staged*.md >/dev/null 2>&1; then
  ok "T6: re-run after approve re-proposes nothing (per-envelope watermark)"
else
  fail "T6: envelope idempotency (rc=$RC)"
fi

# ---------------------------------------------------------------------------
# T7: ambiguous (name matches existing card, new address) → staged w/ dup hint
# ---------------------------------------------------------------------------
HUB7="$TMPDIR_TEST/hub-t7"; make_hub "$HUB7"
$PY - "$HUB7" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
import _kb_people.index as idx
hub = Path(sys.argv[1])
card.PEOPLE_DIR = hub / "people"
idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Bob Smith", email="bob@vendor.io", source="manual", draft=False)
post = card.load(p.stem)
idx.register(post["id"], p.stem, "Bob Smith", {"email": "bob@vendor.io"})
PYEOF
write_envelope "$HUB7" 2026-07-05 morning '[{"name": "Bob Smith", "address": "bob.smith@personal.email", "domain": "personal.email", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB7"
STAGED7=$(ls "$HUB7/people/"*.staged.md 2>/dev/null | head -1)
if [[ -n "$STAGED7" ]] && grep -q "possible_duplicate_of: bob-smith" "$STAGED7" \
   && ! grep -q "bob.smith@personal.email" "$HUB7/people/bob-smith.md"; then
  ok "T7: same-name new-address → staged with possible_duplicate_of, never auto-merged"
else
  fail "T7: ambiguous sender staging"
fi

# ---------------------------------------------------------------------------
# T8: run lock contention → exit code 2
# ---------------------------------------------------------------------------
HUB8="$TMPDIR_TEST/hub-t8"; make_hub "$HUB8"
mkdir -p "$HUB8/.orchestrator/locks"
LOCKFILE="$HUB8/.orchestrator/locks/people-extraction.lock"
$PY - "$LOCKFILE" <<'PYEOF' &
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
# Signal the parent that the lock is held.
open(sys.argv[1] + ".held", "w").write("1")
time.sleep(15)
PYEOF
HOLDER=$!
for _ in $(seq 1 50); do [[ -f "$LOCKFILE.held" ]] && break; sleep 0.1; done
run_extract "$HUB8"
RC=$?
kill "$HOLDER" 2>/dev/null; wait "$HOLDER" 2>/dev/null
if [[ $RC -eq 2 ]]; then
  ok "T8: held people-extraction.lock → second run exits 2 (contention)"
else
  fail "T8: lock contention exit code (got rc=$RC, want 2)"
fi

# ---------------------------------------------------------------------------
# T9: --no-mail opt-out
# ---------------------------------------------------------------------------
HUB9="$TMPDIR_TEST/hub-t9"; make_hub "$HUB9"
write_envelope "$HUB9" 2026-07-05 morning '[{"name": "Skip Me", "address": "skip.me@corp.io", "domain": "corp.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB9" --no-mail
RC=$?
if [[ $RC -eq 0 ]] && ! ls "$HUB9/people/"*.staged*.md >/dev/null 2>&1 \
   && [[ ! -f "$HUB9/people/.mail-envelopes-processed.json" ]]; then
  ok "T9: --no-mail skips envelopes entirely (nothing staged, watermark untouched)"
else
  fail "T9: --no-mail opt-out (rc=$RC)"
fi

# ---------------------------------------------------------------------------
# T10: .rejected.yaml sender never staged
# ---------------------------------------------------------------------------
HUB10="$TMPDIR_TEST/hub-t10"; make_hub "$HUB10"
cat > "$HUB10/people/.rejected.yaml" <<'EOF'
- email: spammy@vendor.io
  reason: manual-reject
EOF
write_envelope "$HUB10" 2026-07-05 morning '[{"name": "Spammy Vendor", "address": "spammy@vendor.io", "domain": "vendor.io", "first_ts": "t", "last_ts": "t", "count": 4}]'
run_extract "$HUB10"
# Non-vacuous: the envelope must actually have been processed (watermark set),
# yet nothing staged for the rejected identity.
if [[ -f "$HUB10/people/.mail-envelopes-processed.json" ]] \
   && grep -q "2026-07-05-morning" "$HUB10/people/.mail-envelopes-processed.json" \
   && ! ls "$HUB10/people/"*.staged*.md >/dev/null 2>&1; then
  ok "T10: .rejected.yaml identity dropped before staging (envelope still processed)"
else
  fail "T10: rejected sender handling"
fi

# ---------------------------------------------------------------------------
# T11: digest D1 firing rule
# ---------------------------------------------------------------------------
HUB11="$TMPDIR_TEST/hub-t11"; make_hub "$HUB11"
write_envelope "$HUB11" 2026-07-05 morning '[{"name": "Digest Person", "address": "digest.person@corp.io", "domain": "corp.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
# (a) new items this run → digest sent, with mail counts
KB_PROCESS_OUTPUTS=telegram run_extract "$HUB11"
if [[ -f "$HUB11/sent.log" ]] && grep -qi "mail" "$HUB11/sent.log"; then
  ok "T11a: new items → digest sent with mail counts"
else
  fail "T11a: new-items digest (sent.log: $(cat "$HUB11/sent.log" 2>/dev/null))"
fi
# (b) re-run: zero new, pending > 0, last digest today → silent
rm -f "$HUB11/sent.log"
KB_PROCESS_OUTPUTS=telegram run_extract "$HUB11"
if [[ ! -f "$HUB11/sent.log" ]]; then
  ok "T11b: zero new + pending, recent digest → silent"
else
  fail "T11b: expected silence, got: $(cat "$HUB11/sent.log")"
fi
# (c) last digest ≥7 days ago → weekly nudge fires
$PY - "$HUB11" <<'PYEOF'
import datetime, json, sys
from pathlib import Path
old = (datetime.date.today() - datetime.timedelta(days=8)).isoformat()
p = Path(sys.argv[1]) / "people" / ".digest-state.json"
p.write_text(json.dumps({"schema_version": 1, "last_sent": old}))
PYEOF
KB_PROCESS_OUTPUTS=telegram run_extract "$HUB11"
if [[ -f "$HUB11/sent.log" ]]; then
  ok "T11c: pending untouched for 7+ days → weekly nudge sent"
else
  fail "T11c: weekly nudge missing"
fi
# (d) nothing new, nothing pending → nothing
HUB11D="$TMPDIR_TEST/hub-t11d"; make_hub "$HUB11D"
KB_PROCESS_OUTPUTS=telegram run_extract "$HUB11D"
if [[ ! -f "$HUB11D/sent.log" ]]; then
  ok "T11d: nothing new + nothing pending → nothing sent"
else
  fail "T11d: unexpected send: $(cat "$HUB11D/sent.log")"
fi

# ---------------------------------------------------------------------------
# T12: stale --llm argparse help fixed
# ---------------------------------------------------------------------------
HELP=$($PY "$BIN/kb-extract-people" --help 2>&1)
if ! grep -q "not yet implemented" <<<"$HELP" && grep -q -- "--no-mail" <<<"$HELP"; then
  ok "T12: --llm help no longer claims 'not yet implemented'; --no-mail documented"
else
  fail "T12: stale argparse help"
fi

# ---------------------------------------------------------------------------
# T13: approve never clobbers an existing live card (slug collision)
# ---------------------------------------------------------------------------
HUB13="$TMPDIR_TEST/hub-t13"; make_hub "$HUB13"
cat > "$HUB13/people/jane-doe.md" <<'EOF'
---
name: Jane Doe
slug: jane-doe
email: jane@realjane.com
draft: false
---

## Notes
<!-- MANUAL-NOTES-BEGIN -->
owner's precious manual notes
<!-- MANUAL-NOTES-END -->
EOF
write_envelope "$HUB13" 2026-07-05 morning '[{"name": "Jane Doe", "address": "jane.doe@impostor.io", "domain": "impostor.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB13"
if [[ -f "$HUB13/people/jane-doe.staged.md" ]]; then
  $PY "$BIN/kb-extract-people" --hub "$HUB13" --approve jane-doe >/dev/null 2>&1
  # A2: the promoted card must be registered in _index.yaml in the SAME
  # step (atomic card write + register), so future extraction dedups on it.
  IDX_OK=no
  if grep -q "jane.doe@impostor.io" "$HUB13/people/_index.yaml" 2>/dev/null; then IDX_OK=yes; fi
  if grep -q "owner's precious manual notes" "$HUB13/people/jane-doe.md" \
     && grep -q "jane@realjane.com" "$HUB13/people/jane-doe.md" \
     && ls "$HUB13/people/"jane-doe-*.md >/dev/null 2>&1 \
     && [[ "$IDX_OK" == "yes" ]]; then
    ok "T13: approve with slug collision keeps live card, promotes + indexes under suffixed slug"
  else
    fail "T13: live card clobbered / suffixed promotion missing / not indexed (idx=$IDX_OK)"
  fi
else
  fail "T13: expected staged card jane-doe.staged.md ($(ls "$HUB13/people"))"
fi

# ---------------------------------------------------------------------------
# T14: same display name, different address, pending staged → separate staged
# ---------------------------------------------------------------------------
HUB14="$TMPDIR_TEST/hub-t14"; make_hub "$HUB14"
write_envelope "$HUB14" 2026-07-05 morning '[{"name": "Alex Smith", "address": "alex@firstco.com", "domain": "firstco.com", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB14"
write_envelope "$HUB14" 2026-07-06 morning '[{"name": "Alex Smith", "address": "alex@otherco.io", "domain": "otherco.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB14"
STAGED_COUNT=$(ls "$HUB14/people/"*.staged.md 2>/dev/null | wc -l | tr -d ' ')
if [[ "$STAGED_COUNT" == "2" ]] \
   && grep -q "alex@firstco.com" "$HUB14/people/alex-smith.staged.md" \
   && ! grep -q "alex@otherco.io" "$HUB14/people/alex-smith.staged.md"; then
  ok "T14: same-name different-address sender staged separately (no identity merge)"
else
  fail "T14: expected 2 distinct staged cards, got $STAGED_COUNT: $(ls "$HUB14/people" 2>/dev/null)"
fi

# ---------------------------------------------------------------------------
# T15: rejecting one sender never blacklists an unrelated same-name person
# ---------------------------------------------------------------------------
HUB15="$TMPDIR_TEST/hub-t15"; make_hub "$HUB15"
cat > "$HUB15/people/.rejected.yaml" <<'EOF'
- name: Alex Smith
  email: spam@blast.io
  reason: manual-reject
  rejected_at: '2026-07-01'
EOF
write_envelope "$HUB15" 2026-07-05 morning '[{"name": "Alex Smith", "address": "spam@blast.io", "domain": "blast.io", "first_ts": "t", "last_ts": "t", "count": 1}, {"name": "Alex Smith", "address": "alex@goodco.com", "domain": "goodco.com", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB15"
if [[ ! -f "$HUB15/people/alex-smith.staged.md" ]]; then
  fail "T15: unrelated same-name sender was dropped ($(ls "$HUB15/people" 2>/dev/null))"
elif grep -q "alex@goodco.com" "$HUB15/people/alex-smith.staged.md" \
     && ! ls "$HUB15/people/"*.md 2>/dev/null | xargs grep -l "spam@blast.io" >/dev/null 2>&1; then
  ok "T15: rejected email dropped; unrelated same-name sender still staged"
else
  fail "T15: rejection scoping ($(ls "$HUB15/people"))"
fi

# ---------------------------------------------------------------------------
# T16: a suffixed (non-base) identity that reappears in a later envelope is
# updated in place, never re-staged as a fresh duplicate. find_existing only
# sees LIVE cards, so a same-name-different-address sender who is not the
# base-slug owner must be matched against its own pending staged sibling.
# ---------------------------------------------------------------------------
HUB16="$TMPDIR_TEST/hub-t16"; make_hub "$HUB16"
# Day 1: base identity claims the plain slug.
write_envelope "$HUB16" 2026-07-05 morning '[{"name": "Alex Smith", "address": "alex@firstco.com", "domain": "firstco.com", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB16"
# Day 2: a DIFFERENT person, same name → suffixed staged card.
write_envelope "$HUB16" 2026-07-06 morning '[{"name": "Alex Smith", "address": "alex@otherco.io", "domain": "otherco.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB16"
# Day 3: the SUFFIXED person emails again → must append to their own card,
# not mint a second suffixed duplicate.
write_envelope "$HUB16" 2026-07-07 morning '[{"name": "Alex Smith", "address": "alex@otherco.io", "domain": "otherco.io", "first_ts": "t", "last_ts": "t", "count": 2}]'
run_extract "$HUB16"
STAGED_COUNT16=$(ls "$HUB16/people/"*.staged.md 2>/dev/null | wc -l | tr -d ' ')
OTHERCO_CARDS=$(grep -l "alex@otherco.io" "$HUB16/people/"*.staged.md 2>/dev/null | wc -l | tr -d ' ')
OTHERCO_FILE=$(grep -l "alex@otherco.io" "$HUB16/people/"*.staged.md 2>/dev/null | head -1)
if [[ "$STAGED_COUNT16" == "2" && "$OTHERCO_CARDS" == "1" ]] \
   && grep -q "mail:morning-2026-07-07" "$OTHERCO_FILE"; then
  ok "T16: reappearing suffixed identity updated in place (no duplicate re-stage)"
else
  fail "T16: expected 2 staged / 1 otherco card with the day-3 sighting, got staged=$STAGED_COUNT16 otherco=$OTHERCO_CARDS ($(ls "$HUB16/people" 2>/dev/null | tr '\n' ' '))"
fi

# ---------------------------------------------------------------------------
# T17: collision approve must NOT consume a DIFFERENT live person's pending
# staged-sightings. `alex.staged.md` (person B, new) + live `alex.md` (person
# A) + `alex.staged-sightings.md` (A's pending sightings). Approving alex
# promotes B under a suffix and must leave A's sightings untouched, never
# merging A's interaction history into B's new card.
# ---------------------------------------------------------------------------
HUB17="$TMPDIR_TEST/hub-t17"; make_hub "$HUB17"
cat > "$HUB17/people/alex.md" <<'EOF'
---
name: Alex
slug: alex
email: alex@livecard.com
draft: false
---

## Interactions
<!-- DERIVED-SIGHTINGS-BEGIN -->
| Date | Source | Summary |
|------|--------|---------|
<!-- DERIVED-SIGHTINGS-END -->
EOF
cat > "$HUB17/people/alex.staged-sightings.md" <<'EOF'
| 2026-06-01 | project-alpha/notes.md:3 | A's pending interaction |
EOF
# Person B (different address, same display name) staged as a NEW card.
write_envelope "$HUB17" 2026-07-05 morning '[{"name": "Alex", "address": "alex@newperson.io", "domain": "newperson.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
run_extract "$HUB17"
$PY "$BIN/kb-extract-people" --hub "$HUB17" --approve alex >/dev/null 2>&1
SUFFIXED=$(ls "$HUB17/people/"alex-*.md 2>/dev/null | grep -v staged | head -1)
if [[ -n "$SUFFIXED" ]] \
   && [[ -f "$HUB17/people/alex.staged-sightings.md" ]] \
   && ! grep -q "A's pending interaction" "$SUFFIXED" \
   && grep -q "alex@newperson.io" "$SUFFIXED"; then
  ok "T17: collision approve leaves the other person's staged-sightings intact (no cross-identity merge)"
else
  fail "T17: staged-sightings mis-merged (suffixed=$SUFFIXED, sightings_left=$([[ -f "$HUB17/people/alex.staged-sightings.md" ]] && echo yes || echo no))"
fi

# ---------------------------------------------------------------------------
# T18: the shared staged-new path never clobbers a different same-name
# identity, and re-staging the same identity accumulates instead of
# rewriting. Exercises _stage_for_review directly (the path _apply_hit_staged_new
# uses for project/backfill hits) — the mail guard must live in one place.
# ---------------------------------------------------------------------------
HUB18="$TMPDIR_TEST/hub-t18"; make_hub "$HUB18"
$PY - "$HUB18" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_loader = SourceFileLoader(
    "kbextract", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-extract-people")
spec = importlib.util.spec_from_loader("kbextract", _loader)
kbx = importlib.util.module_from_spec(spec); _loader.exec_module(kbx)
import _kb_people.card as card
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"

def hit(ref, ctx="x"):
    return {"date": "2026-07-05", "source_ref": ref, "context": ctx}

# Two different people, same slugified name, different emails.
kbx._stage_for_review("sam-lee", [hit("proj/a.md:1")],
                      new_card_kwargs={"name": "Sam Lee", "email": "sam@one.com"})
kbx._stage_for_review("sam-lee", [hit("proj/b.md:2")],
                      new_card_kwargs={"name": "Sam Lee", "email": "sam@two.com"})
staged = sorted((hub / "people").glob("sam-lee*.staged.md"))
assert len(staged) == 2, f"expected 2 distinct staged cards, got {[p.name for p in staged]}"
emails = sorted(kbx._staged_locators(p)[0] for p in staged)
assert emails == ["sam@one.com", "sam@two.com"], emails
# First person's card must be intact (not clobbered by the second write).
base = hub / "people" / "sam-lee.staged.md"
assert kbx._staged_locators(base)[0] == "sam@one.com", "base card clobbered"
# Re-stage the FIRST identity again on a new line → append, no third card.
kbx._stage_for_review("sam-lee", [hit("proj/c.md:9", "third mention")],
                      new_card_kwargs={"name": "Sam Lee", "email": "sam@one.com"})
staged2 = sorted((hub / "people").glob("sam-lee*.staged.md"))
assert len(staged2) == 2, f"re-stage must not create a duplicate: {[p.name for p in staged2]}"
assert "proj/c.md:9" in base.read_text(), "re-stage sighting not appended"
print("T18_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T18: shared staged-new path never clobbers different same-name people; same identity accumulates" || fail "T18: staged-new conflation on project/backfill path"

# ---------------------------------------------------------------------------
# T19: D1 counts NEWLY created staged candidates only. A later envelope from an
# already-pending sender appends a sighting (no new card) and must NOT re-fire
# the immediate digest when the last digest is recent (pending-only → silent).
# ---------------------------------------------------------------------------
HUB19="$TMPDIR_TEST/hub-t19"; make_hub "$HUB19"
write_envelope "$HUB19" 2026-07-05 morning '[{"name": "Dana Ray", "address": "dana@corp.io", "domain": "corp.io", "first_ts": "t", "last_ts": "t", "count": 1}]'
KB_PROCESS_OUTPUTS=telegram run_extract "$HUB19"        # new card → digest #1
write_envelope "$HUB19" 2026-07-06 morning '[{"name": "Dana Ray", "address": "dana@corp.io", "domain": "corp.io", "first_ts": "t", "last_ts": "t", "count": 3}]'
KB_PROCESS_OUTPUTS=telegram run_extract "$HUB19"        # append-only → must be silent
DIGEST_LINES=$(grep -c "people-staged" "$HUB19/sent.log" 2>/dev/null || echo 0)
if [[ "$DIGEST_LINES" == "1" ]] \
   && grep -q "mail:morning-2026-07-06" "$HUB19/people/dana-ray.staged.md"; then
  ok "T19: append to a pending candidate does not re-fire the digest (drafts_created counts creates only)"
else
  fail "T19: pending-only append fired digest again (digest_lines=$DIGEST_LINES)"
fi

# ---------------------------------------------------------------------------
# T20: an envelope whose filename is NOT the canonical <date>-<period>.json is
# warned and skipped, so duplicate logical keys can't be reprocessed forever.
# ---------------------------------------------------------------------------
HUB20="$TMPDIR_TEST/hub-t20"; make_hub "$HUB20"
cat > "$HUB20/personal/mail/people/2026-07-05-morning-copy.json" <<'EOF'
{"schema": "mail-people/v1", "date": "2026-07-05", "period": "morning",
 "generated_at": "2026-07-05T06:15:00+02:00", "available": true,
 "senders": [{"name": "Ghost", "address": "ghost@corp.io", "domain": "corp.io", "first_ts": "t", "last_ts": "t", "count": 1}]}
EOF
$PY - "$HUB20" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
from _kb_people.sources import mail_source as ms
hub = Path(sys.argv[1])
pending, warnings = ms.MailSource(hub).pending_envelopes()
assert pending == [], f"non-canonical filename must not be pending: {pending}"
assert any(w["kind"] == "mail_envelope_noncanonical_name" for w in warnings), warnings
print("T20_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T20: non-canonical envelope filename warned + skipped (one logical key ↔ one file)" || fail "T20: non-canonical filename guard"

# ---------------------------------------------------------------------------
# T21: card.upsert_sighting is safe under concurrent writers (C2). Two
# processes each append 25 distinct sightings to the SAME live card at once.
# An unlocked read-modify-write would lose rows (last save wins); the internal
# cards_lock must serialize them so all 50 land, and neither process deadlocks.
# ---------------------------------------------------------------------------
HUB21="$TMPDIR_TEST/hub-t21"; make_hub "$HUB21"
$PY - "$HUB21" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"
p = card.create("Concur Rent", email="concur@corp.io", source="manual", draft=False)
PYEOF
writer() {  # $1 = worker id
  $PY - "$HUB21" "$1" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
hub = Path(sys.argv[1]); wid = sys.argv[2]; card.PEOPLE_DIR = hub / "people"
for n in range(25):
    card.upsert_sighting("concur-rent", "2026-01-01", f"w{wid}", f"row-{wid}-{n:02d}")
PYEOF
}
writer A & WP1=$!
writer B & WP2=$!
wait "$WP1"; RC1=$?
wait "$WP2"; RC2=$?
ROWS=$(grep -c "row-[AB]-" "$HUB21/people/concur-rent.md" 2>/dev/null || echo 0)
if [[ $RC1 -eq 0 && $RC2 -eq 0 && "$ROWS" == "50" ]]; then
  ok "T21: concurrent upsert_sighting keeps all 50 rows (no lost update, no deadlock)"
else
  fail "T21: concurrent upsert lost rows or hung (rc1=$RC1 rc2=$RC2 rows=$ROWS/50)"
fi

# ---------------------------------------------------------------------------
# T22: last_seen is monotonic — an older-dated sighting never drags it back,
# a newer one advances it, and a non-ISO date leaves it untouched. The lock
# stops concurrent loss; this stops logical regression (backfill / late older
# envelope / out-of-order staged merge).
# ---------------------------------------------------------------------------
HUB22="$TMPDIR_TEST/hub-t22"; make_hub "$HUB22"
$PY - "$HUB22" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"
card.create("Mono Tonic", email="mono@corp.io", source="manual", draft=False,
            first_met="2026-07-05", last_seen="2026-07-05")
def last_seen():
    return str(card.load("mono-tonic")["last_seen"])
card.upsert_sighting("mono-tonic", "2026-07-03", "mail", "older sighting")
assert last_seen() == "2026-07-05", f"older sighting regressed last_seen to {last_seen()}"
card.upsert_sighting("mono-tonic", "2026-07-09", "mail", "newer sighting")
assert last_seen() == "2026-07-09", f"newer sighting did not advance last_seen: {last_seen()}"
card.upsert_sighting("mono-tonic", "not-a-date", "mail", "garbage date")
assert last_seen() == "2026-07-09", f"non-ISO date corrupted last_seen: {last_seen()}"
# ISO-SHAPED but invalid calendar dates must NOT corrupt last_seen even
# though they sort lexically above real dates (regex shape check is not
# enough; strptime rejects them).
for bad in ("2026-13-45", "9999-99-99", "2026-02-30"):
    card.upsert_sighting("mono-tonic", bad, "mail", f"invalid {bad}")
    assert last_seen() == "2026-07-09", f"invalid ISO-shaped date {bad} corrupted last_seen: {last_seen()}"
print("T22_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T22: last_seen is monotonic (older never regresses, newer advances, non-ISO ignored)" || fail "T22: last_seen regression not prevented"

# ---------------------------------------------------------------------------
# T23: staging is race-safe — two processes concurrently stage two DIFFERENT
# same-name people (different emails). Resolve+existence+write happen under one
# cards_lock, so neither clobbers the other: both distinct cards must survive
# and neither process deadlocks. (A check→write TOCTOU would let both claim the
# base slug and lose one identity.)
# ---------------------------------------------------------------------------
HUB23="$TMPDIR_TEST/hub-t23"; make_hub "$HUB23"
stager() {  # $1 = email tag
  $PY - "$HUB23" "$1" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("kbx", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-extract-people")
kbx = importlib.util.module_from_spec(importlib.util.spec_from_loader("kbx", _l)); _l.exec_module(kbx)
import _kb_people.card as card
hub = Path(sys.argv[1]); tag = sys.argv[2]; card.PEOPLE_DIR = hub / "people"
for _ in range(6):
    kbx._stage_new_card("race-name",
        [{"date": "2026-07-05", "source_ref": f"mail:x-{tag}", "context": "c"}],
        {"name": "Race Name", "email": f"race-{tag}@corp.io", "source": "mail"})
PYEOF
}
stager A & SP1=$!
stager B & SP2=$!
wait "$SP1"; SRC1=$?
wait "$SP2"; SRC2=$?
CARDS=$(ls "$HUB23/people/"race-name*.staged.md 2>/dev/null | wc -l | tr -d ' ')
EMAILS=$(grep -h "^email:" "$HUB23/people/"race-name*.staged.md 2>/dev/null | sort -u | wc -l | tr -d ' ')
if [[ $SRC1 -eq 0 && $SRC2 -eq 0 && "$CARDS" == "2" && "$EMAILS" == "2" ]]; then
  ok "T23: concurrent staging of two same-name identities keeps both cards (no clobber, no deadlock)"
else
  fail "T23: staging race lost a card or hung (rc=$SRC1/$SRC2 cards=$CARDS emails=$EMAILS)"
fi

# ---------------------------------------------------------------------------
# T24: approving a staged card whose EMAIL is already live under a DIFFERENT
# slug must NOT create a duplicate live person. This happens when the same
# email is staged under a second display name, or when extraction stages a
# candidate while that person goes live via another path (approve does not
# hold the run lock, so it can race an extraction). Approve must merge into
# the existing live card instead of minting a second one for the same email.
# ---------------------------------------------------------------------------
HUB24="$TMPDIR_TEST/hub-t24"; make_hub "$HUB24"
$PY - "$HUB24" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card, _kb_people.index as idx
import frontmatter as fm
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"; idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Bob Jones", email="shared@x.com", source="manual", draft=False)
post = card.load(p.stem); idx.register(post["id"], p.stem, "Bob Jones", {"email": "shared@x.com"})
# Same email, DIFFERENT name → distinct base slug, invisible to find_existing at stage time.
fmd = card._default_frontmatter("Robert Jones", "robert-jones", email="shared@x.com"); fmd["draft"] = True
(hub / "people" / "robert-jones.staged.md").write_text(fm.dumps(fm.Post(card._build_body(), **fmd)))
PYEOF
$PY "$BIN/kb-extract-people" --hub "$HUB24" --approve robert-jones >/dev/null 2>&1
LIVE_SHARED=$(grep -l "shared@x.com" "$HUB24/people/"*.md 2>/dev/null | grep -v _index | wc -l | tr -d ' ')
IDX_SHARED=$(grep -c "shared@x.com" "$HUB24/people/_index.yaml" 2>/dev/null || echo 0)
if [[ "$LIVE_SHARED" == "1" && "$IDX_SHARED" == "1" && ! -f "$HUB24/people/robert-jones.md" && ! -f "$HUB24/people/robert-jones.staged.md" ]]; then
  ok "T24: approve of a same-email different-name staged card merges into the live card (no duplicate person)"
else
  fail "T24: duplicate live person (live-with-email=$LIVE_SHARED idx=$IDX_SHARED robert-live=$([[ -f "$HUB24/people/robert-jones.md" ]] && echo yes || echo no))"
fi
# T24b: same guard for a telegram-only identity (no email).
HUB24B="$TMPDIR_TEST/hub-t24b"; make_hub "$HUB24B"
$PY - "$HUB24B" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card, _kb_people.index as idx
import frontmatter as fm
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"; idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Tg One", telegram="@tghandle", source="manual", draft=False)
post = card.load(p.stem); idx.register(post["id"], p.stem, "Tg One", {"telegram": "@tghandle"})
fmd = card._default_frontmatter("Tg Two", "tg-two", telegram="@tghandle"); fmd["draft"] = True
(hub / "people" / "tg-two.staged.md").write_text(fm.dumps(fm.Post(card._build_body(), **fmd)))
PYEOF
$PY "$BIN/kb-extract-people" --hub "$HUB24B" --approve tg-two >/dev/null 2>&1
TG_LIVE=$(grep -l "@tghandle" "$HUB24B/people/"*.md 2>/dev/null | grep -v _index | wc -l | tr -d ' ')
if [[ "$TG_LIVE" == "1" && ! -f "$HUB24B/people/tg-two.md" ]]; then
  ok "T24b: same-telegram different-name staged card merges into the live card (no duplicate)"
else
  fail "T24b: telegram duplicate live person (live-with-tg=$TG_LIVE tg-two-live=$([[ -f "$HUB24B/people/tg-two.md" ]] && echo yes || echo no))"
fi
# T24c: same email under the SAME slug must merge too — the identity dedup must
# not be skipped just because the live card shares the staged slug (else approve
# suffix-promotes a duplicate of the same person).
HUB24C="$TMPDIR_TEST/hub-t24c"; make_hub "$HUB24C"
$PY - "$HUB24C" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card, _kb_people.index as idx
import frontmatter as fm
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"; idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Bob", email="bob@x.com", source="manual", draft=False)
post = card.load(p.stem); idx.register(post["id"], p.stem, "Bob", {"email": "bob@x.com"})
fmd = card._default_frontmatter("Bob", "bob", email="bob@x.com"); fmd["draft"] = True
(hub / "people" / "bob.staged.md").write_text(fm.dumps(fm.Post(card._build_body(), **fmd)))
PYEOF
$PY "$BIN/kb-extract-people" --hub "$HUB24C" --approve bob >/dev/null 2>&1
BOB_LIVE=$(grep -l "bob@x.com" "$HUB24C/people/"*.md 2>/dev/null | grep -v _index | wc -l | tr -d ' ')
if [[ "$BOB_LIVE" == "1" && ! -f "$HUB24C/people/bob.staged.md" ]] && ! ls "$HUB24C/people/"bob-*.md >/dev/null 2>&1; then
  ok "T24c: same-slug same-email staged card merges (no suffixed duplicate of the same identity)"
else
  fail "T24c: same-slug duplicate ($(ls "$HUB24C/people" | grep -v _index | tr '\n' ' '))"
fi

# ---------------------------------------------------------------------------
# T25: merging a staged card must not truncate a sighting summary that itself
# contains a `|`. Staged rows are written unescaped, so the merge parser must
# rejoin cells past the source instead of keeping only the 3rd cell.
# ---------------------------------------------------------------------------
HUB25="$TMPDIR_TEST/hub-t25"; make_hub "$HUB25"
$PY - "$HUB25" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("kbx", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-extract-people")
kbx = importlib.util.module_from_spec(importlib.util.spec_from_loader("kbx", _l)); _l.exec_module(kbx)
import _kb_people.card as card, _kb_people.index as idx
import frontmatter as fm
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"; idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Bob", email="bob@x.com", source="manual", draft=False)
post = card.load(p.stem); idx.register(post["id"], p.stem, "Bob", {"email": "bob@x.com"})
# Staged card, same email, different name, with a pipe-containing summary.
fmd = card._default_frontmatter("Bob Two", "bob-two", email="bob@x.com"); fmd["draft"] = True
(hub / "people" / "bob-two.staged.md").write_text(fm.dumps(fm.Post(card._build_body(), **fmd)))
kbx._append_staged_sighting("bob-two",
    {"date": "2026-07-05", "source_ref": "mail:x", "context": "alpha | beta | gamma"},
    into_staged_card=True)
PYEOF
$PY "$BIN/kb-extract-people" --hub "$HUB25" --approve bob-two >/dev/null 2>&1
# The full summary (incl. the part after the last pipe) must reach bob.md.
if grep -q "alpha" "$HUB25/people/bob.md" 2>/dev/null && grep -q "gamma" "$HUB25/people/bob.md" 2>/dev/null; then
  ok "T25: merge preserves a pipe-containing summary (no truncation at the first '|')"
else
  fail "T25: summary truncated on merge ($(grep -m1 'alpha' "$HUB25/people/bob.md" 2>/dev/null))"
fi

# ---------------------------------------------------------------------------
# T26: the project staging path counts a NEW candidate only when a card is
# actually created. Re-staging an already-pending identity appends and must
# increment sightings_appended, not drafts_created (else D1 over-counts).
# ---------------------------------------------------------------------------
HUB26="$TMPDIR_TEST/hub-t26"; make_hub "$HUB26"
$PY - "$HUB26" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("kbx", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-extract-people")
kbx = importlib.util.module_from_spec(importlib.util.spec_from_loader("kbx", _l)); _l.exec_module(kbx)
import _kb_people.card as card
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"
ap = {"drafts_created": 0, "sightings_appended": 0}
def hit(line):
    return {"name": "Proj Person", "email": "proj@corp.io", "date": "2026-07-05",
            "project_slug": "projX", "source_path": "a.md", "line_no": str(line)}
kbx._apply_hit_staged_new(hit(1), ap)   # creates the staged card
kbx._apply_hit_staged_new(hit(2), ap)   # SAME identity, new line → append
staged = list((hub / "people").glob("proj-person*.staged.md"))
assert len(staged) == 1, f"expected 1 staged card, got {[p.name for p in staged]}"
assert ap["drafts_created"] == 1, f"drafts_created should be 1, got {ap['drafts_created']}"
assert ap["sightings_appended"] == 1, f"sightings_appended should be 1, got {ap['sightings_appended']}"
print("T26_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T26: project re-stage counts as append (sightings_appended), not a new draft" || fail "T26: project staging miscounts append as new"

# ---------------------------------------------------------------------------
# T27: Pass-1 email filter — RFC-reserved documentation domains
# (example.com/org/net incl. subdomains, *.invalid, *.localhost) and role
# local-parts (receipts@, owner@) are doc snippets / org mailboxes, never
# people. They minted junk live cards during the 2026-07-05 dogfood and must
# never leave extract_pass1. The .test/.example TLDs stay extractable — they
# are the sanctioned fixture-space for these public suites.
# ---------------------------------------------------------------------------
HUB27="$TMPDIR_TEST/hub-t27"; make_hub "$HUB27"
$PY - "$HUB27" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
from _kb_people.sources import project_source as ps
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"
text = """contact jane.doe@corp.io about the deal
fixtures: owner@example.com receipts@corp.io mailer@sub.example.org
more: x@baz.invalid y@qux.localhost
fixture-space survives: someone@foo.test other@bar.example
"""
hits = ps.extract_pass1(text, "projX", "log.md")
emails = {h["email"] for h in hits}
assert emails == {"jane.doe@corp.io", "someone@foo.test", "other@bar.example"}, \
    f"filter gap: {sorted(emails)}"
print("T27_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T27: Pass-1 drops reserved example domains and role local-parts, keeps real people" || fail "T27: Pass-1 example-domain/role-local-part filter gap"

# ---------------------------------------------------------------------------
# T28: Pass-1 telegram personal blocklist overlay — owner-curated handles live
# in <PEOPLE_DIR>/.blocklist-telegram.txt (never in the shipped package
# blocklist, which must stay free of personal identifiers). Both lists apply.
# ---------------------------------------------------------------------------
HUB28="$TMPDIR_TEST/hub-t28"; make_hub "$HUB28"
$PY - "$HUB28" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
from _kb_people.sources import project_source as ps
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"
(hub / "people" / ".blocklist-telegram.txt").write_text("privatehandle\n", encoding="utf-8")
text = "chat with @privatehandle and @realperson and @dependabot today\n"
hits = ps.extract_pass1(text, "projX", "log.md")
handles = {h["telegram"] for h in hits}
assert "@privatehandle" not in handles, f"personal blocklist ignored: {sorted(handles)}"
assert "@dependabot" not in handles, f"system blocklist regressed: {sorted(handles)}"
assert "@realperson" in handles, f"over-filtering: {sorted(handles)}"
print("T28_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T28: personal telegram blocklist overlay applies alongside the shipped system list" || fail "T28: personal telegram blocklist overlay missing"

# ---------------------------------------------------------------------------
# T29 (B1): the project live-create path must re-check the live index under
# ONE cards_lock before creating. dedup_resolve runs unlocked, so a concurrent
# approve can make the same email live between resolve and create — the create
# branch must then upsert into the existing card, never mint a second live
# card for the same identity.
# ---------------------------------------------------------------------------
HUB29="$TMPDIR_TEST/hub-t29"; make_hub "$HUB29"
$PY - "$HUB29" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("kbx", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-extract-people")
kbx = importlib.util.module_from_spec(importlib.util.spec_from_loader("kbx", _l)); _l.exec_module(kbx)
import _kb_people.card as card, _kb_people.index as idx
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"; idx.INDEX_PATH = hub / "people" / "_index.yaml"
# The identity is ALREADY live (approve won the race)...
p = card.create("Bob Jones", email="dup@corp.io", source="manual", draft=False)
post = card.load(p.stem); idx.register(post["id"], p.stem, "Bob Jones", {"email": "dup@corp.io"})
# ...but this extraction resolved "create" BEFORE that approve landed.
kbx.dedup_resolve = lambda **kw: {"action": "create"}
ap = {"live_created": 0, "live_upserted": 0, "drafts_created": 0, "sightings_appended": 0}
hit = {"name": "Bobby Jones", "email": "dup@corp.io", "telegram": "", "date": "2026-07-05",
       "project_slug": "projX", "source_path": "a.md", "line_no": "3", "context": "ctx"}
kbx._apply_hit_live(hit, ap)
live = [f for f in (hub / "people").glob("*.md")
        if not f.name.endswith(".staged.md") and f.name != "_index.yaml"
        and "dup@corp.io" in f.read_text(encoding="utf-8")]
assert len(live) == 1, f"duplicate live person: {[f.name for f in live]}"
assert ap["live_created"] == 0, f"live_created={ap['live_created']} (should merge, not create)"
assert ap["live_upserted"] == 1, f"live_upserted={ap['live_upserted']}"
assert "projX/a.md:3" in (hub / "people" / "bob-jones.md").read_text(encoding="utf-8"), "sighting not merged into the live card"
print("T29_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T29: live-create re-checks the index under cards_lock (race with approve cannot duplicate)" || fail "T29: create/approve race can mint a duplicate live card"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
