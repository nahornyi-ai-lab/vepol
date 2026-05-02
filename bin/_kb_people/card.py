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
    """Create a new people/<slug>.md. Returns path.

    Raises ValueError on empty/whitespace name — the slug derived from
    such a name would be "", landing the card at PEOPLE_DIR/.md (a
    hidden file). Callers MUST supply a non-empty name; sources that
    have only an email should derive a local-part fallback before
    calling.
    """
    if not (name or "").strip():
        raise ValueError("create() refuses empty name (would produce hidden .md file)")
    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    slug = _unique_slug(name)
    if not slug:
        raise ValueError(
            f"create() name {name!r} slugified to empty string "
            "(only special chars / whitespace?) — supply a usable name"
        )
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


def _escape_markdown_table_cell(text: str) -> str:
    """Make `text` safe to drop into a single markdown table cell.

    External data (calendar event titles, mail subjects, etc.) can contain
    pipes, newlines, and HTML-comment markers that would corrupt the
    interactions table or escape the DERIVED-SIGHTINGS region. We do the
    escaping here, centrally, so every source is protected regardless of
    what its sanitizer did or didn't do.

    Transformations:
    - `\\` → `\\\\` (must be first to avoid double-escaping)
    - `|`  → `\\|`  (pipe would split the cell)
    - newline / CR / tab → space (single-line cells)
    - `<!--` and `-->` → `<! --` and `-- >` (defang HTML comment markers
      so a row body can never escape the managed region)
    """
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\")
    s = s.replace("|", "\\|")
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = s.replace("<!--", "<! --").replace("-->", "-- >")
    # Collapse runs of whitespace introduced by newline/tab replacement.
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


def upsert_sighting(slug: str, event_date: str, source: str, summary: str):
    """Append a sighting row to DERIVED-SIGHTINGS block. Idempotent by date+summary.

    All cell content is markdown-escaped before insertion — see
    `_escape_markdown_table_cell` for the full set of transformations.
    Sources should NOT pre-escape; the escape is the canonical authority.
    """
    path = PEOPLE_DIR / f"{slug}.md"
    if not path.exists():
        return
    post = load(slug)
    body = post.content

    safe_date = _escape_markdown_table_cell(event_date)
    safe_source = _escape_markdown_table_cell(source)
    safe_summary = _escape_markdown_table_cell(summary)
    new_row = f"| {safe_date} | {safe_source} | {safe_summary} |"

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


def list_drafts() -> list[dict]:
    """Return all draft cards. Sorted: drafts WITH possible_duplicate_of
    first (more important to review), then by last_seen ASC.
    """
    results = []
    for path in sorted(PEOPLE_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        post = load(path)
        if post is None or not post.get("draft", False):
            continue
        results.append({
            "slug": post.get("slug", path.stem),
            "name": post.get("name", ""),
            "email": post.get("email", ""),
            "possible_duplicate_of": post.get("possible_duplicate_of", ""),
            "first_met": post.get("first_met", ""),
            "last_seen": post.get("last_seen", ""),
        })
    # Drafts with a duplicate hint sort first; ties by last_seen.
    results.sort(key=lambda r: (not bool(r["possible_duplicate_of"]), r["last_seen"]))
    return results


def promote_draft(slug: str) -> bool:
    """Clear `draft: true` on a card. Returns False if card not found."""
    post = load(slug)
    if post is None:
        return False
    post["draft"] = False
    if "possible_duplicate_of" in post.metadata:
        del post.metadata["possible_duplicate_of"]
    save(post, PEOPLE_DIR / f"{slug}.md")
    return True


def delete(slug: str) -> bool:
    """Delete a card from disk + remove its index entry. Returns True on
    success, False if not found.

    Sightings on the card go away with the file. The matching index
    entry (UUID → slug + email) is removed so search/lookup don't
    return stale results.
    """
    path = PEOPLE_DIR / f"{slug}.md"
    if not path.exists():
        return False
    post = load(slug)
    if post is not None:
        # Lazy-import index to avoid circular dependency.
        from . import index as _idx
        uid = post.get("id")
        if uid:
            _idx.remove(uid)
    path.unlink()
    return True


def merge_into(src_slug: str, dst_slug: str) -> bool:
    """Merge a draft (src) into an existing card (dst).

    Strategy: do ALL dst mutations in-memory, save once at the end.
    Do NOT call upsert_sighting on dst here — that would write to
    disk before our final save(dst), which would then clobber the
    appended rows on save.

      1. Verify both cards exist; if dst missing, return False.
      2. Parse src's interactions table; append (dedup-by-row) into
         dst's in-memory body.
      3. Carry forward scalar fields from src ONLY where dst is empty.
      4. Add src.email to dst.aliases if dst.email differs.
      5. Save dst once. Delete src (file + index entry).

    Returns False if dst doesn't exist.
    """
    dst_path = PEOPLE_DIR / f"{dst_slug}.md"
    if not dst_path.exists():
        return False

    src = load(src_slug)
    dst = load(dst_slug)
    if src is None or dst is None:
        return False

    # 1. Carry sightings src → dst (in-memory — no disk write yet)
    src_body = src.content
    new_rows: list[str] = []
    if SIGHTINGS_BEGIN in src_body:
        try:
            block_start = src_body.index(SIGHTINGS_BEGIN) + len(SIGHTINGS_BEGIN)
            block_end = src_body.index(SIGHTINGS_END)
            block = src_body[block_start:block_end]
        except ValueError:
            block = ""
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|") or "Date" in line or "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 3:
                safe_d = _escape_markdown_table_cell(cells[0])
                safe_s = _escape_markdown_table_cell(cells[1])
                safe_summ = _escape_markdown_table_cell(cells[2])
                new_rows.append(f"| {safe_d} | {safe_s} | {safe_summ} |")

    if new_rows:
        dst_body = dst.content
        # Dedup against rows already in dst.
        unique = [r for r in new_rows if r not in dst_body]
        if unique:
            insertion = "\n".join(unique) + "\n"
            if SIGHTINGS_BEGIN not in dst_body:
                dst_body += (f"\n## Interactions\n{SIGHTINGS_BEGIN}\n"
                             f"{SIGHTINGS_HEADER}\n{insertion}{SIGHTINGS_END}\n")
            else:
                dst_body = dst_body.replace(
                    SIGHTINGS_END, f"{insertion}{SIGHTINGS_END}",
                )
            dst.content = dst_body
            # last_seen → max of (existing, src.last_seen)
            src_last = src.get("last_seen", "")
            dst_last = dst.get("last_seen", "")
            if src_last and src_last > dst_last:
                dst["last_seen"] = src_last

    # 2. Fill empty dst scalar fields from src
    for k in ("company", "role", "phone", "telegram", "linkedin",
              "first_met_context", "first_met"):
        if not dst.get(k) and src.get(k):
            dst[k] = src[k]

    # 3. Alias merge — keep dst.email, append src.email to aliases
    src_email = src.get("email", "")
    if src_email and src_email != dst.get("email", ""):
        aliases = dst.get("aliases", []) or []
        if src_email not in aliases:
            aliases.append(src_email)
        dst["aliases"] = aliases

    save(dst, dst_path)

    # 4. Delete src (file + index entry)
    delete(src_slug)
    return True
