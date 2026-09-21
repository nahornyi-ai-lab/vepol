#!/usr/bin/env bash
# Scheduler audio flags + runtime guard:
# scheduled `telegram_audio` or `notebooklm_audio` passes ONLY for the digest processes with their
# EXACT run commands (id+command binding — same ids with a different run are
# rejected; any other id stays fail-closed), DEFAULT_PROCESSES_YAML wires both
# digests correctly, and kb-morning-digest's own runtime guard makes a
# background invocation file-only unless (allowlisted id + matching argv +
# telegram_audio in KB_PROCESS_OUTPUTS). Background-without-ID is denied.
#
# Selector spec: spec-contract:sha256:64c99d1d0e31cc701bcedcbe371b603ef179991db5ab508a17abb31ea8d99062

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
  outputs: [file, telegram_audio]
EOF
} | check_yaml valid "morning-digest with exact run command passes"

{ base_procs; cat <<'EOF'

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest --period evening
  outputs: [file, telegram_audio]
EOF
} | check_yaml valid "evening-digest with exact run command passes"

{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-morning-digest
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml valid "morning-digest may select NotebookLM with exact run command"

{ base_procs; cat <<'EOF'

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest --period evening
  outputs: [file, notebooklm_audio]
EOF
} | check_yaml valid "evening-digest may select NotebookLM with exact run command"

{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-morning-digest
  outputs: {file: true, telegram_audio: true, notebooklm_audio: true}
EOF
} | check_yaml valid "managed digest accepts independent true channel flags"

python3 - "$SRC_BIN" <<'PY' && ok "AC4: boolean output map keeps only true channels" \
                            || fail "AC4: boolean output map parsing failed"
import sys
sys.path.insert(0, sys.argv[1])
from _kb_processes import parse_processes_text

base = """\
- id: morning-digest
  enabled: true
  when: on-demand
  run: kb-morning-digest
  outputs: {file: true, telegram_audio: %s, notebooklm_audio: %s}
"""
assert parse_processes_text(base % ("true", "false"))[0]["outputs"] == ["file", "telegram_audio"]
assert parse_processes_text(base % ("false", "true"))[0]["outputs"] == ["file", "notebooklm_audio"]
assert parse_processes_text(base % ("true", "true"))[0]["outputs"] == ["file", "telegram_audio", "notebooklm_audio"]
assert parse_processes_text(base % ("false", "false"))[0]["outputs"] == ["file"]
PY

{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-morning-digest
  outputs: {file: true, telegram_audo: false, notebooklm_audio: true}
EOF
} | check_yaml invalid "unknown false channel is rejected"

{ base_procs; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-exfiltrate --to evil
  outputs: [file, telegram_audio]
EOF
} | check_yaml invalid "allowlisted id with a DIFFERENT run command is rejected"

{ base_procs; cat <<'EOF'

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest
  outputs: [file, telegram_audio]
EOF
} | check_yaml invalid "evening-digest without '--period evening' argv is rejected"

{ base_procs; cat <<'EOF'

- id: my-podcast
  enabled: true
  when: "10:00"
  run: kb-morning-digest
  outputs: [file, telegram_audio]
EOF
} | check_yaml invalid "non-allowlisted id stays fail-closed even with the digest command"

{ base_procs; cat <<'EOF'

- id: my-podcast
  enabled: true
  when: on-demand
  run: anything-goes
  outputs: [file, telegram_audio]
EOF
} | check_yaml valid "on-demand telegram_audio remains allowed"

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
  outputs: [file, telegram_audio]
EOF
} | check_yaml valid "absolute-path run normalizes to the same command (basename)"

# ── AC13: optional per-process `timeout` field (D12) ─────────────────────────
# absent → default (no behavior change); positive bounded int 60..7200 accepted;
# anything else fails closed (never silently ignored).
{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 3600
EOF
} | check_yaml valid "AC13: timeout=3600 accepted"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 60
EOF
} | check_yaml valid "AC13: timeout=60 lower bound accepted"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 7200
EOF
} | check_yaml valid "AC13: timeout=7200 upper bound accepted"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 59
EOF
} | check_yaml invalid "AC13: timeout below 60 fails closed"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 7201
EOF
} | check_yaml invalid "AC13: timeout above 7200 fails closed"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 0
EOF
} | check_yaml invalid "AC13: timeout=0 fails closed"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: -60
EOF
} | check_yaml invalid "AC13: negative timeout fails closed"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: abc
EOF
} | check_yaml invalid "AC13: non-integer timeout fails closed"

{ base_procs; cat <<'EOF'

- id: heavy
  enabled: true
  when: after:learning
  run: kb-heavy
  outputs: [file]
  timeout: 900.5
EOF
} | check_yaml invalid "AC13: fractional timeout fails closed"

# Parsed value shape: present → int; absent → no timeout key (kb-tick applies 1800).
python3 - "$SRC_BIN" <<'PY' && ok "AC13: parsed timeout is int when present, absent otherwise" \
                            || fail "AC13: parsed timeout shape wrong"
