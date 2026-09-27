#!/usr/bin/env bash
# Open the sample workspace (demo/workspace) in Vepol Desktop, isolated from your own data:
# a fresh copy in ~/.vepol/demo-workspace, its own state, port 8782 and its own tmux server.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/.." && pwd)"
copy="$HOME/.vepol/demo-workspace"
app="$here/desktop/build/VepolDesktop.app"

if lsof -nP -iTCP:8782 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "A demo is already running (port 8782 is in use). Quit it first." >&2
  exit 1
fi

# End the previous demo's terminals before their folder is replaced: its tmux dir is recorded in the old
# copy, and only a socket under a /tmp/vd-* dir is ever addressed, never your own tmux server.
if [ -f "$copy/.tmux-dir" ]; then
  old_dir="$(cat "$copy/.tmux-dir")"
  case "$old_dir" in
    /tmp/vd-*) env -u TMUX -u TMUX_PANE tmux -S "$old_dir/tmux-$(id -u)/default" kill-server 2>/dev/null || true ;;
  esac
fi

# A fresh copy every run; the previous copy is replaced.
mkdir -p "$HOME/.vepol"
rm -rf "$copy"
cp -R "$repo/demo/workspace" "$copy"
ln -s "$repo/bin" "$copy/knowledge/bin"

if [ ! -d "$app" ]; then
  echo "Build the app first: see face/README.md" >&2
  exit 1
fi

# The demo's own tmux server lives in a fresh short socket dir, so demo terminals never reach your sessions.
tmux_dir="$(mktemp -d /tmp/vd-XXXXXX)"
printf '%s\n' "$tmux_dir" > "$copy/.tmux-dir"

config="$copy/.face-test-config.json"
printf '{"port": 8782, "hub": "%s", "state_dir": "%s"}\n' "$copy/knowledge" "$copy/.face-state" > "$config"

exec env -u TMUX -u TMUX_PANE TMUX_TMPDIR="$tmux_dir" KB_HUB="$copy/knowledge" \
  "$app/Contents/MacOS/VepolDesktop" --test-config "$config"
