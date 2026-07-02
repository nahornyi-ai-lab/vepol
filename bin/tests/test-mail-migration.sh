#!/usr/bin/env bash
# test-mail-migration.sh — AC1 process ordering + build-plan migration item.
#
# The idempotent processes.yaml migration turns the mail feature on for existing
# installs: it inserts mail-morning / mail-evening and rewires daily -> retro to
# run behind them, WITHOUT losing any existing downstream edge, and is a no-op on
# re-run. A malformed source must fail closed: non-zero exit, no rewrite.
#
# Fixtures only — this test NEVER touches the live ~/knowledge/personal/processes.yaml.
#
# Spec: knowledge/decisions/mail-briefing-integration-2026-06-29.md (AC1, AC12)
# Plan: knowledge/decisions/mail-briefing-integration-build-plan-2026-07-01.md
set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MAIL_SRC_BIN:-$HOME/knowledge/bin}"
MIG="$SRC_BIN/kb-mail-migrate"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# Deterministic oracle: interrogate a processes.yaml through the real validator
# (reuse, not a second parser). Prints the python repr of <expr> over `m` (id->proc)
# and `ids` (declared order). Exits non-zero if the file itself is invalid.
pyq() { # $1=file  $2=python-expr
  KB_MAIL_SRC_BIN="$SRC_BIN" python3 - "$1" "$2" <<'PY'
import os, sys
sys.path.insert(0, os.environ["KB_MAIL_SRC_BIN"])
from _kb_processes import parse_processes_text
path, expr = sys.argv[1], sys.argv[2]
procs = parse_processes_text(open(path, encoding="utf-8").read())
m = {p["id"]: p for p in procs}
ids = [p["id"] for p in procs]
print(eval(expr))
PY
}
is_true() { [[ "$1" == "True" ]]; }

# ── realistic fixture: live SHAPE (daily 06:30, retro 20:45) + after:-chains ──
FIX="$TMP/processes.yaml"
cat > "$FIX" <<'YAML'
# Vepol background processes — test fixture (realistic shape).
# Exactly five fields per process: id, enabled, when, run, outputs.

- id: daily
  enabled: true
  when: "06:30"
  run: kb-brief
  outputs: [telegram, file]

- id: retro
  enabled: true
  when: "20:45"
  run: kb-retro
  outputs: [telegram, file]

# arXiv learning digest keeps its after:daily edge.
- id: learning
  enabled: true
  when: after:daily
  run: kb-learning-arxiv --text-only
  outputs: [telegram, file]

- id: money-radar
  enabled: true
  when: after:learning
  run: kb-money-radar --text-only
  outputs: [telegram, file]

- id: people-extract
  enabled: true
  when: after:retro
  run: kb-extract-people --hub ~/knowledge --no-llm --quiet
  outputs: [people, telegram, file]

- id: people-remind
  enabled: true
  when: "08:00"
  run: kb-people-remind --horizon 0
  outputs: [telegram]
YAML

# ── 1. migrate rewires daily/retro and inserts the mail processes ────────────
F1="$TMP/f1.yaml"; cp "$FIX" "$F1"
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$F1" >/dev/null 2>"$TMP/e1.txt"; rc=$?
[[ $rc -eq 0 ]] && ok "migrate: exit 0" || { fail "migrate: exit $rc ($(cat "$TMP/e1.txt"))"; }

is_true "$(pyq "$F1" "m['daily']['when']=='after:mail-morning'")"  && ok "migrate: daily -> after:mail-morning"  || fail "migrate: daily not rewired"
is_true "$(pyq "$F1" "m['retro']['when']=='after:mail-evening'")"  && ok "migrate: retro -> after:mail-evening"  || fail "migrate: retro not rewired"
is_true "$(pyq "$F1" "'mail-morning' in m and 'mail-evening' in m")" && ok "migrate: both mail processes present" || fail "migrate: mail processes missing"

# mail-morning exact fields
is_true "$(pyq "$F1" "m['mail-morning']==dict(id='mail-morning',enabled=True,when='06:15',run='kb-mail-brief --period morning --write',outputs=['file'])")" \
  && ok "migrate: mail-morning has the exact 5 fields" || fail "migrate: mail-morning fields wrong"
# mail-evening exact fields
is_true "$(pyq "$F1" "m['mail-evening']==dict(id='mail-evening',enabled=True,when='20:30',run='kb-mail-brief --period evening --write',outputs=['file'])")" \
  && ok "migrate: mail-evening has the exact 5 fields" || fail "migrate: mail-evening fields wrong"

