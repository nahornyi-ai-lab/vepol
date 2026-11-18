#!/usr/bin/env bash
# codex-cleanup-scope — kb-codex-cleanup (run after every cycle retro and from
# kb-tick) stops only the processes Vepol owns:
#   - codex brokers whose --cwd is the hub or a project knowledge/ folder
#     linked from <hub>/projects/ (a --cwd with a space must also have its
#     real working directory there);
#   - the Telegram plugin's processes, matched by the plugin's path.
# A broker serving some other folder and a Bun dev server running `server.ts`
# elsewhere must survive.
#
# Every process here is a harmless `python3 -c sleep` whose argv carries the
# strings the script matches. The plugin marker is a path inside this
# sandbox, so a real Telegram plugin on this machine can never match, and HOME
# is a sandbox, so no LaunchAgent is touched. The marker deliberately does not
# contain the real plugin path (claude-plugins-official/telegram): kb-doctor
# and kb-tick on this machine must never count these fakes as plugin copies.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLEANUP="$REPO_ROOT/bin/kb-codex-cleanup"
SANDBOX="$(cd "$(mktemp -d)" && pwd -P)"
HUB="$SANDBOX/knowledge"
MARKER="$SANDBOX/plugins/vepol-test-plugins/telegram"
PLUGIN_DIR="$MARKER/0.0.6"

