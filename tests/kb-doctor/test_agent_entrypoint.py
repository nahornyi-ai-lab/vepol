"""Acceptance tests for kb-doctor agent-entrypoint mode."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import textwrap


HUB_REPO = pathlib.Path(__file__).resolve().parents[2]
DOCTOR = HUB_REPO / "bin" / "kb-doctor"


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def run_doctor(hub: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["KB_HUB"] = str(hub)
    return subprocess.run(
        [str(DOCTOR), "agent-entrypoint", "--format", "json", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def findings(hub: pathlib.Path, *args: str) -> list[dict]:
    result = run_doctor(hub, *args)
    assert result.returncode in {0, 2}, result.stderr
    return json.loads(result.stdout)["findings"]


def make_hub(tmp_path: pathlib.Path) -> pathlib.Path:
    hub = tmp_path / "hub"
    hub.mkdir()
    write(hub / "AGENTS.md", "# Hub AGENTS\n")
    write(hub / "CLAUDE.md", "# Claude adapter\n\nRead `AGENTS.md`.\n")
    write(hub / "GEMINI.md", "# Gemini adapter\n\n@./AGENTS.md\n")
    write(hub / "_template" / "AGENTS.md", "# {{PROJECT_NAME}} AGENTS\n")
    write(hub / "_template" / "CLAUDE.md", "# Claude adapter\n\nRead `AGENTS.md`.\n")
    write(hub / "_template" / "GEMINI.md", "# Gemini adapter\n\n@./AGENTS.md\n")
    write(hub / "bin" / "new-wiki", "render \"$TEMPLATE/AGENTS.md\" \"$PROJECT_PATH/AGENTS.md\"\n")
    write(hub / "bin" / "kb-seed-sync", "cp \"$HUB/AGENTS.md\" \"$SEED/knowledge/AGENTS.md\"\n")
    write(hub / "bin" / "kb-bootstrap-manifest", '"source_path": "knowledge/AGENTS.md"\n')
    return hub


def assert_finding(items: list[dict], prefix: str) -> None:
    assert any(item["id"].startswith(prefix) for item in items), items


def test_missing_hub_agents_is_p0(tmp_path):
    hub = make_hub(tmp_path)
    (hub / "AGENTS.md").unlink()

    items = findings(hub)

    assert_finding(items, "agent-entrypoint:missing-hub-agents")
    assert any(item["severity"] == "P0" for item in items)


def test_long_adapter_is_p1(tmp_path):
    hub = make_hub(tmp_path)
    write(hub / "CLAUDE.md", "\n".join(["Read AGENTS.md"] * 31))

    items = findings(hub)

    assert_finding(items, "agent-entrypoint:adapter-too-long")
    assert any(item["severity"] == "P1" for item in items)


def test_adapter_without_agents_reference_is_p1(tmp_path):
    hub = make_hub(tmp_path)
    write(hub / "CLAUDE.md", "# Claude adapter\n\nRead old schema.\n")

    items = findings(hub)

    assert_finding(items, "agent-entrypoint:adapter-missing-agents")
    assert any(item["severity"] == "P1" for item in items)


def test_gemini_importing_claude_is_p1(tmp_path):
    hub = make_hub(tmp_path)
    write(hub / "GEMINI.md", "# Gemini adapter\n\n@./CLAUDE.md\n")

    items = findings(hub)

    assert_finding(items, "agent-entrypoint:gemini-imports-claude")
    assert any(item["severity"] == "P1" for item in items)


def test_agents_with_bare_at_token_is_p1(tmp_path):
    hub = make_hub(tmp_path)
    write(hub / "AGENTS.md", "# Hub AGENTS\n\nUse @mention only in chat.\n")

    items = findings(hub)

    assert_finding(items, "agent-entrypoint:gemini-unsafe-at-token")
    assert any(item["severity"] == "P1" for item in items)


def test_happy_path_has_no_p0_or_p1(tmp_path):
    hub = make_hub(tmp_path)

    items = findings(hub)

    assert not [item for item in items if item["severity"] in {"P0", "P1"}]
