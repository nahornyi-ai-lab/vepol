#!/usr/bin/env bash
# run-all.sh — exercise every Phase 1b test fixture in sequence.
# Exit non-zero on any failure.
set -euo pipefail

cd "$(dirname "$0")"

pass() { printf '\033[1;32m●\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m●\033[0m %s\n' "$*" >&2; }

echo "=== kb-backlog smoke ==="
bash kb-backlog/smoke.sh > /dev/null && pass "smoke.sh (7 ops)" || { fail "smoke.sh"; exit 1; }

echo
echo "=== claim drift detection (token + content_hash, CR1-B4) ==="
bash kb-backlog/claim-drift.sh > /dev/null && pass "claim-drift.sh" || { fail "claim-drift.sh"; exit 1; }

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
echo "=== Phase 5 carried-item plan dispatch (F1-F4) ==="
python3 cycle-plan/fixtures.py > /dev/null && pass "cycle-plan/fixtures.py" || { fail "cycle-plan"; exit 1; }

echo
echo "=== Phase 6 bootstrap acceptance (synthetic 3-project end-to-end) ==="
python3 bootstrap/synthetic.py > /dev/null && pass "bootstrap/synthetic.py" || { fail "bootstrap"; exit 1; }

echo
echo "=== Phase 8 kb-doctor periodic checks ==="
python3 kb-doctor/phase8.py > /dev/null && pass "kb-doctor/phase8.py (6 fixtures)" || { fail "phase8"; exit 1; }

echo
echo "=== ALL Phase 1b tests passed ==="
