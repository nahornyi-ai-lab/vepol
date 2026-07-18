#!/usr/bin/env bash
# kb-digest-migrate (AC6, daily-audio-digests): inserts evening-digest
# (after:retro) and morning-digest anchored to the LAST enabled SCHEDULED
# morning process (money-radar > learning > daily), re-anchors ONLY its own
# managed morning-digest block when a better anchor appears, preserves the
# independent output flags, leaves customized
# blocks byte-identical, preserves every other process/edge, is idempotent,
# fails closed on malformed input, and --revert round-trips.
#
# Selector spec: spec-contract:sha256:64c99d1d0e31cc701bcedcbe371b603ef179991db5ab508a17abb31ea8d99062

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_DIGEST_SRC_BIN:-$HOME/knowledge/bin}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

MIG="$SRC_BIN/kb-digest-migrate"
if [[ ! -x "$MIG" ]]; then
  fail "kb-digest-migrate missing from $SRC_BIN"
  echo "PASS=$PASS FAIL=$FAIL"; exit 1
fi

# fixture <money_radar: present-enabled|present-disabled|absent> <learning: enabled|disabled>
fixture() {
  cat <<'EOF'
# operator comment that must survive migration
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
EOF
  if [[ "$2" == "enabled" ]]; then
    cat <<'EOF'

- id: learning
  enabled: true
  when: after:daily
  run: kb-learning-arxiv --text-only
  outputs: [telegram, file]
EOF
  else
    cat <<'EOF'

- id: learning
  enabled: false
  when: after:daily
  run: kb-learning-arxiv --text-only
  outputs: [telegram, file]
EOF
  fi
  case "$1" in
    present-enabled) cat <<'EOF'

- id: money-radar
  enabled: true
  when: after:learning
  run: kb-money-radar --text-only
  outputs: [telegram, file]
EOF
    ;;
    present-disabled) cat <<'EOF'

- id: money-radar
  enabled: false
  when: after:learning
  run: kb-money-radar --text-only
  outputs: [telegram, file]
EOF
    ;;
  esac
}

anchor_of() { # $1=file  -> prints morning-digest when: value
  awk '/^- id: morning-digest$/{f=1} f && /^  when:/{print $2; exit}' "$1"
}

# ── (a) money-radar enabled -> after:money-radar ─────────────────────────────
F="$TMP/a.yaml"; fixture present-enabled enabled > "$F"
"$MIG" --file "$F" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "a: migrate exits 0" || fail "a: migrate rc=$RC"
[[ "$(anchor_of "$F")" == "after:money-radar" ]] \
  && ok "a: morning-digest anchored after:money-radar" \
  || fail "a: wrong anchor: $(anchor_of "$F")"
grep -q '^- id: evening-digest$' "$F" \
  && ok "a: evening-digest inserted" || fail "a: evening-digest missing"
awk '/^- id: evening-digest$/{f=1} f && /^  when:/{print $2; exit}' "$F" | grep -q '^after:retro$' \
  && ok "a: evening-digest anchored after:retro" \
  || fail "a: evening-digest anchor wrong"
grep -q '^# operator comment that must survive migration$' "$F" \
  && ok "a: comments survive (text-surgical edit)" || fail "a: comment destroyed"
python3 - "$SRC_BIN" "$F" <<'PY' && ok "a: result validates; other edges preserved" || fail "a: result invalid or edges broken"
import sys
sys.path.insert(0, sys.argv[1])
from _kb_processes import parse_processes_text
procs = {p["id"]: p for p in parse_processes_text(open(sys.argv[2]).read())}
assert procs["daily"]["when"] == "07:30"
assert procs["retro"]["when"] == "20:45"
assert procs["money-radar"]["when"] == "after:learning"
assert procs["morning-digest"]["outputs"] == ["file", "notebooklm_audio"]
assert procs["evening-digest"]["outputs"] == ["file", "notebooklm_audio"]
PY

