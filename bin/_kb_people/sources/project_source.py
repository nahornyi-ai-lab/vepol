"""Project source — extract people mentions from project knowledge files.

Per ~/knowledge/concepts/people-extraction-from-projects.md.

Pass 1 (deterministic, → live):
  - email regex with URL-rejection;
  - telegram handles minus blocklist;
  - known-alias re-resolution (race-safe at apply-time, not snapshot).

Pass 2 (LLM via MCP host, → forced draft):
  - free-text human-name extraction with strict inclusion criteria.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# _kb_mcp lives one level up, alongside _kb_people.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _kb_mcp.runner import (  # noqa: E402
    McpHostError, McpHostRunner, McpResponseError, McpToolError,
)

from . import ContactSource
from .. import filters
from ..date_attribution import attribute_date


# ---------------------------------------------------------------------------
# Email regex set — reused from calendar_source.py for parser consistency.
# ---------------------------------------------------------------------------

_BOT_LOCAL_PART_RE = re.compile(
    r"^(meet|schedule|scheduling|booking|appointments?|"
    r"assistant|bot|robot|automation|automated|"
    r"noreply|no-reply|donotreply|do-not-reply|"
    r"notify|notifications?|alerts?|reminder|reminders|"
    r"info|hello|hi|admin|support|help|contact|"
    r"team|sales|billing|invoice|invoices|"
    r"calendar|cal|notify-cal)"
    r"[\d_-]*@",
    re.IGNORECASE,
)

_RESOURCE_CAL_RE = re.compile(r"resource\.calendar\.google\.com$")

# In-text email finder. Hardened per Codex Layer-2 point 1:
#   - left boundary excludes `@` so "@@a@b.c" is not captured;
#   - URL/query-param rejection is a separate function (regex
#     lookbehind alone can't span multi-token URL patterns reliably).
_EMAIL_INLINE_RE = re.compile(
    r"(?<![/\w.@])([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})(?![/\w])"
)


def _is_email_inside_url(text: str, span: tuple[int, int]) -> bool:
    """Return True if `span` sits inside an http(s)://… URL token or a
    URL query param (?k=… / &k=…)."""
    start = span[0]
    window = text[max(0, start - 200):start]
    if re.search(r"https?://[^\s]*$", window):
        return True
    if re.search(r"[?&][A-Za-z_][\w-]*=$", window):
        return True
    return False


# ---------------------------------------------------------------------------
# Telegram regex + blocklist (loaded from data file).
# ---------------------------------------------------------------------------

# @ followed by 3–32 letters/digits/underscores, starting with a letter.
_TELEGRAM_RE = re.compile(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{2,31})(?![\w])")


def _load_blocklist(path: Path) -> frozenset[str]:
    """Read one-handle-per-line blocklist file. Lowercase, comments
    with `#`, blank lines OK. Missing file → empty blocklist."""
    if not path.exists():
        return frozenset()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return frozenset(out)


_BLOCKLIST_DIR = Path(__file__).resolve().parent.parent / "blocklists"
_TELEGRAM_SYSTEM_BLOCKLIST: frozenset[str] = _load_blocklist(
    _BLOCKLIST_DIR / "telegram.txt"
)


def _load_owner_emails() -> frozenset[str]:
    """Owner-self email blocklist. Lives at
    `<PEOPLE_DIR>/.owner-emails.txt` (one lowercase address per line,
    `#` comments). Without this list the extractor will create cards
    for the human running the system — caught by `--reject` after
    first review, but cleaner to drop up front.
    Resolved lazily so test PEOPLE_DIR overrides are honoured.
    """
    from .. import card as _card
    return _load_blocklist(_card.PEOPLE_DIR / ".owner-emails.txt")


def _load_personal_telegram_blocklist() -> frozenset[str]:
    """Owner-curated telegram-handle blocklist (owner-self handles and
    other machine-local exclusions). Lives at
    `<PEOPLE_DIR>/.blocklist-telegram.txt`, NEVER in the shipped package
    blocklist — the packaged file must stay free of personal
    identifiers. Resolved lazily so test PEOPLE_DIR overrides are
    honoured."""
    from .. import card as _card
    return _load_blocklist(_card.PEOPLE_DIR / ".blocklist-telegram.txt")


# ---------------------------------------------------------------------------
# Pass-1 extraction.
# ---------------------------------------------------------------------------

_CONTEXT_CAP = 500


def _line_index(text: str) -> list[int]:
    """Return sorted list of byte/char offsets where each line begins.
    Index i corresponds to line_no = i + 1."""
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _line_no_for_offset(starts: list[int], offset: int) -> int:
    """Binary-search line number (1-based) for a character offset."""
    import bisect
    return bisect.bisect_right(starts, offset)


def _line_text_for(text: str, line_starts: list[int], line_no: int) -> str:
    """Extract the full content of a 1-based line."""
    if line_no < 1 or line_no > len(line_starts):
        return ""
    start = line_starts[line_no - 1]
    end = line_starts[line_no] if line_no < len(line_starts) else len(text)
    return text[start:end].rstrip("\n")


def extract_pass1(
    file_text: str,
    project_slug: str,
    source_path: str,
    file_path: Path | None = None,
) -> list[dict]:
    """Run Pass-1 deterministic extraction over a single file's text.

    Returns a list of contact-dicts with shape:
        {name, email, telegram, date, context, project_slug,
         source_path, line_no, line_content, confidence: "high"}

    `file_path` is used for date attribution (daily/<date>.md fallback);
    pass `Path(source_path)` if you don't have the absolute path.
    """
    if file_path is None:
        file_path = Path(source_path)

    line_starts = _line_index(file_text)
    hits: list[dict] = []
    owner_emails = _load_owner_emails()
    personal_tg_blocklist = _load_personal_telegram_blocklist()

    # --- Email pass ----------------------------------------------------
    for m in _EMAIL_INLINE_RE.finditer(file_text):
        email_raw = m.group(1)
        if _is_email_inside_url(file_text, m.span()):
            continue
        email = email_raw.strip().lower()
        if _BOT_LOCAL_PART_RE.match(email):
            continue
        if filters.is_role_email(email):
            continue  # org/function mailbox (receipts@, owner@, …), not a person
        if filters.is_reserved_example_email(email):
            continue  # RFC-reserved doc/test domain — a fixture, not a person
        if _RESOURCE_CAL_RE.search(email):
            continue
        if email in owner_emails:
            continue  # owner-self: never extract the human running the system
        line_no = _line_no_for_offset(line_starts, m.start())
        line_content = _line_text_for(file_text, line_starts, line_no)
        date_iso = attribute_date(file_path, line_no=line_no, file_text=file_text)
        # Derive a display name from local-part if we don't have one.
        local_part = email.split("@", 1)[0]
        display = local_part.replace(".", " ").replace("_", " ").strip()
        hits.append({
            "name": display,
            "email": email,
            "telegram": "",
            "date": date_iso,
            "context": line_content[:_CONTEXT_CAP],
            "project_slug": project_slug,
            "source_path": source_path,
            "line_no": line_no,
            "line_content": line_content,
            "confidence": "high",
        })

    # --- Telegram pass -------------------------------------------------
    for m in _TELEGRAM_RE.finditer(file_text):
        handle_raw = m.group(1)
        handle = handle_raw.lower()
        if handle in _TELEGRAM_SYSTEM_BLOCKLIST or handle in personal_tg_blocklist:
            continue
        line_no = _line_no_for_offset(line_starts, m.start())
        line_content = _line_text_for(file_text, line_starts, line_no)
        date_iso = attribute_date(file_path, line_no=line_no, file_text=file_text)
        hits.append({
            "name": handle_raw,  # preserve original case for display
            "email": "",
            "telegram": "@" + handle_raw,
            "date": date_iso,
            "context": line_content[:_CONTEXT_CAP],
            "project_slug": project_slug,
            "source_path": source_path,
            "line_no": line_no,
            "line_content": line_content,
            "confidence": "high",
        })

    return hits


# ---------------------------------------------------------------------------
# Composite-key dedup (Codex Layer-2 IP-I Q2 closed verdict).
# ---------------------------------------------------------------------------

def _normalize_line(content: str) -> str:
    """Normalise a line for hash-based dedup: collapse whitespace, strip."""
    return re.sub(r"\s+", " ", content).strip()


def _composite_key(hit: dict) -> tuple:
    """Build the composite dedup key.

    Per IP-I Q2: (project_slug, source_path, line_no, normalized_line_hash).
    Locator/slug add no information here — they're surface artifacts of
    the same line.
    """
    norm = _normalize_line(hit.get("line_content", ""))
    line_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    return (
        hit.get("project_slug", ""),
        hit.get("source_path", ""),
        hit.get("line_no", -1),
        line_hash,
    )


_CONFIDENCE_RANK = {"high": 2, "low": 1}


def dedup_hits(hits: list[dict]) -> list[dict]:
    """Merge hits that share the same composite key. Higher-confidence
    wins on conflict; locator fields (email/telegram) carry forward
    from whichever source provided them."""
    grouped: dict[tuple, dict] = {}
    for h in hits:
        key = _composite_key(h)
        if key not in grouped:
            grouped[key] = dict(h)
            continue
        existing = grouped[key]
        # Promote confidence if new hit is higher.
        cur_rank = _CONFIDENCE_RANK.get(existing.get("confidence", "low"), 0)
        new_rank = _CONFIDENCE_RANK.get(h.get("confidence", "low"), 0)
        if new_rank > cur_rank:
            # Keep new as base, but carry forward non-empty fields from
            # existing where new is empty.
            merged = dict(h)
            for k, v in existing.items():
                if not merged.get(k) and v:
                    merged[k] = v
            grouped[key] = merged
        else:
            # Existing wins; fill empty fields from new.
            for k, v in h.items():
                if not existing.get(k) and v:
                    existing[k] = v
    return list(grouped.values())


# ---------------------------------------------------------------------------
# ContactSource adapter (full impl lands with Pass-2 + scanner).
# ---------------------------------------------------------------------------

class ProjectSource(ContactSource):
    """ContactSource over project knowledge files.

    Construction is cheap; actual scanning happens in `get_contacts`.
    The full scanner (registry walk, watermark resolution, MCP Pass 2)
    arrives with the kb-extract-people CLI; this class is the
    Pass-1 entry point used by tests today.
    """

    def __init__(self, hub: Path, runner=None):
        self.hub = hub
        self.runner = runner  # optional MCP host runner for Pass 2

    def get_contacts(self) -> list[dict]:
        # Full impl: read registry, walk active projects, scan in-scope
        # files, apply watermarks, run Pass 1 + Pass 2, dedup, return.
        # Stage gated by kb-extract-people CLI; intentionally raises
        # until that lands so callers don't silently get an empty list.
        raise NotImplementedError(
            "ProjectSource.get_contacts: full scanner lands with "
            "bin/kb-extract-people. Use extract_pass1() directly for "
            "single-file Pass-1 work."
        )


# ---------------------------------------------------------------------------
# Pass-2 LLM extraction — chunking + prompt + apply.
# ---------------------------------------------------------------------------

LLM_PROMPT_TEMPLATE = """\
You are extracting REAL HUMAN CONTACTS from a project knowledge log.

