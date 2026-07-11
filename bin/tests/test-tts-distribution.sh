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
  ok "audio-backend installer setting not applicable to this standalone root"
elif grep -q -- '--audio-backend' "$PUBLIC/install.sh" \
  && grep -q 'local_qwen' "$PUBLIC/install.sh" \
  && grep -q 'notebooklm' "$PUBLIC/install.sh"; then
  ok "installer exposes NotebookLM/local-Qwen audio backend selection"
else
  bad "installer has no explicit dual-backend setting"
fi

if [[ -f "$PUBLIC/install.sh" ]]; then
  CAPS=$("$PUBLIC/install.sh" --capabilities --json 2>/dev/null); RC=$?
  [[ $RC -eq 0 && "$CAPS" == *'"audio_backends": ["notebooklm", "local_qwen"]'* ]] \
    && ok "installer capabilities advertise both backend values" \
    || bad "installer capabilities omit the backend values"
  "$PUBLIC/install.sh" --capabilities --audio-backend invalid >/dev/null 2>&1; RC=$?
  [[ $RC -eq 2 ]] \
    && ok "installer rejects an invalid backend before mutation" \
    || bad "installer accepted an invalid backend (rc=$RC)"
fi

# Behavioral installer matrix in an isolated HOME against the exact staged
# release artifact. Fake Qwen install records the route it observed, proving
# model smoke happens before the managed outputs switch.
if [[ -n "$ARTIFACT_TMP" ]]; then
  CASE="$ARTIFACT_TMP/install-case"; HOME_CASE="$CASE/home"; FAKEBIN="$CASE/fakebin"
  mkdir -p "$HOME_CASE" "$FAKEBIN"
  for name in claude rg; do
    printf '#!/bin/sh\nexit 0\n' >"$FAKEBIN/$name"; chmod +x "$FAKEBIN/$name"
  done
  printf '#!/bin/sh\necho v20.0.0\n' >"$FAKEBIN/node"; chmod +x "$FAKEBIN/node"
  printf '#!/bin/sh\necho 1.1.0\n' >"$FAKEBIN/bun"; chmod +x "$FAKEBIN/bun"
  INSTALL_ENV=(HOME="$HOME_CASE" PATH="$FAKEBIN:$PATH" VEPOL_NONINTERACTIVE=1)

  env "${INSTALL_ENV[@]}" "$PUBLIC/install.sh" --apply \
    >/dev/null 2>&1; RC=$?
  CONFIG="$HOME_CASE/knowledge/personal/processes.yaml"
  [[ $RC -eq 0 && $(grep -c '^  outputs: \[file, notebooklm_audio\]$' "$CONFIG") -eq 2 ]] \
    && ok "fresh installer default writes NotebookLM route" \
    || bad "fresh installer default did not write NotebookLM route (rc=$RC)"

  cat >"$PUBLIC/bin/kb-tts-install" <<'SH'
#!/usr/bin/env bash
set -u
config="$HOME/knowledge/personal/processes.yaml"
if grep -q '^  outputs: \[file, notebooklm_audio\]$' "$config"; then
  echo observed_notebooklm >>"$HOME/tts-install-order.log"
else
  echo observed_other >>"$HOME/tts-install-order.log"
fi
[[ "${KB_FAKE_TTS_INSTALL_MODE:-success}" == success ]]
SH
  chmod +x "$PUBLIC/bin/kb-tts-install"
  env "${INSTALL_ENV[@]}" KB_FAKE_TTS_INSTALL_MODE=success \
    "$PUBLIC/install.sh" --apply --audio-backend local_qwen >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 && $(grep -c '^observed_notebooklm$' "$HOME_CASE/tts-install-order.log") -eq 1 \
     && $(grep -c '^  outputs: \[file, telegram_audio\]$' "$CONFIG") -eq 2 ]] \
    && ok "Qwen install succeeds before managed outputs switch" \
    || bad "Qwen installer ordering/selection is wrong (rc=$RC)"

  cp "$CONFIG" "$CASE/preserve.before"
  env "${INSTALL_ENV[@]}" "$PUBLIC/install.sh" --apply >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 ]] && cmp -s "$CONFIG" "$CASE/preserve.before" \
    && ok "upgrade without selection preserves managed config byte-identical" \
    || bad "upgrade without selection changed managed config"

  env "${INSTALL_ENV[@]}" "$PUBLIC/install.sh" --apply --audio-backend notebooklm \
    >/dev/null 2>&1
  cp "$CONFIG" "$CASE/failure.before"
  env "${INSTALL_ENV[@]}" KB_FAKE_TTS_INSTALL_MODE=failure \
    "$PUBLIC/install.sh" --apply --audio-backend local_qwen >/dev/null 2>&1; RC=$?
  [[ $RC -ne 0 ]] && cmp -s "$CONFIG" "$CASE/failure.before" \
    && ok "failed Qwen install leaves prior route byte-identical" \
    || bad "failed Qwen install changed the prior route"

  python3 - "$CONFIG" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1]); lines = path.read_text().splitlines()
active = None
for i, line in enumerate(lines):
    if line == "- id: morning-digest": active = "morning"
    elif line == "- id: evening-digest": active = "evening"
    elif line.startswith("- id: "): active = None
    elif active and line.startswith("  run:"):
        lines[i] = "  run: kb-morning-digest --custom-operator-route"
    elif active and line.startswith("  outputs:"):
        lines[i] = "  outputs: [file]"
path.write_text("\n".join(lines) + "\n")
PY
  cp "$CONFIG" "$CASE/custom.before"
  env "${INSTALL_ENV[@]}" KB_FAKE_TTS_INSTALL_MODE=success \
    "$PUBLIC/install.sh" --apply --audio-backend local_qwen >/dev/null 2>&1; RC=$?
  [[ $RC -eq 0 ]] && cmp -s "$CONFIG" "$CASE/custom.before" \
    && ok "installer leaves customized digest blocks byte-identical" \
    || bad "installer rewrote customized digest blocks"
fi

if [[ ! -f "$PUBLIC/README.md" || ! -f "$PUBLIC/CHANGELOG.md" ]]; then
  ok "public guidance check not applicable to this standalone root"
elif grep -Fq 'kb-tts-install' "$PUBLIC/README.md" \
   && grep -Fq 'NotebookLM' "$PUBLIC/README.md" \
   && grep -Fq 'local Qwen' "$PUBLIC/CHANGELOG.md"; then
  ok "public guidance documents both selectable audio routes"
else
  bad "public guidance does not document both audio routes"
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