# Idempotence: re-run is a byte-identical no-op.
CP="$TMP/a.before"; cp "$F" "$CP"
"$MIG" --file "$F" >/dev/null 2>&1
cmp -s "$F" "$CP" && ok "a: re-run is a byte-identical no-op" || fail "a: re-run changed the file"

# ── (b) money-radar absent/disabled -> after:learning ────────────────────────
F="$TMP/b1.yaml"; fixture absent enabled > "$F"
"$MIG" --file "$F" >/dev/null 2>&1
[[ "$(anchor_of "$F")" == "after:learning" ]] \
  && ok "b: money-radar absent -> after:learning" \
  || fail "b: wrong anchor (absent): $(anchor_of "$F")"
F="$TMP/b2.yaml"; fixture present-disabled enabled > "$F"
"$MIG" --file "$F" >/dev/null 2>&1
[[ "$(anchor_of "$F")" == "after:learning" ]] \
  && ok "b: money-radar disabled -> after:learning" \
  || fail "b: wrong anchor (disabled): $(anchor_of "$F")"

# ── (c) learning disabled too -> after:daily ─────────────────────────────────
F="$TMP/c.yaml"; fixture present-disabled disabled > "$F"
"$MIG" --file "$F" >/dev/null 2>&1
[[ "$(anchor_of "$F")" == "after:daily" ]] \
  && ok "c: learning disabled too -> after:daily" \
  || fail "c: wrong anchor: $(anchor_of "$F")"

# ── (d) managed re-anchor: fresh default + later-enabled money-radar ─────────
F="$TMP/d.yaml"
{ fixture absent enabled; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-morning-digest
  outputs: [file, notebooklm_audio]

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest --period evening
  outputs: [file, notebooklm_audio]
EOF
} > "$F"
# Later: money-radar appears, enabled.
cat >> "$F" <<'EOF'

- id: money-radar
  enabled: true
  when: after:learning
  run: kb-money-radar --text-only
  outputs: [telegram, file]
EOF
BEFORE=$(grep -c '^  when:' "$F")
"$MIG" --file "$F" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "d: re-anchor migrate exits 0" || fail "d: rc=$RC"
[[ "$(anchor_of "$F")" == "after:money-radar" ]] \
  && ok "d: managed morning-digest re-anchored to after:money-radar" \
  || fail "d: managed re-anchor did not happen: $(anchor_of "$F")"
[[ $(grep -c '^  outputs: \[file, notebooklm_audio\]$' "$F") -eq 2 ]] \
  && ok "d: no-option re-anchor preserves NotebookLM route" \
  || fail "d: no-option migration changed the selected route"
AFTER=$(grep -c '^  when:' "$F")
[[ "$BEFORE" -eq "$AFTER" ]] \
  && ok "d: re-anchor changed no block structure (when: count stable)" \
  || fail "d: re-anchor altered block structure"
CP="$TMP/d.before"; cp "$F" "$CP"
"$MIG" --file "$F" >/dev/null 2>&1
cmp -s "$F" "$CP" && ok "d: second run after re-anchor is a no-op" || fail "d: re-anchor not idempotent"

# A boolean-map block remains managed regardless of which channel flags are on.
F2="$TMP/d-flags.yaml"
{ fixture absent enabled; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:learning
  run: kb-morning-digest
  outputs: {file: true, telegram_audio: true, notebooklm_audio: true}

- id: evening-digest
  enabled: true
  when: after:retro
  run: kb-morning-digest --period evening
  outputs: {file: true, telegram_audio: true, notebooklm_audio: false}

- id: money-radar
  enabled: true
  when: after:learning
  run: kb-money-radar --text-only
  outputs: [telegram, file]
EOF
} > "$F2"
MORNING_FLAGS_BEFORE=$(awk '/^- id: morning-digest$/{f=1} f && /^  outputs:/{print; exit}' "$F2")
"$MIG" --file "$F2" >/dev/null 2>&1; RC=$?
MORNING_FLAGS_AFTER=$(awk '/^- id: morning-digest$/{f=1} f && /^  outputs:/{print; exit}' "$F2")
[[ $RC -eq 0 && "$(anchor_of "$F2")" == "after:money-radar" \
   && "$MORNING_FLAGS_BEFORE" == "$MORNING_FLAGS_AFTER" ]] \
  && ok "d: channel flags stay managed and re-anchor without rewriting outputs" \
  || fail "d: channel flags were treated as a hardcoded/custom combination"

