#!/usr/bin/env python3
"""kb_entity_apply.py — Stage 3 apply library + CLI.

Reads `<hub>/.orchestrator/cycle-<date>.json:results`, parses the
`### Entity / asset deltas` section of each non-archived done report,
upserts entities into hub-managed pages (`personal/assets.md`,
`people/<slug>.md`, `companies/<slug>.md`), and writes an audit JSON.

CLI:

    kb_entity_apply.py apply --hub <hub> --date YYYY-MM-DD

Feature flag: KB_ENTITY_ROLLUP=1 (default OFF → no-op exit 0).

Spec: ~/knowledge/concepts/entity-extraction-cycle-pass.md (v2 approved).
Tests: ~/knowledge/tests/entity-extraction/run-all.sh
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

CATEGORIES = {"publish", "account", "subscription", "person", "company", "asset"}
ACTIONS = {
    "created", "updated", "renamed",
    "deprecated", "cancelled", "closed", "transferred", "deleted",
}
ACTIVE_ACTIONS = {"created", "updated", "renamed"}
INACTIVE_ACTIONS = {"deprecated", "cancelled", "closed", "transferred", "deleted"}

ACTION_TO_STATUS = {
    "created": "active",
    "updated": "active",
    "renamed": "active",
    "deprecated": "deprecated",
    "cancelled": "cancelled",
    "closed": "closed",
    "transferred": "transferred",
    "deleted": "deleted",
}

ASSETS_CATS = {"account", "publish", "subscription", "asset"}
PEOPLE_CAT = "person"
COMPANY_CAT = "company"

# Page-group scoping (People Notebook spec D7): the rollup can be
# restricted to target page groups so `person` events never bypass the
# People Notebook staging layer with direct people/ writes.
PAGE_GROUPS = {
    "people": {PEOPLE_CAT},
    "companies": {COMPANY_CAT},
    "assets": set(ASSETS_CATS),
}


def resolve_categories(spec: str | None) -> set:
    """Map a `--categories` value (comma list of page-group names) to the
    internal category set. None/empty → all categories (legacy behavior).
    Unknown tokens raise ValueError — fail fast, apply nothing."""
    if not spec:
        return set(CATEGORIES)
    out: set = set()
    for tok in spec.split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok not in PAGE_GROUPS:
            raise ValueError(
                f"unknown --categories token {tok!r} "
                f"(allowed: {sorted(PAGE_GROUPS)})")
        out |= PAGE_GROUPS[tok]
    if not out:
        raise ValueError("--categories resolved to an empty set")
    return out

ASSETS_BEGIN = "<!-- ASSETS-DERIVED-BEGIN -->"
ASSETS_END = "<!-- ASSETS-DERIVED-END -->"
SIGHTINGS_BEGIN = "<!-- SIGHTINGS-DERIVED-BEGIN -->"
SIGHTINGS_END = "<!-- SIGHTINGS-DERIVED-END -->"

# Secret blocklist (description redacted → counted malformed)
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+\S{20,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+-----"),
    re.compile(r"\b[A-Za-z0-9+/]{60,}={0,2}\b"),  # long base64
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # generic API key shape
]

# Bullet pattern: `- [cat:action] slug: description [→ provider:ref] @ source: ...`
# Leading whitespace tolerated (textwrap.dedent partial-failure resilience).
BULLET_RE = re.compile(r"^\s*- \[([^:\]\s]+):([^\]\s]+)\]\s*(.*)$")

# Log line prefix: `## [YYYY-MM-DD] <cat> | <action> | <project_slug> | <body>`
LOG_PREFIX_RE = re.compile(
    r"^\s*##\s*\[(\d{4}-\d{2}-\d{2})\]\s+"
    r"(publish|account|subscription|person|company|asset)\s*\|\s*"
    r"([a-z]+)\s*\|\s*([^|]+?)\s*\|\s*(.+)$"
)

DELTAS_HEADING_RE = re.compile(
    r"^\s*###\s*Entity\s*/\s*asset\s*deltas", re.IGNORECASE
)

NEXT_HEADING_RE = re.compile(r"^\s*##\s+\S")
NEXT_H3_RE = re.compile(r"^\s*###\s+\S")


# ----------------------------------------------------------------------------
# Hashing / identity
# ----------------------------------------------------------------------------

def _sha(parts: list) -> str:
    h = hashlib.sha256("".join(p or "" for p in parts).encode("utf-8"))
    return h.hexdigest()[:16]


def compute_entity_id(category: str, provider: str | None, external_ref: str | None,
                      project_slug: str, source_path: str, slug: str) -> tuple[str, str]:
    """Return (entity_id, kind) where kind ∈ {'preferred', 'fallback'}."""
    if provider and external_ref:
        return "p:" + _sha([category, provider, external_ref]), "preferred"
    return "f:" + _sha([category, project_slug, source_path, slug]), "fallback"


def compute_event_id(report_id: str, line_no: int) -> str:
    return _sha([report_id, str(line_no)])


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

def has_secret(text: str) -> bool:
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Cheap YAML frontmatter parser: only string scalars, no nesting."""
    fm: dict = {}
    if not text.startswith("---"):
        return fm, text
    end = text.find("\n---", 3)
    if end < 0:
        return fm, text
    block = text[3:end].strip("\n")
    body_start = end + len("\n---")
    if text[body_start:body_start + 1] == "\n":
        body_start += 1
    for line in block.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                items = [x.strip().strip("'\"") for x in inner.split(",")]
                fm[key] = [x for x in items if x]
        else:
            fm[key] = val.strip("'\"")
    return fm, text[body_start:]


