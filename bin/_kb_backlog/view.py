"""view.py — read-only viewer (back-compat for bare `kb-backlog`).

Identical behavior to the pre-Phase-1b kb-backlog: scan all backlogs, group
by status, render colored output. Pulled out so the CLI dispatcher can keep
view + mutation subcommands distinct.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))

STATUS_MAP = {
    "[ ]": "open",
    "[>]": "in_progress",
    "[x]": "done",
    "[X]": "done",
}

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "cyan": "\033[36m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "gray": "\033[90m",
    "red": "\033[31m",
}

LINE_RE = re.compile(r"^\s*-\s*(\[[ xX>]\])\s*(.+?)\s*$")


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _looks_like_placeholder(body: str) -> bool:
    return bool(re.search(r"<[^>]{2,}>", body)) and "YYYY-MM-DD" in body


def _parse_backlog(path: pathlib.Path, owner: str) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    raw = _strip_html_comments(raw)
    items = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        m = LINE_RE.match(line)
        if not m:
            continue
        marker, body = m.group(1), m.group(2)
        status = STATUS_MAP.get(marker)
        if status is None:
            continue
        if _looks_like_placeholder(body):
            continue
        items.append({
            "owner": owner,
            "status": status,
            "body": body,
            "path": path,
            "lineno": lineno,
        })
    return items


def _collect(project_filter, hub_only):
    items = []
    if not project_filter:
        items.extend(_parse_backlog(HUB / "backlog.md", owner="hub"))
    if not hub_only:
        proj = HUB / "projects"
        if proj.exists():
            for link in sorted(proj.iterdir()):
                # Live hubs use symlinks resolving to <project>/knowledge/
                # Demo hub uses plain dirs with backlog.md flat inside
                if link.is_symlink():
                    backlog_path = link.resolve() / "backlog.md"
                elif link.is_dir():
                    flat = link / "backlog.md"
                    nested = link / "knowledge" / "backlog.md"
                    backlog_path = flat if flat.exists() else nested
                else:
                    continue
                slug = link.name
                if project_filter and slug != project_filter:
                    continue
                items.extend(_parse_backlog(backlog_path, owner=slug))
    return items


def _color(s, name):
    if not sys.stdout.isatty():
        return s
    return f"{ANSI[name]}{s}{ANSI['reset']}"


def _render_group(title, items, color_name):
    if not items:
        return
    print(_color(f"\n── {title} ({len(items)}) ──", color_name))
    by_owner = {}
    for it in items:
        by_owner.setdefault(it["owner"], []).append(it)
    for owner in sorted(by_owner):
        print(_color(f"\n  {owner}", "bold"))
        for it in by_owner[owner]:
            print(f"    {it['body']}")


def run_view(args) -> int:
    items = _collect(args.project, args.hub_only)
    if not items:
        print("(no backlog items found)", file=sys.stderr)
        return 0

    show_open = args.open or args.all or (not any([args.in_progress, args.done]))
    show_in_progress = args.in_progress or args.all
    show_done = args.done or args.all

    if show_open:
        _render_group("Open", [x for x in items if x["status"] == "open"], "yellow")
    if show_in_progress:
        _render_group("In progress", [x for x in items if x["status"] == "in_progress"], "cyan")
    if show_done:
        done = [x for x in items if x["status"] == "done"]
        _render_group("Done (recent 20)", done[-20:], "gray")

    total_open = sum(1 for x in items if x["status"] == "open")
    total_ip = sum(1 for x in items if x["status"] == "in_progress")
    total_done = sum(1 for x in items if x["status"] == "done")
    print(_color(f"\n— summary: {total_open} open, {total_ip} in progress, {total_done} done —", "gray"))
    return 0
