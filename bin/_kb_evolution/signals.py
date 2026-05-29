from __future__ import annotations

import pathlib

from . import scaffold


def append_signal(
    knowledge_path: pathlib.Path,
    *,
    signal_id: str,
    source: str,
    surface: str,
    summary: str,
) -> dict:
    """Append a pending evolution signal if it is not already present."""
    scaffold.ensure_evolution_tree(knowledge_path)
    target = pathlib.Path(knowledge_path) / "evolution" / "pending-signals.md"
    text = target.read_text(encoding="utf-8")
    if signal_id in text:
        return {
            "signal_id": signal_id,
            "status": "exists",
            "path": str(target),
        }
    line = f"- [ ] `{signal_id}` — source: {source} — surface: {surface} — {summary}\n"
    if "## Open\n" in text:
        text = text.replace("## Open\n", "## Open\n\n" + line, 1)
    else:
        text = text.rstrip() + "\n\n## Open\n\n" + line
    target.write_text(text, encoding="utf-8")
    return {
        "signal_id": signal_id,
        "status": "appended",
        "path": str(target),
    }
