#!/usr/bin/env bash
# R6c AC9: allowlisted morning fidelity seed transaction must preserve every
# dirty path outside scope and must never stage/commit/push.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
LIVE_BIN="${KB_MORNING_FIDELITY_SRC_BIN:-$HOME/knowledge/bin}"
SYNC="$LIVE_BIN/kb-seed-sync"
if [[ ! -f "$SYNC" ]]; then
  # Distribution hook is a hub tool; shipped trees don't carry it, and this
  # suite only has meaning where the sync itself lives.
  echo "skip: kb-seed-sync not in $LIVE_BIN — scoped-sync suite is hub-only"
  exit 0
fi
HUB="$TMP/hub"
PRIVATE="$HUB/orchestrator-seed"
PUBLIC="$TMP/vepol-prep"

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }

mkdir -p "$HUB/bin/tests" "$PRIVATE/knowledge/bin/tests" "$PRIVATE/claude" \
         "$PUBLIC/bin/tests" "$PUBLIC/bin/_kb_tts"
for f in kb-brief kb-brief-preflight _kb_brief_delivery.py kb-channel-send-text \
         kb-mail-block \
         kb-morning-digest kb-learning-arxiv kb-seed-sync \
         _kb_claude_runner.py _kb_retro.py; do
  [[ -f "$LIVE_BIN/$f" ]] && cp "$LIVE_BIN/$f" "$HUB/bin/$f"
done
for t in test-morning-brief-fidelity.sh test-channel-send-text.sh \
         test-morning-whole-block-audio.sh test-seed-sync-morning-scope.sh \
         test-brief-reliability.sh test-local-tts-digest-integration.sh \
         test-brief-v2-preflight.sh; do
  [[ -f "$LIVE_BIN/tests/$t" ]] && cp "$LIVE_BIN/tests/$t" "$HUB/bin/tests/$t"
done

# Dirty sentinels mirror the actual out-of-scope dirt in both managed worktrees.
printf 'private-settings-dirty\n' > "$PRIVATE/claude/settings.json.template"
mkdir -p "$PRIVATE/knowledge/bin/_kb_tts"
printf 'private-qwen-dirty\n' > "$PRIVATE/knowledge/bin/_kb_tts/install_model.py"
printf 'private-qwen-test-dirty\n' > "$PRIVATE/knowledge/bin/tests/test-qwen-tts-on-demand.sh"
printf 'private-roster-untracked\n' > "$PRIVATE/knowledge/.active-roster.md"
printf 'public-qwen-dirty\n' > "$PUBLIC/bin/_kb_tts/install_model.py"
printf 'public-mail-test-dirty\n' > "$PUBLIC/bin/tests/test-mail-digest-integration.sh"
printf 'public-preflight-untracked\n' > "$PUBLIC/bin/kb-brief-preflight"
printf 'public-preflight-test-untracked\n' > "$PUBLIC/bin/tests/test-brief-v2-preflight.sh"

for repo in "$PRIVATE" "$PUBLIC"; do
  git -C "$repo" init -q
  git -C "$repo" add -A
  git -C "$repo" -c user.name=test -c user.email=test@example.invalid commit -qm baseline
done
# These three paths are intentionally untracked in the real worktrees.
git -C "$PRIVATE" rm -q --cached knowledge/.active-roster.md
git -C "$PRIVATE" -c user.name=test -c user.email=test@example.invalid commit -qm 'leave roster untracked'
git -C "$PUBLIC" rm -q --cached bin/kb-brief-preflight bin/tests/test-brief-v2-preflight.sh
git -C "$PUBLIC" -c user.name=test -c user.email=test@example.invalid commit -qm 'leave preflight work untracked'
# Make tracked sentinels dirty after baseline.
printf 'private-settings-dirty-v2\n' >> "$PRIVATE/claude/settings.json.template"
printf 'private-qwen-dirty-v2\n' >> "$PRIVATE/knowledge/bin/_kb_tts/install_model.py"
printf 'private-qwen-test-dirty-v2\n' >> "$PRIVATE/knowledge/bin/tests/test-qwen-tts-on-demand.sh"
printf 'public-qwen-dirty-v2\n' >> "$PUBLIC/bin/_kb_tts/install_model.py"
printf 'public-mail-test-dirty-v2\n' >> "$PUBLIC/bin/tests/test-mail-digest-integration.sh"

SENTINELS=(
  "$PRIVATE/claude/settings.json.template"
  "$PRIVATE/knowledge/bin/_kb_tts/install_model.py"
  "$PRIVATE/knowledge/bin/tests/test-qwen-tts-on-demand.sh"
  "$PRIVATE/knowledge/.active-roster.md"
  "$PUBLIC/bin/_kb_tts/install_model.py"
  "$PUBLIC/bin/tests/test-mail-digest-integration.sh"
)
BEFORE="$TMP/before"
for f in "${SENTINELS[@]}"; do printf '%s  %s\n' "$(sha "$f")" "$f"; done > "$BEFORE"
PRIVATE_INDEX=$(git -C "$PRIVATE" write-tree)
PUBLIC_INDEX=$(git -C "$PUBLIC" write-tree)

echo "=== AC9 allowlisted seed sync ==="
set +e
KB_HUB="$HUB" VEPOL_PREP_DIR="$PUBLIC" \
  "$SYNC" --scope morning-brief-fidelity >"$TMP/sync.out" 2>"$TMP/sync.err"
RC=$?
set -e
[[ "$RC" == "0" ]] && ok "scoped sync exits zero" || fail "scoped sync rc=$RC"

AFTER="$TMP/after"
for f in "${SENTINELS[@]}"; do printf '%s  %s\n' "$(sha "$f")" "$f"; done > "$AFTER"
cmp -s "$BEFORE" "$AFTER" && ok "all public/private dirty sentinels byte-identical" \
  || fail "scoped sync changed an out-of-scope dirty sentinel"
[[ "$(git -C "$PRIVATE" write-tree)" == "$PRIVATE_INDEX" \
   && "$(git -C "$PUBLIC" write-tree)" == "$PUBLIC_INDEX" ]] \
  && ok "scoped sync stages nothing" || fail "scoped sync mutated a git index"

for root in "$PRIVATE/knowledge/bin" "$PUBLIC/bin"; do
  for f in kb-brief kb-brief-preflight _kb_brief_delivery.py \
           kb-channel-send-text kb-mail-block \
           kb-morning-digest kb-learning-arxiv \
           _kb_claude_runner.py _kb_retro.py; do
    [[ -f "$root/$f" ]] && ok "distributed ${root##*/}/$f" \
      || fail "missing distributed $root/$f"
  done
  for t in test-morning-brief-fidelity.sh test-channel-send-text.sh \
           test-morning-whole-block-audio.sh test-seed-sync-morning-scope.sh \
           test-brief-reliability.sh test-local-tts-digest-integration.sh \
           test-brief-v2-preflight.sh; do
    [[ -f "$root/tests/$t" ]] && ok "distributed test $t" \
      || fail "missing distributed $root/tests/$t"
  done
done

# Scope output itself must promise the mutation boundary and no staging/push.
grep -q 'morning-brief-fidelity' "$TMP/sync.out" \
  && ok "scope is visible in audit output" || fail "scope missing from audit output"
if grep -Eqi 'git add|commit|push' "$TMP/sync.out" "$TMP/sync.err"; then
  fail "scoped sync attempted or advertised staging/publish"
else
  ok "scope has no stage/commit/push path"
fi

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