Output a SINGLE JSON object on stdout, NO preamble, NO markdown, NO
trailing content. Required shape:

{{"ok": true, "items": [
  {{"name": "<full or first name>", "role": "<role/company hint or empty>", "context": "<one-line evidence>", "date": "<YYYY-MM-DD or empty>", "source_line": <integer line_no>}}
], "stats": {{"n_items": <int>, "fetched_at": "{fetched_at}"}}}}

Inclusion — emit ONLY if ALL hold:
- Named human (first name OR first+last);
- Direct evidence of two-sided interaction with the author of this log:
  meeting, message, call, email thread, joint task, decision, blocker,
  request — NOT just citation;
- Not a public figure cited as authority (Karpathy, Altman, Altshuller, etc.);
- Not a system/bot/role label;
- Not hypothetical/future/generic ("if a CTO joins…").

If uncertain about ANY criterion above, EXCLUDE.

EXCLUDE explicitly:
- Authors of articles cited as sources;
- Public-figure references in concepts;
- Generic role placeholders;
- The log author themselves;
- Family unless context shows business interaction.

Constraints:
- name <= 200 chars; context <= 500 chars;
- source_line MUST be a valid line_no from the input chunk;
- date is empty or ISO YYYY-MM-DD;
- emit MAX 30 items per call. If more exist, set stats.truncated=true
  and emit the first 30 by source_line ascending; do NOT silently drop.