def extract_deltas_section(report_text: str) -> list[tuple[int, str]]:
    """Return list of (line_no_in_report, raw_line) within the Entity / asset deltas section."""
    lines = report_text.splitlines()
    in_section = False
    out = []
    for i, line in enumerate(lines, 1):
        if not in_section:
            if DELTAS_HEADING_RE.match(line):
                in_section = True
            continue
        # Stop on next H2 heading or H3 heading other than our own
        if NEXT_HEADING_RE.match(line):
            break
        if NEXT_H3_RE.match(line) and not DELTAS_HEADING_RE.match(line):
            break
        out.append((i, line))
    return out


def parse_bullet_line(raw: str, line_no: int) -> dict | None:
    """Return event dict or {'malformed': True, 'reason': str} or None for blank."""
    text = raw.rstrip()
    if not text.strip():
        return None
    if text.strip() == "(none)":
        return None
    if not text.lstrip().startswith("- "):
        # Non-bullet noise lines inside deltas section are ignored unless
        # they look like a malformed bullet attempt. Be conservative:
        # only treat lines starting with `- ` as candidates.
        return None
    m = BULLET_RE.match(text)
    if not m:
        return {"malformed": True, "reason": "bullet-format", "line_no": line_no, "raw": text}
    category, action, rest = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    if category not in CATEGORIES or action not in ACTIONS:
        return {"malformed": True, "reason": "bad-category-or-action", "line_no": line_no, "raw": text}

    # Split off "@ source: ..." (rightmost occurrence)
    src_idx = rest.rfind(" @ source:")
    if src_idx < 0:
        # Allow missing source — not strictly malformed; treat as malformed for now
        # because the convention requires it. Tests use it everywhere.
        return {"malformed": True, "reason": "missing-source", "line_no": line_no, "raw": text}
    head = rest[:src_idx].strip()
    source_str = rest[src_idx + len(" @ source:"):].strip()

    # Split slug: description from head
    slug_match = re.match(r"^([^:]+?):\s*(.*)$", head)
    if not slug_match:
        return {"malformed": True, "reason": "missing-slug-colon", "line_no": line_no, "raw": text}
    slug = slug_match.group(1).strip()
    body = slug_match.group(2).strip()

    # Optional "→ provider:external_ref" — take the LAST arrow.
    arrow_idx = body.rfind("→")
    provider = None
    external_ref = None
    description = body
    if arrow_idx >= 0:
        target = body[arrow_idx + len("→"):].strip()
        before = body[:arrow_idx].strip()
        if ":" in target:
            p, _, r = target.partition(":")
            provider = p.strip() or None
            external_ref = r.strip() or None
            description = before

    # Secret blocklist on description
    if has_secret(description):
        return {"malformed": True, "reason": "secret-blocked", "line_no": line_no,
                "raw": "<redacted>"}

    return {
        "category": category,
        "action": action,
        "slug": slug,
        "description": description,
        "provider": provider,
        "external_ref": external_ref,
        "source_str": source_str,
        "line_no": line_no,
    }


