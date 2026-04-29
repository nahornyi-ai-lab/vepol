"""preflight.py — scoped journal-integrity scan (CR10-B1 + CR11-B2).

Before any kb-backlog op, detector run, or recovery, we scan the relevant
audit segments for `terminal_count > 1` per tx_id (per-file) or per xfer_id
(coordinator). Any duplicate terminal indicates pre-existing corruption that
we cannot resolve algorithmically — refuse mutations and emit escalation.

Scoping (CR11-B2): preflight is scoped to the slug being acted upon.
Per-file: we read only that slug's segment chain. Xfer: we read only
records where `slug ∈ {src_slug, dst_slug}`. Unrelated corruption does NOT
block mutations on different slugs.

Global corruption discovery is a separate manual / cron subcommand
(`kb-doctor journal-integrity`), invoked by humans, not on every op.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from . import journal

HUB = pathlib.Path(os.environ.get("KB_HUB", os.path.expanduser("~/knowledge")))
ESCALATIONS_PATH = HUB / "escalations.md"


class JournalCorruption(Exception):
    """Raised when terminal_count > 1 detected. Mutations must be refused."""
    def __init__(self, scope: str, tx_or_xfer_id: str, terminals: list[str]):
        self.scope = scope  # "slug:<slug>" or "xfer"
        self.tx_or_xfer_id = tx_or_xfer_id
        self.terminals = terminals
        super().__init__(
            f"journal corruption: {scope} {tx_or_xfer_id} has terminals {terminals}; "
            f"manual resolve required"
        )


@dataclass
class PreflightReport:
    slug_corruption: list[JournalCorruption]
    xfer_corruption: list[JournalCorruption]

    @property
    def has_corruption(self) -> bool:
        return bool(self.slug_corruption or self.xfer_corruption)


def scan_per_file(slug: str) -> list[JournalCorruption]:
    """Scan slug's audit segments for tx_ids with terminal_count > 1."""
    corruptions: list[JournalCorruption] = []
    grouped = journal.collapse_by_tx(journal.iter_records_chain(slug))
    for tid, st in grouped.items():
        if st.terminal_count > 1:
            phases = [t.get("phase", "?") for t in st.terminals]
            corruptions.append(JournalCorruption(f"slug:{slug}", tid, phases))
    return corruptions


def scan_xfer_for_slug(slug: str) -> list[JournalCorruption]:
    """Scan _xfer journal for xfer_ids touching `slug`, where terminal_count > 1."""
    corruptions: list[JournalCorruption] = []
    seen: set[str] = set()
    grouped = journal.collapse_xfer_by_id(journal.iter_records_chain("_xfer"))
    for xid, st in grouped.items():
        if st.prepared is None:
            continue
        src = st.prepared.get("src_slug")
        dst = st.prepared.get("dst_slug")
        if slug not in (src, dst):
            continue
        if st.terminal_count > 1 and xid not in seen:
            phases = [t.get("phase", "?") for t in st.terminals]
            corruptions.append(JournalCorruption("xfer", xid, phases))
            seen.add(xid)
    return corruptions


def find_dangling_xfers_for_slug(slug: str) -> list[dict]:
    """Return list of xfer-prepared records (without terminal) where
    `slug ∈ {src_slug, dst_slug}`. Used by `_open_op` to decide whether
    coordinator recovery is needed before a normal slug mutation.
    """
    out: list[dict] = []
    grouped = journal.collapse_xfer_by_id(journal.iter_records_chain("_xfer"))
    for xid, st in grouped.items():
        if st.prepared is None:
            continue
        if st.terminal_count >= 1:
            continue
        rec = st.prepared
        if slug in (rec.get("src_slug"), rec.get("dst_slug")):
            out.append(rec)
    return out


def preflight_for_slug(slug: str) -> PreflightReport:
    """Scoped preflight for a single-slug op. Reads slug's segments + xfer
    records where slug ∈ {src, dst}.
    """
    return PreflightReport(
        slug_corruption=scan_per_file(slug),
        xfer_corruption=scan_xfer_for_slug(slug),
    )


def preflight_for_xfer(src: str, dst: str) -> PreflightReport:
    """Preflight for an xfer op. Scans both slugs + xfer records touching either.

    Deduplicates xfer corruption entries: an xfer touching both src+dst could
    otherwise appear twice in the report.
    """
    xfer_corr = scan_xfer_for_slug(src)
    seen = {c.tx_or_xfer_id for c in xfer_corr}
    for c in scan_xfer_for_slug(dst):
        if c.tx_or_xfer_id not in seen:
            xfer_corr.append(c)
            seen.add(c.tx_or_xfer_id)
    return PreflightReport(
        slug_corruption=scan_per_file(src) + scan_per_file(dst),
        xfer_corruption=xfer_corr,
    )


def assert_no_corruption(report: PreflightReport, escalate: bool = True) -> None:
    """If corruption found, escalate to escalations.md and raise."""
    if not report.has_corruption:
        return
    if escalate:
        _append_escalation(report)
    # Raise the first corruption found.
    if report.slug_corruption:
        raise report.slug_corruption[0]
    raise report.xfer_corruption[0]


def _append_escalation(report: PreflightReport) -> None:
    lines: list[str] = []
    for c in report.slug_corruption:
        lines.append(
            f"- [ ] journal corruption {c.scope} tx {c.tx_or_xfer_id} terminals {c.terminals}"
        )
    for c in report.xfer_corruption:
        lines.append(
            f"- [ ] journal corruption xfer {c.tx_or_xfer_id} terminals {c.terminals}"
        )
    if not lines:
        return
    text = ESCALATIONS_PATH.read_text(encoding="utf-8") if ESCALATIONS_PATH.is_file() else "# Escalations\n\n## Open\n\n"
    if "## Open" not in text:
        text = text.rstrip() + "\n\n## Open\n\n"
    # Append at end of Open section (just append at end of text — humans will sort it).
    text = text.rstrip() + "\n" + "\n".join(lines) + "\n"
    ESCALATIONS_PATH.write_text(text, encoding="utf-8")
