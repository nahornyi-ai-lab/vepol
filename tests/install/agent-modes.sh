#!/usr/bin/env bash
# tests/install/agent-modes.sh — regression guard for prompt-first install modes.
# Runs entirely against throwaway HOMEs; never touches the real ~/knowledge.
# spec: agent-self-install-prompt-distribution-2026-06-16 (AC2/AC3/AC8/AC10/AC14)
# + Codex impl-review hardening (managed-only uninstall, C-01 explicit approval).

set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL="$REPO/install.sh"
PASS=0; FAIL=0
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home"; mkdir -p "$HOME"
PREREQ="$WORK/prereq-bin"; mkdir -p "$PREREQ"
cat > "$PREREQ/node" <<'EOF'
#!/usr/bin/env bash
echo "v20.0.0"
EOF
cat > "$PREREQ/bun" <<'EOF'
#!/usr/bin/env bash
echo "1.1.0"
EOF
chmod +x "$PREREQ/node" "$PREREQ/bun"
for t in git claude rg; do
  src="$(command -v "$t" 2>/dev/null || true)"
  if [[ -n "$src" ]]; then
    ln -sf "$src" "$PREREQ/$t"
  else
    cat > "$PREREQ/$t" <<EOF
#!/usr/bin/env bash
echo "$t test shim"
EOF
    chmod +x "$PREREQ/$t"
  fi
done
export PATH="$PREREQ:$PATH"

p() { printf '  ✓ %s\n' "$1"; PASS=$((PASS+1)); }
f() { printf '  ✘ %s\n' "$1"; FAIL=$((FAIL+1)); }
json_ok() { python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1; }

echo "agent-modes tests (HOME=$HOME)"

# AC2 — unknown flag → exit 2, EMPTY stdout
out="$("$INSTALL" --bogus 2>/dev/null)"; rc=$?
[[ "$rc" -eq 2 && -z "$out" ]] && p "unknown flag → exit 2, empty stdout" || f "unknown flag (rc=$rc, out='$out')"

# conflicting mode flags → exit 2 (no last-wins running apply)
out="$("$INSTALL" --probe --apply 2>/dev/null)"; rc=$?
[[ "$rc" -eq 2 && -z "$out" ]] && p "conflicting modes (--probe --apply) → exit 2" || f "conflicting modes (rc=$rc)"

# --capabilities → valid JSON listing modes, and works WITHOUT python3
"$INSTALL" --capabilities --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "--probe" in d["modes"] and "--apply" in d["modes"]' \
  && p "--capabilities → valid JSON with modes" || f "--capabilities JSON"
# Minimal PATH that has everything install.sh needs to reach --capabilities EXCEPT
# python3 — proving the capabilities path is python-free (pure cat heredoc).
nopy="$WORK/nopy"; mkdir -p "$nopy"
for t in bash dirname cat date uname head sed; do
  src="$(command -v "$t" 2>/dev/null)"; [[ -n "$src" ]] && ln -sf "$src" "$nopy/$t"
done
[[ -z "$(command -v python3 2>/dev/null && true)" ]] || true   # (python3 deliberately absent from $nopy)
out="$(PATH="$nopy" "$INSTALL" --capabilities --json 2>/dev/null)"
printf '%s' "$out" | json_ok && p "--capabilities works without python3 on PATH" || f "--capabilities sans python3"

# AC3 — probe read-only: valid JSON, no hub, and install.log untouched
probe_out="$WORK/probe.json"
log_before="$(stat -f '%m' "$REPO/install.log" 2>/dev/null || echo none)"
"$INSTALL" --probe --json >"$probe_out" 2>/dev/null; rc=$?
log_after="$(stat -f '%m' "$REPO/install.log" 2>/dev/null || echo none)"
json_ok <"$probe_out" && [[ "$rc" -eq 0 || "$rc" -eq 10 || "$rc" -eq 11 ]] && [[ ! -d "$HOME/knowledge" ]] && [[ "$log_before" == "$log_after" ]] \
  && p "--probe → valid JSON, read-only (no hub, log untouched)" || f "--probe read-only (rc=$rc, log $log_before->$log_after)"

