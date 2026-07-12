"""Single production resolver for the standalone Codex CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


class CodexUnavailable(RuntimeError):
    """The one configured Codex executable is missing or not executable."""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"Codex executable unavailable: {path}")


def codex_bin(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> str:
    """Return validated ``KB_CODEX_BIN`` or exactly ``$HOME/.local/bin/codex``."""

    values = os.environ if env is None else env
    home_path = Path(home) if home is not None else Path.home()
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    configured = values.get("KB_CODEX_BIN", "").strip()

    if configured:
        if configured == "~":
            candidate = home_path
        elif configured.startswith("~/"):
            candidate = home_path / configured[2:]
        else:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = cwd_path / candidate
    else:
        candidate = home_path / ".local" / "bin" / "codex"

    candidate = candidate.resolve(strict=False)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise CodexUnavailable(candidate)
    return str(candidate)
