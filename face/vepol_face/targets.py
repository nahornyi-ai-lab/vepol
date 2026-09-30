"""Target discovery from the existing KB. MVP-3.

Targets come from the hub's projects/ symlinks — the same source Obsidian and
kb-search use. No parallel project list is invented here.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass

HUB = pathlib.Path(os.path.expanduser("~/knowledge"))


@dataclass
class Target:
    slug: str
    label: str
    cwd: str
    knowledge: str
    kind: str  # hub | project

    def as_dict(self) -> dict:
        return {
            "slug": self.slug, "label": self.label, "cwd": self.cwd,
            "knowledge": self.knowledge, "kind": self.kind,
        }


def discover_targets(hub: pathlib.Path | None = None) -> list[Target]:
    hub = pathlib.Path(hub or HUB)
    targets = [
        Target(
            slug="hub", label="Vepol hub",
            cwd=str(hub.parent), knowledge=str(hub), kind="hub",
        )
    ]

    projects = hub / "projects"
    if not projects.is_dir():
        return targets

    for entry in sorted(projects.iterdir()):
        try:
            resolved = entry.resolve(strict=True)
        except (OSError, RuntimeError):
            continue  # broken symlink — skip, never crash discovery
        if not resolved.is_dir():
            continue
        targets.append(
            Target(
                slug=entry.name,
                label=entry.name,
                cwd=str(resolved.parent),
                knowledge=str(resolved),
                kind="project",
            )
        )
    return targets


def _parse(at: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(at) if at else None
    except ValueError:
        return None


def with_last_active(targets: list[Target], conversations: list[dict]) -> list[dict]:
    """Targets as dicts with last_active, newest first.

    Last activity = the newest of the target's conversations in the app and the
    modification time of its knowledge/log.md (session capture writes there).
    """
    latest: dict[str, dt.datetime] = {}
    for conv in conversations:
        at = _parse(conv.get("last_activity_at"))
        if at and (conv["target"] not in latest or at > latest[conv["target"]]):
            latest[conv["target"]] = at
    rows = []
    for t in targets:
        found = [latest[t.slug]] if t.slug in latest else []
        try:
            mtime = (pathlib.Path(t.knowledge) / "log.md").stat().st_mtime
            found.append(dt.datetime.fromtimestamp(mtime, dt.timezone.utc))
        except OSError:
            pass
        rows.append({**t.as_dict(), "last_active": max(found).isoformat() if found else None})
    # Newest first (a stable sort): targets with no activity keep discovery order at the end.
    rows.sort(key=lambda r: _parse(r["last_active"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
              reverse=True)
    return rows


class ProjectRefused(ValueError):
    """The chosen folder cannot become a project; the message says why."""


NEW_WIKI_TIMEOUT = 60


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def add_project(hub: pathlib.Path, path: str) -> tuple[Target, bool]:
    """Register a folder as a project with the hub's own new-wiki. Returns (target, created)."""
    hub = pathlib.Path(hub)
    raw = pathlib.Path(str(path or "").strip()).expanduser()
    if not raw.is_absolute():
        raise ProjectRefused("the folder path must be absolute")
    if not raw.is_dir():
        raise ProjectRefused(f"no such folder: {raw}")
    folder = raw.resolve()
    if folder.name == "knowledge" and folder.parent != folder:
        folder = folder.parent  # the wiki folder was picked; the project is its parent
    home = pathlib.Path.home().resolve()
    hub_real = hub.resolve()
    if folder in (home, pathlib.Path("/"), hub_real) or hub_real in folder.parents:
        raise ProjectRefused("pick a project folder, not the home folder or the hub")

    knowledge = folder / "knowledge"
    if knowledge.exists():
        for t in discover_targets(hub):
            if t.kind == "project" and pathlib.Path(t.knowledge) == knowledge.resolve():
                return t, False

    base = _slug(folder.name)
    slug, n = base, 1
    while slug == "hub" or os.path.lexists(hub / "projects" / slug):
        n += 1
        slug = f"{base}-{n}"
    new_wiki = hub / "bin" / "new-wiki"
    if not new_wiki.is_file():
        raise RuntimeError(f"new-wiki not found: {new_wiki}")
    try:
        proc = subprocess.run([str(new_wiki), str(folder), slug], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=NEW_WIKI_TIMEOUT,
                              env={**os.environ, "KNOWLEDGE_HUB": str(hub)})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"new-wiki did not finish: {exc}") from exc
    if proc.returncode != 0:
        lines = [line for line in proc.stderr.splitlines() if line.strip()]
        raise RuntimeError(lines[-1].strip() if lines else f"new-wiki exited {proc.returncode}")
    for t in discover_targets(hub):
        if t.slug == slug and pathlib.Path(t.knowledge) == knowledge.resolve():
            return t, True
    raise RuntimeError(f"new-wiki finished but projects/{slug} does not point at {knowledge}")
