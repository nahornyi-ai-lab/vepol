#!/usr/bin/env bash
# install.sh profile.yaml creation — locale matrix + never-overwrite + mode.
# Spec: user-language-setting-2026-06-12 (acceptance 9).
# Exercises only the profile-creation block (extracted by sourcing install.sh
# would run the world; instead run the real installer per case in a sandbox).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0
FAIL=0
ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

extra_path=()
for d in /opt/homebrew/opt/node@20/bin /opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin; do
  [[ -d "$d" ]] && extra_path+=("$d")
done
if [[ ${#extra_path[@]} -gt 0 ]]; then
  IFS=:
  export PATH="${extra_path[*]}:$PATH"
  unset IFS
fi

run_case() { # label lang_env expected
  local label="$1" lang_env="$2" expected="$3"
  local SANDBOX HOME_DIR HUB
  SANDBOX="$(mktemp -d)"
  HOME_DIR="$SANDBOX/home"
  HUB="$HOME_DIR/knowledge"
  if [[ "$lang_env" == "UNSET" ]]; then
    env -u LANG HOME="$HOME_DIR" VEPOL_HUB="$HUB" KB_HUB="$HUB" VEPOL_NONINTERACTIVE=1 \
      "$REPO_ROOT/install.sh" >/dev/null 2>&1 || true
  else
    env LANG="$lang_env" HOME="$HOME_DIR" VEPOL_HUB="$HUB" KB_HUB="$HUB" VEPOL_NONINTERACTIVE=1 \
      "$REPO_ROOT/install.sh" >/dev/null 2>&1 || true
  fi
  local P="$HUB/personal/profile.yaml"
  if [[ ! -f "$P" ]]; then
    fail "$label: profile.yaml not created"
    rm -rf "$SANDBOX"; return
  fi
  if grep -q "language: $expected" "$P"; then
    ok "$label: language: $expected"
  else
    fail "$label: $(grep language "$P" || echo missing) (expected $expected)"
  fi
  # The canonical reader must be installed where shell runners can call it.
  [[ -f "$HUB/bin/_kb_profile.py" ]] && ok "$label: _kb_profile.py installed in hub bin" \
    || fail "$label: _kb_profile.py missing from hub bin"
  local mode
  mode=$(stat -f '%Lp' "$P" 2>/dev/null || stat -c '%a' "$P")
  [[ "$mode" == "600" ]] && ok "$label: mode 600" || fail "$label: mode $mode"
  # re-run with a user-edited value must never overwrite
  echo "language: uk" > "$P"
  if [[ "$lang_env" == "UNSET" ]]; then
    env -u LANG HOME="$HOME_DIR" VEPOL_HUB="$HUB" KB_HUB="$HUB" VEPOL_NONINTERACTIVE=1 \
      "$REPO_ROOT/install.sh" >/dev/null 2>&1 || true
  else
    env LANG="$lang_env" HOME="$HOME_DIR" VEPOL_HUB="$HUB" KB_HUB="$HUB" VEPOL_NONINTERACTIVE=1 \
      "$REPO_ROOT/install.sh" >/dev/null 2>&1 || true
  fi
  grep -q "language: uk" "$P" && ok "$label: re-run preserves user edit" \
    || fail "$label: re-run overwrote user edit"
  rm -rf "$SANDBOX"
}

echo "=== install profile.yaml locale matrix ==="
run_case "ru_RU.UTF-8" "ru_RU.UTF-8" "ru"
run_case "pt_BR.UTF-8" "pt_BR.UTF-8" "pt"
run_case "LANG=C" "C" "en"
run_case "LANG unset" "UNSET" "en"

echo
echo "=== install profile-language tests: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] || exit 1
