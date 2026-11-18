"""Desktop «Add project…» on a folder that already has its own AGENTS.md.

The app runs the hub's new-wiki, which keeps the user's text and appends one
marked Vepol block with the startup-context line, so Codex and other agents
load the project's context. Adding the project again never adds a second block.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

STARTUP = '`~/knowledge/bin/kb-session-start --print --cwd "$PWD"`'


def _hub(tmp_path: pathlib.Path) -> pathlib.Path:
    # This repo's new-wiki and template when it carries them, else ~/knowledge's.
    repo = pathlib.Path(__file__).resolve().parents[2]
    kb_root = repo if (repo / "bin" / "new-wiki").is_file() and (repo / "_template").is_dir() \
        else pathlib.Path.home() / "knowledge"
    hub = tmp_path / "knowledge"
    (hub / "bin").mkdir(parents=True)
    (hub / "projects").mkdir()
    (hub / "bin" / "new-wiki").symlink_to(kb_root / "bin" / "new-wiki")
    (hub / "_template").symlink_to(kb_root / "_template")
    return hub


def test_add_project_keeps_own_agents_md_and_adds_the_vepol_block_once(tmp_path):
    from vepol_face.targets import add_project

    hub = _hub(tmp_path)
    folder = tmp_path / "other-app"
    folder.mkdir()
    own = "# Mine\nkeep me\n"
    (folder / "AGENTS.md").write_text(own, encoding="utf-8")

    target, created = add_project(hub, str(folder))
    assert created and target.slug == "other-app"
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith(own)
    assert text.count("<!-- BEGIN VEPOL") == 1 and "<!-- END VEPOL -->" in text
    assert STARTUP in text

    # Picking the project again opens it; the file is not touched a second time.
    _, again = add_project(hub, str(folder))
    assert again is False
    assert (folder / "AGENTS.md").read_text(encoding="utf-8") == text
