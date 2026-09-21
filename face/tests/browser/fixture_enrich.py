"""Add representative existing history via the real RunStore, without agent runs."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from vepol_face.runs import RunStore

store = RunStore(pathlib.Path(sys.argv[2]) / "state")
records = json.load(sys.stdin)
statuses = ("done", "done", "stopped", "degraded", "failed", "interrupted")
for i, record in enumerate(records):
    conv_id = record["id"]
    store.append_message(conv_id, "user", record["title"])
    run = store.start_run(conv_id, run_id=f"fixture-run-{i:02}")
    store.finish_run(conv_id, run.id, status=statuses[i % len(statuses)],
                     text=record["preview"], reason="Existing test history",
                     evidence={"fixture": True})
    if i in (54, 55):
        store.start_run(conv_id, run_id=f"fixture-active-{i}")
print(json.dumps({"enriched": len(records)}))
