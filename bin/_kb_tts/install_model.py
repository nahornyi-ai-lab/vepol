#!/usr/bin/env python3
"""Download and verify the one approved Qwen3-TTS model snapshot."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"
MODEL_REVISION = "7d3824abff87e49756bb0f83fb5411de75d160c4"
EXPECTED = {
    "model.safetensors": "96ae28bec2205ec0b5e0c750bea2b8a5deac4f14d33a8a25a5f753299486b70e",
    "speech_tokenizer/model.safetensors": "836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    args = parser.parse_args()
    args.model_dir.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=str(args.model_dir),
    )

    for relative, expected in EXPECTED.items():
        path = args.model_dir / relative
        if not path.is_file():
            raise SystemExit(f"missing model file: {path}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(
                f"model integrity failure for {relative}: expected {expected}, got {actual}"
            )
        print(f"verified {relative}: sha256:{actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
