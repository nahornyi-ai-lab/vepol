#!/usr/bin/env bash
# kb-claude-hooks: adds Vepol's SessionStart/SessionEnd/PreCompact hooks to an
# existing ~/.claude/settings.json without touching anything else.
# Runs against throwaway settings files only.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_CLAUDE_HOOKS_SRC_BIN:-$(cd "$(dirname "$0")/.." && pwd)}"
TOOL="$SRC_BIN/kb-claude-hooks"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

H="$TMP/home"; mkdir -p "$H/.claude"
run() { HOME="$H" python3 "$TOOL" "$@"; }
backups() { ls "$1".bak-* 2>/dev/null | wc -l | tr -d ' '; }
# hooks_ok FILE — all three events run the expected script with $HOME rendered
hooks_ok() {
  H="$H" python3 - "$1" <<'PY'
import json, os, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
home = os.environ["H"]
want = {"SessionStart": "kb-session-start", "SessionEnd": "kb-session-end",
        "PreCompact": "kb-pre-compact"}
for ev, script in want.items():
    cmds = [h.get("command", "") for e in d["hooks"][ev] for h in e.get("hooks", [])]
    assert f"bash {home}/knowledge/bin/{script}" in cmds, (ev, cmds)
assert "__HOME__" not in json.dumps(d)
PY
}

echo "kb-claude-hooks tests"

# 1. Missing file: --check names all three, --apply creates a hooks-only file.
S="$H/.claude/settings.json"
out=$(run --check); rc=$?
[[ $rc -eq 1 && "$out" == *SessionStart* && "$out" == *SessionEnd* && "$out" == *PreCompact* ]] \
  && ok "missing file: --check exits 1 and names all three hooks" || fail "missing file --check (rc=$rc out=$out)"
run --apply >/dev/null; rc=$?
[[ $rc -eq 0 && -f "$S" ]] && hooks_ok "$S" \
  && [[ "$(python3 -c 'import json,sys; print(sorted(json.load(open(sys.argv[1]))))' "$S")" == "['hooks']" ]] \
  && ok "missing file: --apply creates settings.json holding only the hooks (\$HOME rendered)" \
  || fail "missing file --apply (rc=$rc)"
run --check >/dev/null; [[ $? -eq 0 ]] && ok "missing file: --check exits 0 after --apply" || fail "check after create"

# 2. File without hooks: other keys untouched, backup holds the original bytes.
S2="$TMP/s2/settings.json"; mkdir -p "$(dirname "$S2")"
cat > "$S2" <<'EOF'
{"permissions": {"allow": ["Read", "Bash(git:*)"], "defaultMode": "default"},
 "theme": "dark", "model": "opus", "env": {"FOO": "1"}, "statusLine": {"type": "command", "command": "x"}}
EOF
chmod 600 "$S2"
orig="$(cat "$S2")"
run --check --settings "$S2" >/dev/null; [[ $? -eq 1 ]] && ok "no hooks: --check exits 1" || fail "no hooks --check"
run --apply --settings "$S2" >/dev/null; rc=$?
bk="$(ls "$S2".bak-* 2>/dev/null | head -1)"
[[ $rc -eq 0 && -n "$bk" && "$(cat "$bk")" == "$orig" ]] && ok "no hooks: --apply writes a timestamped backup of the original" \
  || fail "no hooks backup (rc=$rc bk=$bk)"
hooks_ok "$S2" && ok "no hooks: all three hooks added" || fail "no hooks: hooks not added"
python3 - "$S2" "$bk" <<'PY' && ok "no hooks: every other key and its order untouched" || fail "no hooks: other keys changed"
import json, sys
new = json.load(open(sys.argv[1])); old = json.load(open(sys.argv[2]))
hooks = new.pop("hooks")
assert new == old, (new, old)
assert list(new) == list(old)
assert set(hooks) == {"SessionStart", "SessionEnd", "PreCompact"}
PY
[[ "$(stat -f '%Lp' "$S2")" == "600" ]] && ok "no hooks: file mode kept (600)" || fail "mode changed to $(stat -f '%Lp' "$S2")"

# 3. Idempotent: second --apply changes nothing and makes no new backup.
before="$(cat "$S2")"; nb="$(backups "$S2")"
out=$(run --apply --settings "$S2"); rc=$?
[[ $rc -eq 0 && "$(cat "$S2")" == "$before" && "$(backups "$S2")" == "$nb" && "$out" == *"nothing changed"* ]] \
  && ok "second --apply is a no-op (same bytes, no new backup)" || fail "second apply not idempotent (rc=$rc)"

# 4. Some hooks present: only the missing ones are added; the user's own hooks stay.
S3="$TMP/s3/settings.json"; mkdir -p "$(dirname "$S3")"
cat > "$S3" <<EOF
{
  "hooks": {
    "SessionStart": [
      {"matcher": "", "hooks": [{"type": "command", "command": "$H/knowledge/bin/kb-session-start", "timeout": 30}]},
      {"matcher": "startup", "hooks": [{"type": "command", "command": "echo mine"}]}
    ],
    "Stop": [{"hooks": [{"type": "command", "command": "afplay /System/Library/Sounds/Glass.aiff"}]}],
    "PreCompact": [{"matcher": "manual", "hooks": [{"type": "command", "command": "echo compact"}]}]
  },
  "permissions": {"allow": []}
}
EOF
out=$(run --check --settings "$S3"); rc=$?
[[ $rc -eq 1 && "$out" == *SessionEnd* && "$out" == *PreCompact* && "$out" != *SessionStart* ]] \
  && ok "some hooks: --check names only the missing ones" || fail "some hooks --check (rc=$rc out=$out)"
