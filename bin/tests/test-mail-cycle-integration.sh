#!/usr/bin/env bash
# AC6 — cycle integration: kb-orchestrator-cycle retro bypasses kb-tick by
# invoking hub kb-retro inline, so it must reproduce kb-tick's
# `mail-evening -> retro` ordering itself. Invariant: a cycle path can NEVER
# produce retro without a same-day EVENING mail envelope on disk first.
#
# We reach exactly the guard code path with a deterministic seam,
# KB_CYCLE_GUARD_ONLY=1, that mirrors kb-retro's KB_RETRO_PROMPT_ONLY: the cycle
# runs the mail guard and then stops immediately, before spawning the heavy
# inline kb-retro / LLM work. So when the run returns:
#   - the same-day evening envelope is on disk (guard ran), and
#   - the inline retro has NOT run (no daily "Cycle summary" appended).
# That is the "envelope present before the inline retro" proof.
#
# A minimal hub with a single root node lets cmd_retro walk through steps 1-4
# (no project spawns) straight to the hub-level pre-retro guard.
#
# Spec: knowledge/decisions/mail-briefing-integration-2026-06-29.md (AC6)
# Plan: knowledge/decisions/mail-briefing-integration-build-plan-2026-07-01.md

set -uo pipefail
PASS=0; FAIL=0
ROOT_TMP=$(mktemp -d); trap 'rm -rf "$ROOT_TMP"' EXIT
SRC_BIN="${KB_MAIL_SRC_BIN:-$HOME/knowledge/bin}"
CYCLE="$SRC_BIN/kb-orchestrator-cycle"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

DATE="2026-07-01"                  # cycle --date
NOW="2026-07-01T20:45:00+02:00"    # kb-mail-brief "now" (same day)

# Build an isolated fixture hub. $1 = name.
mk_hub() {
  local hub="$ROOT_TMP/$1"
  mkdir -p "$hub/personal"
  ln -s "$SRC_BIN" "$hub/bin"
  : > "$hub/personal/.secrets"
  cat > "$hub/hierarchy.yaml" <<YAML
root: hub
nodes:
  hub:
    slug: hub
    kind: root
    knowledge_path: $hub
    parent: null
    children: []
    cycle_enabled: false
YAML
  printf '%s' "$hub"
}

# Build a fake Gmail backend fixture. $1 = dir, $2 = mode (ok|unavailable).
mk_fake() {
  local d="$1"; mkdir -p "$d"; echo "$2" > "$d/mode"
  cat > "$d/threads.json" <<'JSON'
[
  { "thread_ref": "t-1", "message_ref": "m-1", "date": "2026-07-01", "time": "18:02",
    "sender_label": "Ops <ops@corp.example>",
    "subject": "deploy status",
    "body": "secret body do-not-persist", "has_attachment": false,
    "classification": "needs_reply", "urgency": "normal", "action_needed": true,
    "summary": "Ops asks for a deploy status update.",
    "proposed_actions": [{"type": "reply_draft", "summary": "Draft a short reply."}],
    "privacy_flags": [], "confidence": "medium" }
]
JSON
}

env_path() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["available"])' "$1" 2>/dev/null; }

# ── Scenario A: normal path — guard runs kb-mail-brief (fake ok) before retro ──
HUB_A=$(mk_hub a); FAKE_A="$ROOT_TMP/fake-a"; mk_fake "$FAKE_A" ok
EVE_A="$HUB_A/personal/mail/briefs/$DATE-evening.json"
ERR_A=$(KB_HUB="$HUB_A" KB_MAIL_NOW="$NOW" KB_MAIL_FAKE_DIR="$FAKE_A" \
        KB_CYCLE_GUARD_ONLY=1 \
        "$CYCLE" retro --date "$DATE" --skip-registry-check 2>&1)
RC_A=$?
[[ "$RC_A" == "0" ]] && ok "A: cycle guard path exits 0 (fail-soft)" || fail "A: cycle exited rc=$RC_A"
[[ -f "$EVE_A" ]] && ok "A: same-day evening envelope on disk before inline retro" \
                  || fail "A: evening envelope missing"
