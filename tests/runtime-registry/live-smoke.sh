#!/usr/bin/env bash
# live-smoke.sh — one real probe against the live hub, run NON-NESTED.
#
# Test acceptance 3 of runtime-capability-registry-2026-08-15.md: "one live
# probe smoke against a runtime that is genuinely available, run non-nested."
# Not part of run-all.sh (needs network + quota). Invoke by hand:
#
#   bash ~/knowledge/tests/runtime-registry/live-smoke.sh [runtime]   # default: codex
#
# Non-nested by construction: the agent-session markers (same list as
# vepol_face/broker.py SESSION_ENV_* and _kb_runtime_registry/probe.py) are
# stripped from the environment before the registry runs, so the probe is a
# real child of this shell, not of an agent session. Costs one trivial prompt
# of the chosen runtime's quota.
set -euo pipefail

HUB="${KB_HUB:-$HOME/knowledge}"
RUNTIME="${1:-codex}"
BIN="$HUB/bin/kb-runtime-registry"

unset_markers=(CLAUDECODE CLAUDE_EFFORT CLAUDE_PLUGIN_DATA AI_AGENT ANTHROPIC_BASE_URL)
while IFS='=' read -r key _; do
  case "$key" in
    CLAUDE_CODE_*|CLAUDE_AGENT_SDK_*|CODEX_COMPANION_*) unset_markers+=("$key") ;;
  esac
done < <(env)

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

env "${unset_markers[@]/#/-u}" "$BIN" --probe "$RUNTIME" --json > "$out"
rc=$?
echo "[live-smoke] rc=$rc"

python3 - "$out" "$RUNTIME" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
name = sys.argv[2]
row = {r["name"]: r for r in doc["runtimes"]}[name]
res = {r["runtime"]: r for r in doc["probe"]["results"]}[name]
print(f"[live-smoke] nested={doc['nested']['detected']} probe={res['outcome']} reason={res['reason']!r}")
print(f"[live-smoke] {name}: healthy={row['healthy']} authenticated={row['authenticated']} "
      f"quota_available={row['quota_available']} available={row['available']} "
      f"observed_at={row['provenance']['observed_at']} evidence={row['provenance']['evidence']!r}")
assert doc["nested"]["detected"] is False, "smoke ran nested — markers not stripped"
assert res["outcome"] == "success", f"probe did not succeed: {res}"
assert row["healthy"] == "yes" and row["available"] is True, "registry did not flip to available"
print("[live-smoke] PASS")
PY
