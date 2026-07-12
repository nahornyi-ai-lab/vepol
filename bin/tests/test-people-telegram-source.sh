#!/usr/bin/env bash
# Tests for TelegramSource (telegram-people/v1 envelopes) + kb-extract-people
# wiring + the kb-telegram-people collector's non-network paths.
#
# Covers (People Notebook P3b, owner directive 2026-07-12 — direct Telegram,
# multibot deprecated):
#   - strict telegram-people/v1 envelope validation (unknown keys rejected,
#     no field can carry message text)
#   - per-envelope processed-watermark idempotency
#   - sender filters (bots, system + personal handle blocklists)
#   - staged-only policy: known telegram locator → live sighting; new →
#     staged card with telegram/phone; rejected identities dropped
#   - D1 counters (drafts_created vs sightings_appended) + digest line
#   - --no-telegram opt-out
#   - collector degradation: no credentials → available:false envelope, rc=1
#
# All hubs are throwaway temp dirs — never the live ~/knowledge. No network,
# no telethon: the collector is exercised only on its pre-connect paths.
# Usage: bash bin/tests/test-people-telegram-source.sh

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

make_hub() {
  local hub="$1"
  mkdir -p "$hub/people" "$hub/personal/telegram/people" "$hub/bin"
}

# Write a telegram-people/v1 envelope. args: hub date senders_json [avail] [trunc]
write_envelope() {
  local hub="$1" day="$2" senders="$3" avail="${4:-true}" trunc="${5:-false}"
  cat > "$hub/personal/telegram/people/$day-daily.json" <<EOF
{"schema": "telegram-people/v1", "date": "$day", "period": "daily",
 "generated_at": "${day}T21:30:00Z", "available": $avail,
 "truncated": $trunc, "senders": $senders}
EOF
}

run_extract() {
  local hub="$1"; shift
  KB_HUB="$hub" $PY "$BIN/kb-extract-people" --hub "$hub" --no-llm --quiet "$@" 2>/dev/null
}

SENDER_JANE='{"name": "Jane Doe", "username": "janedoe", "user_id": 111,
  "phone": "+34600111222", "chat_type": "private",
  "first_ts": "2026-07-12T08:00:00Z", "last_ts": "2026-07-12T09:00:00Z", "count": 3}'

echo "=== TelegramSource + kb-extract-people telegram wiring tests ==="

# ---------------------------------------------------------------------------
# T1: strict envelope validation
# ---------------------------------------------------------------------------
$PY - <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
from _kb_people.sources import telegram_source as ts

GOOD = {
    "schema": "telegram-people/v1", "date": "2026-07-12", "period": "daily",
    "generated_at": "2026-07-12T21:30:00Z", "available": True,
    "truncated": False,
    "senders": [{"name": "Jane Doe", "username": "janedoe", "user_id": 111,
                 "phone": "+34600111222", "chat_type": "private",
                 "first_ts": "2026-07-12T08:00:00Z",
                 "last_ts": "2026-07-12T09:00:00Z", "count": 3}],
}
assert ts.validate_envelope(GOOD) is True, "valid envelope must pass"

import copy
def bad(mut):
    env = copy.deepcopy(GOOD)
    mut(env)
    assert ts.validate_envelope(env) is False, f"must reject: {env}"

