"""Personal Idea OS card model and lifecycle operations."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from .locks import ideas_lock

STATUS_ACTIVE = {"captured", "triage", "critique", "ready", "promoted"}
STATUS_PARKED = {"parked"}
STATUS_TERMINAL = {"killed", "merged", "done"}


def hub_path(hub: str | Path | None = None) -> Path:
    if hub is not None:
        return Path(hub)
    return Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))


def ideas_dir(hub: str | Path | None = None) -> Path:
    return hub_path(hub) / "personal" / "ideas"


def dashboard_path(hub: str | Path | None = None) -> Path:
    return hub_path(hub) / "personal" / "ideas.md"


def capture(
    raw_text: str,
    *,
    source: str = "chat",
    now: str | datetime | None = None,
    title: str | None = None,
    owner: str = "personal",
    hub: str | Path | None = None,
) -> dict[str, str]:
    """Capture raw idea text into an atomic canonical card."""
    root = hub_path(hub)
    raw = (raw_text or "").strip()
    if not raw:
        raise ValueError("capture requires non-empty raw_text")
    ts = _coerce_datetime(now)
    clean_title = _derive_title(raw, title)
    slug = _slugify(clean_title) or _slugify(raw) or "idea"
    cards = ideas_dir(root)
    cards.mkdir(parents=True, exist_ok=True)

    with ideas_lock(root):
        idea_id = _unique_idea_id(ts, slug, cards)
        path = cards / f"{idea_id}.md"
        fm = _default_frontmatter(
            idea_id=idea_id,
            title=clean_title,
            source=source,
            now=ts,
            owner=owner,
        )
        body = _default_body(clean_title, raw, ts)
        _write_post_atomic(path, frontmatter.Post(body, **fm), cards)
        _render_dashboard_unlocked(root)
    return {"id": idea_id, "path": str(path)}


def triage(
    idea_id: str,
    *,
    priority: str = "P2",
    materiality: str = "cheap-test",
    strategic_lines: list[str] | None = None,
    next_action: str = "",
    expected_evidence: str = "",
    why_it_matters: str = "",
    status: str | None = None,
    hub: str | Path | None = None,
) -> dict[str, str]:
    """Route a captured idea into ready/critique/parked/killed state."""
    root = hub_path(hub)
    with ideas_lock(root):
        path, post = _load_required_unlocked(root, idea_id)
        routed_status = status or ("critique" if materiality == "material" else "ready")
        _validate_priority(priority)
        _validate_status(routed_status)
        post["status"] = routed_status
        post["priority"] = priority
        post["priority_scored_at"] = _today()
        post["materiality"] = materiality
        if strategic_lines is not None:
            post["strategic_lines"] = strategic_lines
        if why_it_matters:
            post.content = _replace_section(post.content, "Why it matters", why_it_matters)
        evidence = expected_evidence or "Define a visible proof before promotion."
        action = next_action or "Define smallest testable action."
        post["next_action"] = action
        post["expected_evidence"] = evidence
        post.content = _replace_section(
            post.content,
            "Dedupe",
            "Checked against current idea cards during triage. No duplicate selected.",
        )
        post.content = _replace_section(
            post.content,
            "Priority",
            "\n".join(
                [
                    f"- priority: {priority}",
                    f"- materiality: {materiality}",
                    f"- scored_at: {_today()}",
                    f"- strategic_lines: {', '.join(strategic_lines or post.get('strategic_lines') or []) or '[]'}",
                ]
            ),
        )
        post.content = _replace_section(
            post.content,
            "Next action",
            f"{action}\n\nEvidence: {evidence}",
        )
        _save_post_unlocked(path, post)
        _render_dashboard_unlocked(root)
    return {"id": post["id"], "status": post["status"], "priority": post["priority"]}


def _board_path_for_slug(root: Path, project_slug: str) -> Path:
    """Resolve the kb-board backlog file for a promotion target.

    "hub" targets the hub's own board; any other slug targets the project's
    board through the hub's projects/<slug> link. No silent fallbacks: a
    missing board is an error, not an invitation to create one in a guessed
    location.
    """
    if project_slug in ("", "hub"):
        board = root / "backlog.md"
    else:
        board = root / "projects" / project_slug / "backlog.md"
    if not board.exists():
        raise ValueError(
            f"no kb-board backlog for project_slug={project_slug!r} at {board}"
        )
    return board


def _create_board_task(
    root: Path,
    *,
    project_slug: str,
    idea_id: str,
    title: str,
    priority: str,
    acceptance: str,
    context: str,
) -> str:
    """Create a Ready kb-board task for a promoted idea; returns plan_item_id.

    The idea id doubles as the plan_item_id: it is already unique, stable,
    and greppable, and reusing it makes promotion idempotent — if the task
    already exists the existing id is returned instead of minting a twin.
    """
    from _kb_board import check as check_mod, fmt as fmt_mod
    from _kb_board.locks import acquire_file_lock
    from _kb_board.model import TaskBlock
    from _kb_board.mutation import _write_atomic
    from _kb_board.parsing import parse_board

    board_path = _board_path_for_slug(root, project_slug)
    lock_path = board_path.with_name(board_path.name + ".lock")
    with acquire_file_lock(lock_path, timeout_s=30.0):
        board = parse_board(board_path.read_text(encoding="utf-8"))
        for existing in board.tasks:
            if existing.fields.get("plan_item_id") == idea_id:
                return idea_id
        today = datetime.now().astimezone().date().isoformat()
        fields = {
            "plan_item_id": idea_id,
            "priority": priority,
            "owner": "unassigned",
            "created": today,
            "updated": today,
            "acceptance": acceptance,
            "body": context.strip() or f"Promoted from idea {idea_id}.",
            "idea_id": idea_id,
        }
        board.sections.setdefault("Ready", []).append(
            TaskBlock(title=title, status="Ready", marker="[ ]", fields=fields)
        )
        candidate = fmt_mod.format_board(board)
        result = check_mod.check_board_text(candidate)
        if not result.ok:
            raise ValueError(f"generated board task failed kb-board check: {result}")
        _write_atomic(board_path, candidate)
    return idea_id


def promote(
    idea_id: str,
    *,
    project_slug: str,
    plan_item_id: str | None = None,
    create_task: bool = False,
    priority: str | None = None,
    context: str = "",
    hub: str | Path | None = None,
) -> dict[str, str]:
    """Promote a ready idea into a markdown kb-board task.

    Two modes: with an existing plan_item_id the card just records the
    pointer; with create_task=True the task itself is created first (status
    Ready, linked back via an idea_id field) and the minted id is recorded.
    The board mutation and the card mutation take their locks sequentially,
    never nested. Failure between the two leaves a visible board task without
    a promoted card — recoverable by re-running — never a card that claims a
    task which does not exist.
    """
    root = hub_path(hub)
    if create_task and not plan_item_id:
        with ideas_lock(root):
            _, post = _load_required_unlocked(root, idea_id)
            task_title = str(post.get("title") or idea_id)
            task_priority = priority or str(post.get("priority") or "P2")
            task_acceptance = (
                str(post.get("expected_evidence") or "").strip()
                or "Task is complete when its requested outcome is delivered."
            )
        plan_item_id = _create_board_task(
            root,
            project_slug=project_slug,
            idea_id=idea_id,
            title=task_title,
            priority=task_priority,
            acceptance=task_acceptance,
            context=context,
        )
    with ideas_lock(root):
        path, post = _load_required_unlocked(root, idea_id)
        if not plan_item_id:
            raise ValueError("promote requires --plan-item-id (or --create-task)")
        post["status"] = "promoted"
        post["promoted_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        post["project_slug"] = project_slug
        if plan_item_id:
            post["plan_item_id"] = plan_item_id
        post.content = _replace_section(
            post.content,
            "Promotion",
            "\n".join(
                [
                    f"- promoted_at: {post['promoted_at']}",
                    f"- project_slug: {project_slug}",
                    f"- plan_item_id: {plan_item_id or ''}",
                    "",
                    "Execution state after promotion belongs to the markdown kb-board task.",
                ]
            ).strip(),
        )
        _save_post_unlocked(path, post)
        _render_dashboard_unlocked(root)
    return {
        "id": idea_id,
        "status": "promoted",
        "plan_item_id": plan_item_id or "",
    }


def propose_calendar(
    idea_id: str,
    *,
    title: str,
    start: str,
    end: str,
    proposal_id: str | None = None,
    timezone: str = "Europe/Madrid",
    hub: str | Path | None = None,
) -> dict[str, str]:
    """Attach a calendar proposal without creating a calendar event."""
    root = hub_path(hub)
    with ideas_lock(root):
        path, post = _load_required_unlocked(root, idea_id)
        proposals = list(post.get("calendar_proposals") or [])
        pid = proposal_id or _next_calendar_proposal_id(start, proposals)
        if any(p.get("proposal_id") == pid for p in proposals):
            raise ValueError(f"calendar proposal already exists: {pid}")
        proposal = {
            "proposal_id": pid,
            "title": title,
            "start": start,
            "end": end,
            "timezone": timezone,
            "status": "proposed",
        }
        proposals.append(proposal)
        post["calendar_proposals"] = proposals
        post["calendar_event_ids"] = list(post.get("calendar_event_ids") or [])
        post.content = _replace_section(
            post.content,
            "Promotion",
            _promotion_with_calendar(_section(post.content, "Promotion"), proposals),
        )
        _save_post_unlocked(path, post)
        _render_dashboard_unlocked(root)
    return {"id": idea_id, "proposal_id": pid}


def approve_calendar(
    idea_id: str,
    *,
    proposal_id: str,
    event_id: str | None = None,
    approved_at: str | None = None,
    apply: bool = False,
    hub: str | Path | None = None,
) -> dict[str, str]:
    """Approve a calendar proposal and write the event pointer back."""
    root = hub_path(hub)
    with ideas_lock(root):
        path, post = _load_required_unlocked(root, idea_id)
        proposals = list(post.get("calendar_proposals") or [])
        proposal = _find_proposal(proposals, proposal_id)
        if proposal is None:
            raise ValueError(f"unknown calendar proposal: {proposal_id}")
        if event_id is None and apply:
            event_id = _create_google_calendar_event(proposal, idea_id)
        if event_id is None:
            raise ValueError("calendar approve requires event_id or apply=True")
        proposal["status"] = "approved"
        proposal["event_id"] = event_id
        proposal["approved_at"] = approved_at or datetime.now().astimezone().isoformat(timespec="seconds")
        post["calendar_proposals"] = proposals
        ids = list(post.get("calendar_event_ids") or [])
        if event_id not in ids:
            ids.append(event_id)
        post["calendar_event_ids"] = ids
        post.content = _replace_section(
            post.content,
            "Promotion",
            _promotion_with_calendar(_section(post.content, "Promotion"), proposals),
        )
        _save_post_unlocked(path, post)
        _render_dashboard_unlocked(root)
    return {"id": idea_id, "proposal_id": proposal_id, "event_id": event_id}


def mark_done(
    idea_id: str,
    *,
    outcome: str,
    hub: str | Path | None = None,
) -> dict[str, str]:
    """Write terminal outcome mirror back into the idea card."""
    root = hub_path(hub)
    with ideas_lock(root):
        path, post = _load_required_unlocked(root, idea_id)
        post["status"] = "done"
        post["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        post.content = _replace_section(
            post.content,
            "Outcome",
            f"{outcome.strip()}\n\nCompleted at: {post['completed_at']}",
        )
        _save_post_unlocked(path, post)
        _render_dashboard_unlocked(root)
    return {"id": idea_id, "status": "done"}


def render_dashboard(*, hub: str | Path | None = None) -> Path:
    root = hub_path(hub)
    with ideas_lock(root):
        _render_dashboard_unlocked(root)
    return dashboard_path(root)


def brief(*, limit: int = 3, hub: str | Path | None = None) -> str:
    """Return deterministic ready/promoted idea digest for daily brief."""
    root = hub_path(hub)
    cards = _list_cards(root)
    candidates: list[tuple[int, str, frontmatter.Post]] = []
    for path, post in cards:
        status = str(post.get("status") or "")
        if status not in {"ready", "promoted"}:
            continue
        candidates.append((_priority_rank(str(post.get("priority") or "P3")), path.name, post))
    candidates.sort(key=lambda item: (item[0], item[1]))
    lines: list[str] = []
    for _, _, post in candidates[:limit]:
        idea_id = str(post.get("id") or "")
        title = str(post.get("title") or idea_id)
        priority = str(post.get("priority") or "P3")
        action = str(post.get("next_action") or _first_line(_section(post.content, "Next action")) or "Define next action.")
        evidence = str(post.get("expected_evidence") or _evidence_from_next_action(post.content) or "Define evidence.")
        lines.append(f"- {priority} {idea_id}: {title}\n  Step: {action}\n  Evidence: {evidence}")
    if not lines:
        return ""
    return "Idea proposals:\n" + "\n".join(lines)


def load(idea_id: str, *, hub: str | Path | None = None) -> frontmatter.Post | None:
    root = hub_path(hub)
    path = ideas_dir(root) / f"{idea_id}.md"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return frontmatter.load(f)


def _default_frontmatter(
    *,
    idea_id: str,
    title: str,
    source: str,
    now: datetime,
    owner: str,
) -> dict[str, Any]:
    return {
        "id": idea_id,
        "title": title,
        "created_at": now.isoformat(timespec="seconds"),
        "source": source,
        "status": "captured",
        "priority": "P2",
        "priority_scored_at": now.date().isoformat(),
        "materiality": "cheap-test",
        "strategic_lines": [],
        "owner": owner,
        "plan_item_id": None,
        "roadmap_ref": None,
        "calendar_event_ids": [],
        "calendar_proposals": [],
        "park_until": None,
        "killed_reason": None,
        "merged_into": None,
    }


def _default_body(title: str, raw: str, now: datetime) -> str:
    return f"""# {title}

