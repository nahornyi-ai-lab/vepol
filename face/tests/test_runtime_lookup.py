"""Desktop agent list: Claude and Codex are found where the hub scripts look.

The hub scripts look for codex in $KB_CODEX_BIN, ~/.local/bin, PATH, then
/opt/homebrew/bin and /usr/local/bin, and for claude on PATH, in ~/.local/bin,
then the same two folders. The Desktop must not hide an agent that the
scripts would run.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

REPO = pathlib.Path(__file__).resolve().parents[2]
NOW = "2026-08-15T23:00:00+00:00"


def _fake(path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def _load(tmp_path, roster_text: str):
    from vepol_face.runtimes import load_runtimes

    roster = tmp_path / "cli-tools.tsv"
    roster.write_text(roster_text)
    return load_runtimes(broker_state=tmp_path / "no-state.json", roster=roster, now=NOW)


def _sandbox(tmp_path, monkeypatch, path_dirs: list[pathlib.Path]) -> pathlib.Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", ":".join(str(d) for d in path_dirs) or "/nonexistent")
    return home


def test_shipped_roster_finds_codex_that_is_only_on_path(tmp_path, monkeypatch):
    brew = tmp_path / "brewbin"
    _fake(brew / "codex")
    _sandbox(tmp_path, monkeypatch, [brew])

    out = _load(tmp_path, (REPO / "bin" / "cli-tools.tsv").read_text())

    assert out["codex"].installed is True
    assert out["codex"].state != "missing"
    assert out["codex"].capabilities.get("interactive") is True


def test_shipped_roster_finds_claude_in_local_bin_without_path(tmp_path, monkeypatch):
    home = _sandbox(tmp_path, monkeypatch, [])
    _fake(home / ".local" / "bin" / "claude")

    out = _load(tmp_path, (REPO / "bin" / "cli-tools.tsv").read_text())

    assert out["claude"].installed is True


def test_older_hub_roster_still_finds_codex_on_path(tmp_path, monkeypatch):
    """install.sh never overwrites the hub roster, so its codex row may list only ~/.local/bin."""
    brew = tmp_path / "brewbin"
    _fake(brew / "codex")
    _sandbox(tmp_path, monkeypatch, [brew])

    out = _load(tmp_path, "codex | path-any | $HOME/.local/bin/codex | review\n"
                          "agy   | path-any | $HOME/.local/bin/agy   | third pass\n")

    assert out["codex"].installed is True
    # Only claude and codex get the scripts' fallbacks; other rows are read as written.
    assert out["agy"].installed is False and out["agy"].state == "missing"
