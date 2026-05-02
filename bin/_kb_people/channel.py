"""Thin wrapper around kb-channel-send.

Works both interactively (kb-channel-send in PATH) and from cron /
LaunchAgent / direct python invocations (where PATH may exclude
$KB_HUB/bin). Lookup order:
  1. shutil.which("kb-channel-send") — PATH lookup.
  2. $KB_HUB/bin/kb-channel-send — Vepol's canonical install location.
  3. ~/knowledge/bin/kb-channel-send — default hub.

If none found, falls back to stdout with a clear `[channel:<type>]`
prefix so callers in dev see what would have been sent.
"""

import os
import shutil
import subprocess
from pathlib import Path


def _find_kb_channel_send() -> str | None:
    found = shutil.which("kb-channel-send")
    if found:
        return found
    candidates = [
        Path(os.environ.get("KB_HUB", "")) / "bin" / "kb-channel-send" if os.environ.get("KB_HUB") else None,
        Path.home() / "knowledge" / "bin" / "kb-channel-send",
    ]
    for cand in candidates:
        if cand and cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


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