CP="$TMP/d.no-selector"; cp "$F" "$CP"
"$MIG" --file "$F" --audio-backend local_qwen >/dev/null 2>&1; RC=$?
[[ $RC -eq 2 && $(cmp -s "$F" "$CP"; echo $?) -eq 0 ]] \
  && ok "d: legacy audio-backend selector is removed; outputs stay untouched" \
  || fail "d: second delivery setting still exists or changed outputs"

# ── (e) customized morning-digest block stays byte-identical ─────────────────
F="$TMP/e.yaml"
{ fixture present-enabled enabled; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: "05:00"
  run: kb-morning-digest --date 2026-01-01
  outputs: [file]
EOF
} > "$F"
"$MIG" --file "$F" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "e: migrate with customized block exits 0" || fail "e: rc=$RC"
[[ "$(anchor_of "$F")" == '"05:00"' ]] \
  && ok "e: customized morning-digest left untouched (when unchanged)" \
  || fail "e: customized block was rewritten: $(anchor_of "$F")"
grep -q '^  run: kb-morning-digest --date 2026-01-01$' "$F" \
  && ok "e: customized run preserved" || fail "e: customized run rewritten"
grep -q '^- id: evening-digest$' "$F" \
  && ok "e: evening-digest still inserted alongside custom block" \
  || fail "e: evening-digest missing with custom block"

# ── (f) customized evening block also stays byte-identical ──────────────────
F="$TMP/f.yaml"
{ fixture present-enabled enabled; cat <<'EOF'

- id: morning-digest
  enabled: true
  when: after:money-radar
  run: kb-morning-digest
  outputs: [file, telegram_audio]

- id: evening-digest
  enabled: true
  when: "22:00"
  run: kb-morning-digest --period evening --date 2026-01-01
  outputs: [file]
EOF
} >"$F"
CP="$TMP/f.before"; cp "$F" "$CP"
"$MIG" --file "$F" >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "f: migrate with customized evening exits 0" || fail "f: rc=$RC"
cmp -s "$F" "$CP" \
  && ok "f: customized evening block remains byte-identical" \
  || fail "f: customized evening block was rewritten"

# ── Malformed input fails closed (no rewrite/partial file) ───────────────────
F="$TMP/bad.yaml"; printf -- "- id: broken\n  garbage without fields\n" > "$F"
CP="$TMP/bad.before"; cp "$F" "$CP"
"$MIG" --file "$F" >/dev/null 2>&1; RC=$?
[[ $RC -ne 0 ]] && ok "malformed input: non-zero exit" || fail "malformed input accepted"
cmp -s "$F" "$CP" && ok "malformed input: file untouched" || fail "malformed input: file was rewritten"

# ── --revert round-trips ──────────────────────────────────────────────────────
F="$TMP/rt.yaml"; fixture present-enabled enabled > "$F"
CP="$TMP/rt.orig"; cp "$F" "$CP"
"$MIG" --file "$F" >/dev/null 2>&1
"$MIG" --file "$F" --revert >/dev/null 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "revert exits 0" || fail "revert rc=$RC"
cmp -s "$F" "$CP" && ok "revert round-trips to the original file" || fail "revert did not round-trip"
# Revert on a non-migrated file is a no-op.
"$MIG" --file "$F" --revert >/dev/null 2>&1
cmp -s "$F" "$CP" && ok "revert on non-migrated file is a no-op" || fail "revert damaged a non-migrated file"

echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