# ----------------------------------------------------------------------------
# State store
# ----------------------------------------------------------------------------

def store_path(hub: Path) -> Path:
    return hub / ".orchestrator" / "entity-store.json"


def load_store(hub: Path) -> dict:
    p = store_path(hub)
    if not p.is_file():
        return {"entities": {}, "events_seen": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("entities", {})
        data.setdefault("events_seen", [])
        return data
    except Exception:
        return {"entities": {}, "events_seen": []}


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def save_store(hub: Path, store: dict) -> None:
    atomic_write_text(store_path(hub), json.dumps(store, indent=2, ensure_ascii=False, sort_keys=True))


# ----------------------------------------------------------------------------
# Apply logic
# ----------------------------------------------------------------------------

def _new_entity(eid: str, eid_kind: str, ev: dict, project_slug: str, date: str,
                source_path: str, report_id: str) -> dict:
    return {
        "entity_id": eid,
        "entity_id_kind": eid_kind,
        "category": ev["category"],
        "provider": ev.get("provider"),
        "external_ref": ev.get("external_ref"),
        "slug": ev["slug"],
        "status": ACTION_TO_STATUS[ev["action"]],
        "first_seen": date,
        "last_seen": date,
        "source_refs": [{
            "project": project_slug,
            "report_id": report_id,
            "source_path": source_path,
            "log_line": ev["source_str"],
            "line_no": ev["line_no"],
        }],
        "aliases": [],
        "payload": {"description": ev.get("description", "")},
    }


def _absorb_fallback(store: dict, fallback_id: str, new_id: str, ev: dict) -> dict | None:
    """Promote fallback entity to preferred id; merge metadata."""
    if fallback_id not in store["entities"]:
        return None
    old = store["entities"].pop(fallback_id)
    old["entity_id"] = new_id
    old["entity_id_kind"] = "preferred"
    if ev.get("provider"):
        old["provider"] = ev["provider"]
    if ev.get("external_ref"):
        old["external_ref"] = ev["external_ref"]
    if old["slug"] and old["slug"] not in old["aliases"] and old["slug"] != ev["slug"]:
        old["aliases"].append(old["slug"])
    return old


def _find_fallback_match(store: dict, category: str, slug: str, project_slug: str) -> str | None:
    """Locate an existing fallback-only entity matching same (category, project, slug)."""
    for eid, ent in store["entities"].items():
        if ent.get("entity_id_kind") != "fallback":
            continue
        if ent.get("category") != category:
            continue
        if ent.get("slug") != slug:
            continue
        # source_refs[0].project == project_slug to avoid cross-project collision
        srefs = ent.get("source_refs") or []
        if srefs and srefs[0].get("project") == project_slug:
            return eid
    return None


def apply_event(store: dict, ev: dict, *, project_slug: str, date: str,
                source_path: str, report_id: str, counts: dict,
                touched: set) -> None:
    """Mutate `store` in place; bump `counts`. Track entity_ids in `touched`."""
    eid, kind = compute_entity_id(
        ev["category"], ev.get("provider"), ev.get("external_ref"),
        project_slug, source_path, ev["slug"],
    )
    event_id = compute_event_id(report_id, ev["line_no"])

    # Replay dedupe
    if event_id in store["events_seen"]:
        counts["skipped_duplicate"] += 1
        return

    existing = store["entities"].get(eid)

    # Preferred event may absorb a fallback row
    if existing is None and kind == "preferred":
        fb = _find_fallback_match(store, ev["category"], ev["slug"], project_slug)
        if fb:
            absorbed = _absorb_fallback(store, fb, eid, ev)
            if absorbed is not None:
                store["entities"][eid] = absorbed
                existing = absorbed
                _mutate_existing(existing, ev, project_slug, date, source_path, report_id)
                counts["updated"] += 1
                counts["merged"] = counts.get("merged", 0) + 1
                store["events_seen"].append(event_id)
                touched.add(eid)
                return

    if existing is None:
        ent = _new_entity(eid, kind, ev, project_slug, date, source_path, report_id)
        if ev["action"] in INACTIVE_ACTIONS:
            ent["status"] = ACTION_TO_STATUS[ev["action"]]
            counts["closed_or_inactivated"] += 1
        else:
            counts["created"] += 1
        store["entities"][eid] = ent
        store["events_seen"].append(event_id)
        touched.add(eid)
        return

    # Existing entity
    if ev["action"] == "created":
        existing["last_seen"] = date
        _append_source_ref(existing, project_slug, report_id, source_path, ev)
        counts["skipped_duplicate"] += 1
        store["events_seen"].append(event_id)
        touched.add(eid)
        return

    _mutate_existing(existing, ev, project_slug, date, source_path, report_id)
    if ev["action"] in INACTIVE_ACTIONS:
        counts["closed_or_inactivated"] += 1
    else:
        counts["updated"] += 1
    store["events_seen"].append(event_id)
    touched.add(eid)


def _append_source_ref(ent: dict, project_slug: str, report_id: str,
                       source_path: str, ev: dict) -> None:
    ref = {
        "project": project_slug,
        "report_id": report_id,
        "source_path": source_path,
        "log_line": ev["source_str"],
        "line_no": ev["line_no"],
    }
    # Avoid duplicate refs (same project+report_id pair)
    for r in ent["source_refs"]:
        if r.get("project") == project_slug and r.get("report_id") == report_id:
            return
    ent["source_refs"].append(ref)


def _mutate_existing(ent: dict, ev: dict, project_slug: str, date: str,
                     source_path: str, report_id: str) -> None:
    ent["last_seen"] = date
    ent["status"] = ACTION_TO_STATUS[ev["action"]]
    if ev.get("description"):
        ent["payload"]["description"] = ev["description"]
    if ev.get("provider") and not ent.get("provider"):
        ent["provider"] = ev["provider"]
    if ev.get("external_ref") and not ent.get("external_ref"):
        ent["external_ref"] = ev["external_ref"]
    if ev["action"] == "renamed":
        old_slug = ent.get("slug")
        if old_slug and old_slug != ev["slug"] and old_slug not in ent["aliases"]:
            ent["aliases"].append(old_slug)
        # New handle becomes alias too if we keep canonical = first slug
        if ev["slug"] and ev["slug"] not in ent["aliases"]:
            ent["aliases"].append(ev["slug"])
    _append_source_ref(ent, project_slug, report_id, source_path, ev)


def _audit_row(ent: dict) -> dict:
    return {
        "entity_id": ent["entity_id"],
        "category": ent["category"],
        "provider": ent.get("provider"),
        "external_ref": ent.get("external_ref"),
        "slug": ent["slug"],
        "status": ent["status"],
        "source_refs": [
            {"project": r.get("project"), "report_id": r.get("report_id")}
            for r in ent.get("source_refs", [])
        ],
        "aliases": ent.get("aliases", []),
    }


# ----------------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------------

def _replace_managed_block(text: str, begin: str, end: str, new_inner: str) -> str:
    i = text.find(begin)
    j = text.find(end)
    if i < 0 or j < 0 or j < i:
        # No managed block — append one at end
        return text.rstrip() + "\n\n" + begin + "\n" + new_inner + "\n" + end + "\n"
    return text[:i] + begin + "\n" + new_inner + "\n" + text[j:]


def _render_assets_block(entities: list[dict]) -> str:
    by_status: dict[str, dict[str, list[dict]]] = {"active": {}, "archive": {}}
    for ent in sorted(entities, key=lambda e: (e["category"], e["slug"], e["entity_id"])):
        if ent["category"] not in ASSETS_CATS:
            continue
        bucket = "active" if ent["status"] == "active" else "archive"
        by_status[bucket].setdefault(ent["category"], []).append(ent)

    def format_row(ent: dict) -> str:
        prov = ent.get("provider") or ""
        ref = ent.get("external_ref") or ""
        target = f"{prov}:{ref}" if prov or ref else ""
        desc = ent["payload"].get("description") or ""
        sources = sorted({r.get("project", "") for r in ent.get("source_refs", []) if r.get("project")})
        srcs = ", ".join(sources)
        bits = [f"**{ent['slug']}**"]
        if desc:
            bits.append(desc)
        line = ": ".join(bits)
        if target:
            line += f" → {target}"
        meta = []
        if srcs:
            meta.append(f"project: {srcs}")
        meta.append(f"first_seen: {ent.get('first_seen', '')}")
        meta.append(f"last_seen: {ent.get('last_seen', '')}")
        if ent.get("aliases"):
            meta.append("aliases: " + ", ".join(ent["aliases"]))
        if ent["status"] != "active":
            meta.append(f"status: {ent['status']}")
        return f"- {line} ({'; '.join(meta)})"

    out = []
    out.append("## Active")
    if not any(by_status["active"].values()):
        out.append("")
        out.append("_(no active entities)_")
    else:
        for cat in ("account", "publish", "subscription", "asset"):
            rows = by_status["active"].get(cat) or []
            if not rows:
                continue
            out.append("")
            out.append(f"### {cat}")
            for ent in rows:
                out.append(format_row(ent))
    out.append("")
    out.append("## Архив")
    if not any(by_status["archive"].values()):
        out.append("")
        out.append("_(no archived entities)_")
    else:
        for cat in ("account", "publish", "subscription", "asset"):
            rows = by_status["archive"].get(cat) or []
            if not rows:
                continue
            out.append("")
            out.append(f"### {cat}")
            for ent in rows:
                out.append(format_row(ent))
    return "\n".join(out)


def write_assets_md(hub: Path, entities: list[dict]) -> None:
    p = hub / "personal" / "assets.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file():
        text = p.read_text(encoding="utf-8")
    else:
        # Minimal skeleton if missing
        text = (
            "---\ntitle: Assets\n---\n\n# Assets\n\n"
            f"{ASSETS_BEGIN}\n{ASSETS_END}\n"
        )
    new_inner = _render_assets_block(entities)
    new_text = _replace_managed_block(text, ASSETS_BEGIN, ASSETS_END, new_inner)
    atomic_write_text(p, new_text)


def _render_sightings_block(ent: dict) -> str:
    lines = []
    for ref in sorted(ent.get("source_refs", []),
                      key=lambda r: (r.get("project", ""), r.get("report_id", ""))):
        proj = ref.get("project", "")
        rid = ref.get("report_id", "")
        lines.append(f"- {proj} @ {rid}: {ent['payload'].get('description', '')}")
    if not lines:
        lines = ["_(no sightings)_"]
    return "\n".join(lines)


def _render_person_or_company_md(ent: dict, *, kind: str) -> str:
    canonical = sorted({r.get("project", "") for r in ent.get("source_refs", []) if r.get("project")})
    aliases = ent.get("aliases", [])
    confidence = ent.get("payload", {}).get("confidence", "high")
    fm_lines = [
        "---",
        f"slug: {ent['slug']}",
        f"kind: {kind}",
        "synthesized: true",
        "canonical_refs: [" + ", ".join(canonical) + "]",
        f"confidence: {confidence}",
        "aliases: [" + ", ".join(aliases) + "]",
        f"first_seen: {ent.get('first_seen', '')}",
        f"last_seen: {ent.get('last_seen', '')}",
        f"status: {ent['status']}",
        "---",
        "",
        f"# {ent['slug']}",
        "",
    ]
    if ent.get("provider") or ent.get("external_ref"):
        prov = ent.get("provider") or ""
        ref = ent.get("external_ref") or ""
        fm_lines.append(f"_{prov}:{ref}_")
        fm_lines.append("")
    fm_lines.append(SIGHTINGS_BEGIN)
    fm_lines.append(_render_sightings_block(ent))
    fm_lines.append(SIGHTINGS_END)
    fm_lines.append("")
    return "\n".join(fm_lines)


def write_people_or_companies(hub: Path, ent: dict) -> None:
    if ent["category"] == PEOPLE_CAT:
        path = hub / "people" / f"{ent['slug']}.md"
        kind = "person"
    elif ent["category"] == COMPANY_CAT:
        path = hub / "companies" / f"{ent['slug']}.md"
        kind = "company"
    else:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        # Preserve manual notes outside SIGHTINGS block by replacing block only
        if SIGHTINGS_BEGIN in existing and SIGHTINGS_END in existing:
            block = _render_sightings_block(ent)
            new = _replace_managed_block(existing, SIGHTINGS_BEGIN, SIGHTINGS_END, block)
            # Also bump frontmatter fields
            new = _patch_frontmatter(new, ent)
            atomic_write_text(path, new)
            return
    atomic_write_text(path, _render_person_or_company_md(ent, kind=kind))


def _patch_frontmatter(text: str, ent: dict) -> str:
    fm, body = parse_frontmatter(text)
    aliases = ent.get("aliases", [])
    canonical = sorted({r.get("project", "") for r in ent.get("source_refs", []) if r.get("project")})
    fm["slug"] = ent["slug"]
    fm["synthesized"] = "true"
    fm["canonical_refs"] = canonical
    fm["confidence"] = ent.get("payload", {}).get("confidence", "high")
    fm["aliases"] = aliases
    fm["last_seen"] = ent.get("last_seen", "")
    fm["status"] = ent["status"]
    out = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            out.append(f"{k}: [" + ", ".join(v) + "]")
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    out.append("")
    out.append(body.lstrip("\n"))
    return "\n".join(out)


# ----------------------------------------------------------------------------
# Cycle JSON + report reading
# ----------------------------------------------------------------------------

def read_cycle_summary(hub: Path, date: str) -> dict:
    p = hub / ".orchestrator" / f"cycle-{date}.json"
    if not p.is_file():
        return {"date": date, "results": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def parse_report(report_path: Path) -> tuple[dict, list[tuple[int, str]]]:
    text = report_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)
    deltas = extract_deltas_section(text)
    return fm, deltas


# ----------------------------------------------------------------------------
# Locking
# ----------------------------------------------------------------------------

class HubLock:
    def __init__(self, hub: Path, name: str = "entity-rollup.lock"):
        self.path = hub / ".orchestrator" / "locks" / name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.fh is not None:
            try:
                fcntl.flock(self.fh, fcntl.LOCK_UN)
            finally:
                self.fh.close()
                self.fh = None


# ----------------------------------------------------------------------------
# Apply pass — full pipeline
# ----------------------------------------------------------------------------

def run_apply(hub: Path, date: str, categories: set | None = None) -> dict:
    """Run the apply pass synchronously. Returns audit dict.

    `categories` restricts BOTH event application and page rendering to
    the given internal category set (D7 scoping); None → all categories.
    """
    if categories is None:
        categories = set(CATEGORIES)
    cycle = read_cycle_summary(hub, date)
    results = cycle.get("results", {})

    counts = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "closed_or_inactivated": 0,
        "skipped_duplicate": 0,
        "skipped_low_confidence": 0,
        "malformed": 0,
        "skipped_archived": 0,
        "skipped_out_of_scope": 0,
    }
    touched: set = set()
    malformed_audit: list[dict] = []

    with HubLock(hub):
        store = load_store(hub)

        for slug, info in results.items():
            status = info.get("status", "")
            if status != "done":
                if status == "archived":
                    counts["skipped_archived"] += 1
                continue
            report_path = Path(info.get("report_path", ""))
            if not report_path.is_file():
                continue
            fm, deltas = parse_report(report_path)
            report_id = fm.get("report_id") or f"{slug}-{date}"
            source_path_rel = f"reports/{date}.md"

            for line_no, raw in deltas:
                ev = parse_bullet_line(raw, line_no)
                if ev is None:
                    continue
                if ev.get("malformed"):
                    counts["malformed"] += 1
                    malformed_audit.append({
                        "project": slug,
                        "report_id": report_id,
                        "line_no": ev["line_no"],
                        "reason": ev["reason"],
                    })
                    continue
                if ev["category"] not in categories:
                    # D7: out-of-scope events (e.g. person under
                    # --categories companies,assets) never reach the
                    # store or the pages — the People Notebook staging
                    # layer owns that flow.
                    counts["skipped_out_of_scope"] += 1
                    continue
                counts["processed"] += 1
                apply_event(
                    store, ev,
                    project_slug=slug,
                    date=date,
                    source_path=source_path_rel,
                    report_id=report_id,
                    counts=counts,
                    touched=touched,
                )

        # Persist store
        save_store(hub, store)

        # Render hub pages from full store — scoped: the render pass must
        # respect the same category restriction, else a store carrying old
        # person entities would rewrite people/ pages on a companies/assets
        # run (D7 guard).
        all_entities = list(store["entities"].values())
        if ASSETS_CATS & categories:
            write_assets_md(hub, all_entities)
        for ent in all_entities:
            if (ent["category"] in (PEOPLE_CAT, COMPANY_CAT)
                    and ent["category"] in categories):
                write_people_or_companies(hub, ent)

    rows_audit = [_audit_row(store["entities"][eid]) for eid in sorted(touched)
                  if eid in store["entities"]]
    audit = {
        "date": date,
        "categories": sorted(g for g, cats in PAGE_GROUPS.items()
                             if cats <= categories),
        "counts": counts,
        "rows": rows_audit,
        "malformed": malformed_audit,
    }
    apath = hub / ".orchestrator" / f"entity-rollup-{date}.json"
    atomic_write_text(apath, json.dumps(audit, indent=2, ensure_ascii=False))
    return audit


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kb_entity_apply.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--hub", required=True, type=Path)
    a.add_argument("--date", default="",
                   help="cycle date YYYY-MM-DD (default: today — lets the "
                        "scheduled entity-rollup process run without date "
                        "templating)")
    a.add_argument("--categories", default="",
                   help="restrict to page groups (comma list of "
                        "people,companies,assets); default: all")
    args = p.parse_args(argv)

    if args.cmd == "apply":
        if os.environ.get("KB_ENTITY_ROLLUP", "0") != "1":
            return 0
        try:
            categories = resolve_categories(args.categories)
        except ValueError as e:
            print(f"kb_entity_apply.py: {e}", file=sys.stderr)
            return 2
        date = args.date or time.strftime("%Y-%m-%d")
        run_apply(args.hub.resolve(), date, categories)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
