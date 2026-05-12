"""Agent registry — load per-project .orchestration.yaml into in-memory dict.

Concept §7.1: hub-level derived `~/knowledge/.orchestrator/agents.yaml` собирается
из per-project `.orchestration.yaml`. Editable per-project: `parent_slug`, `bot_*`,
`persona`, `topics`, `allowed_users`. Derived: `children_slugs` (computed from
inverse parent_slug relationship).

Loader is read-only — does not write the derived agents.yaml file. That's the job
of `kb-rebuild-registry --agents` subcommand (see kb-rebuild-registry script).

This module is the runtime-side: supervisor at startup walks `~/knowledge/projects/*/
knowledge/.orchestration.yaml` and builds AgentRegistry in memory.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclasses.dataclass(frozen=True)
class AgentSpec:
    """One agent's runtime spec — frozen, immutable post-load.

    Mirrors fields in `.orchestration.yaml` `telegram:` block plus inherited
    project fields. Children populated by `AgentRegistry._link_children`.
    """

    slug: str
    bot_id: int | None  # parsed from token prefix `12345:ABC...` or null pre-creation
    bot_username: str | None  # without @
    bot_token_ref: str  # path to ~/.claude/channels/bots/<slug>.env
    workdir: str  # absolute path to project root
    runtime: str  # "claude" | "codex"
    parent_slug: str | None
    children_slugs: tuple[str, ...] = ()
    persona: str = ""
    topics: tuple[str, ...] = ()
    allowed_users: tuple[str | int, ...] = ("*",)  # "*" wildcard or list of user_ids
    cooldown_sec: int = 30
    watchdog_silence_sec: int = 900
    task_timeout_sec: int | None = None  # off by default
    warm_session: bool = False
    enabled: bool = True

    def allows_user(self, user_id: int) -> bool:
        """Check if a Telegram user_id is allowed to trigger this agent.

        `["*"]` (default) — all-access in closed group.
        Otherwise — exact match against user_ids in allowed_users.
        """
        if "*" in self.allowed_users:
            return True
        return user_id in self.allowed_users


class AgentRegistry:
    """In-memory registry of all agents, keyed by slug.

    Built once at supervisor startup by walking projects. Read-only at runtime
    (would need re-load on config change, atomic flow).
    """

    def __init__(self, agents: dict[str, AgentSpec]):
        self._by_slug: dict[str, AgentSpec] = dict(agents)
        # Secondary index for fast mention-to-slug lookup. Bot usernames are
        # case-insensitive on Telegram side, so we normalize to lowercase here
        # to match mention.extract_mentions output.
        self._by_username: dict[str, str] = {
            spec.bot_username.lower(): slug
            for slug, spec in agents.items()
            if spec.bot_username
        }

    def get(self, slug: str) -> AgentSpec | None:
        return self._by_slug.get(slug)

    def by_username(self, username: str) -> AgentSpec | None:
        """Lookup by bot @username (no leading @, lowercase or any case)."""
        slug = self._by_username.get(username.lower())
        return self._by_slug.get(slug) if slug else None

    def known_bot_usernames(self) -> set[str]:
        """All known bot usernames lowercased — for `mention.filter_bot_mentions`."""
        return set(self._by_username.keys())

    def enabled_agents(self) -> list[AgentSpec]:
        return [a for a in self._by_slug.values() if a.enabled]

    def all_agents(self) -> list[AgentSpec]:
        return list(self._by_slug.values())

    def children_of(self, slug: str) -> list[AgentSpec]:
        spec = self.get(slug)
        if not spec:
            return []
        return [self._by_slug[s] for s in spec.children_slugs if s in self._by_slug]

    def root_agents(self) -> list[AgentSpec]:
        """Agents with parent_slug=null."""
        return [a for a in self._by_slug.values() if a.parent_slug is None]


    def by_username_or_none_from_chat_id(self, chat_id: int) -> AgentSpec | None:
        """Lookup an agent by its bot user-account id (Telegram numeric id).

        Used for DM routing: a private chat's chat_id equals the user_id of
        the other party, so when chat_id matches a known bot, we can find
        that bot's AgentSpec without an extra lookup table.
        """
        for spec in self._by_slug.values():
            if spec.bot_id == chat_id:
                return spec
        return None

    def __len__(self) -> int:
        return len(self._by_slug)

    def __contains__(self, slug: str) -> bool:
        return slug in self._by_slug


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping at top level, got {type(data).__name__}")
    return data


def _parse_bot_id(token_ref: str) -> int | None:
    """Extract numeric bot_id from BotFather token prefix `12345:ABC...`.

    Reads the env file if it exists; returns None pre-creation (when token_ref
    points to a path that does not yet exist — agent registered but not yet
    created in BotFather).
    """
    path = Path(os.path.expanduser(token_ref))
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    _, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    if ":" in val:
                        prefix = val.split(":", 1)[0]
                        if prefix.isdigit():
                            return int(prefix)
    except OSError:
        return None
    return None


def _spec_from_yaml(
    slug: str, workdir: str, orch_yaml: dict[str, Any]
) -> AgentSpec | None:
    """Build AgentSpec from one .orchestration.yaml file content.

    Returns None if `telegram:` block missing or `bot_username` unset — that
    agent project hasn't been onboarded for multibot yet (no bot in BotFather).
    """
    tg = orch_yaml.get("telegram") or {}
    if not tg:
        return None
    bot_username = tg.get("bot_username")
    if not bot_username:
        return None

    # Strip leading @ if present, normalize case for storage (lowercase).
    bot_username = bot_username.lstrip("@").lower()

    token_ref = tg.get("bot_token_ref", "")
    bot_id = _parse_bot_id(token_ref) if token_ref else None

    parent_slug = tg.get("parent_slug")
    if parent_slug == "" or parent_slug == "null":
        parent_slug = None

    topics_raw = tg.get("topics") or orch_yaml.get("topics") or []
    allowed_users_raw = tg.get("allowed_users") or ["*"]

    runtime = tg.get("runtime", "claude")
    if runtime not in {"claude", "codex"}:
        raise ValueError(
            f"{slug}: runtime must be 'claude' or 'codex', got {runtime!r}"
        )

    return AgentSpec(
        slug=slug,
        bot_id=bot_id,
        bot_username=bot_username,
        bot_token_ref=token_ref,
        workdir=workdir,
        runtime=runtime,
        parent_slug=parent_slug,
        children_slugs=(),  # filled by _link_children
        persona=tg.get("persona", ""),
        topics=tuple(topics_raw),
        allowed_users=tuple(allowed_users_raw),
        cooldown_sec=int(tg.get("cooldown_sec", 30)),
        watchdog_silence_sec=int(tg.get("watchdog_silence_sec", 900)),
        task_timeout_sec=tg.get("task_timeout_sec"),  # may be None
        warm_session=bool(tg.get("warm_session", False)),
        enabled=bool(tg.get("enabled", True)),
    )


def _link_children(agents: dict[str, AgentSpec]) -> dict[str, AgentSpec]:
    """Compute children_slugs (inverse of parent_slug) and return updated registry.

    Since AgentSpec is frozen, we replace with copies carrying children_slugs.
    """
    inverse: dict[str, list[str]] = {}
    for spec in agents.values():
        if spec.parent_slug:
            inverse.setdefault(spec.parent_slug, []).append(spec.slug)
    # Deterministic order — slug sorted, for stable prompts and tests.
    return {
        slug: dataclasses.replace(spec, children_slugs=tuple(sorted(inverse.get(slug, []))))
        for slug, spec in agents.items()
    }


def load_from_projects_dir(projects_dir: str | Path) -> AgentRegistry:
    """Walk `~/knowledge/projects/*/` and build registry from .orchestration.yaml's.

    `~/knowledge/projects/<slug>` is a symlink to `<project>/knowledge/` per
    existing kb-rebuild-registry convention. So we look for
    `<projects_dir>/<slug>/.orchestration.yaml` directly.

    Also loads hub itself from `<projects_dir>/../`. Hub is the orchestrator
    root — its workdir IS the knowledge hub, with `.orchestration.yaml` at
    the top level (not under projects/). See concept §7.1.
    """
    base = Path(projects_dir)
    if not base.is_dir():
        return AgentRegistry({})

    agents: dict[str, AgentSpec] = {}

    # Hub — special case, sits at projects_dir.parent
    hub_root = base.parent
    hub_yaml = hub_root / ".orchestration.yaml"
    if hub_yaml.is_file():
        try:
            orch = _read_yaml(hub_yaml)
            spec = _spec_from_yaml("hub", str(hub_root), orch)
            if spec:
                agents["hub"] = spec
        except (OSError, yaml.YAMLError, ValueError):
            pass

    # Regular projects under projects/
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() and not entry.is_symlink():
            continue
        orch_path = entry / ".orchestration.yaml"
        if not orch_path.is_file():
            continue
        try:
            orch = _read_yaml(orch_path)
        except (OSError, yaml.YAMLError, ValueError):
            continue
        try:
            knowledge_dir = entry.resolve(strict=True)
            workdir = str(knowledge_dir.parent)
        except (OSError, RuntimeError):
            continue
        spec = _spec_from_yaml(entry.name, workdir, orch)
        if spec:
            agents[entry.name] = spec

    agents = _link_children(agents)
    return AgentRegistry(agents)


def load_from_specs(specs: Iterable[AgentSpec]) -> AgentRegistry:
    """Convenience constructor from a list of AgentSpec — used by tests."""
    by_slug = {s.slug: s for s in specs}
    by_slug = _link_children(by_slug)
    return AgentRegistry(by_slug)


__all__ = [
    "AgentSpec",
    "AgentRegistry",
    "load_from_projects_dir",
    "load_from_specs",
]
