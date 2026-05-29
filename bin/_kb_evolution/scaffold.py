from __future__ import annotations

import pathlib


LEDGER_HEADER = """# Vepol Evolution mutations ledger

Append-only YAML-block-per-entry ledger. Do not edit past entries in place.
"""

PENDING_SIGNALS_HEADER = """# Pending evolution signals

Durable queue for observed correction/incident/retro signals before proposal.

## Open

## Resolved
"""


def ensure_evolution_tree(knowledge_path: pathlib.Path) -> None:
    """Create the v0-minimal evolution directory layout if absent."""
    evolution = pathlib.Path(knowledge_path) / "evolution"
    for name in ("proposals", "archive", "replay-fixtures"):
        (evolution / name).mkdir(parents=True, exist_ok=True)
    ledger = evolution / "mutations.md"
    if not ledger.exists():
        ledger.write_text(LEDGER_HEADER, encoding="utf-8")
    pending = evolution / "pending-signals.md"
    if not pending.exists():
        pending.write_text(PENDING_SIGNALS_HEADER, encoding="utf-8")