PIDS=()
cleanup() {
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    kill -9 "${PIDS[@]}" 2>/dev/null || true
  fi
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

mkdir -p "$HUB/projects" "$SANDBOX/proj/knowledge/sub" "$SANDBOX/elsewhere" \
  "$SANDBOX/knowledge-old" "$SANDBOX/tmp" "$SANDBOX/home" "$PLUGIN_DIR" \
  "$SANDBOX/knowledge copy/repo" "$SANDBOX/knowledge 2" "$HUB/sub dir"
ln -s "$SANDBOX/proj/knowledge" "$HUB/projects/proj"

LAST_PID=""
# spawn <cwd> <argv strings...> — a sleeping process with that cwd and argv.
spawn() {
  local dir="$1"; shift
  (cd "$dir" && exec python3 -c 'import time; time.sleep(120)' "$@") &
  LAST_PID=$!
  PIDS+=("$LAST_PID")
}

alive() {
  local st
  st="$(ps -o stat= -p "$1" 2>/dev/null | tr -d ' ')"
  [[ -n "$st" && "$st" != Z* ]]
}

FAIL=0
expect_alive() {
  if alive "$1"; then echo "  ok   survives: $2"; else echo "  FAIL was stopped: $2"; FAIL=1; fi
}
expect_dead() {
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do alive "$1" || break; sleep 0.2; done
  if alive "$1"; then echo "  FAIL still running: $2"; FAIL=1; else echo "  ok   stopped: $2"; fi
}

spawn "$SANDBOX/elsewhere" node /opt/x/app-server-broker.mjs --cwd "$SANDBOX/elsewhere"
other_broker=$LAST_PID
spawn "$SANDBOX/elsewhere" node /opt/x/app-server-broker.mjs --cwd "$SANDBOX/knowledge-old"
sibling_broker=$LAST_PID
# Folders named like the hub path plus a space (Finder's "knowledge copy",
# "knowledge 2"): ps joins argv with spaces, so the --cwd value must not be
# cut at the first space and read as the hub.
spawn "$SANDBOX/knowledge copy/repo" node /opt/x/app-server-broker.mjs \
  --cwd "$SANDBOX/knowledge copy/repo" --pid-file "$SANDBOX/tmp/copy.pid"
copy_broker=$LAST_PID
spawn "$SANDBOX/knowledge 2" node /opt/x/app-server-broker.mjs --cwd "$SANDBOX/knowledge 2"
numbered_broker=$LAST_PID
spawn "$SANDBOX/elsewhere" bun server.ts
dev_server=$LAST_PID
# A hub folder with a space in its name: the --cwd text is ambiguous, so the
# broker is stopped only when its real working directory agrees.
spawn "$HUB/sub dir" node /opt/x/app-server-broker.mjs --cwd "$HUB/sub dir" \
  --pid-file "$SANDBOX/tmp/sub.pid"
spaced_hub_broker=$LAST_PID
spawn "$SANDBOX/elsewhere" node /opt/x/app-server-broker.mjs --cwd "$HUB/sub dir"
unconfirmed_broker=$LAST_PID
spawn "$HUB" node /opt/x/app-server-broker.mjs --cwd "$HUB"
hub_broker=$LAST_PID
spawn "$SANDBOX/proj" node /opt/x/app-server-broker.mjs --cwd "$SANDBOX/proj/knowledge/sub"
project_broker=$LAST_PID
spawn "$SANDBOX/elsewhere" bun run --cwd "$PLUGIN_DIR" start
wrapper_a=$LAST_PID
spawn "$SANDBOX/elsewhere" bun run --cwd "$PLUGIN_DIR" start
wrapper_b=$LAST_PID
spawn "$PLUGIN_DIR" bun server.ts
plugin_orphan=$LAST_PID
sleep 0.5

run_cleanup() {
  env HOME="$SANDBOX/home" KB_HUB="$HUB" TMPDIR="$SANDBOX/tmp/" \
    KB_TELEGRAM_PLUGIN_MARKER="$MARKER" bash "$CLEANUP" "$@"
}

echo "=== --dry-run stops nothing ==="
run_cleanup --dry-run > "$SANDBOX/dry.out"
for pid in "${PIDS[@]}"; do
  alive "$pid" || { echo "  FAIL --dry-run stopped PID $pid"; FAIL=1; }
done
grep -q "would stop PID $hub_broker" "$SANDBOX/dry.out" \
  || { echo "  FAIL --dry-run did not list the hub broker"; FAIL=1; }
if grep -q "would stop PID $other_broker" "$SANDBOX/dry.out"; then
  echo "  FAIL --dry-run listed the unrelated broker"; FAIL=1
fi

echo "=== cleanup stops only owned processes ==="
run_cleanup > "$SANDBOX/run.out"
expect_alive "$other_broker" "broker serving an unrelated folder"
expect_alive "$sibling_broker" "broker serving a sibling folder that only shares the hub's name prefix"
expect_alive "$copy_broker" "broker serving '<hub> copy/repo' (hub path plus a space)"
expect_alive "$numbered_broker" "broker serving '<hub> 2' (hub path plus a space)"
expect_alive "$unconfirmed_broker" "broker whose spaced --cwd is in the hub but whose real cwd is not"
expect_alive "$dev_server" "unrelated 'bun server.ts' dev server"
expect_dead "$hub_broker" "broker serving the hub"
expect_dead "$project_broker" "broker serving a project knowledge/ folder linked from the hub"
expect_dead "$spaced_hub_broker" "broker serving a hub folder with a space in its name (real cwd agrees)"
expect_dead "$wrapper_a" "duplicate Telegram plugin wrapper (1)"
expect_dead "$wrapper_b" "duplicate Telegram plugin wrapper (2)"
expect_dead "$plugin_orphan" "orphaned plugin 'bun server.ts' (cwd in the plugin folder)"

echo "=== a single healthy plugin instance is left alone ==="
spawn "$SANDBOX/elsewhere" bun run --cwd "$PLUGIN_DIR" start
single_wrapper=$LAST_PID
sleep 0.3
run_cleanup > "$SANDBOX/single.out"
grep -q "exactly 1 telegram channel instance" "$SANDBOX/single.out" \
  || { echo "  FAIL one wrapper was not counted as exactly one instance"; FAIL=1; }
expect_alive "$single_wrapper" "the only Telegram plugin wrapper"
cat "$SANDBOX/single.out" >> "$SANDBOX/run.out"

if [[ $FAIL -ne 0 ]]; then
  echo "--- kb-codex-cleanup output ---"
  cat "$SANDBOX/run.out"
  exit 1
fi
echo "codex-cleanup-scope: all checks passed"
