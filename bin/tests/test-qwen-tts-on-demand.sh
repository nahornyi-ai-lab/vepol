#!/usr/bin/env bash
# Acceptance tests for the approved BF16 migration addendum.
# Contract: spec-contract:sha256:9a2a772620f31df501c3e5b3fd0e8b487d91a3fb12b1a21ab7c89323e7e6da4a

set -uo pipefail

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_TTS_SRC_BIN:-$HOME/knowledge/bin}"
INSTALL="$SRC_BIN/kb-tts-install"
RENDER="$SRC_BIN/kb-tts-render"

ok() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
bad() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

expect_ok() {
  local label="$1"; shift
  if "$@" >"$TMP/stdout" 2>"$TMP/stderr"; then ok "$label"; else bad "$label: $(tail -1 "$TMP/stderr")"; fi
}

expect_fail() {
  local label="$1"; shift
  if "$@" >"$TMP/stdout" 2>"$TMP/stderr"; then bad "$label (unexpected success)"; else ok "$label"; fi
}

if [[ ! -x "$INSTALL" ]]; then bad "installer exists and is executable"; else ok "installer exists and is executable"; fi
if [[ ! -x "$RENDER" ]]; then bad "renderer exists and is executable"; else ok "renderer exists and is executable"; fi

HOME_DIR="$TMP/home"
MODEL_DIR="$HOME_DIR/model"
mkdir -p "$MODEL_DIR" "$HOME_DIR/venv/bin"
ln -s "$(command -v python3)" "$HOME_DIR/venv/bin/python"

cat >"$HOME_DIR/install.json" <<EOF
{
  "schema": 1,
  "python_version": "3.12.9",
  "mlx_audio_version": "0.4.5",
  "model_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
  "model_revision": "7d3824abff87e49756bb0f83fb5411de75d160c4",
  "model_path": "$MODEL_DIR"
}
EOF

FAKE_WORKER="$TMP/fake-worker.py"
cat >"$FAKE_WORKER" <<'PY'
import argparse, json, os, signal, subprocess, sys, time, wave
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--config", required=True)
a = p.parse_args()
cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
capture = os.environ.get("KB_TTS_TEST_CAPTURE")
if capture:
    payload = dict(cfg)
    payload["text"] = Path(cfg["input_path"]).read_text(encoding="utf-8")
    payload["offline_env"] = {k: os.environ.get(k) for k in (
        "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY")}
    Path(capture).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

mode = os.environ.get("KB_TTS_FAKE_MODE", "success")
if mode == "failure":
    raise SystemExit(7)
if mode in {"slow", "stubborn"}:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    def stop(signum, _frame):
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait()
        raise SystemExit(128 + signum)
    if mode == "slow":
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
    else:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        child.send_signal(signal.SIGSTOP)
    Path(os.environ["KB_TTS_TEST_PIDS"]).write_text(
        f"{os.getpid()} {child.pid} {os.getpgrp()}\n", encoding="utf-8")
    while True:
        time.sleep(1)

