#!/usr/bin/env bash
# An upgrade runs `install.sh --apply` without VEPOL_ENABLE_* answers. Extras that are
# already installed must be kept, not recorded as declined; an explicit 0 still declines.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX/home" VEPOL_HUB="$SANDBOX/home/knowledge" KB_HUB="$SANDBOX/home/knowledge"
mkdir -p "$HOME" "$SANDBOX/stubs"
# launchctl stub: never touch the real launchd from a test.
printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/stubs/launchctl"; chmod +x "$SANDBOX/stubs/launchctl"
export PATH="$SANDBOX/stubs:$PATH"
fail() { echo "FAIL: $*" >&2; exit 1; }
MARK="$VEPOL_HUB/.orchestrator/launchagents.opted-out"

VEPOL_ENABLE_LAUNCHD=1 "$REPO_ROOT/install.sh" --apply > "$SANDBOX/1.out" 2>&1 || true
ls "$HOME/Library/LaunchAgents"/com.knowledge.*.plist >/dev/null 2>&1 || fail "first install did not write LaunchAgents"
[[ ! -f "$MARK" ]] || fail "opted-out marker after an explicit yes"

"$REPO_ROOT/install.sh" --apply > "$SANDBOX/2.out" 2>&1 || true   # what upgrade.sh does
[[ ! -f "$MARK" ]] || fail "upgrade-style --apply recorded installed scheduled tasks as declined"
grep -q "already installed — kept" "$SANDBOX/2.out" || fail "upgrade-style --apply did not say the tasks were kept"

VEPOL_ENABLE_LAUNCHD=0 "$REPO_ROOT/install.sh" --apply > "$SANDBOX/3.out" 2>&1 || true
[[ -f "$MARK" ]] || fail "an explicit VEPOL_ENABLE_LAUNCHD=0 must still record the decline"
echo "PASS upgrade keeps installed extras"
