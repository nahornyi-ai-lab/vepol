"""Contact card model — parse/write people/<slug>.md files."""

import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path

import frontmatter

PEOPLE_DIR = Path.home() / "knowledge" / "people"
COMPANIES_DIR = Path.home() / "knowledge" / "companies"

MANUAL_NOTES_BEGIN = "<!-- MANUAL-NOTES-BEGIN -->"
MANUAL_NOTES_END = "<!-- MANUAL-NOTES-END -->"
SIGHTINGS_BEGIN = "<!-- DERIVED-SIGHTINGS-BEGIN -->"
SIGHTINGS_END = "<!-- DERIVED-SIGHTINGS-END -->"

SIGHTINGS_HEADER = "| Date | Source | Summary |\n|------|--------|---------|"


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _unique_slug(name: str) -> str:
    base = _slugify(name)
    path = PEOPLE_DIR / f"{base}.md"
    if not path.exists():
        return base
    short_id = uuid.uuid4().hex[:8]
    return f"{base}-{short_id}"


def _default_frontmatter(name: str, slug: str, **kwargs) -> dict:
    today = date.today().isoformat()
    fm = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "name": name,
        "aliases": [],
        "email": kwargs.get("email", ""),
        "telegram": kwargs.get("telegram", ""),
        "linkedin": "",
        "phone": "",
        "company": kwargs.get("company", ""),
        "role": kwargs.get("role", ""),
        "location": "",
        "timezone": "",
        "first_met": kwargs.get("first_met", today),
        "first_met_context": kwargs.get("first_met_context", ""),
        "last_seen": kwargs.get("last_seen", today),
        "next_touch_due": kwargs.get("next_touch_due", ""),
        "tags": kwargs.get("tags", []),
        "source": kwargs.get("source", "manual"),
        "enrichment_status": "manual",
        "draft": kwargs.get("draft", False),
        "possible_duplicate_of": kwargs.get("possible_duplicate_of", ""),
        "created_at": today,
        "updated_at": today,
    }
    return {k: v for k, v in fm.items() if v != "" or k in ("aliases", "tags", "draft")}


def _build_body(notes: str = "", sightings: list[dict] | None = None) -> str:
    notes_block = f"{MANUAL_NOTES_BEGIN}\n{notes.strip()}\n{MANUAL_NOTES_END}" if notes else f"{MANUAL_NOTES_BEGIN}\n{MANUAL_NOTES_END}"
    sighting_rows = ""
    if sightings:
        rows = "\n".join(f"| {s['date']} | {s['source']} | {s['summary']} |" for s in sightings)
        sighting_rows = f"{SIGHTINGS_BEGIN}\n{SIGHTINGS_HEADER}\n{rows}\n{SIGHTINGS_END}"
    else:
        sighting_rows = f"{SIGHTINGS_BEGIN}\n{SIGHTINGS_HEADER}\n{SIGHTINGS_END}"

    return f"## Notes\n{notes_block}\n\n## Interactions\n{sighting_rows}\n"


def create(name: str, **kwargs) -> Path:
    """Create a new people/<slug>.md. Returns path."""
    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    slug = _unique_slug(name)
    path = PEOPLE_DIR / f"{slug}.md"
    fm = _default_frontmatter(name, slug, **kwargs)
    body = _build_body()
    post = frontmatter.Post(body, **fm)
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    return path


def load(slug_or_path) -> frontmatter.Post | None:
    """Load a card by slug or path."""
    path = Path(slug_or_path) if "/" in str(slug_or_path) else PEOPLE_DIR / f"{slug_or_path}.md"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return frontmatter.load(f)


def save(post: frontmatter.Post, path: Path):
    """Write card back atomically."""
    post["updated_at"] = date.today().isoformat()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    os.replace(tmp, path)


def upsert_sighting(slug: str, event_date: str, source: str, summary: str):
    """Append a sighting row to DERIVED-SIGHTINGS block. Idempotent by date+summary."""
    path = PEOPLE_DIR / f"{slug}.md"
    if not path.exists():
        return
    post = load(slug)
    body = post.content

    new_row = f"| {event_date} | {source} | {summary} |"

    if SIGHTINGS_BEGIN not in body:
        body += f"\n## Interactions\n{SIGHTINGS_BEGIN}\n{SIGHTINGS_HEADER}\n{new_row}\n{SIGHTINGS_END}\n"
    elif new_row in body:
        return  # idempotent
    else:
        body = body.replace(
            SIGHTINGS_END,
            f"{new_row}\n{SIGHTINGS_END}"
        )

    post.content = body
    post["last_seen"] = event_date
    save(post, path)


def set_remind(slug: str, due_date: str):
    """Set next_touch_due on a card."""
    path = PEOPLE_DIR / f"{slug}.md"
    post = load(slug)
    if post is None:
        return
    post["next_touch_due"] = due_date
    save(post, path)


def list_due(horizon_days: int = 7) -> list[dict]:
    """Return cards where next_touch_due <= today + horizon_days."""
    from datetime import timedelta
    cutoff = date.today() + timedelta(days=horizon_days)
    results = []
    for path in sorted(PEOPLE_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        post = load(path)
        if post is None:
            continue
        if post.get("draft", False):
            continue
        due = post.get("next_touch_due", "")
        if not due:
            continue
        try:
            due_date = date.fromisoformat(str(due))
        except ValueError:
            continue
        if due_date <= cutoff:
            results.append({
                "slug": post.get("slug", path.stem),
                "name": post.get("name", ""),
                "due": str(due),
                "last_seen": post.get("last_seen", ""),
                "tags": post.get("tags", []),
            })
    return results


def search(query: str) -> list[dict]:
    """Simple grep over people/*.md content."""
    query_lower = query.lower()
    results = []
    for path in sorted(PEOPLE_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8").lower()
        if query_lower in text:
            post = load(path)
            if post:
                results.append({
                    "slug": post.get("slug", path.stem),
                    "name": post.get("name", ""),
                    "company": post.get("company", ""),
                    "tags": post.get("tags", []),
                    "draft": post.get("draft", False),
                })
    return results
