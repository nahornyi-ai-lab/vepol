#!/usr/bin/env python3
"""Download and verify the one approved Qwen3-TTS model snapshot."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
MODEL_REVISION = "f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee"
EXPECTED = {
    "model.safetensors": "1a84179d87c972353ccdd9b48f3c4422509b3d1b11030d32358312fb0f3800d7",
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