[[ "$out" == *"~/knowledge/bin/kb-claude-hooks --apply --settings"* ]] \
  && ok "some hooks: --check prints a runnable fix command" || fail "fix hint (out=$out)"
cp "$S3" "$TMP/s3.orig"
run --apply --settings "$S3" >/dev/null; rc=$?
python3 - "$S3" "$TMP/s3.orig" <<'PY' && [[ $rc -eq 0 ]] && ok "some hooks: adds only SessionEnd + PreCompact, keeps user and existing entries" || fail "some hooks apply (rc=$rc)"
import json, sys
new = json.load(open(sys.argv[1])); old = json.load(open(sys.argv[2]))
assert new["hooks"]["SessionStart"] == old["hooks"]["SessionStart"]  # already present: untouched
assert new["hooks"]["Stop"] == old["hooks"]["Stop"]
assert new["hooks"]["PreCompact"][0] == old["hooks"]["PreCompact"][0]  # user's entry kept first
assert len(new["hooks"]["PreCompact"]) == 2
assert "kb-pre-compact" in new["hooks"]["PreCompact"][1]["hooks"][0]["command"]
assert len(new["hooks"]["SessionEnd"]) == 1
assert new["permissions"] == old["permissions"]
PY
run --check --settings "$S3" >/dev/null; [[ $? -eq 0 ]] && ok "some hooks: --check exits 0 after --apply" || fail "some hooks check after apply"

# 5. Invalid JSON: refused, file unchanged, no backup.
S4="$TMP/s4/settings.json"; mkdir -p "$(dirname "$S4")"
printf '{ "permissions": { "allow": ["Read"], } // comment\n' > "$S4"
b4="$(cat "$S4")"
err=$(run --apply --settings "$S4" 2>&1 >/dev/null); rc=$?
[[ $rc -eq 2 && "$(cat "$S4")" == "$b4" && "$(backups "$S4")" == "0" && "$err" == *"not valid JSON"* ]] \
  && ok "invalid JSON: --apply exits 2, writes nothing, no backup" || fail "invalid JSON (rc=$rc err=$err)"
run --check --settings "$S4" >/dev/null 2>&1; [[ $? -eq 2 ]] && ok "invalid JSON: --check exits 2" || fail "invalid JSON --check"
printf '[1, 2]\n' > "$S4"
run --apply --settings "$S4" >/dev/null 2>&1; rc=$?
[[ $rc -eq 2 && "$(cat "$S4")" == "[1, 2]" ]] && ok "non-object JSON: refused, unchanged" || fail "non-object JSON (rc=$rc)"

# 6. A symlinked settings.json (dotfile managers) stays a symlink; the target gets the hooks.
real="$TMP/dotfiles/claude-settings.json"; mkdir -p "$(dirname "$real")"
printf '{"theme": "light"}\n' > "$real"
S5="$TMP/s5/settings.json"; mkdir -p "$(dirname "$S5")"; ln -s "$real" "$S5"
run --apply --settings "$S5" >/dev/null; rc=$?
[[ $rc -eq 0 && -L "$S5" ]] && hooks_ok "$real" && ok "symlinked settings.json: link kept, target updated" \
  || fail "symlinked settings (rc=$rc)"

# 7. Usage: a mode is required.
run >/dev/null 2>&1; [[ $? -eq 2 ]] && ok "no mode → usage error (exit 2)" || fail "no mode exit code"

# 8. A hub whose bin/ holds a copy of the tool (not a link into the repo).
H8="$TMP/home8"; mkdir -p "$H8/.claude" "$TMP/copybin"
cp "$TOOL" "$TMP/copybin/kb-claude-hooks"
cp "$S2" "$H8/.claude/settings.json"   # all three hooks present
out=$(HOME="$H8" python3 "$TMP/copybin/kb-claude-hooks" --apply 2>&1); rc=$?
[[ $rc -eq 0 && "$out" == *"nothing changed"* ]] \
  && ok "copied tool, hooks present: --apply is a no-op without the template" || fail "copy no-op (rc=$rc out=$out)"
printf '{"theme": "dark"}\n' > "$H8/.claude/settings.json"
HOME="$H8" python3 "$TMP/copybin/kb-claude-hooks" --apply >/dev/null 2>&1; rc=$?
[[ $rc -eq 2 && "$(cat "$H8/.claude/settings.json")" == '{"theme": "dark"}' && "$(backups "$H8/.claude/settings.json")" == "0" ]] \
  && ok "copied tool, no template reachable: --apply exits 2, writes nothing" || fail "copy without template (rc=$rc)"
mkdir -p "$H8/knowledge"; ln -s "$(cd "$SRC_BIN/.." && pwd)" "$H8/knowledge/orchestrator-seed"
HOME="$H8" python3 "$TMP/copybin/kb-claude-hooks" --apply >/dev/null 2>&1; rc=$?
[[ $rc -eq 0 ]] && H="$H8" hooks_ok "$H8/.claude/settings.json" \
  && ok "copied tool: template found through ~/knowledge/orchestrator-seed" || fail "copy via orchestrator-seed (rc=$rc)"

echo
echo "kb-claude-hooks: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