bad(lambda e: e.__setitem__("schema", "mail-people/v1"))
bad(lambda e: e.__setitem__("extra", 1))                        # unknown top-level key
bad(lambda e: e.pop("truncated"))                               # missing top-level key
bad(lambda e: e["senders"][0].__setitem__("text", "hi"))        # content smuggling
bad(lambda e: e["senders"][0].pop("count"))
bad(lambda e: e["senders"][0].__setitem__("count", True))       # bool is not a count
bad(lambda e: e["senders"][0].__setitem__("count", 0))
bad(lambda e: e["senders"][0].__setitem__("user_id", -5))
bad(lambda e: e["senders"][0].__setitem__("username", "Bad-Name"))  # not lowercase tg form
bad(lambda e: e["senders"][0].__setitem__("name", "x" * 201))
bad(lambda e: e["senders"][0].__setitem__("name", "line\nbreak"))
bad(lambda e: e["senders"][0].__setitem__("phone", "call me maybe"))
bad(lambda e: e["senders"][0].__setitem__("chat_type", "channel"))
bad(lambda e: e.__setitem__("period", "morning"))
bad(lambda e: e.__setitem__("date", "12.07.2026"))
bad(lambda e: e.__setitem__("available", "yes"))
bad(lambda e: e.__setitem__("available", False))                # false must carry no senders
def _anon(e):
    e["senders"][0]["name"] = ""
    e["senders"][0]["username"] = ""
