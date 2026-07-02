#!/usr/bin/env bash
# Mail window / watermark (AC11): the window is incremental — each run reads from
# the GLOBAL high-water mark (last point any period covered) to now, so morning
# and evening tile the day with no overlap (no stale re-read) and no gap; a missed
# run catches up, capped at MAX_LOOKBACK_DAYS. Regression for the Codex finding
# "mail window re-reads stale mail after normal watermark".
#
# Spec: knowledge/decisions/mail-briefing-integration-2026-06-29.md (window selection, AC11)

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MAIL_SRC_BIN:-$HOME/knowledge/bin}"
BRIEF="$SRC_BIN/kb-mail-brief"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

HUB="$TMP/hub"; mkdir -p "$HUB/personal"
FAKE="$TMP/fake"; mkdir -p "$FAKE"; echo ok > "$FAKE/mode"
echo '[{"thread_ref":"t","message_ref":"m","date":"2026-07-02","time":"06:02","sender_label":"x","subject":"hi","classification":"fyi","urgency":"low","action_needed":false,"summary":"s","proposed_actions":[],"privacy_flags":[],"confidence":"low"}]' > "$FAKE/threads.json"

# run <period> <iso-now> -> prints "<from>|<to>"
run() {
  KB_HUB="$HUB" KB_MAIL_FAKE_DIR="$FAKE" KB_MAIL_NOW="$2" "$BRIEF" --period "$1" --write --json 2>/dev/null \
    | python3 -c 'import json,sys; e=json.load(sys.stdin); print(e["window"]["from"]+"|"+e["window"]["to"])'
}

# Run 1 — first ever morning run: no watermark, falls back to the fixed period
# window (previous evening 20:30). Sets the watermark to its `to`.
W1=$(run morning "2026-07-02T06:15:00+02:00"); F1=${W1%|*}; T1=${W1#*|}
[[ "$T1" == "2026-07-02T06:15:00+02:00" ]] && ok "run1: to = now" || fail "run1: to=$T1"
[[ "$F1" == "2026-07-01T20:30:00+02:00" ]] && ok "run1: first run uses fixed period start (prev 20:30)" || fail "run1: from=$F1"

# Run 2 — evening: must start at the MORNING watermark (06:15), not the evening
# period start (07:00) and not before — proves no cross-period stale re-read.
W2=$(run evening "2026-07-02T20:30:00+02:00"); F2=${W2%|*}
[[ "$F2" == "2026-07-02T06:15:00+02:00" ]] && ok "run2: evening reads from global watermark (06:15), no re-read/gap" || fail "run2: from=$F2"

# Run 3 — next morning: starts at the EVENING watermark (20:30), reads overnight
# only. Forward progress: from advanced past run2's from.
W3=$(run morning "2026-07-03T06:15:00+02:00"); F3=${W3%|*}
[[ "$F3" == "2026-07-02T20:30:00+02:00" ]] && ok "run3: morning reads from prior evening watermark (overnight only)" || fail "run3: from=$F3"

# Run 4 — a week-long gap: catch-up must be CAPPED at now - MAX_LOOKBACK_DAYS (3d),
# not the stale 07-03 watermark, so a long outage never becomes an unbounded audit.
W4=$(run morning "2026-07-10T06:15:00+02:00"); F4=${W4%|*}
[[ "$F4" == "2026-07-07T06:15:00+02:00" ]] && ok "run4: long gap capped at max-lookback (3 days)" || fail "run4: from=$F4"

echo; echo "PASS=$PASS FAIL=$FAIL"; [[ "$FAIL" == "0" ]]
