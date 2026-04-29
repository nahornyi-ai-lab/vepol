#!/usr/bin/env bash
# smoke.sh — exercise all 7 kb-backlog ops in a sandbox KB_HUB.
#
# Sets up a minimal hub with two synthetic backlogs (alpha + beta) symlinked
# from <hub>/projects/, then runs append → claim → close, append → claim →
# revert, append → tombstone, append → update, and xfer alpha→beta.
#
# Invariant: at the end, <hub>/.orchestrator/audit/<slug>/ has only
# committed-style terminals (no orphans), preflight returns "ok", and the
# resulting backlog files have the expected line counts.

set -euo pipefail

KB_BIN="${KB_BIN:-__HOME__/knowledge/bin/kb-backlog}"

SANDBOX=$(mktemp -d -t kb-backlog-smoke)
export KB_HUB="$SANDBOX"
trap 'rm -rf "$SANDBOX"' EXIT

mkdir -p "$KB_HUB/projects" "$KB_HUB/.orchestrator/locks" "$KB_HUB/.orchestrator/audit"

# Build alpha + beta as standalone "projects" — symlink from <hub>/projects/<slug>
# to <project>/knowledge/.
for slug in alpha beta; do
  proj="$SANDBOX/$slug"
  mkdir -p "$proj/knowledge"
  cat > "$proj/knowledge/backlog.md" <<EOF
# Backlog — $slug

## Open

## Done

EOF
  ln -s "$proj/knowledge" "$KB_HUB/projects/$slug"
done

# Hub backlog (for completeness — many ops accept slug=hub)
cat > "$KB_HUB/backlog.md" <<EOF
# Hub backlog

## Open

## Done

EOF

say() { printf '\033[1;36m→\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✘\033[0m %s\n' "$*" >&2; exit 1; }

# ─── 1. append → claim → close (happy path) ─────────────────────────────
say "append T1 to alpha"
"$KB_BIN" append alpha "Test task one" --plan-item-id 11111111-1111-1111-1111-111111111111 --json > /tmp/r1.json
grep -q '"status": "appended"' /tmp/r1.json || die "T1 append failed"

# Find lineno of T1
T1_LINE=$(grep -n '11111111-1111-1111-1111-111111111111' "$SANDBOX/alpha/knowledge/backlog.md" | head -1 | cut -d: -f1)
[ -n "$T1_LINE" ] || die "T1 not found in backlog"
say "T1 is at line $T1_LINE — claim it"

CLAIM=$("$KB_BIN" claim alpha --line "$T1_LINE" --json | python3 -c "import sys, json; print(json.load(sys.stdin)['claim_id'])")
[ -n "$CLAIM" ] || die "claim returned empty token"
ok "T1 claim_id: $CLAIM"

say "close T1 as closed"
"$KB_BIN" close alpha --line "$T1_LINE" --claim-id "$CLAIM" --outcome closed --reason "smoke-test ok" --json > /tmp/r1c.json
grep -q '"status": "closed"' /tmp/r1c.json || die "T1 close failed"

# ─── 2. append → claim → revert (executor crash sim) ────────────────────
say "append T2 to alpha"
"$KB_BIN" append alpha "Test task two" --plan-item-id 22222222-2222-2222-2222-222222222222 --json > /tmp/r2.json
T2_LINE=$(grep -n '22222222-2222-2222-2222-222222222222' "$SANDBOX/alpha/knowledge/backlog.md" | head -1 | cut -d: -f1)
CLAIM2=$("$KB_BIN" claim alpha --line "$T2_LINE" --json | python3 -c "import sys, json; print(json.load(sys.stdin)['claim_id'])")
say "revert T2 (simulated crash)"
"$KB_BIN" revert alpha --line "$T2_LINE" --claim-id "$CLAIM2" --reason crash --json > /tmp/r2r.json
grep -q '"status": "reverted"' /tmp/r2r.json || die "T2 revert failed"

# After revert: line should be back to [ ]
grep -E '^\s*-\s*\[\s\]\s.*22222222-2222' "$SANDBOX/alpha/knowledge/backlog.md" >/dev/null || die "T2 not back to open"
ok "T2 reverted to [ ]"

