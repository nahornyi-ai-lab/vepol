#!/usr/bin/env bash
# kb-search smoke — searches board tasks from an isolated KB_HUB.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SANDBOX="$(mktemp -d)"
cleanup() {
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

mkdir -p "$SANDBOX/projects"
cat > "$SANDBOX/backlog.md" <<'EOF'
# Hub Board

## Backlog
- [ ] Smoke Needle from board
  plan_item_id: smoke-needle

## Ready

## In Progress

## Blocked

## Review

## Done

## Cancelled
EOF

out="$(KB_HUB="$SANDBOX" HOME=/tmp/kb-search-home "$REPO_ROOT/bin/kb-search" "Smoke Needle" --hub-only)"
[[ "$out" == *"backlog.md"* ]]
[[ "$out" == *"from board"* ]]
