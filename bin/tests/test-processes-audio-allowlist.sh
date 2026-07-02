#!/usr/bin/env bash
# Scheduler audio allowlist + runtime guard (AC4/AC5, daily-audio-digests):
# scheduled `notebooklm_audio` passes ONLY for the digest processes with their
# EXACT run commands (id+command binding — same ids with a different run are
# rejected; any other id stays fail-closed), DEFAULT_PROCESSES_YAML wires both
# digests correctly, and kb-morning-digest's own runtime guard makes a
# background invocation file-only unless (allowlisted id + matching argv +
# notebooklm_audio in KB_PROCESS_OUTPUTS).
#
# Spec: knowledge/decisions/daily-audio-digests-2026-07-02.md  (D4, D5)

set -uo pipefail
# The `{ fixture; } | check_yaml` pipelines must mutate PASS/FAIL in THIS shell.
shopt -s lastpipe
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_DIGEST_SRC_BIN:-$HOME/knowledge/bin}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# ── AC4: config validator — id+command binding ───────────────────────────────
# check_yaml <expect: valid|invalid> <label> <yaml on stdin>
check_yaml() {
  local expect="$1" label="$2" rc yaml_file="$TMP/check.yaml"
  cat > "$yaml_file"
  python3 - "$SRC_BIN" "$yaml_file" <<'PY' >/dev/null 2>&1
import sys
sys.path.insert(0, sys.argv[1])
from _kb_processes import parse_processes_text
parse_processes_text(open(sys.argv[2], encoding="utf-8").read())
PY
  rc=$?
  if [[ "$expect" == "valid" ]]; then
    [[ $rc -eq 0 ]] && ok "AC4: $label" || fail "AC4: $label (expected valid, got invalid)"
  else
    [[ $rc -ne 0 ]] && ok "AC4: $label" || fail "AC4: $label (expected invalid, got valid)"
  fi
}

base_procs() {
  cat <<'EOF'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram, file]

- id: retro
  enabled: true
  when: "20:45"
  run: kb-retro
  outputs: [telegram, file]

- id: learning
  enabled: true
  when: after:daily
  run: kb-learning-arxiv --text-only
  outputs: [telegram, file]
EOF
}