if mode == "escape":
    out = Path(cfg["output_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000)
        f.writeframes((b"\x00\x10" * 2400))
    child = subprocess.Popen([
        sys.executable, "-c",
        "import os,time; time.sleep(.35); os.setsid(); time.sleep(300)",
    ])
    Path(os.environ["KB_TTS_TEST_PIDS"]).write_text(
        f"{os.getpid()} {child.pid} {os.getpgrp()}\n", encoding="utf-8")
    time.sleep(1)
    raise SystemExit(0)

out = Path(cfg["output_path"])
out.parent.mkdir(parents=True, exist_ok=True)
if out.suffix.lower() == ".wav":
    with wave.open(str(out), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000)
        f.writeframes((b"\x00\x10" * 2400))
else:
    out.write_bytes(b"ID3-fake-mp3-audio")
PY

run_render() {
  KB_TTS_HOME="$HOME_DIR" \
  KB_TTS_PYTHON="$HOME_DIR/venv/bin/python" \
  KB_TTS_WORKER="$FAKE_WORKER" \
  "$RENDER" "$@"
}

if [[ -x "$INSTALL" ]]; then
  DRY=$(KB_TTS_HOME="$TMP/install-dry" "$INSTALL" --dry-run 2>&1 || true)
  [[ "$DRY" == *"CPython 3.12.9"* ]] && ok "installer pins CPython 3.12.9" || bad "installer dry-run misses CPython pin"
  [[ "$DRY" == *"mlx-audio==0.4.5"* ]] && ok "installer pins mlx-audio 0.4.5" || bad "installer dry-run misses mlx-audio pin"
  [[ "$DRY" == *"mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"* ]] && ok "installer pins BF16 model ID" || bad "installer dry-run misses BF16 model ID"
  [[ "$DRY" == *"7d3824abff87e49756bb0f83fb5411de75d160c4"* ]] && ok "installer pins model revision" || bad "installer dry-run misses model revision"
  [[ "$DRY" == *"96ae28bec2205ec0b5e0c750bea2b8a5deac4f14d33a8a25a5f753299486b70e"* ]] && ok "installer records main weight hash" || bad "installer misses main weight hash"
  [[ "$DRY" == *"836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258"* ]] && ok "installer records tokenizer weight hash" || bad "installer misses tokenizer weight hash"
  [[ "$DRY" == *"immutable verified release"* && "$DRY" == *"atomic install.json"* ]] && ok "installer declares immutable atomic promotion" || bad "installer dry-run misses immutable atomic promotion"

  if python3 - "$INSTALL" "$TMP/transaction" <<'PY'
import fcntl
import hashlib
import json
import os
import runpy
import sys
from pathlib import Path

ns = runpy.run_path(sys.argv[1], run_name="kb_tts_install_test")
promote = ns["promote_verified_release"]
lock = ns["installation_lock"]
root = Path(sys.argv[2])

def digest(data):
    return hashlib.sha256(data).hexdigest()

main = b"fake-bf16-main"
tokenizer = b"fake-tokenizer"
expected = {
    "model.safetensors": digest(main),
    "speech_tokenizer/model.safetensors": digest(tokenizer),
}

def stage(home, name=".stage-test"):
    path = home / "models" / name
    (path / "speech_tokenizer").mkdir(parents=True)
    (path / "model.safetensors").write_bytes(main)
    (path / "speech_tokenizer/model.safetensors").write_bytes(tokenizer)
    return path

def payload():
    return {
        "schema": 1,
        "python_version": "3.12.9",
        "mlx_audio_version": "0.4.5",
        "model_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
        "model_revision": "7d3824abff87e49756bb0f83fb5411de75d160c4",
    }

# Fresh success.
home = root / "fresh"
final = promote(home, stage(home), "bf16-test", payload(), expected=expected)
assert final.is_dir()
assert json.loads((home / "install.json").read_text())["model_path"] == str(final.resolve())

# Upgrade success preserves the old model directory.
home = root / "upgrade"
old = home / "model"
old.mkdir(parents=True)
(old / "sentinel").write_text("old-8bit")
old_marker = b'{"model_id":"old-8bit","model_path":"old"}\n'
(home / "install.json").write_bytes(old_marker)
final = promote(home, stage(home), "bf16-test", payload(), expected=expected)
assert (old / "sentinel").read_text() == "old-8bit"
assert json.loads((home / "install.json").read_text())["model_path"] == str(final.resolve())
assert (home / "rollback" / "install-before-bf16-test.json").read_bytes() == old_marker

# Missing/invalid staged files and an invalid final collision preserve marker bytes.
for case in ("missing-main", "bad-main", "bad-tokenizer"):
    home = root / case
    home.mkdir(parents=True)
    marker = home / "install.json"
    marker.write_bytes(b"old-marker\n")
    before = marker.read_bytes()
    candidate = stage(home)
    if case == "missing-main":
        (candidate / "model.safetensors").unlink()
    elif case == "bad-main":
        (candidate / "model.safetensors").write_bytes(b"wrong")
    else:
        (candidate / "speech_tokenizer/model.safetensors").write_bytes(b"wrong")
    try:
        promote(home, candidate, "bf16-test", payload(), expected=expected)
    except (RuntimeError, SystemExit):
        pass
    else:
        raise AssertionError(case)
    assert marker.read_bytes() == before

home = root / "collision"
home.mkdir(parents=True)
marker = home / "install.json"
marker.write_bytes(b"old-marker\n")
before = marker.read_bytes()
bad_final = home / "models" / "bf16-test"
bad_final.mkdir(parents=True)
(bad_final / "model.safetensors").write_bytes(b"wrong")
try:
    promote(home, stage(home), "bf16-test", payload(), expected=expected)
except (RuntimeError, SystemExit):
    pass
else:
    raise AssertionError("invalid final collision")
assert marker.read_bytes() == before

# Marker-write failure leaves the prior marker byte-identical; retry reuses the verified release.
home = root / "marker-failure"
home.mkdir(parents=True)
marker = home / "install.json"
marker.write_bytes(b"old-marker\n")
before = marker.read_bytes()
real_replace = os.replace
def fail_marker(src, dst):
    if Path(dst).name == "install.json":
        raise OSError("simulated marker failure")
    return real_replace(src, dst)
try:
    promote(home, stage(home), "bf16-test", payload(), expected=expected, replace_fn=fail_marker)
except OSError:
    pass
else:
    raise AssertionError("marker failure")
assert marker.read_bytes() == before
final = promote(home, None, "bf16-test", payload(), expected=expected)
assert json.loads(marker.read_text())["model_path"] == str(final.resolve())

# A second non-blocking lock acquisition is rejected without marker mutation.
home = root / "lock"
home.mkdir(parents=True)
marker = home / "install.json"
marker.write_bytes(b"old-marker\n")
with lock(home / "install.lock"):
    try:
        with lock(home / "install.lock"):
            pass
    except RuntimeError:
        pass
    else:
        raise AssertionError("concurrent lock accepted")
assert marker.read_bytes() == b"old-marker\n"
PY
  then
    ok "immutable release transaction preserves rollback across failures and lock contention"
  else
    bad "immutable release transaction contract failed"
  fi
else
  bad "installer dry-run contract unavailable"
fi

if [[ -x "$RENDER" ]]; then
  expect_fail "renderer rejects neither input" run_render --out "$TMP/no-input.wav"
  expect_fail "renderer rejects both inputs" run_render --text x --file "$TMP/x.txt" --out "$TMP/both.wav"
  expect_fail "renderer rejects empty text" run_render --text "" --out "$TMP/empty.wav"
  expect_fail "renderer rejects unsupported extension" run_render --text x --out "$TMP/audio.ogg"

  cp "$HOME_DIR/install.json" "$TMP/install-bf16.json"
  OLD_MODEL_ID="mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-"$'8bit'
  OLD_MODEL_REVISION="f90d617701d9f7f4ca499291e0b57f2b3c2"$'fd2ee'
  cat >"$HOME_DIR/install.json" <<EOF
{
  "schema": 1,
  "python_version": "3.12.9",
  "mlx_audio_version": "0.4.5",
  "model_id": "$OLD_MODEL_ID",
  "model_revision": "$OLD_MODEL_REVISION",
  "model_path": "$MODEL_DIR"
}
EOF
  expect_fail "renderer rejects superseded 8-bit marker before worker" run_render --text x --out "$TMP/old-marker.wav"
  mv "$TMP/install-bf16.json" "$HOME_DIR/install.json"

  TEXT='Сегодня 10 июля. Qwen должен прочитать этот текст буквально: Gmail, MLX и 3 500 рублей.'
  CAPTURE="$TMP/capture.json"
  KB_TTS_TEST_CAPTURE="$CAPTURE" run_render --text "$TEXT" --out "$TMP/sample.wav"
  RC=$?
  [[ $RC -eq 0 && -s "$TMP/sample.wav" ]] && ok "WAV render is atomic and non-empty" || bad "WAV render failed"
  python3 - "$CAPTURE" "$TEXT" <<'PY' && ok "literal Russian text, pinned model, and offline env reach worker" || bad "worker handoff mutated text/model/env"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["text"] == sys.argv[2]
assert d["language"] == "Russian"
assert d["model_id"] == "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"
assert d["model_revision"] == "7d3824abff87e49756bb0f83fb5411de75d160c4"
assert d["offline_env"] == {
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
PY

  printf '%s' "$TEXT" >"$TMP/input.txt"
  KB_TTS_TEST_CAPTURE="$CAPTURE" run_render --file "$TMP/input.txt" --out "$TMP/sample.mp3"
  [[ $? -eq 0 && -s "$TMP/sample.mp3" ]] && ok "file input produces non-empty MP3" || bad "MP3 render failed"

  KB_TTS_FAKE_MODE=failure run_render --text x --out "$TMP/failure.wav" >/dev/null 2>&1
  [[ $? -ne 0 && ! -e "$TMP/failure.wav" ]] && ok "child failure leaves no final output" || bad "child failure cleanup failed"

  rm -f "$CAPTURE"
  KB_TTS_FFMPEG="$TMP/definitely-missing-ffmpeg" KB_TTS_TEST_CAPTURE="$CAPTURE" \
    run_render --text x --out "$TMP/no-ffmpeg.mp3" >/dev/null 2>&1
  [[ $? -ne 0 && ! -e "$CAPTURE" && ! -e "$TMP/no-ffmpeg.mp3" ]] \
    && ok "missing ffmpeg fails before worker/model input" \
    || bad "ffmpeg preflight happened too late"

  for sig in TERM INT; do
    PIDS="$TMP/pids-$sig"
    KB_TTS_HOME="$HOME_DIR" \
    KB_TTS_PYTHON="$HOME_DIR/venv/bin/python" \
    KB_TTS_WORKER="$FAKE_WORKER" \
    KB_TTS_FAKE_MODE=slow \
    KB_TTS_TEST_PIDS="$PIDS" \
      "$RENDER" --text x --out "$TMP/interrupted-$sig.wav" >/dev/null 2>&1 &
    wrapper=$!
    for _ in {1..100}; do [[ -s "$PIDS" ]] && break; sleep 0.05; done
    if [[ ! -s "$PIDS" ]]; then
      bad "$sig interruption started worker"; kill -KILL "$wrapper" 2>/dev/null || true; wait "$wrapper" 2>/dev/null || true; continue
    fi
    read -r worker grandchild pgid <"$PIDS"
    kill -"$sig" "$wrapper" 2>/dev/null || true
    wait "$wrapper" 2>/dev/null; rc=$?
    sleep 0.1
    alive=0
    kill -0 "$worker" 2>/dev/null && alive=1
    kill -0 "$grandchild" 2>/dev/null && alive=1
    [[ $rc -ne 0 && $alive -eq 0 && ! -e "$TMP/interrupted-$sig.wav" ]] \
      && ok "$sig reaps owned process group and output" \
      || bad "$sig cleanup failed (rc=$rc alive=$alive pgid=$pgid)"
  done

  # A child first observed in the owned group must not survive by calling setsid().
  PIDS="$TMP/pids-escape"
  KB_TTS_HOME="$HOME_DIR" KB_TTS_PYTHON="$HOME_DIR/venv/bin/python" \
  KB_TTS_WORKER="$FAKE_WORKER" KB_TTS_FAKE_MODE=escape KB_TTS_TEST_PIDS="$PIDS" \
    "$RENDER" --text x --out "$TMP/escape.wav" >/dev/null 2>&1
  rc=$?
  read -r _ escaped _ <"$PIDS"
  sleep 0.1
  if kill -0 "$escaped" 2>/dev/null; then alive=1; kill -KILL "$escaped" 2>/dev/null || true; else alive=0; fi
  [[ $rc -ne 0 && $alive -eq 0 && ! -e "$TMP/escape.wav" ]] \
    && ok "observed descendant cannot escape its process group" \
    || bad "escaped descendant survived or render succeeded (rc=$rc alive=$alive)"

  # A pending signal during the launch critical section must be delivered only
  # after the child PID/PGID is captured, so cleanup can reap it.
  KB_TTS_HOME="$HOME_DIR" KB_TTS_PYTHON="$HOME_DIR/venv/bin/python" \
  KB_TTS_WORKER="$FAKE_WORKER" KB_TTS_TEST_PRE_POPEN_DELAY=0.4 \
    "$RENDER" --text x --out "$TMP/launch-race.wav" >/dev/null 2>&1 &
  wrapper=$!
  sleep 0.1; kill -TERM "$wrapper" 2>/dev/null || true
  wait "$wrapper" 2>/dev/null; rc=$?
  [[ $rc -ne 0 && ! -e "$TMP/launch-race.wav" ]] \
    && ok "signal during launch cannot orphan a child" \
    || bad "launch signal race not handled (rc=$rc)"

  # Cleanup itself must be non-reentrant when a second signal arrives.
  PIDS="$TMP/pids-double"
  KB_TTS_HOME="$HOME_DIR" KB_TTS_PYTHON="$HOME_DIR/venv/bin/python" \
  KB_TTS_WORKER="$FAKE_WORKER" KB_TTS_FAKE_MODE=stubborn KB_TTS_TEST_PIDS="$PIDS" \
    "$RENDER" --text x --out "$TMP/double-signal.wav" >/dev/null 2>&1 &
  wrapper=$!
  for _ in {1..100}; do [[ -s "$PIDS" ]] && break; sleep 0.05; done
  read -r worker grandchild _ <"$PIDS"
  kill -TERM "$wrapper" 2>/dev/null || true
  sleep 0.05; kill -INT "$wrapper" 2>/dev/null || true
  wait "$wrapper" 2>/dev/null; rc=$?
  sleep 0.1; alive=0
  kill -0 "$worker" 2>/dev/null && alive=1
  kill -0 "$grandchild" 2>/dev/null && alive=1
  if [[ $alive -ne 0 ]]; then
    kill -KILL -- -"$(awk '{print $3}' "$PIDS")" 2>/dev/null || true
  fi
  [[ $rc -ne 0 && $alive -eq 0 && ! -e "$TMP/double-signal.wav" ]] \
    && ok "repeated signal cannot interrupt cleanup" \
    || bad "cleanup is signal-reentrant (rc=$rc alive=$alive)"

  if find "$TMP" -name '*.kb-tts-*' -print -quit | grep -q .; then
    bad "temporary render files are removed"
  else
    ok "temporary render files are removed"
  fi
else
  for label in \
    "renderer rejects invalid input combinations" \
    "literal Russian text and offline env reach worker" \
    "WAV and MP3 outputs are atomic" \
    "child failure leaves no output" \
    "TERM reaps process group" \
    "INT reaps process group"; do bad "$label (renderer missing)"; done
fi

echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]]