If unable to process, instead output:
{{"ok": false, "error": "<short_snake_case>", "detail": "<short>"}}

Project: {project_slug}
Source path: {source_path}
Request ID: {request_id}

--- BEGIN CHUNK ---
{chunk_text}
--- END CHUNK ---
"""

_HEADING_DATE_RE = re.compile(r"^##\s*\[\d{4}-\d{2}-\d{2}\]")


def _format_chunk_for_prompt(text: str, line_offset: int = 1) -> tuple[str, set[int]]:
    """Render chunk as `<line_no>: <content>` lines. Returns the
    formatted text plus the set of line numbers it includes.
    """
    out_lines: list[str] = []
    valid_lines: set[int] = set()
    for i, line in enumerate(text.splitlines()):
        ln = line_offset + i
        out_lines.append(f"{ln}: {line}")
        valid_lines.add(ln)
    return "\n".join(out_lines), valid_lines


def chunk_text_by_heading(
    file_text: str,
    *,
    max_chars: int = 4000,
) -> list[tuple[str, int]]:
    """Split `file_text` into chunks, each ≤ `max_chars`.

    Heuristic: split at `## [YYYY-MM-DD]` heading boundaries; if a
    single heading-section exceeds max_chars, split that section by
    line until each piece fits.

    Returns list of `(chunk_text, starting_line_no_1_based)`.
    """
    lines = file_text.splitlines()
    if not lines:
        return []

    # Find heading line indices (0-based).
    heading_idx: list[int] = [
        i for i, ln in enumerate(lines) if _HEADING_DATE_RE.match(ln)
    ]

    sections: list[tuple[int, int]] = []  # (start_line0, end_line0_excl)
    if not heading_idx:
        sections.append((0, len(lines)))
    else:
        # Pre-heading content is its own section.
        if heading_idx[0] > 0:
            sections.append((0, heading_idx[0]))
        for k, h in enumerate(heading_idx):
            end = heading_idx[k + 1] if k + 1 < len(heading_idx) else len(lines)
            sections.append((h, end))

    chunks: list[tuple[str, int]] = []
    for start, end in sections:
        section = "\n".join(lines[start:end])
        if len(section) <= max_chars:
            chunks.append((section, start + 1))
            continue
        # Split section by lines into sub-chunks of <= max_chars.
        cur_start = start
        cur_buf: list[str] = []
        cur_size = 0
        for j in range(start, end):
            line = lines[j]
            line_len = len(line) + 1
            if cur_size + line_len > max_chars and cur_buf:
                chunks.append(("\n".join(cur_buf), cur_start + 1))
                cur_buf = [line]
                cur_size = line_len
                cur_start = j
            else:
                cur_buf.append(line)
                cur_size += line_len
        if cur_buf:
            chunks.append(("\n".join(cur_buf), cur_start + 1))

    return chunks


def _make_mcp_runner() -> McpHostRunner:
    """Factory. Returns a real McpHostRunner in production; in tests
    (KB_PEOPLE_FAKE_MCP=1), wires the fake runner from
    `tests/people-extraction/mocks/fake_mcp_runner.py`."""
    if os.environ.get("KB_PEOPLE_FAKE_MCP") != "1":
        return McpHostRunner()
    # Test mode — locate fake_mcp_runner.py via PYTHONPATH or repo path.
    try:
        from fake_mcp_runner import fake_runner_fn  # type: ignore
    except ImportError:
        # Fallback to repo-relative path.
        repo_mocks = Path.home() / "knowledge" / "tests" / "people-extraction" / "mocks"
        spec = importlib.util.spec_from_file_location(
            "fake_mcp_runner", repo_mocks / "fake_mcp_runner.py"
        )
        if spec is None or spec.loader is None:
            raise
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fake_runner_fn = mod.fake_runner_fn
    return McpHostRunner(runner=fake_runner_fn)


def extract_pass2(
    file_text: str,
    project_slug: str,
    source_path: str,
    file_path: Path,
    *,
    runner: McpHostRunner | None = None,
    backfill: bool = False,
    single_call: bool = False,
    chunk_max_chars: int = 4000,
    audit_calls: list[dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """Run Pass-2 LLM extraction over a single file.

    Args:
        backfill:        cycle mode caps to 1 LLM call/project; backfill
                         re-chunks on truncation (4000→2000→1000) up to
                         3 attempts.
        single_call:     if True (cycle mode), only the most-recent chunk
                         is sent to the LLM — enforces the 1-call-per-
                         project budget per IP-D / IP-I Q6.
        audit_calls:     if provided, per-call telemetry is appended.

    Returns (hits, errors) — each hit dict shaped like Pass-1 hits but
    `confidence: "low"` and forced-draft semantics expected by caller.
    Errors is a list of short error codes for project audit.
    """
    if runner is None:
        runner = _make_mcp_runner()

    chunks = chunk_text_by_heading(file_text, max_chars=chunk_max_chars)
    if not chunks:
        return [], []
    if single_call:
        # Cycle-mode budget: only the most recent heading-section.
        chunks = [chunks[-1]]

    hits: list[dict] = []
    errors: list[str] = []

    for chunk_text, start_line in chunks:
        result, err = _call_one_chunk(
            chunk_text=chunk_text,
            start_line=start_line,
            file_text=file_text,
            project_slug=project_slug,
            source_path=source_path,
            file_path=file_path,
            runner=runner,
            audit_calls=audit_calls,
            backfill=backfill,
            shrink_attempts_remaining=3 if backfill else 0,
            chunk_max_chars=chunk_max_chars,
        )
        if err:
            errors.append(err)
        hits.extend(result)
    return hits, errors


def _call_one_chunk(
    *,
    chunk_text: str,
    start_line: int,
    file_text: str,
    project_slug: str,
    source_path: str,
    file_path: Path,
    runner: McpHostRunner,
    audit_calls: list[dict] | None,
    backfill: bool,
    shrink_attempts_remaining: int,
    chunk_max_chars: int,
) -> tuple[list[dict], str | None]:
    """Format prompt, call MCP, validate response, return hits + error code."""
    formatted, valid_lines = _format_chunk_for_prompt(chunk_text, start_line)
    request_id = str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prompt = LLM_PROMPT_TEMPLATE.format(
        project_slug=project_slug,
        source_path=source_path,
        request_id=request_id,
        fetched_at=fetched_at,
        chunk_text=formatted,
    )
    chunk_id = hashlib.sha256(formatted.encode("utf-8")).hexdigest()[:16]
    t0 = time.monotonic()
    err_code: str | None = None
    items: list[dict] = []
    truncated = False
    try:
        envelope = runner.call(prompt, timeout_s=120)
        items_raw = envelope.get("items", [])
        truncated = bool(envelope.get("stats", {}).get("truncated", False))
    except McpHostError as e:
        err_code = "host_error"
        envelope = None
    except McpToolError as e:
        err_code = f"tool_error:{e.error}"
        envelope = None
    except McpResponseError:
        err_code = "response_schema_error"
        envelope = None
    duration_ms = int((time.monotonic() - t0) * 1000)

    if audit_calls is not None:
        audit_calls.append({
            "chunk_id": chunk_id,
            "request_id": request_id,
            "duration_ms": duration_ms,
            "timeout_s": 120,
            "input_chars": len(formatted),
            "items_returned": len(items_raw) if envelope is not None else 0,
            "truncated": truncated,
            "error": err_code,
        })

    if err_code is not None:
        return [], err_code

    # Apply-side source_line validation against the actual chunk lines.
    hits: list[dict] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        src_line = raw.get("source_line")
        if not isinstance(src_line, int) or src_line not in valid_lines:
            continue
        name = (raw.get("name") or "").strip()
        if not name or len(name) > 200:
            continue
        # Determine the actual line content for line_content/dedup.
        # Line numbers are 1-based; subtract 1 for splitlines indexing.
        all_lines = file_text.splitlines()
        if 1 <= src_line <= len(all_lines):
            line_content = all_lines[src_line - 1]
        else:
            line_content = raw.get("context", "") or ""
        date_iso = raw.get("date") or attribute_date(
            file_path, src_line, file_text
        )
        hits.append({
            "name": name,
            "email": "",
            "telegram": "",
            "date": date_iso,
            "context": (raw.get("context") or "")[:500],
            "project_slug": project_slug,
            "source_path": source_path,
            "line_no": src_line,
            "line_content": line_content,
            "confidence": "low",  # forced draft on apply
            "role_hint": (raw.get("role") or "")[:200],
        })

    # Backfill re-chunk on saturation/truncation.
    saturating = (truncated or len(items_raw) >= 30)
    if backfill and saturating and shrink_attempts_remaining > 0:
        smaller = max(1000, chunk_max_chars // 2)
        if smaller < chunk_max_chars:
            sub_chunks = chunk_text_by_heading(chunk_text, max_chars=smaller)
            for sub_text, sub_offset in sub_chunks:
                sub_start = start_line + sub_offset - 1
                sub_hits, sub_err = _call_one_chunk(
                    chunk_text=sub_text,
                    start_line=sub_start,
                    file_text=file_text,
                    project_slug=project_slug,
                    source_path=source_path,
                    file_path=file_path,
                    runner=runner,
                    audit_calls=audit_calls,
                    backfill=backfill,
                    shrink_attempts_remaining=shrink_attempts_remaining - 1,
                    chunk_max_chars=smaller,
                )
                if sub_err:
                    return hits, sub_err
                hits.extend(sub_hits)

    return hits, None