import sys
sys.path.insert(0, sys.argv[1])
from _kb_processes import parse_processes_text
text = """\
- id: a
  enabled: true
  when: "07:30"
  run: kb-a
  outputs: [file]
- id: b
  enabled: true
  when: after:a
  run: kb-b
  outputs: [file]
  timeout: 3600
"""
procs = {p["id"]: p for p in parse_processes_text(text)}
assert "timeout" not in procs["a"] or procs["a"]["timeout"] is None, procs["a"]
assert procs["b"]["timeout"] == 3600 and isinstance(procs["b"]["timeout"], int), procs["b"]
PY

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
  mkdir -p "$1/personal" "$1/briefs" "$1/reports" "$1/.orchestrator" "$1/bin" "$1/tts"
  : > "$1/personal/.secrets"
  printf '{"fixture":true}\n' >"$1/tts/install.json"
  printf '## Retro (20:45)\n\nguard-fixture retro.\n' > "$1/briefs/$DAY.md"
cat >"$1/bin/kb-tts-render" <<'SH'
#!/usr/bin/env bash
echo "render $*" >>"$AUDIOLOG"
[[ "${FAIL_TTS:-0}" == "1" ]] && exit 1
out=''; while [[ $# -gt 0 ]]; do case "$1" in --out) out="$2"; shift 2;; *) shift;; esac; done
printf 'ID3-guard-audio' >"$out"
SH
  cat >"$1/bin/kb-channel-send-audio" <<'SH'
#!/usr/bin/env bash
echo "send $*" >>"$AUDIOLOG"
echo '{"outcome":"success","message_id":7,"audio":{"file_id":"f","file_unique_id":"u","duration":3}}'
SH
  chmod +x "$1/bin/"*
}
NBLOG="$TMP/guard-nblm.log"; : > "$NBLOG"
AUDIOLOG="$TMP/guard-audio.log"; : > "$AUDIOLOG"
cat > "$TMP/fake-notebooklm" <<FAKE
#!/usr/bin/env bash
echo "\$*" >> "$NBLOG"
if [[ "\${FAIL_NLM:-0}" == "1" && "\$1 \${2:-}" == "generate audio" ]]; then exit 1; fi
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
                     "KB_NOTEBOOKLM_BIN=$TMP/fake-notebooklm" "AUDIOLOG=$AUDIOLOG"
                     "KB_TTS_HOME=$hub/tts")
  if [[ "$pid" == "background-no-id" ]]; then
    env_args+=("KB_PROCESS_BACKGROUND=1")
  elif [[ "$pid" != "-" ]]; then
    env_args+=("KB_PROCESS_ID=$pid" "KB_PROCESS_BACKGROUND=1")
  fi
  [[ "$outs" != "-" ]] && env_args+=("KB_PROCESS_OUTPUTS=$outs")
  env "${env_args[@]}" "$SRC_BIN/kb-morning-digest" "$@" >/dev/null 2>&1
}

# 1. Rogue process id -> file-only, zero TTS/Telegram/NotebookLM calls.
H="$TMP/g1"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "rogue-audio" "file,telegram_audio" --period evening; RC=$?
[[ $RC -eq 0 && -f "$H/reports/evening-digest-$DAY.md" && ! -s "$NBLOG" && ! -s "$AUDIOLOG" ]] \
  && ok "AC4: non-allowlisted KB_PROCESS_ID -> file-only, zero external audio calls" \
  || fail "AC4: rogue background id reached an audio backend (rc=$RC)"

# 2. Allowlisted id but WRONG argv (morning-digest id running evening argv).
H="$TMP/g2"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "morning-digest" "file,telegram_audio" --period evening; RC=$?
[[ $RC -eq 0 && ! -s "$NBLOG" && ! -s "$AUDIOLOG" ]] \
  && ok "AC4: allowlisted id with mismatched argv -> file-only" \
  || fail "AC4: id/argv mismatch still reached NotebookLM (rc=$RC)"

# 3. Allowlisted id + argv but telegram_audio OMITTED from outputs.
H="$TMP/g3"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "evening-digest" "file" --period evening; RC=$?
[[ $RC -eq 0 && ! -s "$NBLOG" && ! -s "$AUDIOLOG" ]] \
  && ok "AC4: omitted telegram_audio in KB_PROCESS_OUTPUTS -> file-only" \
  || fail "AC4: omitted-outputs bypass reached audio backend (rc=$RC)"

# 4. Background context without an ID is denied fail-closed.
H="$TMP/g4"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "background-no-id" "file,telegram_audio" --period evening; RC=$?
[[ $RC -eq 0 && ! -s "$AUDIOLOG" && ! -s "$NBLOG" ]] \
  && ok "AC4: background-without-ID is file-only" \
  || fail "AC4: background-without-ID reached audio backend (rc=$RC)"

# 5. Fully legitimate background evening run -> local render + send happens.
H="$TMP/g5"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "evening-digest" "file,telegram_audio" --period evening; RC=$?
[[ $RC -eq 0 && $(grep -c '^render ' "$AUDIOLOG") -eq 1 && $(grep -c '^send ' "$AUDIOLOG") -eq 1 && ! -s "$NBLOG" ]] \
  && ok "AC4: legitimate background evening-digest -> local Qwen + Telegram" \
  || fail "AC4: legitimate background run was blocked (rc=$RC)"

