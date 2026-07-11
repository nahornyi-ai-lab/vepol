#!/usr/bin/env python3
"""Short-lived offline MLX worker. It is always launched in its own process group."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import mlx.core as mx
import numpy as np
from mlx_audio.audio_io import write as audio_write
from mlx_audio.tts.utils import load_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))

    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        if os.environ.get(key) != "1":
            raise SystemExit(f"offline guard missing: {key}=1")

    model_path = Path(config["model_path"])
    if not model_path.is_dir():
        raise SystemExit(f"pinned local model snapshot is missing: {model_path}")
    text = Path(config["input_path"]).read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit("input text is empty")

    model = load_model(str(model_path))
    results = list(
        model.generate_voice_design(
            text=text,
            language=config["language"],
            instruct=config["voice_instruct"],
        )
    )
    if not results:
        raise SystemExit("model produced no audio")

    sample_rate = int(results[0].sample_rate)
    chunks = [result.audio for result in results]
    audio = chunks[0] if len(chunks) == 1 else mx.concatenate(chunks, axis=0)
    output = Path(config["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.suffix.lower() == ".wav":
        audio_write(str(output), np.array(audio), sample_rate, format="wav")
    else:
        fd, raw_name = tempfile.mkstemp(prefix="qwen-raw-", suffix=".wav", dir=output.parent)
        os.close(fd)
        raw = Path(raw_name)
        try:
            audio_write(str(raw), np.array(audio), sample_rate, format="wav")
            subprocess.run(
                [
                    config["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(raw), "-codec:a", "libmp3lame", "-b:a", "128k", str(output),
                ],
                check=True,
            )
        finally:
            raw.unlink(missing_ok=True)

    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit("model produced an empty audio file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