bad(_anon)                                                      # identity needs name or username
env = copy.deepcopy(GOOD); env["available"] = False; env["senders"] = []
assert ts.validate_envelope(env) is True, "available:false with [] must pass"
env = copy.deepcopy(GOOD)
dup = dict(env["senders"][0]); dup["username"] = "other"
env["senders"].append(dup)                                      # same user_id twice
assert ts.validate_envelope(env) is False, "dup user_id must fail"
print("T1_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T1: strict telegram-people/v1 validation (unknown keys, bounds, dups, no-text-by-schema)" || fail "T1: envelope validation"

# ---------------------------------------------------------------------------
# T2: pending_envelopes + processed-watermark
# ---------------------------------------------------------------------------
HUB2="$TMPDIR_TEST/hub-t2"; make_hub "$HUB2"
write_envelope "$HUB2" 2026-07-12 "[$SENDER_JANE]"
$PY - "$HUB2" <<'PYEOF'
import json, sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
from _kb_people.sources import telegram_source as ts

hub = Path(sys.argv[1])
src = ts.TelegramSource(hub)
pending, warnings = src.pending_envelopes()
assert len(pending) == 1, f"expected 1 pending, got {len(pending)}"
item = pending[0]
assert item["key"] == "2026-07-12-daily", item["key"]
assert len(item["sha"]) == 64

ts.mark_processed(hub, item["key"], item["sha"])
wm = json.loads(ts.processed_path(hub).read_text())
assert wm["schema_version"] == 1
assert wm["processed"]["2026-07-12-daily"] == item["sha"]
pending2, _ = src.pending_envelopes()
assert pending2 == [], f"processed envelope must not be pending: {pending2}"

# Rewritten content (new sha) → pending again.
p = item["path"]
env = json.loads(p.read_text())
env["senders"][0]["count"] = 9
p.write_text(json.dumps(env))
pending3, _ = src.pending_envelopes()
assert len(pending3) == 1, "changed content must re-pend"

# Corrupt + noncanonical names warn, never pend.
(hub / "personal/telegram/people/2026-07-11-daily.json").write_text("{not json")
good = json.loads(p.read_text()); good["date"] = "2026-07-10"
(hub / "personal/telegram/people/2026-07-10-copy.json").write_text(json.dumps(good))
pending4, warn4 = src.pending_envelopes()
assert len(pending4) == 1, f"invalid/noncanonical must not pend: {[i['key'] for i in pending4]}"
kinds = {w["kind"] for w in warn4}
assert "telegram_envelope_unreadable" in kinds and "telegram_envelope_noncanonical_name" in kinds, kinds
print("T2_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T2: pending_envelopes + processed-watermark (sha-keyed, invalid warned, canonical names only)" || fail "T2: watermark plumbing"

# ---------------------------------------------------------------------------
# T3: sender filters (bots, system blocklist, personal blocklist)
# ---------------------------------------------------------------------------
HUB3="$TMPDIR_TEST/hub-t3"; make_hub "$HUB3"
echo "privatehandle" > "$HUB3/people/.blocklist-telegram.txt"
$PY - "$HUB3" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card
from _kb_people.sources import telegram_source as ts

hub = Path(sys.argv[1])
card.PEOPLE_DIR = hub / "people"

def s(uid, name="X", username="", phone=""):
    return {"name": name, "username": username, "user_id": uid, "phone": phone,
            "chat_type": "private", "first_ts": "t", "last_ts": "t", "count": 1}

senders = [
    s(1, "Jane Doe", "janedoe", "+34600111222"),
    s(2, "Weather", "weather_alerts_bot"),      # bot handle
    s(3, "dependabot"),                          # bot-like bare name, no email
    s(4, "Private Person", "privatehandle"),     # personal blocklist
    s(5, "GitHub", "github"),                    # system blocklist
    s(6, "NoHandle Person"),                     # name-only, kept
]
kept, dropped = ts.TelegramSource.filter_senders(senders)
names = [k["name"] for k in kept]
assert names == ["Jane Doe", "NoHandle Person"], names
assert dropped == 4, f"expected 4 dropped, got {dropped}"
assert kept[0]["telegram"] == "@janedoe" and kept[0]["phone"] == "+34600111222"
assert kept[1]["telegram"] == "id:6", kept[1]  # stable no-username locator
print("T3_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T3: filters drop bots + system/personal blocklists, keep + normalize people" || fail "T3: sender filters"

# ---------------------------------------------------------------------------
# T4: apply policy end-to-end — new → staged (telegram+phone on the card);
# known telegram locator → live sighting; idempotent re-run.
# ---------------------------------------------------------------------------
HUB4="$TMPDIR_TEST/hub-t4"; make_hub "$HUB4"
$PY - "$HUB4" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as card, _kb_people.index as idx
hub = Path(sys.argv[1]); card.PEOPLE_DIR = hub / "people"; idx.INDEX_PATH = hub / "people" / "_index.yaml"
p = card.create("Known Guy", telegram="@knownguy", source="manual", draft=False)
post = card.load(p.stem)
idx.register(post["id"], p.stem, "Known Guy", {"telegram": "@knownguy"})
PYEOF
write_envelope "$HUB4" 2026-07-12 "[$SENDER_JANE,
  {\"name\": \"Known Guy\", \"username\": \"knownguy\", \"user_id\": 222,
   \"phone\": \"\", \"chat_type\": \"private\",
   \"first_ts\": \"t\", \"last_ts\": \"t\", \"count\": 5}]"
run_extract "$HUB4"
STAGED_OK=false; LIVE_OK=false
if [[ -f "$HUB4/people/jane-doe.staged.md" ]] \
   && grep -q "telegram: '@janedoe'" "$HUB4/people/jane-doe.staged.md" \
   && grep -q "phone: '+34600111222'" "$HUB4/people/jane-doe.staged.md" \
   && grep -q "source: telegram" "$HUB4/people/jane-doe.staged.md"; then STAGED_OK=true; fi
if grep -q "telegram:daily-2026-07-12" "$HUB4/people/known-guy.md" 2>/dev/null \
   && [[ ! -f "$HUB4/people/known-guy-1.staged.md" ]] \
   && ! ls "$HUB4/people/"known-guy*.staged.md >/dev/null 2>&1; then LIVE_OK=true; fi
[[ "$STAGED_OK" == "true" ]] && ok "T4a: new telegram sender staged with @handle + phone, never live" || fail "T4a: staged card wrong ($(ls "$HUB4/people" 2>/dev/null | tr '\n' ' '))"
[[ "$LIVE_OK" == "true" ]] && ok "T4b: known telegram locator upserts a live sighting, no staged duplicate" || fail "T4b: live sighting missing or duplicated"

# Idempotent re-run: envelope watermarked → second run proposes nothing new.
BEFORE=$(cat "$HUB4/people/jane-doe.staged.md" 2>/dev/null | shasum | cut -d' ' -f1)
run_extract "$HUB4"
AFTER=$(cat "$HUB4/people/jane-doe.staged.md" 2>/dev/null | shasum | cut -d' ' -f1)
N_STAGED=$(ls "$HUB4/people/"*.staged.md 2>/dev/null | wc -l | tr -d ' ')
[[ "$BEFORE" == "$AFTER" && "$N_STAGED" == "1" ]] && ok "T4c: re-run on a processed envelope proposes nothing" || fail "T4c: watermark not honored (staged=$N_STAGED)"

# ---------------------------------------------------------------------------
# T5: rejected.yaml drops a telegram identity (strong-id equality)
# ---------------------------------------------------------------------------
HUB5="$TMPDIR_TEST/hub-t5"; make_hub "$HUB5"
cat > "$HUB5/people/.rejected.yaml" <<'EOF'
- name: Spam Guy
  telegram: '@spamguy'
EOF
write_envelope "$HUB5" 2026-07-12 '[{"name": "Spam Guy", "username": "spamguy",
  "user_id": 333, "phone": "", "chat_type": "private",
  "first_ts": "t", "last_ts": "t", "count": 2}]'
run_extract "$HUB5"
if ! ls "$HUB5/people/"*.staged.md >/dev/null 2>&1; then
  ok "T5: rejected telegram identity is dropped at apply"
else
  fail "T5: rejected identity staged anyway ($(ls "$HUB5/people" | tr '\n' ' '))"
fi

# ---------------------------------------------------------------------------
# T6: D1 counters — new envelope day re-proposing the SAME pending identity
# counts as sightings_appended, not a new draft
# ---------------------------------------------------------------------------
HUB6="$TMPDIR_TEST/hub-t6"; make_hub "$HUB6"
write_envelope "$HUB6" 2026-07-11 "[$SENDER_JANE]"
run_extract "$HUB6"
write_envelope "$HUB6" 2026-07-12 "[$SENDER_JANE]"
run_extract "$HUB6"
AUDIT=$(ls -t "$HUB6"/people/.extract-audit-*.json 2>/dev/null | head -1)
[[ -z "$AUDIT" ]] && AUDIT=$(ls -t "$HUB6"/.extract-audit-*.json 2>/dev/null | head -1)
COUNTS=$($PY - "$HUB6" <<'PYEOF'
import json, sys, glob
from pathlib import Path
hub = sys.argv[1]
audits = sorted(glob.glob(f"{hub}/.orchestrator/people-extraction-*.json"))
if not audits:
    print("NOAUDIT"); raise SystemExit(0)
data = json.loads(Path(audits[-1]).read_text())
proj = data.get("projects", {}).get("telegram:envelopes", {})
print(f"{proj.get('drafts_created', -1)}/{proj.get('sightings_appended', -1)}")
PYEOF
)
N_STAGED6=$(ls "$HUB6/people/"jane-doe*.staged.md 2>/dev/null | wc -l | tr -d ' ')
if [[ "$N_STAGED6" == "1" && "$COUNTS" == "0/1" ]]; then
  ok "T6: reappearing pending identity appends (one card, audit counts 0 new / 1 append)"
else
  fail "T6: duplicate staged or miscount (staged=$N_STAGED6 audit=$COUNTS)"
fi

# ---------------------------------------------------------------------------
# T7: --no-telegram opts out
# ---------------------------------------------------------------------------
HUB7="$TMPDIR_TEST/hub-t7"; make_hub "$HUB7"
write_envelope "$HUB7" 2026-07-12 "[$SENDER_JANE]"
run_extract "$HUB7" --no-telegram
if ! ls "$HUB7/people/"*.staged.md >/dev/null 2>&1 \
   && [[ ! -f "$HUB7/people/.telegram-envelopes-processed.json" ]]; then
  ok "T7: --no-telegram skips envelopes entirely (no staging, no watermark)"
else
  fail "T7: --no-telegram still consumed the envelope"
fi

# ---------------------------------------------------------------------------
# T8: digest message carries a Telegram line when the connector contributed
# ---------------------------------------------------------------------------
DIGEST_OK=$($PY - <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("kbx", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-extract-people")
kbx = importlib.util.module_from_spec(importlib.util.spec_from_loader("kbx", _l)); _l.exec_module(kbx)
msg = kbx.staged_digest_message(["jane-doe"], 1, "/tmp/h", new_count=1,
                                tg_staged=2, tg_upserts=1)
assert "Telegram" in msg, msg
msg2 = kbx.staged_digest_message(["jane-doe"], 1, "/tmp/h", new_count=1)
assert "Telegram" not in msg2, msg2
print("OK")
PYEOF
)
[[ "$DIGEST_OK" == "OK" ]] && ok "T8: digest adds a Telegram line only when the connector contributed" || fail "T8: digest telegram line wrong"

# ---------------------------------------------------------------------------
# T9: collector degradation — no credentials → available:false envelope, rc=1;
# extract consumes it without staging anything
# ---------------------------------------------------------------------------
HUB9="$TMPDIR_TEST/hub-t9"; make_hub "$HUB9"
OUT9=$(env -u TG_API_ID -u TG_API_HASH KB_TG_ENV_FILE="$TMPDIR_TEST/nonexistent.env" \
  $PY "$BIN/kb-telegram-people" --hub "$HUB9" --quiet --date 2026-07-12 2>&1); RC9=$?
ENV9="$HUB9/personal/telegram/people/2026-07-12-daily.json"
AVAIL9=$($PY -c "import json;print(json.load(open('$ENV9'))['available'])" 2>/dev/null)
if [[ $RC9 -ne 0 && "$AVAIL9" == "False" ]]; then
  ok "T9a: collector without creds writes available:false and exits non-zero"
else
  fail "T9a: degradation wrong (rc=$RC9 avail=$AVAIL9 out=$OUT9)"
fi
run_extract "$HUB9"
if ! ls "$HUB9/people/"*.staged.md >/dev/null 2>&1; then
  ok "T9b: extract consumes an unavailable envelope without staging"
else
  fail "T9b: unavailable envelope produced staging"
fi

# ---------------------------------------------------------------------------
# T10: watermark contract in finalize_run — a COMPLETE run advances to the
# collector's `now`; a TRUNCATED run advances only to the covered boundary
# the collector computed (never past uncovered-but-newer work); a merge that
# overflows the sender cap HOLDS the watermark entirely.
# ---------------------------------------------------------------------------
HUB10="$TMPDIR_TEST/hub-t10"; make_hub "$HUB10"
$PY - "$HUB10" <<'PYEOF'
import json, sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("ktp", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-telegram-people")
ktp = importlib.util.module_from_spec(importlib.util.spec_from_loader("ktp", _l)); _l.exec_module(ktp)
from datetime import datetime, timezone
hub = Path(sys.argv[1])
now = datetime(2026, 7, 12, 21, 0, tzinfo=timezone.utc)
boundary = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)  # covered floor < now

def env(truncated, senders=None):
    return {"schema": ktp.ts.SCHEMA, "date": "2026-07-12", "period": "daily",
            "generated_at": "2026-07-12T21:00:00Z", "available": True,
            "truncated": truncated, "senders": senders or []}

# Truncated → watermark = the collector's covered boundary, NOT now.
ktp.finalize_run(hub, env(True), boundary)
wm = json.loads(ktp.watermark_path(hub).read_text())
assert wm["last_run_utc"] == "2026-07-12T18:00:00Z", wm
# Complete → advances to now.
ktp.finalize_run(hub, env(False), now)
wm = json.loads(ktp.watermark_path(hub).read_text())
assert wm["last_run_utc"] == "2026-07-12T21:00:00Z", wm
# Monotonic: a later truncated run with an older boundary never regresses.
ktp.finalize_run(hub, env(True), datetime(2026, 7, 12, 5, 0, tzinfo=timezone.utc))
wm = json.loads(ktp.watermark_path(hub).read_text())
assert wm["last_run_utc"] == "2026-07-12T21:00:00Z", f"watermark regressed: {wm}"
print("T10_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T10: watermark advances to now (complete) / covered boundary (truncated), never regresses" || fail "T10: watermark contract"

# ---------------------------------------------------------------------------
# T10b: the collector itself (via a fake Telethon client) makes MONOTONIC
# forward progress under a dialog cap — a truncated run advances the cursor
# to the newest dialog it covered (oldest-first), so re-running drains the
# backlog instead of livelocking on the same capped prefix.
# ---------------------------------------------------------------------------
HUB10B="$TMPDIR_TEST/hub-t10b"; make_hub "$HUB10B"
$PY - "$HUB10B" <<'PYEOF'
import sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("ktp", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-telegram-people")
ktp = importlib.util.module_from_spec(importlib.util.spec_from_loader("ktp", _l)); _l.exec_module(ktp)
from datetime import datetime, timezone

# telethon is imported lazily inside collect(); provide a stub module so the
# `from telethon...` lines resolve and isinstance(x, User) works.
import types
class _User:
    def __init__(self, uid, first, username="", bot=False):
        self.id = uid; self.first_name = first; self.last_name = ""
        self.username = username; self.phone = ""
        self.bot = bot; self.is_self = False; self.deleted = False
tl = types.ModuleType("telethon"); errs = types.ModuleType("telethon.errors")
tltypes = types.ModuleType("telethon.tl.types"); tlmod = types.ModuleType("telethon.tl")
class _FloodWaitError(Exception):
    def __init__(self, seconds=0): self.seconds = seconds
errs.FloodWaitError = _FloodWaitError
tltypes.User = _User
sys.modules["telethon"] = tl; sys.modules["telethon.errors"] = errs
sys.modules["telethon.tl"] = tlmod; sys.modules["telethon.tl.types"] = tltypes

def dt(h): return datetime(2026, 7, 12, h, 0, tzinfo=timezone.utc)

class _Dialog:
    def __init__(self, entity, when): self.entity = entity; self.date = when; self.is_group = False
class _Msg:
    def __init__(self, sender, when, out=False): self.sender = sender; self.date = when; self.out = out

class FakeClient:
    def __init__(self, dialogs, msgs): self._dialogs = dialogs; self._msgs = msgs
    def iter_dialogs(self, limit=None):
        return iter(self._dialogs[:limit] if limit else self._dialogs)
    def iter_messages(self, entity):
        return iter(self._msgs.get(entity.id, []))

# 3 eligible dialogs at 10:00, 12:00, 14:00 (activity times); cap covers 2.
uA, uB, uC = _User(1, "A"), _User(2, "B"), _User(3, "C")
dialogs = [_Dialog(uC, dt(14)), _Dialog(uA, dt(10)), _Dialog(uB, dt(12))]  # unsorted
msgs = {1: [_Msg(uA, dt(10))], 2: [_Msg(uB, dt(12))], 3: [_Msg(uC, dt(14))]}
client = FakeClient(dialogs, msgs)

since = dt(8)
senders, truncated, nwm = ktp.collect(client, me_id=999, since=since, now=dt(21),
    include_groups=False, scan_dialogs=100, limit_dialogs=2, limit_msgs=100, quiet=True)
ids = sorted(s["user_id"] for s in senders)
assert truncated is True, "3 eligible > cap 2 must truncate"
assert ids == [1, 2], f"oldest-first cover A,B: {ids}"          # C (newest) deferred
assert nwm == dt(12), f"watermark = newest covered (B@12): {nwm}"  # monotonic, < now
# Next run from dt(12): only C remains, completes, advances to now.
senders2, truncated2, nwm2 = ktp.collect(client, me_id=999, since=dt(12), now=dt(21),
    include_groups=False, scan_dialogs=100, limit_dialogs=2, limit_msgs=100, quiet=True)
ids2 = sorted(s["user_id"] for s in senders2)
assert ids2 == [3], f"remainder C covered next run: {ids2}"
assert truncated2 is False and nwm2 == dt(21), f"complete → now: {truncated2} {nwm2}"
print("T10B_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T10b: collector covers oldest-first, truncation advances cursor to covered boundary (no livelock)" || fail "T10b: collector livelock/monotonic progress"

# ---------------------------------------------------------------------------
# T11: a same-day re-collection must MERGE with an existing UNPROCESSED
# envelope (collector succeeded, extract didn't run yet, retry would
# otherwise overwrite sender A with sender B); an already-consumed envelope
# is replaced with the fresh window.
# ---------------------------------------------------------------------------
HUB11="$TMPDIR_TEST/hub-t11"; make_hub "$HUB11"
$PY - "$HUB11" <<'PYEOF'
import json, sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("ktp", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-telegram-people")
ktp = importlib.util.module_from_spec(importlib.util.spec_from_loader("ktp", _l)); _l.exec_module(ktp)
ts = ktp.ts
from datetime import datetime, timezone
hub = Path(sys.argv[1])
now = datetime(2026, 7, 12, 21, 0, tzinfo=timezone.utc)

def sender(uid, name, count=1, username=""):
    return {"name": name, "username": username, "user_id": uid, "phone": "",
            "chat_type": "private", "first_ts": "t1", "last_ts": "t2",
            "count": count}

def env(senders):
    return {"schema": ts.SCHEMA, "date": "2026-07-12", "period": "daily",
            "generated_at": "2026-07-12T21:00:00Z", "available": True,
            "truncated": False, "senders": senders}

# Run 1: sender A. NOT consumed by extract.
ktp.finalize_run(hub, env([sender(1, "Alice A", count=2)]), now)
# Run 2 same day: sender B only (window moved on) → must carry A too.
ktp.finalize_run(hub, env([sender(2, "Bob B")]), now)
data = json.loads((ts.envelopes_dir(hub) / "2026-07-12-daily.json").read_text())
ids = sorted(s["user_id"] for s in data["senders"])
assert ids == [1, 2], f"unprocessed identities lost on same-day rewrite: {ids}"
assert ts.validate_envelope(data), "merged envelope must stay valid"

# Consume it, then a fresh same-day run replaces (no merge with consumed rows).
key = ts.envelope_key(data)
sha = ts.file_sha256(ts.envelopes_dir(hub) / "2026-07-12-daily.json")
ts.mark_processed(hub, key, sha)
ktp.finalize_run(hub, env([sender(3, "Cara C")]), now)
data2 = json.loads((ts.envelopes_dir(hub) / "2026-07-12-daily.json").read_text())
ids2 = sorted(s["user_id"] for s in data2["senders"])
assert ids2 == [3], f"consumed rows must not be re-merged: {ids2}"
print("T11_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T11: same-day re-collection merges unprocessed identities, replaces consumed ones" || fail "T11: same-day envelope overwrite loses identities"

# ---------------------------------------------------------------------------
# T11b: a same-day merge whose union exceeds the sender cap must set
# truncated AND hold the watermark — the dropped identities beyond the cap
# would otherwise be lost behind an advanced cursor.
# ---------------------------------------------------------------------------
HUB11B="$TMPDIR_TEST/hub-t11b"; make_hub "$HUB11B"
$PY - "$HUB11B" <<'PYEOF'
import json, sys
from pathlib import Path
import os; sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("ktp", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-telegram-people")
ktp = importlib.util.module_from_spec(importlib.util.spec_from_loader("ktp", _l)); _l.exec_module(ktp)
ts = ktp.ts
from datetime import datetime, timezone
hub = Path(sys.argv[1])
now = datetime(2026, 7, 12, 21, 0, tzinfo=timezone.utc)

def sender(uid):
    return {"name": f"P{uid}", "username": "", "user_id": uid, "phone": "",
            "chat_type": "private", "first_ts": "t", "last_ts": "t", "count": 1}
def env(senders):
    return {"schema": ts.SCHEMA, "date": "2026-07-12", "period": "daily",
            "generated_at": "2026-07-12T21:00:00Z", "available": True,
            "truncated": False, "senders": senders}

# Run 1: 400 unprocessed identities, complete → watermark = now.
ktp.finalize_run(hub, env([sender(i) for i in range(1, 401)]), now)
wm1 = json.loads(ktp.watermark_path(hub).read_text())["last_run_utc"]
assert wm1 == "2026-07-12T21:00:00Z", wm1
# Run 2 same day: 200 more NEW ids → union 600 > cap 500 → overflow.
later = datetime(2026, 7, 12, 22, 0, tzinfo=timezone.utc)
ktp.finalize_run(hub, env([sender(i) for i in range(401, 601)]), later)
data = json.loads((ts.envelopes_dir(hub) / "2026-07-12-daily.json").read_text())
assert len(data["senders"]) == 500, len(data["senders"])
assert data["truncated"] is True, "overflowed merge must flag truncated"
wm2 = json.loads(ktp.watermark_path(hub).read_text())["last_run_utc"]
assert wm2 == "2026-07-12T21:00:00Z", f"overflow merge must HOLD watermark, got {wm2}"
print("T11B_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T11b: merge past the sender cap flags truncated and holds the watermark" || fail "T11b: silent merge overflow"

# ---------------------------------------------------------------------------
# T12: a sender WITHOUT a username still has a stable identity — the reader
# derives an `id:<user_id>` locator so the same person never mints a second
# suffixed staged card on the next envelope.
# ---------------------------------------------------------------------------
HUB12="$TMPDIR_TEST/hub-t12"; make_hub "$HUB12"
NO_HANDLE='{"name": "No Handle", "username": "", "user_id": 777, "phone": "",
  "chat_type": "private", "first_ts": "t", "last_ts": "t", "count": 1}'
write_envelope "$HUB12" 2026-07-11 "[$NO_HANDLE]"
run_extract "$HUB12"
write_envelope "$HUB12" 2026-07-12 "[$NO_HANDLE]"
run_extract "$HUB12"
N12=$(ls "$HUB12/people/"no-handle*.staged.md 2>/dev/null | wc -l | tr -d ' ')
LOC12=$(grep -h "^telegram:" "$HUB12/people/"no-handle*.staged.md 2>/dev/null | head -1)
if [[ "$N12" == "1" && "$LOC12" == *"id:777"* ]]; then
  ok "T12: name-only telegram sender stays ONE staged card across envelopes (id:<user_id> locator)"
else
  fail "T12: name-only sender duplicated or locator missing (cards=$N12 loc=$LOC12)"
fi

# ---------------------------------------------------------------------------
# T13: the collector session file and its directory are secured BEFORE any
# client work — 0700 dir, 0600 session — so a fresh --login can never leave
# the Telegram auth key world-readable under a permissive umask.
# ---------------------------------------------------------------------------
HUB13="$TMPDIR_TEST/hub-t13"; make_hub "$HUB13"
PERMS=$(umask 022; $PY - "$HUB13" <<'PYEOF'
import os, sys, stat
from pathlib import Path
sys.path.insert(0, os.environ.get("SRC_BIN") or str(Path.home() / "knowledge" / "bin"))
import importlib.util
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("ktp", (os.environ.get("SRC_BIN") or str(Path.home()/"knowledge"/"bin")) + "/kb-telegram-people")
ktp = importlib.util.module_from_spec(importlib.util.spec_from_loader("ktp", _l)); _l.exec_module(ktp)
hub = Path(sys.argv[1])
sess = ktp.session_path(hub)
ktp._ensure_session_security(sess)
d = stat.S_IMODE(os.stat(sess.parent).st_mode)
f = stat.S_IMODE(os.stat(sess).st_mode)
print(f"{oct(d)}/{oct(f)}")
PYEOF
)
[[ "$PERMS" == "0o700/0o600" ]] && ok "T13: session dir 0700 + session file 0600 pre-created before login" || fail "T13: session perms $PERMS"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
