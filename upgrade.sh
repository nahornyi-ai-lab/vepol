#!/usr/bin/env bash
# upgrade.sh — pull the latest Vepol and re-apply, preserving all user data.
#
# Vepol's hub uses symlinks into this repo, so "upgrade" = update the repo, then
# re-run the idempotent installer (--apply). User data in ~/knowledge is never
# touched; only managed files (symlinks, ~/.claude/.vepol/CLAUDE.managed.md,
# skills, templates) are refreshed.
#
# Flags:
#   --check   show current vs. available version and exit (no changes)
#   passes VEPOL_ENABLE_* / VEPOL_APPLY_C01 through to install.sh --apply
#
# Project: https://github.com/nahornyi-ai-lab/vepol

set -euo pipefail

VEPOL_DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${HOME}"
HUB="${VEPOL_HUB:-$HOME_DIR/knowledge}"

CHECK=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'upgrade.sh: unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

if [[ -t 1 ]]; then C_I=$'\033[1;36m'; C_OK=$'\033[1;32m'; C_W=$'\033[1;33m'; C_O=$'\033[0m'
else C_I=''; C_OK=''; C_W=''; C_O=''; fi
say()  { printf '%s==>%s %s\n' "$C_I" "$C_O" "$1"; }
ok()   { printf '%s ✓%s  %s\n' "$C_OK" "$C_O" "$1"; }
warn() { printf '%s !%s  %s\n' "$C_W" "$C_O" "$1" >&2; }

CUR="$(cat "$VEPOL_DIR/VERSION" 2>/dev/null || echo unknown)"
say "Vepol upgrade — repo: $VEPOL_DIR (current v$CUR)"

if ! git -C "$VEPOL_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  warn "repo is not a git checkout — cannot upgrade automatically."
  warn "re-clone the latest from https://github.com/nahornyi-ai-lab/vepol and re-run install.sh."
  exit 1
fi

git -C "$VEPOL_DIR" fetch --quiet origin 2>/dev/null || warn "git fetch failed (offline?) — continuing with local state"
LOCAL="$(git -C "$VEPOL_DIR" rev-parse @ 2>/dev/null || echo '?')"
REMOTE="$(git -C "$VEPOL_DIR" rev-parse '@{u}' 2>/dev/null || echo '?')"

if [[ "$CHECK" -eq 1 ]]; then
  echo "  local:  $LOCAL"
  echo "  remote: $REMOTE"
  if [[ "$REMOTE" == "?" ]]; then warn "no upstream / offline — cannot check for updates"
  elif [[ "$LOCAL" == "$REMOTE" ]]; then ok "up to date"
  else warn "an update is available — run ./upgrade.sh"; fi
  exit 0
fi

if [[ "$LOCAL" == "$REMOTE" || "$REMOTE" == "?" ]]; then
  ok "already up to date (or offline) — re-applying installer to repair any drift"
else
  say "pulling latest…"
  if git -C "$VEPOL_DIR" pull --ff-only --quiet; then
    ok "updated to $(cat "$VEPOL_DIR/VERSION" 2>/dev/null || echo '?')"
  else
    warn "fast-forward pull failed (local changes or diverged history)."
    warn "resolve manually in $VEPOL_DIR, then re-run ./upgrade.sh."
    exit 1
  fi
fi

say "re-applying installer (idempotent; user data preserved)…"
VEPOL_HUB="$HUB" "$VEPOL_DIR/install.sh" --apply

say "verifying…"
VEPOL_HUB="$HUB" "$VEPOL_DIR/install.sh" --verify --json >/dev/null \
  && ok "upgrade verified" \
  || warn "verify reported issues — run VEPOL_HUB=\"$HUB\" ./install.sh --verify --json"
