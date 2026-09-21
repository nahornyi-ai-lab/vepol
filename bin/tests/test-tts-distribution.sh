#!/usr/bin/env bash
# Distribution acceptance for source-only local Qwen TTS runtime.
# Contracts: local delivery + v0.6 semantic-freshness release.

set -uo pipefail
PASS=0; FAIL=0
SELF_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
HUB="${KB_HUB:-$SELF_ROOT}"
ARTIFACT_TMP=""
cleanup() { [[ -n "$ARTIFACT_TMP" ]] && rm -rf "$ARTIFACT_TMP"; }
trap cleanup EXIT
if [[ -z "${KB_TTS_SEED:-}" && -z "${KB_TTS_PUBLIC:-}" ]] \
   && git -C "$SELF_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ARTIFACT_TMP=$(mktemp -d)
  mkdir -p "$ARTIFACT_TMP/release"
  git -C "$SELF_ROOT" checkout-index --prefix="$ARTIFACT_TMP/release/" -a
  SEED="$ARTIFACT_TMP/release"
  PUBLIC="$ARTIFACT_TMP/release"
else
  SEED="${KB_TTS_SEED:-$SELF_ROOT}"
  PUBLIC="${KB_TTS_PUBLIC:-$SELF_ROOT}"
fi
ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

FILES=(
  kb-morning-digest kb-channel-send-audio kb-tts-install kb-tts-render _kb_processes.py
  _kb_digest_migrate.py kb-digest-migrate
)
TTS_FILES=(install_model.py requirements.in requirements.lock worker.py)
TESTS=(
  test-channel-send-audio.sh test-local-tts-digest-integration.sh
  test-evening-digest.sh test-processes-audio-allowlist.sh
  test-digest-migration.sh test-qwen-tts-on-demand.sh test-tts-distribution.sh
)

for root in "$SEED" "$PUBLIC"; do
  label=$(basename "$root")
  missing=0
  for f in "${FILES[@]}"; do [[ -f "$root/bin/$f" ]] || missing=1; done
  for f in "${TTS_FILES[@]}"; do [[ -f "$root/bin/_kb_tts/$f" ]] || missing=1; done
  for f in "${TESTS[@]}"; do [[ -f "$root/bin/tests/$f" ]] || missing=1; done
  [[ $missing -eq 0 ]] && ok "$label ships complete source/test surface" || bad "$label source/test surface incomplete"

  drift=0
  for f in "${FILES[@]}"; do cmp -s "$HUB/bin/$f" "$root/bin/$f" || drift=1; done
  for f in "${TTS_FILES[@]}"; do cmp -s "$HUB/bin/_kb_tts/$f" "$root/bin/_kb_tts/$f" || drift=1; done
  for f in "${TESTS[@]}"; do cmp -s "$HUB/bin/tests/$f" "$root/bin/tests/$f" || drift=1; done
  [[ $drift -eq 0 ]] && ok "$label generic files are byte-identical" || bad "$label generic file drift"

  forbidden=$(find "$root" -type f \( -name '*.safetensors' -o -name '*.gguf' \
    -o -name 'install.json' -o -name 'last-render.json' -o -name '*.pyc' \
    -o -name '*.mp3' -o -name '*.wav' \) -print 2>/dev/null)
  secret_values=$(find "$root" -type f -name '.secrets' -exec awk -F= \
    '!/^[[:space:]]*#/ && NF > 1 {v=$0; sub(/^[^=]*=/,"",v); if (v != "") print FILENAME ":" $0}' {} + 2>/dev/null)
  [[ -z "$forbidden" && -z "$secret_values" ]] \
    && ok "$label contains no weights/credentials/cache/audio artifacts" \
    || bad "$label leaked runtime artifacts: $forbidden $secret_values"
done

if [[ ! -f "$PUBLIC/install.sh" ]]; then
  ok "public installer check not applicable to this standalone root"
elif grep -Eq 'for pkg in .*_kb_tts([[:space:]]|;)' "$PUBLIC/install.sh"; then
  ok "public installer links _kb_tts beside kb-tts-install"