{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-morning-digest
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml valid "morning-digest with exact run command passes"

{ base_procs; cat <<'EOF'

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest --period evening
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml valid "evening-digest with exact run command passes"

{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-exfiltrate --to evil
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml invalid "allowlisted id with a DIFFERENT run command is rejected"

{ base_procs; cat <<'EOF'

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml invalid "evening-digest without '--period evening' argv is rejected"

{ base_procs; cat <<'EOF'

- id: my-podcast
  enabled: true
  when: "10:00"
  run: kb-morning-digest
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml invalid "non-allowlisted id stays fail-closed even with the digest command"

{ base_procs; cat <<'EOF'

- id: my-podcast
  enabled: true
  when: on-demand
  run: anything-goes
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml valid "on-demand notebooklm_audio remains allowed (unchanged policy)"

# Basename normalization: an absolute path to the digest binary is the same command.
{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: /opt/hub/bin/kb-morning-digest
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml valid "absolute-path run normalizes to the same command (basename)"

# ── AC5: DEFAULT_PROCESSES_YAML wires both digests, preserves existing edges ─
python3 - "$SRC_BIN" <<'PY' && ok "AC5: DEFAULT_PROCESSES_YAML valid + both digests wired + edges preserved" \
                            || fail "AC5: DEFAULT_PROCESSES_YAML check failed"
import sys
sys.path.insert(0, sys.argv[1])
from _kb_processes import DEFAULT_PROCESSES_YAML, parse_processes_text
procs = {p["id"]: p for p in parse_processes_text(DEFAULT_PROCESSES_YAML)}
md = procs["morning-digest"]; ed = procs["evening-digest"]
assert md["enabled"] and md["when"] == "after:learning", md
assert md["run"] == "kb-morning-digest", md
assert md["outputs"] == ["file", "notebooklm_audio"], md
assert ed["enabled"] and ed["when"] == "after:retro", ed
assert ed["run"] == "kb-morning-digest --period evening", ed
assert ed["outputs"] == ["file", "notebooklm_audio"], ed
# Existing default edges preserved (mail spec wiring).
assert procs["daily"]["when"] == "after:mail-morning"
assert procs["retro"]["when"] == "after:mail-evening"
assert procs["learning"]["when"] == "after:daily"
assert procs["mail-morning"]["when"] == "07:15"
assert procs["mail-evening"]["when"] == "20:30"
PY

# ── AC4: runtime guard in kb-morning-digest (background context) ─────────────
# kb-morning-digest is present in every distribution this suite targets after
# v0.5.0; a missing binary here is a FAIL, not a skip.
if [[ ! -x "$SRC_BIN/kb-morning-digest" ]]; then
  fail "AC4: kb-morning-digest missing from $SRC_BIN (public surface after v0.5.0)"
  echo "PASS=$PASS FAIL=$FAIL"; exit 1
fi

# Runtime-guard fixtures use REAL today and NO --date: kb-tick launches the exact
# `run` command with no extra argv, and the guard compares argv strictly.
DAY=$(date +%Y-%m-%d)
NOVEPOL="$TMP/no-project"
mk_hub() { # $1 = dir
  mkdir -p "$1/personal" "$1/briefs" "$1/reports" "$1/.orchestrator"
  ln -s "$SRC_BIN" "$1/bin"
  : > "$1/personal/.secrets"
  printf '## Retro (20:45)\n\nguard-fixture retro.\n' > "$1/briefs/$DAY.md"
}
NBLOG="$TMP/guard-nblm.log"; : > "$NBLOG"
cat > "$TMP/fake-notebooklm" <<FAKE
#!/usr/bin/env bash
echo "\$*" >> "$NBLOG"
case "\$1 \${2:-}" in
  "list --json"*|"list "*) echo '{"notebooks": []}' ;;
  "create "*)              echo '{"id": "nb-fake-1"}' ;;
  "source add")            echo '{"source_id": "src-fake-1"}' ;;
  "source wait")           echo '{}' ;;
  "generate audio")        echo '{"task_id": "art-fake-1"}' ;;
  *)                       echo '{}' ;;
esac
FAKE
chmod +x "$TMP/fake-notebooklm"

# guard_run <hub> <process_id or -> <outputs or -> [extra argv...]
guard_run() {
  local hub="$1" pid="$2" outs="$3"; shift 3
  local -a env_args=("KB_HUB=$hub" "KB_VEPOL_DEV=$NOVEPOL"
                     "KB_MORNING_SYNTH_AGENTS=none"
                     "KB_NOTEBOOKLM_BIN=$TMP/fake-notebooklm")
  [[ "$pid" != "-" ]] && env_args+=("KB_PROCESS_ID=$pid" "KB_PROCESS_BACKGROUND=1")
  [[ "$outs" != "-" ]] && env_args+=("KB_PROCESS_OUTPUTS=$outs")
  env "${env_args[@]}" "$SRC_BIN/kb-morning-digest" "$@" >/dev/null 2>&1
}

# 1. Rogue process id -> file-only, zero NotebookLM calls.
H="$TMP/g1"; mk_hub "$H"; : > "$NBLOG"
guard_run "$H" "rogue-audio" "file,notebooklm_audio" --period evening; RC=$?
[[ $RC -eq 0 && -f "$H/reports/evening-digest-$DAY.md" && ! -s "$NBLOG" ]] \
  && ok "AC4: non-allowlisted KB_PROCESS_ID -> file-only, zero NotebookLM calls" \
  || fail "AC4: rogue background id reached NotebookLM (rc=$RC, calls=$(wc -l < "$NBLOG"))"

# 2. Allowlisted id but WRONG argv (morning-digest id running evening argv).
H="$TMP/g2"; mk_hub "$H"; : > "$NBLOG"
guard_run "$H" "morning-digest" "file,notebooklm_audio" --period evening; RC=$?
[[ $RC -eq 0 && ! -s "$NBLOG" ]] \
  && ok "AC4: allowlisted id with mismatched argv -> file-only" \
  || fail "AC4: id/argv mismatch still reached NotebookLM (rc=$RC)"

# 3. Allowlisted id + argv but notebooklm_audio OMITTED from outputs.
H="$TMP/g3"; mk_hub "$H"; : > "$NBLOG"
guard_run "$H" "evening-digest" "file" --period evening; RC=$?
[[ $RC -eq 0 && ! -s "$NBLOG" ]] \
  && ok "AC4: omitted notebooklm_audio in KB_PROCESS_OUTPUTS -> file-only" \
  || fail "AC4: omitted-outputs bypass reached NotebookLM (rc=$RC)"

# 4. Fully legitimate background evening run -> push happens.
H="$TMP/g4"; mk_hub "$H"; : > "$NBLOG"
guard_run "$H" "evening-digest" "file,notebooklm_audio" --period evening; RC=$?
[[ $RC -eq 0 && -s "$NBLOG" ]] \
  && ok "AC4: legitimate background evening-digest -> NotebookLM push happens" \
  || fail "AC4: legitimate background run was blocked (rc=$RC)"

# 5. Manual run (no KB_PROCESS_ID) unaffected -> push happens.
H="$TMP/g5"; mk_hub "$H"; : > "$NBLOG"
guard_run "$H" "-" "-" --period evening; RC=$?
[[ $RC -eq 0 && -s "$NBLOG" ]] \
  && ok "AC4: manual run (no KB_PROCESS_ID) unaffected by the guard" \
  || fail "AC4: manual run was wrongly blocked (rc=$RC)"

echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
