"""Thin wrapper around kb-channel-send."""

import subprocess
import shutil
from pathlib import Path


def _find_kb_channel_send() -> str | None:
    return shutil.which("kb-channel-send")


def send(message_type: str, message: str) -> bool:
    """Send a message via Vepol channel layer. Returns True on success."""
    cmd = _find_kb_channel_send()
    if not cmd:
        # Fallback: print to stdout (useful in dev/dry-run)
        print(f"[channel:{message_type}] {message}")
        return False
    try:
        subprocess.run([cmd, message_type, message], check=True, timeout=30)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        print(f"[channel:{message_type}] {message}")
        return False
