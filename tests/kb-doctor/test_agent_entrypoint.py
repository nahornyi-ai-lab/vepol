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
    write(hub / "_template" / "AGENTS.md", "# {{PROJECT_NAME}} AGENTS\n")
    write(hub / "_template" / "CLAUDE.md", "# Claude adapter\n\nRead `AGENTS.md`.\n")
    write(hub / "bin" / "new-wiki", "render \"$TEMPLATE/AGENTS.md\" \"$PROJECT_PATH/AGENTS.md\"\n")
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


def test_agents_with_bare_at_token_is_p1(tmp_path):
    # Antigravity CLI inherits Gemini-style `@<token>` import semantics from
    # `~/.gemini/GEMINI.md`. Bare at-tokens in any file `agy` loads must be
    # escaped (`` `@`-mention ``) to avoid false-positive file imports.
    hub = make_hub(tmp_path)
    write(hub / "AGENTS.md", "# Hub AGENTS\n\nUse @mention only in chat.\n")

    items = findings(hub)

    assert_finding(items, "agent-entrypoint:gemini-unsafe-at-token")
    assert any(item["severity"] == "P1" for item in items)


def test_happy_path_has_no_p0_or_p1(tmp_path):
    hub = make_hub(tmp_path)

    items = findings(hub)

    assert not [item for item in items if item["severity"] in {"P0", "P1"}]


def test_template_and_gemini_adapters_are_optional(tmp_path):
    # new-wiki creates no project adapter and install.sh ships no GEMINI.md, so
    # only the hub CLAUDE.md is required; the others are linted when present.
    hub = make_hub(tmp_path)
    (hub / "_template" / "CLAUDE.md").unlink()

    items = findings(hub)

    assert not [item for item in items if item["severity"] in {"P0", "P1"}], items

    write(hub / "GEMINI.md", "# Legacy Gemini adapter\n\nRead CLAUDE.md.\n")
    items = findings(hub)
    assert_finding(items, "agent-entrypoint:adapter-missing-agents")
    assert_finding(items, "agent-entrypoint:gemini-imports-claude")


def test_missing_hub_claude_adapter_is_p1(tmp_path):
    hub = make_hub(tmp_path)
    (hub / "CLAUDE.md").unlink()

    items = findings(hub)

    missing = [item for item in items if item["id"].startswith("agent-entrypoint:missing-adapter")]
    assert [item["file"] for item in missing] == [str(hub / "CLAUDE.md")], items
    assert missing[0]["severity"] == "P1"
    assert "install.sh" in missing[0]["message"]


def test_kb_seed_sync_is_not_required(tmp_path):
    # kb-seed-sync is the maintainer's hub-only tool; it does not ship.
    hub = make_hub(tmp_path)
    assert not (hub / "bin" / "kb-seed-sync").exists()

    items = findings(hub)

    assert not [item for item in items if "kb-seed-sync" in item["file"]], items


def test_strict_exits_one_on_p1_only(tmp_path):
    hub = make_hub(tmp_path)
    write(hub / "CLAUDE.md", "# Claude adapter\n\nRead old schema.\n")

    assert run_doctor(hub).returncode == 0
    assert run_doctor(hub, "--strict").returncode == 1
    clean = tmp_path / "clean"
    clean.mkdir()
    assert run_doctor(make_hub(clean), "--strict").returncode == 0


def test_shipped_contract_and_adapters_are_clean(tmp_path):
    # The files install.sh puts in a hub must pass the guard as shipped:
    # no bare @ token in knowledge/AGENTS.md or _template/AGENTS.md, and thin
    # adapters that point to AGENTS.md.
    hub = tmp_path / "hub"
    for rel_src, rel_dst in (
        ("knowledge/AGENTS.md", "AGENTS.md"),
        ("knowledge/CLAUDE.md", "CLAUDE.md"),
        ("_template/AGENTS.md", "_template/AGENTS.md"),
        ("_template/CLAUDE.md", "_template/CLAUDE.md"),
        ("bin/new-wiki", "bin/new-wiki"),
        ("bin/kb-bootstrap-manifest", "bin/kb-bootstrap-manifest"),
    ):
        dst = hub / rel_dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((HUB_REPO / rel_src).read_bytes())

    result = run_doctor(hub, "--strict")
    items = json.loads(result.stdout)["findings"]

    assert result.returncode == 0, items
    assert not [item for item in items if item["severity"] in {"P0", "P1"}], items


def test_cycle_retro_prompt_points_to_shipped_locations():
    # The retro agent runs in <project>/knowledge/, but the daily plan is the
    # hub's (kb-orchestrator-cycle writes ~/knowledge/daily-plan/<date>.md), and
    # the entity-event categories live in the project template AGENTS.md.
    prompt = (HUB_REPO / "bin" / "templates" / "cycle-retro.prompt.md").read_text(encoding="utf-8")
    template = (HUB_REPO / "_template" / "AGENTS.md").read_text(encoding="utf-8")

    assert "~/knowledge/daily-plan/{{DATE}}.md" in prompt
    assert "`daily-plan/{{DATE}}.md`" not in prompt
    assert "~/knowledge/_template/AGENTS.md` (Significant external state changes)" in prompt
    assert "## Significant external state changes" in template
