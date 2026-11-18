"""Shared production resolver for the Codex CLI.

Lookup order (the first executable hit wins):

1. ``$KB_CODEX_BIN`` — an explicit override. When it is set it is the only
   candidate: a missing or non-executable override makes Codex unavailable
   instead of quietly running some other copy, so an owner (or a test) can
   pin or switch off Codex deterministically.
2. ``$HOME/.local/bin/codex`` — where the official standalone installer puts it.
3. ``codex`` on ``PATH``.
4. ``/opt/homebrew/bin/codex`` and ``/usr/local/bin/codex`` — Homebrew and npm
   global installs. Scheduled jobs run under launchd, whose PATH may lack them.

Copies found through steps 3-4 that live inside a macOS app bundle (for example
``/Applications/Codex.app/Contents/Resources/codex``) are skipped: the app
replaces that file when it auto-updates, which used to pull the launcher out
from under running jobs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

# Fixed fallbacks after PATH (Homebrew on Apple silicon, then Intel/npm prefix).
SYSTEM_CANDIDATES: tuple[str, ...] = ("/opt/homebrew/bin/codex", "/usr/local/bin/codex")


class CodexUnavailable(RuntimeError):
    """No usable Codex executable was found.

    ``path`` is the override when ``KB_CODEX_BIN`` is set, otherwise the
    standalone location ``$HOME/.local/bin/codex``.
    """

    def __init__(self, path: Path, searched: tuple[str, ...] = ()):
        self.path = path
        self.searched = searched
        message = f"Codex executable unavailable: {path}"
        if searched:
            message += f" (also looked in: {', '.join(searched)})"
        super().__init__(message)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _inside_app_bundle(path: Path) -> bool:
    return any(part.endswith(".app") for part in path.parts)


def codex_bin(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> str:
    """Return the resolved path of the Codex CLI to launch.

    Raises ``CodexUnavailable`` when nothing usable is found. With an explicit
    ``env`` mapping that has no ``PATH`` key, PATH is not searched.
    """

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
        candidate = candidate.resolve(strict=False)
        if not _is_executable(candidate):
            raise CodexUnavailable(candidate)
        return str(candidate)

    canonical = (home_path / ".local" / "bin" / "codex").resolve(strict=False)
    if _is_executable(canonical):
        return str(canonical)

    search_path = values.get("PATH")
    if search_path is None and env is None:
        search_path = os.defpath
    discovered: list[Path] = []
    for directory in (search_path or "").split(os.pathsep):
        # A relative PATH entry depends on the caller's cwd; skip it.
        if directory and os.path.isabs(directory):
            discovered.append(Path(directory) / "codex")
    discovered.extend(Path(path) for path in SYSTEM_CANDIDATES)

    for candidate in discovered:
        resolved = candidate.resolve(strict=False)
        if _is_executable(resolved) and not _inside_app_bundle(resolved):
            return str(resolved)
    raise CodexUnavailable(canonical, ("PATH", *SYSTEM_CANDIDATES))
