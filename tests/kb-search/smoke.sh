#!/usr/bin/env bash
# kb-search smoke — searches board tasks and every hub folder from an isolated KB_HUB.
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

# Hub folders that hold routine outputs and personal cards are searched too.
mkdir -p "$SANDBOX/reports/money-radar" "$SANDBOX/sources" "$SANDBOX/briefs" "$SANDBOX/daily" \
  "$SANDBOX/personal/ideas" "$SANDBOX/proj/knowledge/reports/money-radar"
echo "arXiv review: needle-reports" > "$SANDBOX/reports/2026-11-17-arxiv.md"
echo "Radar digest: needle-radar-digest" > "$SANDBOX/reports/money-radar/2026-11-17-digest.txt"
echo "Research packet: needle-sources" > "$SANDBOX/sources/packet.md"
echo "Morning brief: needle-briefs" > "$SANDBOX/briefs/2026-11-17.md"
echo "Daily note: needle-daily" > "$SANDBOX/daily/2026-11-17.md"
echo "# My first Vepol idea needle-personal" > "$SANDBOX/personal/ideas/idea-20261117-0900-first.md"
echo "Project radar: needle-project-digest" > "$SANDBOX/proj/knowledge/reports/money-radar/2026-11-17-digest.txt"
ln -s "$SANDBOX/proj/knowledge" "$SANDBOX/projects/proj"
# Secrets sit next to searchable files and must never be searched.
printf 'TELEGRAM_BOT_TOKEN=needle-secret\n' > "$SANDBOX/personal/.secrets"
printf 'API_KEY=needle-secret\n' > "$SANDBOX/personal/app.env"
printf 'needle-secret\n' > "$SANDBOX/reports/money-radar/api-token.txt"
printf 'needle-secret\n' > "$SANDBOX/reports/.secrets.txt"
# Plain .txt outside reports/ stays out of the search.
echo "needle-plain-txt" > "$SANDBOX/sources/notes.txt"

check_engine() {
  local label="$1" path="$2" needle out
  for needle in needle-reports needle-radar-digest needle-sources needle-briefs needle-daily \
                needle-personal needle-project-digest; do
    out="$(PATH="$path" KB_HUB="$SANDBOX" HOME=/tmp/kb-search-home "$REPO_ROOT/bin/kb-search" "$needle" 2>&1 || true)"
    [[ "$out" == *"$needle"* ]] || { echo "[$label] kb-search did not find $needle" >&2; exit 1; }
  done
  out="$(PATH="$path" KB_HUB="$SANDBOX" HOME=/tmp/kb-search-home "$REPO_ROOT/bin/kb-search" "needle-project-digest" --project proj 2>&1 || true)"
  [[ "$out" == *"needle-project-digest"* ]] || { echo "[$label] --project missed its reports/ digest" >&2; exit 1; }
  for needle in needle-secret needle-plain-txt; do
    out="$(PATH="$path" KB_HUB="$SANDBOX" HOME=/tmp/kb-search-home "$REPO_ROOT/bin/kb-search" "$needle" 2>&1 || true)"
    if [[ "$out" == *"$needle"* && "$out" != *"no matches for: $needle"* ]]; then
      echo "[$label] kb-search searched a file it must skip ($needle):" >&2
      echo "$out" >&2
      exit 1
    fi
  done
}

if command -v rg >/dev/null 2>&1; then
  check_engine ripgrep "$PATH"
fi
# grep fallback (no ripgrep on PATH).
check_engine grep "/usr/bin:/bin:/usr/sbin:/sbin"

echo "kb-search smoke: ok"