[[ "$(env_path "$EVE_A")" == "True" ]] && ok "A: envelope available:true (fake ok backend)" \
                  || fail "A: envelope not available:true"
[[ "$ERR_A" == *"KB_CYCLE_GUARD_ONLY=1"* ]] && ok "A: stopped at guard, before inline kb-retro" \
                  || fail "A: guard seam marker not seen on stderr"
[[ ! -f "$HUB_A/daily/$DATE.md" || "$(cat "$HUB_A/daily/$DATE.md" 2>/dev/null)" != *"Cycle summary"* ]] \
   && ok "A: inline retro did not run (no daily Cycle summary)" \
   || fail "A: retro appears to have run past the guard"
# No leak of raw sender/body into the envelope file.
if grep -q "ops@corp.example\|secret body" "$EVE_A" 2>/dev/null; then
  fail "A: raw address/body leaked into envelope"
else
  ok "A: no raw address/body in envelope"
fi

# ── Scenario B: Gmail unavailable — guard still guarantees an envelope ─────────
HUB_B=$(mk_hub b); FAKE_B="$ROOT_TMP/fake-b"; mk_fake "$FAKE_B" unavailable
EVE_B="$HUB_B/personal/mail/briefs/$DATE-evening.json"
KB_HUB="$HUB_B" KB_MAIL_NOW="$NOW" KB_MAIL_FAKE_DIR="$FAKE_B" \
  KB_CYCLE_GUARD_ONLY=1 \
  "$CYCLE" retro --date "$DATE" --skip-registry-check >/dev/null 2>&1
RC_B=$?
[[ "$RC_B" == "0" ]] && ok "B: Gmail-unavailable cycle exits 0 (outage does not break cycle)" \
                     || fail "B: cycle exited rc=$RC_B on unavailable Gmail"
[[ -f "$EVE_B" ]] && ok "B: evening envelope present even when Gmail unavailable" \
                  || fail "B: evening envelope missing on unavailable Gmail"
[[ "$(env_path "$EVE_B")" == "False" ]] && ok "B: envelope available:false on unavailable Gmail" \
                  || fail "B: envelope not available:false"
grep -q "gmail_unavailable" "$EVE_B" 2>/dev/null && ok "B: envelope carries gmail_unavailable error" \
                  || fail "B: missing gmail_unavailable error"

# ── Scenario C: fail closed — kb-mail-brief leaves no same-day envelope ────────
# kb-mail-brief exits 0 but writes for a DIFFERENT day (KB_MAIL_NOW on 06-30),
# so the guard's same-day (07-01) re-check finds nothing and must fail closed
# with a direct available:false write. Proves the guard does not trust the
# reader's exit code — only a valid same-day envelope satisfies the invariant.
HUB_C=$(mk_hub c); FAKE_C="$ROOT_TMP/fake-c"; mk_fake "$FAKE_C" ok
OTHER_NOW="2026-06-30T20:45:00+02:00"
EVE_C="$HUB_C/personal/mail/briefs/$DATE-evening.json"
KB_HUB="$HUB_C" KB_MAIL_NOW="$OTHER_NOW" KB_MAIL_FAKE_DIR="$FAKE_C" \
  KB_CYCLE_GUARD_ONLY=1 \
  "$CYCLE" retro --date "$DATE" --skip-registry-check >/dev/null 2>&1
RC_C=$?
[[ "$RC_C" == "0" ]] && ok "C: fail-closed path exits 0" || fail "C: cycle exited rc=$RC_C"
[[ -f "$EVE_C" ]] && ok "C: guard fail-closed direct write produced same-day envelope" \
                  || fail "C: same-day envelope missing after fail-closed path"
[[ "$(env_path "$EVE_C")" == "False" ]] && ok "C: fail-closed envelope available:false" \
                  || fail "C: fail-closed envelope not available:false"
grep -q "gmail_unavailable:cycle-guard-no-envelope" "$EVE_C" 2>/dev/null \
   && ok "C: fail-closed envelope tagged cycle-guard-no-envelope" \
   || fail "C: missing cycle-guard-no-envelope reason"

echo; echo "PASS=$PASS FAIL=$FAIL"; [[ "$FAIL" == "0" ]]