# --dry-run mutates nothing
"$INSTALL" --dry-run --json | python3 -c 'import json,sys; assert json.load(sys.stdin)["mutates"] is False' \
  && [[ ! -d "$HOME/knowledge" ]] && p "--dry-run → mutates:false, no hub" || f "--dry-run"

# --verify on a fresh machine → 13
"$INSTALL" --verify --json >/dev/null 2>&1; [[ $? -eq 13 ]] && p "--verify (fresh) → exit 13" || f "--verify fresh"

# full --apply (no opt-ins) → exit 0, hub + receipt, opt-ins normalized to off
"$INSTALL" --apply >/dev/null 2>&1; rc=$?
rcpt="$(ls "$HOME/knowledge/install/receipts/"*.md 2>/dev/null | head -1)"
[[ "$rc" -eq 0 && -L "$HOME/knowledge/bin/kb-doctor" && -n "$rcpt" ]] && grep -q "opt_ins: launchd=off telegram=off memory_compiler=off" "$rcpt" \
  && p "--apply → installs, receipt with normalized off opt-ins" || f "--apply (rc=$rc)"

# --verify after apply → 0
"$INSTALL" --verify --json >/dev/null 2>&1; [[ $? -eq 0 ]] && p "--verify (installed) → exit 0" || f "--verify installed"

# --verify must catch a TAMPERED managed link (retargeted but still a symlink → green before)
# Use a regular-file decoy as the tamper target so ln -sfn never dereferences into a dir.
touch "$WORK/decoy"
ln -sfn "$WORK/decoy" "$HOME/knowledge/bin/kb-doctor"
vout="$("$INSTALL" --verify --json 2>/dev/null)"; vrc=$?
printf '%s' "$vout" | grep -q "bin-tampered:kb-doctor" && [[ "$vrc" -eq 13 ]] \
  && p "--verify catches tampered managed link (retargeted) → exit 13" || f "--verify tamper (rc=$vrc)"
ln -sfn "$REPO/bin/kb-doctor" "$HOME/knowledge/bin/kb-doctor"   # restore clean install for later steps

# --verify must catch a tampered orchestrator-seed pointer (retargeted symlink)
ln -sfn "$WORK/decoy" "$HOME/knowledge/orchestrator-seed"
sout="$("$INSTALL" --verify --json 2>/dev/null)"; src=$?
printf '%s' "$sout" | grep -q "seed-pointer-tampered" && [[ "$src" -eq 13 ]] \
  && p "--verify catches tampered orchestrator-seed pointer → exit 13" || f "--verify seed-pointer (rc=$src)"
# ...and a seed pointer REPLACED by a real file (not a symlink at all)
rm -f "$HOME/knowledge/orchestrator-seed"; printf 'evil\n' > "$HOME/knowledge/orchestrator-seed"
sout2="$("$INSTALL" --verify --json 2>/dev/null)"; src2=$?
printf '%s' "$sout2" | grep -q "seed-pointer-not-symlink" && [[ "$src2" -eq 13 ]] \
  && p "--verify catches replaced non-symlink seed locator → exit 13" || f "--verify seed-pointer non-symlink (rc=$src2)"
rm -f "$HOME/knowledge/orchestrator-seed"; ln -sfn "$REPO" "$HOME/knowledge/orchestrator-seed"   # restore

# apply/verify consistency: a pre-existing non-symlink seed pointer must be self-healed
# by --apply (backed up + replaced with the correct symlink) so --verify then passes —
# verify must never reject a state that a fresh --apply leaves behind.
cons="$WORK/conshome"; mkdir -p "$cons/knowledge"
printf 'old\n' > "$cons/knowledge/orchestrator-seed"
HOME="$cons" "$INSTALL" --apply >/dev/null 2>&1
HOME="$cons" "$INSTALL" --verify --json >/dev/null 2>&1; cvrc=$?
cbak="$(ls "$cons/knowledge/orchestrator-seed.pre-vepol."* 2>/dev/null | head -1)"
[[ -L "$cons/knowledge/orchestrator-seed" && "$cvrc" -eq 0 && -n "$cbak" && "$(cat "$cbak")" == "old" ]] \
  && p "apply self-heals non-symlink seed pointer (backup) → verify passes (apply/verify consistent)" || f "apply/verify seed-pointer consistency (verify rc=$cvrc)"