# 6. The same exact process may select NotebookLM; local audio stays untouched.
H="$TMP/g6"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "evening-digest" "file,notebooklm_audio" --period evening; RC=$?
[[ $RC -eq 0 && $(grep -c '^generate audio' "$NBLOG") -eq 1 && ! -s "$AUDIOLOG" ]] \
  && ok "AC4: legitimate background evening-digest -> NotebookLM only" \
  || fail "AC4: NotebookLM route did not stay isolated (rc=$RC)"

# 7. Both flags call both existing handlers with the same frozen speech path.
H="$TMP/g7"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC=$?
TTS_TEXT=$(sed -n 's/^render .*--file \([^ ]*\).*/\1/p' "$AUDIOLOG" | head -1)
NLM_TEXT=$(sed -n 's/^source add \([^ ]*\).*/\1/p' "$NBLOG" | head -1)
[[ $RC -eq 0 && $(grep -c '^render ' "$AUDIOLOG") -eq 1 \
   && $(grep -c '^send ' "$AUDIOLOG") -eq 1 \
   && $(grep -c '^generate audio' "$NBLOG") -eq 1 \
   && -n "$TTS_TEXT" && "$TTS_TEXT" == "$NLM_TEXT" ]] \
  && ok "AC4: both true -> both handlers receive one frozen speech path" \
  || fail "AC4: both-channel fan-out failed (rc=$RC, tts=$TTS_TEXT, nlm=$NLM_TEXT)"

# 8. A first-handler failure does not suppress the second handler.
H="$TMP/g8"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
FAIL_TTS=1 guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC=$?
[[ $RC -ne 0 && $(grep -c '^render ' "$AUDIOLOG") -eq 1 \
   && $(grep -c '^send ' "$AUDIOLOG") -eq 0 \
   && $(grep -c '^generate audio' "$NBLOG") -eq 1 ]] \
  && ok "AC4: local failure still dispatches NotebookLM and returns retry" \
  || fail "AC4: first-handler failure suppressed NotebookLM (rc=$RC)"

# 9. Manual run (no background vars) unaffected -> local render + send happens.
H="$TMP/g9"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "-" "-" --period evening; RC=$?
[[ $RC -eq 0 && $(grep -c '^render ' "$AUDIOLOG") -eq 1 && $(grep -c '^send ' "$AUDIOLOG") -eq 1 && ! -s "$NBLOG" ]] \
  && ok "AC4: fully manual run unaffected by the guard" \
  || fail "AC4: manual run was wrongly blocked (rc=$RC)"

# 10. Channel toggles never change the manifest owned by a successful handler.
H="$TMP/g10"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
guard_run "$H" "evening-digest" "file,notebooklm_audio" --period evening; RC1=$?
guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC2=$?
guard_run "$H" "evening-digest" "file,notebooklm_audio" --period evening; RC3=$?
[[ $RC1 -eq 0 && $RC2 -eq 0 && $RC3 -eq 0 \
   && $(grep -c '^generate audio' "$NBLOG") -eq 1 \
   && $(grep -c '^render ' "$AUDIOLOG") -eq 1 \
   && -f "$H/.orchestrator/evening-digest-$DAY.json" \
   && -f "$H/.orchestrator/evening-digest-$DAY-notebooklm.json" ]] \
  && ok "AC4: single/both toggles keep stable per-channel manifests" \
  || fail "AC4: channel toggle repeated a completed handler"

# 11. Telegram success + NotebookLM retry only retries NotebookLM.
H="$TMP/g11"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
FAIL_NLM=1 guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC1=$?
guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC2=$?
[[ $RC1 -ne 0 && $RC2 -eq 0 \
   && $(grep -c '^render ' "$AUDIOLOG") -eq 1 \
   && $(grep -c '^send ' "$AUDIOLOG") -eq 1 \
   && $(grep -c '^generate audio' "$NBLOG") -eq 2 ]] \
  && ok "AC4: retry invokes only failed NotebookLM handler" \
  || fail "AC4: NotebookLM retry repeated Telegram"

# 12. NotebookLM success + Telegram retry only retries Telegram.
H="$TMP/g12"; mk_hub "$H"; : > "$NBLOG"; : > "$AUDIOLOG"
FAIL_TTS=1 guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC1=$?
guard_run "$H" "evening-digest" "file,telegram_audio,notebooklm_audio" --period evening; RC2=$?
[[ $RC1 -ne 0 && $RC2 -eq 0 \
   && $(grep -c '^render ' "$AUDIOLOG") -eq 2 \
   && $(grep -c '^send ' "$AUDIOLOG") -eq 1 \
   && $(grep -c '^generate audio' "$NBLOG") -eq 1 ]] \
  && ok "AC4: retry invokes only failed Telegram handler" \
  || fail "AC4: Telegram retry repeated NotebookLM"

echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
