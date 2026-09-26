"""Read-only view of a target's knowledge/ folder for the Knowledge panel.

Targets come from targets.discover_targets(hub); nothing here writes, renders or
executes anything. Symlinks are listed as the dir/file they point to but never
walked into, and a file read is confined to the realpath of the target's
knowledge root (so a link that escapes it lists but cannot be opened).
"""
from __future__ import annotations

import os
import pathlib
import stat

from . import targets as targets_mod

MAX_DEPTH = 4
MAX_ENTRIES = 2000
MAX_FILE_BYTES = 512 * 1024


class FileTooLarge(Exception):
    """The file exists inside the root but is over MAX_FILE_BYTES (HTTP 413)."""


def _root(hub: pathlib.Path, target_slug: str) -> str:
    for target in targets_mod.discover_targets(hub=hub):
        if target.slug == target_slug:
            return target.knowledge
    raise KeyError(target_slug)


def knowledge_tree(hub: pathlib.Path, target_slug: str) -> dict:
    """Entries under the target's knowledge root, depth-first, dirs before files."""
    root = _root(hub, target_slug)
    entries: list[dict] = []
    truncated = False

    def walk(directory: str, rel: str, depth: int) -> None:
        nonlocal truncated
        try:
            with os.scandir(directory) as it:
                children = [c for c in it if not c.name.startswith(".")]
        except OSError:
            return
        children.sort(key=lambda c: (not c.is_dir(), c.name.lower()))
        for child in children:
            if len(entries) >= MAX_ENTRIES:
                truncated = True
                return
            path = f"{rel}/{child.name}" if rel else child.name
            try:
                info = child.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode):
                # Classify a symlink by its target, but never walk into it.
                try:
                    info = os.stat(child.path)
                except OSError:
                    continue
                is_link = True
            else:
                is_link = False
            if stat.S_ISDIR(info.st_mode):
                kind = "dir"
            elif stat.S_ISREG(info.st_mode):
                kind = "file"
            else:
                continue
            entries.append({"path": path, "name": child.name, "kind": kind,
                            "size": info.st_size if kind == "file" else None})
            if kind == "dir" and not is_link and depth < MAX_DEPTH:
                walk(child.path, path, depth + 1)
                if truncated:
                    return

    walk(root, "", 1)
    return {"target": target_slug, "entries": entries, "truncated": truncated}


def knowledge_file(hub: pathlib.Path, target_slug: str, rel_path: str) -> dict:
    """Text of one regular file inside the root.

    KeyError: unknown target. FileNotFoundError: empty/escaping path or not a
    regular file. FileTooLarge: over MAX_FILE_BYTES.
    """
    root = _root(hub, target_slug)
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise FileNotFoundError(rel_path)
    try:
        real_root = os.path.realpath(root)
        real = os.path.realpath(os.path.join(real_root, rel_path))
        if real == real_root or os.path.commonpath([real_root, real]) != real_root:
            raise FileNotFoundError(rel_path)
        info = os.stat(real)
    except (OSError, ValueError) as exc:
        raise FileNotFoundError(rel_path) from exc
    if not stat.S_ISREG(info.st_mode):
        raise FileNotFoundError(rel_path)
    if info.st_size > MAX_FILE_BYTES:
        raise FileTooLarge(rel_path)
    try:
        with open(real, "rb") as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise FileNotFoundError(rel_path) from exc
    if len(raw) > MAX_FILE_BYTES:
        raise FileTooLarge(rel_path)
    return {"target": target_slug, "path": rel_path, "size": len(raw),
            "text": raw.decode("utf-8", errors="replace")}