# AC8 — C-01 deferred (legacy bypass, --apply, no flag): no abort, unchanged, marker=1
c01="$WORK/c01"; mkdir -p "$c01/.claude"
printf '{ "permissions": { "defaultMode": "bypassPermissions" } }\n' > "$c01/.claude/settings.json"
before="$(cat "$c01/.claude/settings.json")"
HOME="$c01" "$INSTALL" --apply >/dev/null 2>&1; rc=$?
after="$(cat "$c01/.claude/settings.json")"
marker="$(grep -h needs_security_migration "$c01/knowledge/install/receipts/"*.md 2>/dev/null)"
[[ "$rc" -eq 0 && "$before" == "$after" && "$marker" == *": 1"* ]] \
  && p "C-01 deferred → no abort, settings unchanged, marker=1" || f "C-01 defer (rc=$rc)"

# VEPOL_YES=1 in --apply must NOT migrate (only VEPOL_APPLY_C01 may)
yhome="$WORK/yes"; mkdir -p "$yhome/.claude"
printf '{ "permissions": { "defaultMode": "bypassPermissions" } }\n' > "$yhome/.claude/settings.json"
yb="$(cat "$yhome/.claude/settings.json")"
HOME="$yhome" VEPOL_YES=1 "$INSTALL" --apply >/dev/null 2>&1
ya="$(cat "$yhome/.claude/settings.json")"
[[ "$yb" == "$ya" ]] && p "VEPOL_YES=1 in --apply does NOT migrate C-01" || f "VEPOL_YES leaked into apply migration"

# VEPOL_APPLY_C01=1 migrates
HOME="$c01" VEPOL_APPLY_C01=1 "$INSTALL" --apply >/dev/null 2>&1
mode="$(python3 -c 'import json;print(json.load(open("'"$c01"'/.claude/settings.json")).get("permissions",{}).get("defaultMode"))' 2>/dev/null)"
[[ "$mode" == "default" ]] && p "VEPOL_APPLY_C01=1 → migrates (defaultMode=default)" || f "VEPOL_APPLY_C01 migrate (got $mode)"

# AC10 — uninstall managed-only: removes ONLY exact managed links; preserves user data,
# user symlinks of every shape, and custom skill sidecars.
echo "PRECIOUS" > "$HOME/knowledge/personal/keep.md"
ln -sf /tmp           "$HOME/knowledge/bin/my-user-tool"        # different name → keep
ln -sf /tmp           "$HOME/knowledge/bin/kb-mine"            # managed-looking name, wrong target → keep
ln -sf "$REPO/bin/kb-search" "$HOME/knowledge/bin/my-alias"   # alias to OUR tool, custom name → keep
mkdir -p "$HOME/.claude/skills/init-kb"; echo "MINE" > "$HOME/.claude/skills/init-kb/custom.txt"
"$REPO/uninstall.sh" --yes >/dev/null 2>&1
ok_managed=1
[[ -e "$HOME/knowledge/bin/kb-doctor" ]] && ok_managed=0           # ours (exact managed link) gone
[[ -e "$HOME/knowledge/bin/_kb_ideas" ]] && ok_managed=0          # managed dir-symlink gone too (drift-proof)
# NO managed link of any name may remain (target == seed/bin/<own basename>)
leftover_managed="$(find "$HOME/knowledge/bin" -maxdepth 1 -type l 2>/dev/null | while read -r l; do
  [[ "$(readlink "$l")" == "$REPO/bin/$(basename "$l")" ]] && echo "$l"; done)"
[[ -n "$leftover_managed" ]] && ok_managed=0
[[ -L "$HOME/knowledge/bin/my-user-tool" ]] || ok_managed=0
[[ -L "$HOME/knowledge/bin/kb-mine" ]] || ok_managed=0
[[ -L "$HOME/knowledge/bin/my-alias" ]] || ok_managed=0
[[ "$(cat "$HOME/knowledge/personal/keep.md" 2>/dev/null)" == "PRECIOUS" ]] || ok_managed=0
[[ "$(cat "$HOME/.claude/skills/init-kb/custom.txt" 2>/dev/null)" == "MINE" ]] || ok_managed=0
[[ "$ok_managed" -eq 1 ]] && p "uninstall → ALL managed links gone (incl _kb_ideas); user symlinks/data/sidecars preserved" || f "uninstall managed-only (leftover: ${leftover_managed:-none})"

