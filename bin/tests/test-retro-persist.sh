#!/usr/bin/env bash
# kb-retro persists the retro text into the day file (AC1, daily-audio-digests):
# after composing, the RETRO block is appended to briefs/<today>.md as a
# `## Retro (HH:MM)` section so the day file becomes the durable source for the
# evening audio digest. The Telegram path is unchanged, a missing day file
# degrades gracefully (warn, no crash), and a re-run never produces a duplicate
# `## Retro` section (one persisted retro per day file).
#
# Spec: knowledge/decisions/daily-audio-digests-2026-07-02.md  (D1, AC1)

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_DIGEST_SRC_BIN:-$HOME/knowledge/bin}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

TODAY=$(date +%Y-%m-%d)

# ── Fixture hub: real kb-retro, FAKE orchestrator (canned RETRO/REFLECTION) ──
HUB="$TMP/hub"
mkdir -p "$HUB/personal" "$HUB/bin" "$HUB/briefs" "$HUB/logs"
: > "$HUB/personal/.secrets"

# kb-retro calls $HUB/bin/kb-orchestrator-run — plant a fake that returns a
# deterministic retro so the test exercises the real persist path, no LLM.
cat > "$HUB/bin/kb-orchestrator-run" <<'FAKE'
#!/bin/sh
cat <<'OUT'
---RETRO---
1. Closed today: canned-retro-marker shipped the audio digests.
2. Backlog: five open items.
---REFLECTION---
Brief matched the day; tomorrow add the evening recap.
OUT
FAKE
chmod +x "$HUB/bin/kb-orchestrator-run"
# kb-retro also probes kb-board / kb-mail-block from $HUB/bin — fail-soft stubs.
printf '#!/bin/sh\nexit 0\n' > "$HUB/bin/kb-board";      chmod +x "$HUB/bin/kb-board"
printf '#!/bin/sh\nexit 1\n' > "$HUB/bin/kb-mail-block"; chmod +x "$HUB/bin/kb-mail-block"

day_file() {
  cat > "$HUB/briefs/$TODAY.md" <<EOF
---
title: brief
reflection: pending
---

## Morning brief ($TODAY)

Plans for the day.
EOF
}

run_retro() { KB_HUB="$HUB" KB_RETRO_DRY=1 "$SRC_BIN/kb-retro" 2>/dev/null; }
run_prompt() { KB_HUB="$HUB" KB_RETRO_PROMPT_ONLY=1 "$SRC_BIN/kb-retro" 2>/dev/null; }

# ── v0.5.1 AC1: prompt time authority framing ───────────────────────────────
PROMPT=$(run_prompt)
if [[ -z "$PROMPT" ]]; then
  fail "v0.5.1 AC1: kb-retro prompt-only produced no output"
else
  [[ "$PROMPT" == *"утренний бриф — это план"* \
     && "$PROMPT" == *"исторический контекст"* ]] \
    && ok "v0.5.1 AC1: prompt frames the morning brief as plan/history" \
    || fail "v0.5.1 AC1: prompt does not frame the morning brief as plan/history"
  [[ "$PROMPT" == *"Текущее состояние почты бери только из вечернего"* \
     && "$PROMPT" == *"вечерние блоки побеждают утренний бриф"* ]] \
    && ok "v0.5.1 AC1: prompt gives evening mail/current-state precedence" \
    || fail "v0.5.1 AC1: prompt lacks evening mail/current-state precedence"
  [[ "$PROMPT" == *"Не смешивай отсутствие daily-inbox"* \
     && "$PROMPT" == *"не поломка mail briefing"* ]] \
    && ok "v0.5.1 source-health: daily-inbox gaps are not mail-briefing breakage" \
    || fail "v0.5.1 source-health: prompt can still label daily-inbox gaps as mail breakage"
fi

# ── AC1: retro section appended to the day file ──────────────────────────────
day_file
OUT1=$(run_retro); RC1=$?
[[ $RC1 -eq 0 ]] \
  && ok "AC1: kb-retro dry-run exits 0" \
  || fail "AC1: kb-retro dry-run exited rc=$RC1"
