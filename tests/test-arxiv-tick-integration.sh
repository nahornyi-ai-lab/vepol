#!/usr/bin/env bash
# Acceptance #5 (KEY TEST per Codex review): kb-tick failure isolation.
# Mock kb-arxiv-pull as (a) rc=1, (b) hangs past 60s timeout, (c) FileNotFoundError.
# In every case: kb-tick still calls kb-brief exactly once; brief_fired
# remains driven only by kb-brief rc, never by kb-arxiv-pull.
#
# Strategy: drive kb-tick with a synthetic plan in a tmp HUB, replace
# bin/kb-arxiv-pull with various mocks, replace bin/kb-brief with a
# canary that bumps a counter file. Verify exactly-once invariant.
#
# Usage: bash bin/tests/test-arxiv-tick-integration.sh

set -euo pipefail

PASS=0
FAIL=0
TMPHUB=$(mktemp -d)
trap 'rm -rf "$TMPHUB"' EXIT

mkdir -p "$TMPHUB/bin" "$TMPHUB/logs"
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

# Copy the real kb-tick into the tmp hub (it reads env KB_HUB).
cp "$HOME/knowledge/bin/kb-tick" "$TMPHUB/bin/kb-tick"
chmod +x "$TMPHUB/bin/kb-tick"

# Stub kb-doctor (called by channel_instances_guard, returns empty findings JSON).
cat > "$TMPHUB/bin/kb-doctor" <<'EOF'
#!/usr/bin/env bash
echo '{"findings": []}'
EOF
chmod +x "$TMPHUB/bin/kb-doctor"

# kb-retro stub (won't be invoked; retro_hm set far in future).
cat > "$TMPHUB/bin/kb-retro" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-retro"

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
    ok "$label: kb-brief called exactly once (rc was: $(grep "kb-brief completed" "$TMPHUB/logs/planner.log" | tail -1))"
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
# Use a very short timeout for testing by patching kb-tick env? No — kb-tick
# hardcodes timeout=60. Instead, test the structural path: patch kb-tick to use
# timeout=2, hang for 5s. Verify TimeoutExpired ⇒ brief still fires.
echo "=== B: kb-arxiv-pull hangs (TimeoutExpired) ==="
sed 's/timeout=60,/timeout=2,/' "$HOME/knowledge/bin/kb-tick" > "$TMPHUB/bin/kb-tick"
chmod +x "$TMPHUB/bin/kb-tick"
cat > "$TMPHUB/bin/kb-arxiv-pull" <<'EOF'
#!/usr/bin/env bash
sleep 5
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-pull"
run_tick_and_assert_brief_called_once "B(timeout)"
# Restore real kb-tick
cp "$HOME/knowledge/bin/kb-tick" "$TMPHUB/bin/kb-tick"
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
cat > "$TMPHUB/bin/kb-arxiv-pull" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-pull"
cat > "$TMPHUB/bin/kb-brief" <<'EOF'
#!/usr/bin/env bash
exit 7
EOF
chmod +x "$TMPHUB/bin/kb-brief"
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
FIRED_E=$(python3 -c "import json; print(json.load(open('$TMPHUB/logs/today-plan.json'))['brief_fired'])")
[[ "$FIRED_E" == "False" ]] && ok "E: brief_fired stays False on kb-brief rc=7 (retry next tick)" || fail "E: brief_fired=$FIRED_E (expected False)"

# === Scenario F: kb-arxiv-notebooklm rc=1 must not affect brief_fired ===
echo "=== F: kb-arxiv-notebooklm rc=1 ⇒ brief ok, notebook flag false ==="
cat > "$TMPHUB/bin/kb-arxiv-pull" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-pull"
cat > "$TMPHUB/bin/kb-arxiv-notebooklm" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-notebooklm"
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
CALLS_F=$(cat "$TMPHUB/brief-call-count.txt")
[[ "$CALLS_F" == "1" ]] && ok "F: kb-brief called once despite NotebookLM rc=1" || fail "F: kb-brief calls=$CALLS_F"
FIRED_F=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('arxiv_notebooklm_fired', False))")
[[ "$FIRED_F" == "True False" ]] && ok "F: brief_fired=True, arxiv_notebooklm_fired=False" || fail "F: flags=$FIRED_F"

# === Scenario G: kb-arxiv-notebooklm rc=0 sets arxiv_notebooklm_fired ===
echo "=== G: kb-arxiv-notebooklm rc=0 ⇒ notebook flag true ==="
export KB_ARXIV_NOTEBOOKLM_ENABLE=1
cat > "$TMPHUB/bin/kb-arxiv-notebooklm" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-notebooklm"
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
FIRED_G=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('arxiv_notebooklm_fired', False))")
[[ "$FIRED_G" == "True True" ]] && ok "G: brief_fired=True, arxiv_notebooklm_fired=True" || fail "G: flags=$FIRED_G"

# === Scenario H: kb-arxiv-notebooklm timeout must not affect brief_fired ===
echo "=== H: kb-arxiv-notebooklm timeout ⇒ brief ok, notebook flag false ==="
export KB_ARXIV_NOTEBOOKLM_ENABLE=1
sed 's/timeout=900,/timeout=1,/' "$HOME/knowledge/bin/kb-tick" > "$TMPHUB/bin/kb-tick"
chmod +x "$TMPHUB/bin/kb-tick"
cat > "$TMPHUB/bin/kb-arxiv-notebooklm" <<'EOF'
#!/usr/bin/env bash
sleep 3
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-notebooklm"
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
CALLS_H=$(cat "$TMPHUB/brief-call-count.txt")
[[ "$CALLS_H" == "1" ]] && ok "H: kb-brief called once despite NotebookLM timeout" || fail "H: kb-brief calls=$CALLS_H"
FIRED_H=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('arxiv_notebooklm_fired', False))")
[[ "$FIRED_H" == "True False" ]] && ok "H: brief_fired=True, arxiv_notebooklm_fired=False" || fail "H: flags=$FIRED_H"
unset KB_ARXIV_NOTEBOOKLM_ENABLE

# === Scenario I: kb-daily-research rc=0 sets daily_research_fired ===
echo "=== I: kb-daily-research rc=0 ⇒ daily_research_fired true ==="
cp "$HOME/knowledge/bin/kb-tick" "$TMPHUB/bin/kb-tick"
chmod +x "$TMPHUB/bin/kb-tick"
cat > "$TMPHUB/bin/kb-arxiv-notebooklm" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-arxiv-notebooklm"
cat > "$TMPHUB/bin/kb-daily-research" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMPHUB/bin/kb-daily-research"
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
FIRED_I=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('daily_research_fired', False))")
[[ "$FIRED_I" == "True True" ]] && ok "I: brief_fired=True, daily_research_fired=True" || fail "I: flags=$FIRED_I"

# === Scenario J: kb-daily-research rc=1 leaves daily_research_fired false ===
echo "=== J: kb-daily-research rc=1 ⇒ daily_research_fired false ==="
cat > "$TMPHUB/bin/kb-daily-research" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$TMPHUB/bin/kb-daily-research"
reset_brief_canary
write_plan
"$TMPHUB/bin/kb-tick" >/dev/null 2>&1 || true
FIRED_J=$(python3 -c "import json; p=json.load(open('$TMPHUB/logs/today-plan.json')); print(p.get('brief_fired'), p.get('daily_research_fired', False))")
[[ "$FIRED_J" == "True False" ]] && ok "J: brief_fired=True, daily_research_fired=False" || fail "J: flags=$FIRED_J"

echo
echo "=== arXiv-tick integration tests: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]]