# path-sensitivity: install via real seed path, uninstall via a SYMLINK to the seed.
# A string-compare ownership check would leave managed links behind; pwd -P must not.
ps="$WORK/pshome"; mkdir -p "$ps"
HOME="$ps" "$INSTALL" --apply >/dev/null 2>&1
seedlink="$WORK/seedlink"; ln -s "$REPO" "$seedlink"
HOME="$ps" "$seedlink/uninstall.sh" --yes >/dev/null 2>&1
ps_left="$(find "$ps/knowledge/bin" -maxdepth 1 -type l 2>/dev/null | while read -r l; do
  td="$(cd "$(dirname "$(readlink "$l")")" 2>/dev/null && pwd -P)"; [[ "$td" == "$(cd "$REPO/bin" && pwd -P)" && "$(basename "$l")" == "$(basename "$(readlink "$l")")" ]] && echo "$l"; done)"
[[ -z "$ps_left" ]] && p "uninstall via symlinked seed path still removes all managed links (path-canonical)" || f "path-sensitive uninstall left: $ps_left"

# install must NOT clobber a pre-existing user SKILL.md it doesn't own (backs it up)
sk="$WORK/skills"; mkdir -p "$sk/.claude/skills/init-kb"
printf 'USER OWN SKILL\n' > "$sk/.claude/skills/init-kb/SKILL.md"
HOME="$sk" "$INSTALL" --apply >/dev/null 2>&1
bak="$(ls "$sk/.claude/skills/init-kb/SKILL.md.pre-vepol."* 2>/dev/null | head -1)"
[[ -n "$bak" && "$(cat "$bak")" == "USER OWN SKILL" && -f "$sk/.claude/skills/init-kb/.vepol-managed" ]] \
  && p "install preserves pre-existing user SKILL.md (backup + marker)" || f "install skill clobber"

# uninstall must NOT remove a same-named user skill that lacks the ownership marker
us="$WORK/userskill"; mkdir -p "$us/.claude/skills/init-kb"
printf 'MY OWN\n' > "$us/.claude/skills/init-kb/SKILL.md"   # no .vepol-managed marker
HOME="$us" "$REPO/uninstall.sh" --yes >/dev/null 2>&1
[[ "$(cat "$us/.claude/skills/init-kb/SKILL.md" 2>/dev/null)" == "MY OWN" ]] \
  && p "uninstall leaves un-owned same-named skill untouched" || f "uninstall removed un-owned skill"

# custom VEPOL_HUB in --apply is refused in v1 (fail fast, exit 1, clear message, touches NOTHING)
ch="$WORK/customhubhome"; mkdir -p "$ch"
cherr="$WORK/ch.err"
HOME="$ch" VEPOL_HUB="$ch/customhub" "$INSTALL" --apply >/dev/null 2>"$cherr"; rc=$?
[[ "$rc" -eq 1 && ! -e "$ch/customhub" && ! -e "$ch/knowledge" ]] && grep -q "not supported for install in v1" "$cherr" \
  && p "custom VEPOL_HUB --apply → exit 1 + clear message, creates no hub" || f "custom hub refusal (rc=$rc, err=$(cat "$cherr"))"

# read-only modes still accept a custom VEPOL_HUB (report only, no mutation)
rh="$WORK/rohome"; mkdir -p "$rh"
HOME="$rh" VEPOL_HUB="$rh/ro-hub" "$INSTALL" --probe --json | json_ok && [[ ! -e "$rh/ro-hub" && ! -e "$rh/knowledge" ]] \
  && p "read-only --probe accepts custom VEPOL_HUB, mutates nothing" || f "read-only custom hub"

# shell-emitted JSON stays valid when the hub path contains a double quote
HOME="$WORK/qhome" VEPOL_HUB='/tmp/ab"cd' "$INSTALL" --dry-run --json | json_ok \
  && p "--dry-run JSON valid with quote in hub path" || f "dry-run JSON invalid on quote in path"

echo "  ---"
echo "  PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
