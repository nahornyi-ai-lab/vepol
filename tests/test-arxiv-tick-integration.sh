#!/usr/bin/env bash
# Acceptance #5 (KEY TEST per Codex review): kb-tick failure isolation.
# Mock kb-arxiv-pull as (a) rc=1, (b) hangs past 60s timeout, (c) FileNotFoundError.
# In every case: kb-tick still calls kb-brief exactly once; brief_fired
# remains driven only by kb-brief rc, never by kb-arxiv-pull.
#
# Updated for the processes release (processes-release-spec-2026-06-09):
# kb-tick is gated by personal/processes.yaml; learning (kb-daily-research
# --text-only) runs after:daily on the NEXT tick; the background
# KB_ARXIV_NOTEBOOKLM_ENABLE branch is removed (no background NotebookLM).
#
# Strategy: drive kb-tick with a synthetic plan + processes.yaml in a tmp
# HUB, replace bin/kb-arxiv-pull with various mocks, replace bin/kb-brief
# with a canary that bumps a counter file. Verify exactly-once invariant.
#
# Usage: bash tests/test-arxiv-tick-integration.sh
#   KB_TICK_SRC_BIN=<dir> to test a different kb-tick source (default:
#   $HOME/knowledge/bin — the live install).

set -euo pipefail

PASS=0
FAIL=0
TMPHUB=$(mktemp -d)
trap 'rm -rf "$TMPHUB"' EXIT

SRC_BIN="${KB_TICK_SRC_BIN:-$HOME/knowledge/bin}"

mkdir -p "$TMPHUB/bin" "$TMPHUB/logs" "$TMPHUB/personal"
export KB_HUB="$TMPHUB"

# kb-tick shebang is `#!/usr/bin/env python3` and uses Python 3.10+ syntax.
# Production launchd has /opt/homebrew/bin AT THE FRONT of PATH so env picks
# the homebrew interpreter; mirror that here unconditionally so /usr/bin/python3
# (3.9 on stock macOS) doesn't get picked up first and crash on `dict | None`.
if [[ -d /opt/homebrew/bin ]]; then
  export PATH="/opt/homebrew/bin:$PATH"
fi

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# Copy the real kb-tick + its config reader into the tmp hub (reads env KB_HUB).
cp "$SRC_BIN/kb-tick" "$TMPHUB/bin/kb-tick"
cp "$SRC_BIN/_kb_processes.py" "$TMPHUB/bin/_kb_processes.py"
chmod +x "$TMPHUB/bin/kb-tick"

# Stub kb-doctor (called by channel_instances_guard, returns empty findings JSON).
cat > "$TMPHUB/bin/kb-doctor" <<'EOF'
#!/usr/bin/env bash
echo '{"findings": []}'
EOF
chmod +x "$TMPHUB/bin/kb-doctor"

write_plan() {
  TODAY=$(date +%Y-%m-%d)
  cat > "$TMPHUB/logs/today-plan.json" <<EOF
{
  "date": "$TODAY",
  "brief_hm": "00:00",
  "retro_hm": "23:59",
  "brief_fired": false,
  "retro_fired": false
}
EOF
}

# daily always eligible (00:00); learning declared after:daily so the
# dependent-tick scenarios below can exercise it; retro disabled.
cat > "$TMPHUB/personal/processes.yaml" <<'EOF'
- id: daily
  enabled: true
  when: "00:00"
  run: kb-brief
  outputs: [telegram, file]
- id: retro
  enabled: false
  when: "23:59"
  run: kb-retro
  outputs: [telegram, file]
- id: learning
  enabled: true
  when: after:daily
  run: kb-daily-research --text-only
  outputs: [telegram, file]
EOF

# kb-daily-research stub (used by learning scenarios; rc controlled by marker).
write_daily_research_stub() { # rc
  cat > "$TMPHUB/bin/kb-daily-research" <<EOF
#!/usr/bin/env bash
exit $1
EOF
  chmod +x "$TMPHUB/bin/kb-daily-research"
}
write_daily_research_stub 0

reset_brief_canary() {
  # kb-brief stub: increments counter on every call, exit 0
  cat > "$TMPHUB/bin/kb-brief" <<EOF
#!/usr/bin/env bash
COUNT_FILE="$TMPHUB/brief-call-count.txt"
N=\$(cat "\$COUNT_FILE" 2>/dev/null || echo 0)
echo \$((N+1)) > "\$COUNT_FILE"
exit 0
EOF
  chmod +x "$TMPHUB/bin/kb-brief"
  echo 0 > "$TMPHUB/brief-call-count.txt"
}