else
  bad "public installer omits _kb_tts internal package"
fi

if [[ ! -f "$PUBLIC/install.sh" ]]; then
  ok "installer channel-setting check not applicable to this standalone root"
else
  if grep -q -- '--audio-backend' "$PUBLIC/install.sh"; then
    bad "installer still exposes a second audio-backend setting"
  else
    ok "outputs map is the only installer delivery setting"
  fi
  CAPS=$("$PUBLIC/install.sh" --capabilities --json 2>/dev/null); RC=$?
  [[ $RC -eq 0 && "$CAPS" != *'"audio_backends"'* ]] \
    && ok "installer capabilities have no backend selector" \
    || bad "installer capabilities still advertise backend selector"
  "$PUBLIC/install.sh" --capabilities --audio-backend local_qwen >/dev/null 2>&1; RC=$?
  [[ $RC -eq 2 ]] \
    && ok "legacy audio-backend option is rejected" \
    || bad "legacy audio-backend option is still accepted (rc=$RC)"
fi

# Fresh install writes one boolean output map; upgrades preserve user flags.
if [[ -n "$ARTIFACT_TMP" ]]; then
  CASE="$ARTIFACT_TMP/install-case"; HOME_CASE="$CASE/home"; FAKEBIN="$CASE/fakebin"
  mkdir -p "$HOME_CASE" "$FAKEBIN"
  for name in claude rg; do
    printf '#!/bin/sh\nexit 0\n' >"$FAKEBIN/$name"; chmod +x "$FAKEBIN/$name"
  done
  printf '#!/bin/sh\necho v20.0.0\n' >"$FAKEBIN/node"; chmod +x "$FAKEBIN/node"
  printf '#!/bin/sh\necho 1.1.0\n' >"$FAKEBIN/bun"; chmod +x "$FAKEBIN/bun"
  INSTALL_ENV=(HOME="$HOME_CASE" PATH="$FAKEBIN:$PATH" VEPOL_NONINTERACTIVE=1)

  env "${INSTALL_ENV[@]}" "$PUBLIC/install.sh" --apply >/dev/null 2>&1; RC=$?
  CONFIG="$HOME_CASE/knowledge/personal/processes.yaml"
  [[ $RC -eq 0 && $(grep -c '^  outputs: {file: true, telegram_audio: false, notebooklm_audio: true}$' "$CONFIG") -eq 2 ]] \
    && ok "fresh installer writes one boolean output map" \
    || bad "fresh installer output map is wrong (rc=$RC)"

  cp "$CONFIG" "$CASE/preserve.before"
  env "${INSTALL_ENV[@]}" "$PUBLIC/install.sh" --apply >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 ]] && cmp -s "$CONFIG" "$CASE/preserve.before" \
    && ok "upgrade preserves output flags byte-identical" \
    || bad "upgrade changed output flags"
fi

if [[ ! -f "$PUBLIC/README.md" || ! -f "$PUBLIC/CHANGELOG.md" ]]; then
  ok "public guidance check not applicable to this standalone root"
elif grep -Fq 'telegram_audio: true' "$PUBLIC/README.md" \
   && grep -Fq 'notebooklm_audio: true' "$PUBLIC/README.md" \
   && ! grep -q -- '--audio-backend' "$PUBLIC/README.md"; then
  ok "public guidance documents the single boolean output map"
else
  bad "public guidance does not document the boolean output map"
fi

SEED_INSTALL="${KB_TTS_SEED_INSTALL:-$(cd "$SEED/.." 2>/dev/null && pwd)/install.sh}"
if [[ ! -f "$SEED_INSTALL" ]]; then
  ok "seed installer check not applicable to this standalone root"
elif grep -Fq 'find "$SEED_DIR/knowledge/bin" -mindepth 1 -maxdepth 1 -type d' "$SEED_INSTALL"; then
  ok "seed installer copies source package directories generically"
else
  bad "seed installer does not copy package directories"
fi

echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]]
