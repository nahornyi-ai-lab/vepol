#!/usr/bin/env bash
# install idempotency smoke — first install, repeat install, then task/search/health.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SANDBOX="$(mktemp -d)"
cleanup() {
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

HOME_DIR="$SANDBOX/home"
HUB="$HOME_DIR/knowledge"

extra_path=()
for d in /opt/homebrew/opt/node@20/bin /opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin; do
  [[ -d "$d" ]] && extra_path+=("$d")
done
if [[ ${#extra_path[@]} -gt 0 ]]; then
  IFS=:
  export PATH="${extra_path[*]}:$PATH"
  unset IFS
fi

export HOME="$HOME_DIR"
export VEPOL_HUB="$HUB"
export KB_HUB="$HUB"
export VEPOL_NONINTERACTIVE=1

"$REPO_ROOT/install.sh" > "$SANDBOX/install-1.out" 2> "$SANDBOX/install-1.err"
"$REPO_ROOT/install.sh" > "$SANDBOX/install-2.out" 2> "$SANDBOX/install-2.err"

"$HUB/bin/kb-board" check "$HUB/backlog.md" --json > /dev/null
"$HUB/bin/kb-task" "Installer idempotency smoke" > /dev/null
"$HUB/bin/kb-search" "Installer idempotency smoke" --hub-only > /dev/null
"$HUB/bin/kb-doctor" install-health --strict --format json > /dev/null