# ── 2. every other process + edge preserved exactly ──────────────────────────
is_true "$(pyq "$F1" "m['learning']['when']=='after:daily'")"        && ok "preserve: learning -> after:daily"        || fail "preserve: learning edge lost"
is_true "$(pyq "$F1" "m['money-radar']['when']=='after:learning'")"  && ok "preserve: money-radar -> after:learning"  || fail "preserve: money-radar edge lost"
is_true "$(pyq "$F1" "m['people-extract']['when']=='after:retro'")"  && ok "preserve: people-extract -> after:retro"  || fail "preserve: people-extract edge lost"
is_true "$(pyq "$F1" "m['people-remind']['when']=='08:00'")"         && ok "preserve: people-remind fixed 08:00"      || fail "preserve: people-remind time changed"
is_true "$(pyq "$F1" "set(ids)=={'daily','retro','learning','money-radar','people-extract','people-remind','mail-morning','mail-evening'}")" \
  && ok "preserve: only the two mail processes were added" || fail "preserve: process set changed unexpectedly"
grep -q "arXiv learning digest keeps its after:daily edge." "$F1" \
  && ok "preserve: existing comments survive the rewrite" || fail "preserve: comments dropped"

# ── 3. second migration is an idempotent no-op (byte-identical) ──────────────
cp "$F1" "$TMP/after-first.yaml"
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$F1" >/dev/null 2>&1; rc=$?
[[ $rc -eq 0 ]] && ok "idempotent: second migrate exit 0" || fail "idempotent: second migrate exit $rc"
cmp -s "$F1" "$TMP/after-first.yaml" && ok "idempotent: second migrate is byte-identical" || fail "idempotent: output drifted on re-run"

# ── 4. malformed source fails closed: non-zero, error, file UNCHANGED ─────────
MAL="$TMP/malformed.yaml"
cat > "$MAL" <<'YAML'
- id: daily
  enabled: true
  when: "06:30"
  run: kb-brief
  outputs: [telegram, file]

- id: retro
  enabled: true
  when: after:ghost
  run: kb-retro
  outputs: [telegram, file]
YAML
cp "$MAL" "$MAL.orig"
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$MAL" >/dev/null 2>"$TMP/emal.txt"; rc=$?
[[ $rc -ne 0 ]]        && ok "malformed: non-zero exit"                 || fail "malformed: expected non-zero exit"
[[ -s "$TMP/emal.txt" ]] && ok "malformed: error message printed"      || fail "malformed: no error printed"
cmp -s "$MAL" "$MAL.orig" && ok "malformed: file left byte-for-byte unchanged" || fail "malformed: file was modified"

# ── 5. --revert restores fixed times, removes mail-*, round-trips exactly ─────
F2="$TMP/f2.yaml"; cp "$FIX" "$F2"
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$F2" >/dev/null 2>&1            # migrate
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$F2" --revert >/dev/null 2>&1; rc=$?  # revert
[[ $rc -eq 0 ]] && ok "revert: exit 0" || fail "revert: exit $rc"
is_true "$(pyq "$F2" "'mail-morning' not in m and 'mail-evening' not in m")" && ok "revert: mail processes removed" || fail "revert: mail processes remain"
is_true "$(pyq "$F2" "m['daily']['when']=='06:30' and m['retro']['when']=='20:45'")" && ok "revert: daily/retro restored to fixed times" || fail "revert: fixed times not restored"
is_true "$(pyq "$F2" "m['learning']['when']=='after:daily' and m['money-radar']['when']=='after:learning'")" && ok "revert: other edges intact" || fail "revert: other edges damaged"
cmp -s "$F2" "$FIX" && ok "revert: migrate->revert round-trips to the original file" || fail "revert: round-trip not byte-identical"

# General-time regression: an install whose daily is NOT 06:30 must get
# mail-morning one tick before ITS OWN time (not a hardcoded 06:15), and revert
# must restore ITS original time losslessly — so the rollout never shifts a
# user's ritual by an hour (spec: worst-case ~1-tick shift only).
F3="$TMP/proc-0730.yaml"
cat > "$F3" <<'YAML'
- id: daily
  enabled: true
  when: "07:30"
  run: kb-brief
  outputs: [telegram, file]

- id: learning
  enabled: true
  when: after:daily
  run: kb-learning-arxiv --text-only
  outputs: [file]

- id: retro
  enabled: true
  when: "20:45"
  run: kb-retro
  outputs: [telegram, file]
YAML
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$F3" >/dev/null 2>&1
is_true "$(pyq "$F3" "m['mail-morning']['when']=='07:15' and m['mail-evening']['when']=='20:30'")" \
  && ok "general-time: mail-* derived from this install's own daily/retro (07:30->07:15)" \
  || fail "general-time: mail time hardcoded, not derived"
is_true "$(pyq "$F3" "m['daily']['when']=='after:mail-morning' and m['retro']['when']=='after:mail-evening'")" \
  && ok "general-time: daily/retro rewired" || fail "general-time: not rewired"
KB_MAIL_SRC_BIN="$SRC_BIN" "$MIG" --file "$F3" --revert >/dev/null 2>&1
is_true "$(pyq "$F3" "m['daily']['when']=='07:30' and m['retro']['when']=='20:45'")" \
  && ok "general-time: revert restores original 07:30/20:45 losslessly" \
  || fail "general-time: revert lost the original time"

echo; echo "PASS=$PASS FAIL=$FAIL"; [[ "$FAIL" == "0" ]]