grep -q '^## Retro (' "$HUB/briefs/$TODAY.md" \
  && ok "AC1: day file gained a '## Retro (HH:MM)' section" \
  || fail "AC1: no '## Retro (' section in day file"
grep -q 'canned-retro-marker' "$HUB/briefs/$TODAY.md" \
  && ok "AC1: persisted section carries the retro text" \
  || fail "AC1: retro text missing from day file"

# Telegram path unchanged: dry-run still prints the retro message to stdout.
[[ "$OUT1" == *"canned-retro-marker"* ]] \
  && ok "AC1: Telegram (dry) message still contains the retro" \
  || fail "AC1: Telegram (dry) message lost the retro text"

# Reflection path unchanged: section appended + frontmatter flipped.
grep -q '^## Reflection (' "$HUB/briefs/$TODAY.md" \
  && ok "AC1: Reflection section still appended (unchanged path)" \
  || fail "AC1: Reflection section missing"
grep -q '^reflection: done$' "$HUB/briefs/$TODAY.md" \
  && ok "AC1: reflection frontmatter still flipped to done" \
  || fail "AC1: reflection frontmatter not flipped"

# Retro must be persisted BEFORE the Reflection section so the day file reads
# chronologically (brief -> retro -> reflection).
RETRO_LINE=$(grep -n '^## Retro (' "$HUB/briefs/$TODAY.md" | head -1 | cut -d: -f1)
REFL_LINE=$(grep -n '^## Reflection (' "$HUB/briefs/$TODAY.md" | head -1 | cut -d: -f1)
if [[ -n "$RETRO_LINE" && -n "$REFL_LINE" && "$RETRO_LINE" -lt "$REFL_LINE" ]]; then
  ok "AC1: Retro section precedes Reflection in the day file"
else
  fail "AC1: Retro/Reflection order wrong (retro=$RETRO_LINE refl=$REFL_LINE)"
fi

# ── AC1: re-run does not duplicate the Retro section ─────────────────────────
run_retro >/dev/null
N_RETRO=$(grep -c '^## Retro (' "$HUB/briefs/$TODAY.md")
[[ "$N_RETRO" -eq 1 ]] \
  && ok "AC1: re-run keeps exactly one '## Retro' section (got $N_RETRO)" \
  || fail "AC1: re-run duplicated the Retro section (got $N_RETRO)"

# ── AC1 (amended by morning-digest-inputs-rebalance D11, R-impl blocker 1):
# a missing day file no longer stays missing — kb-retro creates a MINIMAL day
# file (frontmatter + Retro section) so the delivery evidence is durable and a
# later planner regeneration cannot re-fire the retro (AC-9 exactly-once). The
# file must NOT fabricate brief content: no `delivery:` key (the brief still
# counts as undelivered) and no brief text.
rm -f "$HUB/briefs/$TODAY.md"
run_retro >/dev/null; RC3=$?
[[ $RC3 -eq 0 ]] \
  && ok "AC1: missing day file — no crash (rc=0)" \
  || fail "AC1: missing day file crashed kb-retro (rc=$RC3)"
DAYF="$HUB/briefs/$TODAY.md"
[[ -f "$DAYF" && "$(head -n 1 "$DAYF")" == "---" ]] \
  && ok "AC1: minimal day file created for retro evidence (D11)" \
  || fail "AC1: minimal day file not created"
grep -q '^## Retro (' "$DAYF" \
  && ok "AC1: retro persisted into the minimal day file" \
  || fail "AC1: retro not persisted into minimal day file"
if awk 'NR==1&&$0=="---"{fm=1;next} fm&&$0=="---"{exit 0} fm&&index($0,"delivery: ")==1{exit 1}' "$DAYF"; then
  ok "AC1: no phantom brief delivery key in minimal day file"
else
  fail "AC1: minimal day file fabricated a brief delivery key"
fi

echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
