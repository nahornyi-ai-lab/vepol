#!/usr/bin/env bash
# run-all.sh — exercise every Phase 1b test fixture in sequence.
# Exit non-zero on any failure.
set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(cd .. && pwd)"

# Sanitized seed/public fixtures use literal __HOME__/knowledge/... paths.
# Provide that layout locally so the same fixtures run from source checkouts.
COMPAT_HOME="$PWD/__HOME__"
rm -rf "$COMPAT_HOME"
mkdir -p "$COMPAT_HOME/knowledge"
ln -s "$REPO_ROOT/bin" "$COMPAT_HOME/knowledge/bin"
ln -s "$PWD" "$COMPAT_HOME/knowledge/tests"
cleanup() {
  rm -rf "$COMPAT_HOME"
}
trap cleanup EXIT

pass() { printf '\033[1;32m●\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m●\033[0m %s\n' "$*" >&2; }

echo "=== Startup context hotfix bundle ==="
KB_SESSION_START="$REPO_ROOT/bin/kb-session-start" \
KB_STARTUP_TEST_HUB="$REPO_ROOT" \
python3 startup-context/hotfix.py > /dev/null && pass "startup-context/hotfix.py" || { fail "startup-context"; exit 1; }

echo
echo "=== kb-backlog smoke ==="
bash kb-backlog/smoke.sh > /dev/null && pass "smoke.sh (7 ops)" || { fail "smoke.sh"; exit 1; }

echo
echo "=== claim drift detection (token + content_hash, CR1-B4) ==="
bash kb-backlog/claim-drift.sh > /dev/null && pass "claim-drift.sh" || { fail "claim-drift.sh"; exit 1; }

echo
echo "=== kb-board single-source markdown contract ==="
bash kb-board/run.sh > /dev/null && pass "kb-board/run.sh (29 contract tests)" || { fail "kb-board/run.sh"; exit 1; }

echo
echo "=== kb-search board smoke ==="
bash kb-search/smoke.sh > /dev/null && pass "kb-search/smoke.sh" || { fail "kb-search/smoke.sh"; exit 1; }

echo
echo "=== audit-recovery (F-CR-1..F-CR-4) ==="
python3 audit-recovery/crash.py > /dev/null && pass "crash.py (4 fixtures)" || { fail "crash.py"; exit 1; }

echo
echo "=== rotation + chain replay (F-CR-7 + F-CR-8) ==="
python3 audit-recovery/rotation-and-chain.py > /dev/null && pass "rotation-and-chain.py" || { fail "rotation-and-chain.py"; exit 1; }

echo
echo "=== preflight-corruption (F-PC-1..F-PC-4) ==="
python3 preflight-corruption/corruption.py > /dev/null && pass "corruption.py (4 fixtures)" || { fail "corruption.py"; exit 1; }

echo
echo "=== xfer happy + from==to (F3 + F4) ==="
python3 kb-backlog-xfer/xfer.py > /dev/null && pass "xfer.py" || { fail "xfer.py"; exit 1; }

echo
echo "=== xfer crash recovery (F-CR-5 + F-CR-6) ==="
python3 kb-backlog-xfer/crash.py > /dev/null && pass "crash.py (xfer)" || { fail "crash.py xfer"; exit 1; }

echo
echo "=== agent-contract (8 OUTCOME shapes) ==="
python3 agent-contract/parse.py > /dev/null && pass "parse.py (8 shapes)" || { fail "parse.py"; exit 1; }

echo
echo "=== lock-order linter ==="
python3 lock-order/linter.py > /dev/null && pass "linter.py" || { fail "linter.py"; exit 1; }

echo
echo "=== race (3 concurrent writers × 30 appends each) ==="
python3 race/concurrent.py > /dev/null && pass "concurrent.py (90 tasks)" || { fail "concurrent.py"; exit 1; }

echo
echo "=== Phase 3 cycle retro (3-node hierarchy, BFS bottom-up) ==="
python3 cycle-retro/fixture.py > /dev/null && pass "cycle-retro/fixture.py" || { fail "cycle-retro"; exit 1; }

echo
echo "=== Phase 3 CR4+CR5 fixes (B2 disabled-ancestor, B3 no-overwrite, B4 MAX_FANOUT, CR5-B3 spawn-skip) ==="
python3 cycle-retro/cr4-fixes.py > /dev/null && pass "cycle-retro/cr4-fixes.py" || { fail "cr4-fixes"; exit 1; }

echo
echo "=== Phase 3 CR5-B2 broker race (6 concurrent kb-orchestrator-run) ==="
python3 cycle-retro/broker-race.py > /dev/null && pass "cycle-retro/broker-race.py" || { fail "broker-race"; exit 1; }

echo
echo "=== Wave-rollup-to-log (T1-T6, 22 ассерций) ==="
python3 wave-rollup/test-wave-rollup.py > /dev/null && pass "wave-rollup/test-wave-rollup.py" || { fail "wave-rollup"; exit 1; }

echo
echo "=== Phase 5 carried-item plan dispatch (F1-F4) ==="
python3 cycle-plan/fixtures.py > /dev/null && pass "cycle-plan/fixtures.py" || { fail "cycle-plan"; exit 1; }

echo
echo "=== Daily-plan generator v0.1 (E2E-1..E2E-15) ==="
python3 daily-plan-gen/fixtures.py > /dev/null && pass "daily-plan-gen/fixtures.py" || { fail "daily-plan-gen"; exit 1; }

echo
echo "=== Vepol Idea Intake acceptance vertical ==="
python3 idea-os/idea_os.py > /dev/null && pass "idea-os/idea_os.py" || { fail "idea-os"; exit 1; }

echo
echo "=== Owner-approved spec gate methodology contract ==="
python3 methodology/owner_spec_gate.py > /dev/null && pass "methodology/owner_spec_gate.py" || { fail "owner-spec-gate"; exit 1; }

echo
echo "=== Evolution Loop v0-minimal fixtures ==="
python3 evolution/fixtures.py > /dev/null && pass "evolution/fixtures.py" || { fail "evolution"; exit 1; }

echo
echo "=== Phase 6 bootstrap acceptance (synthetic 3-project end-to-end) ==="
python3 bootstrap/synthetic.py > /dev/null && pass "bootstrap/synthetic.py" || { fail "bootstrap"; exit 1; }

echo
echo "=== Installer idempotency smoke ==="
bash install/idempotency.sh > /dev/null && pass "install/idempotency.sh" || { fail "install/idempotency.sh"; exit 1; }

echo
echo "=== Installer agent modes (prompt-first: probe/dry-run/verify/apply, C-01, managed-only uninstall) ==="
bash install/agent-modes.sh > /dev/null && pass "install/agent-modes.sh (23 cases)" || { fail "install/agent-modes.sh"; exit 1; }

echo
echo "=== Phase 8 kb-doctor periodic checks ==="
python3 kb-doctor/phase8.py > /dev/null && pass "kb-doctor/phase8.py (11 fixtures)" || { fail "phase8"; exit 1; }

echo
echo "=== Processes release (processes.yaml gating, 13 acceptance cases) ==="
bash processes/run.sh > /dev/null && pass "processes/run.sh (76 assertions)" || { fail "processes/run.sh"; exit 1; }

echo
echo "=== ALL Phase 1b tests passed ==="