## Raw idea
{raw}

## Interpretation
Captured verbatim at {now.isoformat(timespec="seconds")}. Interpretation is pending triage.

## Why it matters
Pending triage against `personal/priority-profile.md`.

## Dedupe
Pending triage.

## Critique
Pending. Required only if materiality becomes `material`.

## Priority
- priority: P2
- materiality: cheap-test
- scored_at: {now.date().isoformat()}

## Next action
Triage this idea.

Evidence: card routed to ready, critique, parked, killed, or merged.

## Promotion
Not promoted.

## Outcome
Pending.
"""


def _coerce_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime.now().astimezone()


def _derive_title(raw: str, title: str | None) -> str:
    if title and title.strip():
        return title.strip()
    first = raw.splitlines()[0].strip()
    first = re.sub(r"\s+", " ", first).strip(" .")
    ascii_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+.-]*", first)
    if len(ascii_words) >= 2:
        return " ".join(ascii_words[:5])
    words = first.split()
    return " ".join(words[:8]) if words else "Idea"


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    parts = [p for p in slug.split("-") if p]
    return "-".join(parts[:5])


def _unique_idea_id(ts: datetime, slug: str, cards: Path) -> str:
    base = f"idea-{ts.strftime('%Y%m%d-%H%M')}-{slug}"
    candidate = base
    suffix = 2
    while (cards / f"{candidate}.md").exists():
        candidate = f"{base}-{suffix:02d}"
        suffix += 1
    return candidate


def _write_post_atomic(path: Path, post: frontmatter.Post, directory: Path) -> None:
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=str(directory),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _save_post_unlocked(path: Path, post: frontmatter.Post) -> None:
    directory = path.parent
    _write_post_atomic(path, post, directory)


def _load_required_unlocked(root: Path, idea_id: str) -> tuple[Path, frontmatter.Post]:
    path = ideas_dir(root) / f"{idea_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"unknown idea: {idea_id}")
    with path.open(encoding="utf-8") as f:
        return path, frontmatter.load(f)


def _list_cards(root: Path) -> list[tuple[Path, frontmatter.Post]]:
    cards = []
    for path in sorted(ideas_dir(root).glob("idea-*.md")):
        if path.name.startswith("."):
            continue
        try:
            with path.open(encoding="utf-8") as f:
                cards.append((path, frontmatter.load(f)))
        except Exception:
            continue
    return cards


def _render_dashboard_unlocked(root: Path) -> None:
    dash = dashboard_path(root)
    dash.parent.mkdir(parents=True, exist_ok=True)
    cards = _list_cards(root)
    active = []
    parked = []
    terminal = []
    for path, post in cards:
        status = str(post.get("status") or "captured")
        row = _dashboard_row(path, post)
        if status in STATUS_PARKED:
            parked.append(row)
        elif status in STATUS_TERMINAL:
            terminal.append(row)
        else:
            active.append(row)

    body = "\n".join(
        [
            "---",
            f"updated: {_today()}",
            "status: active",
            "generated_by: kb-idea",
            "---",
            "",
            "# Ideas",
            "",
            "> Dashboard личных идей. Канон каждой идеи — карточка в `personal/ideas/`. Этот файл рендерится из карточек; статус редактируется в карточке.",
            "",
            "## Protocol",
            "",
            "1. Capture idea into `personal/ideas/<idea-id>.md`.",
            "2. Render/update this dashboard from cards.",
            "3. Daily triage dedupes, scores, and routes each idea.",
            "4. Material ideas get critique.",
            "5. Ready ideas can be promoted into markdown kb-board tasks or proposed in daily brief.",
            "6. Calendar events are created only after explicit approve.",
            "",
            "## Active Queue",
            "",
            _table(active),
            "",
            "## Parking Lot",
            "",
            _table(parked) if parked else "_Пусто._",
            "",
            "## Killed / Archived",
            "",
            _table(terminal) if terminal else "_Пусто._",
            "",
        ]
    )
    tmp = dash.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, dash)


def _dashboard_row(path: Path, post: frontmatter.Post) -> list[str]:
    idea_id = str(post.get("id") or path.stem)
    title = str(post.get("title") or idea_id)
    priority = str(post.get("priority") or "P3")
    status = str(post.get("status") or "captured")
    next_action = str(post.get("next_action") or _first_line(_section(post.content, "Next action")) or "")
    review = str(post.get("next_review") or post.get("park_until") or post.get("priority_scored_at") or "")
    return [
        f"[{idea_id}](ideas/{path.name})",
        priority,
        status,
        title,
        next_action,
        review,
    ]


def _table(rows: list[list[str]]) -> str:
    header = "| ID | Priority | Status | Title | Next action | Review |"
    sep = "|---|---|---|---|---|---|"
    if not rows:
        return header + "\n" + sep
    rendered = [header, sep]
    for row in rows:
        rendered.append("| " + " | ".join(_table_cell(c) for c in row) + " |")
    return "\n".join(rendered)


def _table_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = text.replace("<!--", "<! --").replace("-->", "-- >")
    return re.sub(r"\s+", " ", text).strip()


def _replace_section(content: str, heading: str, new_body: str) -> str:
    pattern = re.compile(
        rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    replacement = f"## {heading}\n{new_body.strip()}\n\n"
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    suffix = "" if content.endswith("\n") else "\n"
    return f"{content}{suffix}\n{replacement}"


def _section(content: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def _first_line(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("Evidence:"):
            return clean
    return ""


def _evidence_from_next_action(content: str) -> str:
    text = _section(content, "Next action")
    for line in text.splitlines():
        if line.strip().startswith("Evidence:"):
            return line.split("Evidence:", 1)[1].strip()
    return ""


def _promotion_with_calendar(current: str, proposals: list[dict[str, Any]]) -> str:
    base = current.strip()
    if not base or base == "Not promoted.":
        base = "Not promoted."
    lines = [base, "", "Calendar proposals:"]
    for proposal in proposals:
        status = proposal.get("status", "proposed")
        event = proposal.get("event_id", "")
        event_part = f" -> {event}" if event else ""
        lines.append(
            f"- {proposal['proposal_id']} [{status}]: {proposal['start']}..{proposal['end']} — {proposal['title']}{event_part}"
        )
    return "\n".join(lines).strip()


def _find_proposal(proposals: list[dict[str, Any]], proposal_id: str) -> dict[str, Any] | None:
    for proposal in proposals:
        if proposal.get("proposal_id") == proposal_id:
            return proposal
    return None


def _next_calendar_proposal_id(start: str, proposals: list[dict[str, Any]]) -> str:
    date_part = re.sub(r"[^0-9]", "", start[:10]) or datetime.now().strftime("%Y%m%d")
    used = {p.get("proposal_id") for p in proposals}
    i = 1
    while True:
        candidate = f"cal-{date_part}-{i:02d}"
        if candidate not in used:
            return candidate
        i += 1


def _create_google_calendar_event(proposal: dict[str, Any], idea_id: str) -> str:
    """Route through the shared calendar adapter — the single live calendar
    writer in the system. Idempotency, fail-closed behavior, and tests are
    consistent with kb-followup. (Spec: Existing Writer Hardening — two live
    calendar writers are not allowed.)

    The adapter derives its deterministic idempotency key from the event `id`,
    so that id MUST be globally unique. A calendar `proposal_id` (e.g.
    `cal-20260626-01`) is only unique WITHIN one idea card — two different ideas
    can each mint the same `cal-<date>-01`. We therefore namespace it with the
    idea id; otherwise distinct reminders would collapse into one event."""
    import os
    import sys

    bin_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    from _kb_calendar import adapter as cal_adapter
    from _kb_calendar.errors import CalendarError

    pid = proposal.get("proposal_id") or proposal.get("id")
    if not pid:
        # never fall back to a constant — that would collapse every id-less
        # proposal onto a single event. Fail closed instead.
        raise RuntimeError(
            "calendar proposal has no stable id; refusing to create an event "
            "(would risk collapsing distinct reminders)"
        )
    payload = {
        "id": f"idea:{idea_id}:{pid}",
        "summary": proposal["title"],
        "start": proposal["start"],
        "end": proposal["end"],
        "timezone": proposal.get("timezone", "Europe/Madrid"),
        "source": "kb-idea",
    }
    try:
        pointer = cal_adapter.get_adapter().create_event(payload)
    except CalendarError as e:
        raise RuntimeError(f"calendar create_event failed: {e}")
    event_id = pointer.get("event_id") or ""
    if not event_id:
        raise RuntimeError("calendar create_event returned no event id")
    return event_id[:500]


def _priority_rank(priority: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(priority, 9)


def _validate_priority(priority: str) -> None:
    if priority not in {"P0", "P1", "P2", "P3"}:
        raise ValueError(f"invalid priority: {priority}")


def _validate_status(status: str) -> None:
    allowed = STATUS_ACTIVE | STATUS_PARKED | STATUS_TERMINAL
    if status not in allowed:
        raise ValueError(f"invalid status: {status}")


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()
