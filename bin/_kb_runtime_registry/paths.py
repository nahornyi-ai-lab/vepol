"""Every location derives from KB_HUB so a sandbox hub is a real sandbox."""
from __future__ import annotations

import os
import pathlib


class Paths:
    def __init__(self, hub: "str | os.PathLike | None" = None):
        raw = hub or os.environ.get("KB_HUB") or (pathlib.Path.home() / "knowledge")
        self.hub = pathlib.Path(raw).expanduser()
        self.orchestrator = self.hub / ".orchestrator"
        self.roster = self.orchestrator / "cli-tools.tsv"
        self.broker_state = self.orchestrator / "state.json"
        self.cache = self.orchestrator / "runtime-registry.json"
        self.claude_run = self.hub / "bin" / "kb-claude-run"