run_tick_and_assert_brief_called_once() {
  local label="$1"
  reset_brief_canary
  write_plan
  "$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
  CALLS=$(cat "$TMPHUB/brief-call-count.txt")
  if [[ "$CALLS" == "1" ]]; then
    ok "$label: kb-brief called exactly once"
  else
    fail "$label: kb-brief called $CALLS times (expected 1)"
  fi
  # brief_fired must be true since canary returned rc=0
  FIRED=$(python3 -c "import json; print(json.load(open('$TMPHUB/logs/today-plan.json'))['brief_fired'])")
  [[ "$FIRED" == "True" ]] && ok "$label: brief_fired=True (driven by kb-brief rc=0, not kb-arxiv-pull)" || fail "$label: brief_fired=$FIRED"
}

# === Scenario A: kb-arxiv-pull rc=1 ===
echo "=== A: kb-arxiv-pull rc=1 ==="
cat > "$TMPHUB/bin/kb-arxiv-pull" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-pull"
run_tick_and_assert_brief_called_once "A(rc=1)"

# === Scenario B: kb-arxiv-pull hangs past 60s timeout ===
# kb-tick hardcodes timeout=60 for the prefetch; patch to timeout=2 and hang
# for 5s. Verify TimeoutExpired ⇒ brief still fires.
echo "=== B: kb-arxiv-pull hangs (TimeoutExpired) ==="
sed 's/timeout=60,/timeout=2,/' "$SRC_BIN/kb-tick" > "$TMPHUB/bin/kb-tick"
chmod +x "$TMPHUB/bin/kb-tick"
cat > "$TMPHUB/bin/kb-arxiv-pull" <<'EOF'
#!/usr/bin/env bash
sleep 5
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-pull"
run_tick_and_assert_brief_called_once "B(timeout)"
# Restore real kb-tick
cp "$SRC_BIN/kb-tick" "$TMPHUB/bin/kb-tick"
chmod +x "$TMPHUB/bin/kb-tick"

# === Scenario C: kb-arxiv-pull missing (FileNotFoundError) ===
echo "=== C: kb-arxiv-pull missing ==="
rm -f "$TMPHUB/bin/kb-arxiv-pull"
run_tick_and_assert_brief_called_once "C(missing)"

# === Scenario D: kb-arxiv-pull rc=0 (happy path) — sanity ===
echo "=== D: kb-arxiv-pull rc=0 happy path ==="
cat > "$TMPHUB/bin/kb-arxiv-pull" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-pull"
run_tick_and_assert_brief_called_once "D(rc=0)"

# === Scenario E: kb-brief rc=1 — brief_fired must STAY false (existing semantics) ===
echo "=== E: kb-brief rc=1 ⇒ brief_fired stays false ==="
cat > "$TMPHUB/bin/kb-brief" <<'EOF'
#!/usr/bin/env bash
exit 7
EOF
chmod +x "$TMPHUB/bin/kb-brief"
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
FIRED_E=$(python3 -c "import json; print(json.load(open('$TMPHUB/logs/today-plan.json'))['brief_fired'])")
[[ "$FIRED_E" == "False" ]] && ok "E: brief_fired stays False on kb-brief rc=7 (retry next tick)" || fail "E: brief_fired=$FIRED_E (expected False)"

# === Scenario F: background NotebookLM branch is GONE ===
# KB_ARXIV_NOTEBOOKLM_ENABLE used to trigger kb-arxiv-notebooklm from the
# tick; the processes release bans background NotebookLM. Even with the env
# set and the binary present, the tick must never invoke it.
echo "=== F: KB_ARXIV_NOTEBOOKLM_ENABLE no longer triggers background NotebookLM ==="
export KB_ARXIV_NOTEBOOKLM_ENABLE=1
cat > "$TMPHUB/bin/kb-arxiv-notebooklm" <<EOF
#!/usr/bin/env bash
touch "$TMPHUB/arxiv-notebooklm-called.marker"
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-notebooklm"
run_tick_and_assert_brief_called_once "F(no-bg-notebooklm)"
if [[ -f "$TMPHUB/arxiv-notebooklm-called.marker" ]]; then
  fail "F: kb-arxiv-notebooklm was invoked by background tick"
else
  ok "F: kb-arxiv-notebooklm never invoked by background tick"
fi
unset KB_ARXIV_NOTEBOOKLM_ENABLE

# === Scenario I: learning (after:daily) fires on the NEXT tick, rc=0 sets flag ===
echo "=== I: learning after:daily ⇒ next tick, daily_research_fired true ==="
write_daily_research_stub 0
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true   # tick 1: daily fires
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true   # tick 2: learning fires
FIRED_I=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('daily_research_fired', False))")
[[ "$FIRED_I" == "True True" ]] && ok "I: brief_fired=True, daily_research_fired=True" || fail "I: flags=$FIRED_I"

# === Scenario J: learning rc=1 leaves daily_research_fired false ===
echo "=== J: kb-daily-research rc=1 ⇒ daily_research_fired false ==="
write_daily_research_stub 1
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
FIRED_J=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('daily_research_fired', False))")
[[ "$FIRED_J" == "True False" ]] && ok "J: brief_fired=True, daily_research_fired=False" || fail "J: flags=$FIRED_J"

echo
echo "=== arXiv-tick integration tests: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] || exit 1
