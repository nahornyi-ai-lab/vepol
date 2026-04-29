#!/usr/bin/env bash
# claim-drift.sh — verify two-layer drift detection (CR1-B4):
#   (1) claim_id token mismatch → drift
#   (2) claim_id matches but line content modified → drift via content_hash
#
# Scenario for (2): a malicious raw writer modifies the claimed line's
# content (e.g. body text, due field) but keeps `claim_id: <token>` intact.
# close/revert recompute claim_content_hash from the line and detect drift.
set -euo pipefail

KB_BIN="${KB_BIN:-__HOME__/knowledge/bin/kb-backlog}"
SANDBOX=$(mktemp -d -t kb-claim-drift)
export KB_HUB="$SANDBOX"
trap 'rm -rf "$SANDBOX"' EXIT

mkdir -p "$KB_HUB/projects" "$KB_HUB/.orchestrator/locks" "$KB_HUB/.orchestrator/audit"
proj="$SANDBOX/alpha"
mkdir -p "$proj/knowledge"
cat > "$proj/knowledge/backlog.md" <<'EOF'
# alpha

## Open

## Done

EOF
ln -s "$proj/knowledge" "$KB_HUB/projects/alpha"
echo "# Hub" > "$KB_HUB/backlog.md"

ok() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✘\033[0m %s\n' "$*" >&2; exit 1; }

# Append + claim
"$KB_BIN" append alpha "Test task with details" --plan-item-id 11111111-1111-1111-1111-111111111111 --json > /tmp/dr1.json
LINE=$(grep -n '11111111-1111-1111-1111-111111111111' "$proj/knowledge/backlog.md" | head -1 | cut -d: -f1)
CLAIM=$("$KB_BIN" claim alpha --line "$LINE" --json | python3 -c "import sys, json; print(json.load(sys.stdin)['claim_id'])")
ok "claim_id: $CLAIM"

# Verify content_hash field is present
grep -E "claim_content_hash:" "$proj/knowledge/backlog.md" >/dev/null || die "claim_content_hash field missing"
ok "claim_content_hash field present"

# Layer 1: wrong token → drift
set +e
"$KB_BIN" close alpha --line "$LINE" --claim-id wrong-token --outcome closed --reason test --json > /tmp/dr2.json
RC1=$?
set -e
[ $RC1 -eq 23 ] || die "wrong token expected exit 23, got $RC1"
grep -q '"drift_kind": "claim_id"' /tmp/dr2.json || die "expected drift_kind=claim_id"
ok "wrong claim_id → drift exit 23"

# Layer 2: tamper line content but keep claim_id → content_hash drift
# Use python to do an in-place edit of the line, preserving claim_id field.
python3 <<EOF
from pathlib import Path
p = Path("$proj/knowledge/backlog.md")
text = p.read_text()
# Append " — tampered: yes" to the body, keeping all fields intact
import re
def patch(m):
    return m.group(1) + " — tampered: yes" + m.group(2)
new_text, n = re.subn(
    r'(- \[>\] Test task with details)( — opened)',
    patch, text,
)
assert n == 1, f"expected 1 substitution, got {n}"
p.write_text(new_text)
EOF

set +e
"$KB_BIN" close alpha --line "$LINE" --claim-id "$CLAIM" --outcome closed --reason test --json > /tmp/dr3.json
RC2=$?
set -e
[ $RC2 -eq 23 ] || die "tampered content expected exit 23, got $RC2 (output: $(cat /tmp/dr3.json))"
grep -q '"drift_kind": "content_hash"' /tmp/dr3.json || die "expected drift_kind=content_hash (got: $(cat /tmp/dr3.json))"
ok "tampered content → drift via content_hash exit 23"

ok "ALL claim-drift CHECKS PASSED"
