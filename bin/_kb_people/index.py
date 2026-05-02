"""UUID identity map — people/_index.yaml operations."""

import os
import uuid
from pathlib import Path

import yaml

INDEX_PATH = Path.home() / "knowledge" / "people" / "_index.yaml"


def _load() -> dict:
    if not INDEX_PATH.exists():
        return {}
    with open(INDEX_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save(data: dict):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    os.replace(tmp, INDEX_PATH)


def lookup_by_email(email: str) -> str | None:
    """Return UUID if email is a known locator."""
    if not email:
        return None
    email = email.lower().strip()
    data = _load()
    for uid, entry in data.items():
        locators = entry.get("locators", {})
        for v in locators.values():
            if isinstance(v, str) and v.lower() == email:
                return uid
    return None


def lookup_by_name(name: str) -> list[tuple[str, float]]:
    """Return [(uuid, jaro_score)] for name fuzzy match."""
    import jellyfish
    name_lower = name.lower()
    data = _load()
    results = []
    for uid, entry in data.items():
        candidates = [entry.get("slug", "").replace("-", " ")] + entry.get("name_variants", [])
        best = max((jellyfish.jaro_winkler_similarity(name_lower, c.lower()) for c in candidates if c), default=0.0)
        if best > 0.4:
            results.append((uid, best))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def register(uid: str, slug: str, name: str, locators: dict):
    """Add or update an entry in _index.yaml."""
    from datetime import date
    data = _load()
    entry = data.get(uid, {})
    entry["slug"] = slug
    entry.setdefault("name_variants", [])
    if name and name not in entry["name_variants"]:
        entry["name_variants"].append(name)
    existing_locators = entry.get("locators", {})
    existing_locators.update({k: v for k, v in locators.items() if v})
    entry["locators"] = existing_locators
    entry.setdefault("created_at", date.today().isoformat())
    data[uid] = entry
    _save(data)


def get_slug(uid: str) -> str | None:
    data = _load()
    return data.get(uid, {}).get("slug")


def remove(uid: str) -> bool:
    """Remove a UUID's entry from _index.yaml. Returns True if removed."""
    data = _load()
    if uid not in data:
        return False
    del data[uid]
    _save(data)
    return True


def new_uuid() -> str:
    return str(uuid.uuid4())
