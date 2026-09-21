"""Target discovery from the existing KB. MVP-3.

Targets come from the hub's projects/ symlinks — the same source Obsidian and
kb-search use. No parallel project list is invented here.
"""
from __future__ import annotations

import os
import pathlib
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
            slug="hub", label="Vepol (hub orchestrator)",
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