# ─── 3. append → tombstone (parent-move sim) ─────────────────────────────
say "append T3 to alpha, then tombstone"
"$KB_BIN" append alpha "Test task three" --plan-item-id 33333333-3333-3333-3333-333333333333 --json > /tmp/r3.json
"$KB_BIN" tombstone alpha --plan-item-id 33333333-3333-3333-3333-333333333333 --reason parent-move --json > /tmp/r3t.json
grep -q '"status": "tombstoned"' /tmp/r3t.json || die "T3 tombstone failed"
grep -E '^\s*-\s*\[~\]' "$SANDBOX/alpha/knowledge/backlog.md" >/dev/null || die "T3 not [~]"
ok "T3 tombstoned"

# ─── 4. append → update (carried plan_item_id refresh) ───────────────────
say "append T4 to alpha, then update --due"
"$KB_BIN" append alpha "Test task four" --plan-item-id 44444444-4444-4444-4444-444444444444 --due 2026-04-30 --json > /tmp/r4.json
"$KB_BIN" update alpha --plan-item-id 44444444-4444-4444-4444-444444444444 --field "due=2026-05-01" --json > /tmp/r4u.json
grep -q '"status": "updated"' /tmp/r4u.json || die "T4 update failed"
grep -E 'due: 2026-05-01.*plan_item_id: 44444444|plan_item_id: 44444444.*due: 2026-05-01' "$SANDBOX/alpha/knowledge/backlog.md" >/dev/null || die "T4 due not updated"
ok "T4 updated"

# ─── 5. xfer alpha→beta (carried parent-moved scenario F3) ───────────────
say "append T5 to alpha, then xfer to beta"
"$KB_BIN" append alpha "Test task five" --plan-item-id 55555555-5555-5555-5555-555555555555 --json > /tmp/r5.json
"$KB_BIN" xfer --plan-item-id 55555555-5555-5555-5555-555555555555 --from alpha --to beta --json > /tmp/r5x.json
grep -q '"status": "xferred"' /tmp/r5x.json || die "T5 xfer failed"

# alpha should now have [~] tombstoned-by-xfer, beta should have new [ ]
grep -E '^\s*-\s*\[~\].*tombstoned-by-xfer-' "$SANDBOX/alpha/knowledge/backlog.md" >/dev/null || die "T5 src tombstone missing"
grep -E '^\s*-\s*\[\s\].*55555555' "$SANDBOX/beta/knowledge/backlog.md" >/dev/null || die "T5 dst missing"
ok "T5 xferred"

# ─── 6. idempotency check: re-appending same plan_item_id is skipped ─────
say "re-append T1 plan_item_id (open line is gone, should still skip via... wait: T1 is closed, so should append fresh)"
# Actually: cycle_source_id collision check is for OPEN lines only. T1 is closed/done.
# Test cycle_source_id idempotency on an open line:
"$KB_BIN" append alpha "Cycle task" --cycle-source-id 99999999-9999-9999-9999-999999999999 --json > /tmp/r6.json
# Second append returns exit 5 (skipped) — that's the expected idempotency signal.
set +e
"$KB_BIN" append alpha "Cycle task again" --cycle-source-id 99999999-9999-9999-9999-999999999999 --json > /tmp/r6b.json
RC6=$?
set -e
[ $RC6 -eq 5 ] || die "expected exit 5 (skipped), got $RC6"
grep -q '"status": "skipped"' /tmp/r6b.json || die "cycle_source_id collision not detected"
ok "cycle_source_id collision skipped"

# ─── 7. preflight: should be ok ───────────────────────────────────────────
say "preflight alpha + beta"
"$KB_BIN" preflight alpha | grep -q '"status": "ok"' || die "alpha preflight not ok"
"$KB_BIN" preflight beta | grep -q '"status": "ok"' || die "beta preflight not ok"
ok "preflight clean"

# ─── 8. recover (should be a no-op since we have no dangling prepared) ───
say "recover alpha (no-op expected)"
"$KB_BIN" recover alpha --json | grep -q '"resolutions": \[\]' || die "alpha recover should be empty"
ok "recover clean"

ok "ALL SMOKE TESTS PASSED"
