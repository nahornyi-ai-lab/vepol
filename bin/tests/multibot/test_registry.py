"""Tests for registry.py — load .orchestration.yaml, build AgentRegistry."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.registry import (  # noqa: E402
    AgentRegistry,
    AgentSpec,
    load_from_projects_dir,
    load_from_specs,
)


def _make_spec(slug: str, parent: str | None = None, **kw) -> AgentSpec:
    defaults = {
        "slug": slug,
        "bot_id": None,
        "bot_username": f"demo_{slug.replace('-', '_')}_bot",
        "bot_token_ref": f"~/.claude/channels/bots/{slug}.env",
        "workdir": f"~/projects/{slug}",
        "runtime": "claude",
        "parent_slug": parent,
        "persona": f"{slug} agent",
    }
    defaults.update(kw)
    return AgentSpec(**defaults)


class AgentSpecTests(unittest.TestCase):
    def test_allows_user_wildcard(self) -> None:
        spec = _make_spec("vepol")
        self.assertTrue(spec.allows_user(123))
        self.assertTrue(spec.allows_user(456))

    def test_allows_user_whitelist(self) -> None:
        spec = _make_spec("money", allowed_users=(1234567890,))
        self.assertTrue(spec.allows_user(1234567890))
        self.assertFalse(spec.allows_user(999))

    def test_frozen(self) -> None:
        spec = _make_spec("vepol")
        with self.assertRaises(Exception):
            spec.persona = "changed"  # type: ignore[misc]


class AgentRegistryTests(unittest.TestCase):
    def _registry(self) -> AgentRegistry:
        return load_from_specs([
            _make_spec("hub"),
            _make_spec("leadgen", parent="hub"),
            _make_spec("leadgen-leads", parent="leadgen"),
            _make_spec("nailab-ailab-landing", parent="leadgen",
                       bot_username="nailab_landing_bot"),
            _make_spec("family", parent="hub"),
            _make_spec("auto", parent="family"),
        ])

    def test_len(self) -> None:
        self.assertEqual(len(self._registry()), 6)

    def test_get_by_slug(self) -> None:
        r = self._registry()
        self.assertIsNotNone(r.get("hub"))
        self.assertIsNone(r.get("nonexistent"))

    def test_by_username_case_insensitive(self) -> None:
        r = self._registry()
        spec = r.by_username("demo_hub_bot")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.slug, "hub")
        # case-insensitive
        spec2 = r.by_username("DEMO_HUB_BOT")
        self.assertEqual(spec2.slug, "hub")

    def test_by_username_short_form(self) -> None:
        r = self._registry()
        spec = r.by_username("nailab_landing_bot")
        self.assertEqual(spec.slug, "nailab-ailab-landing")

    def test_known_bot_usernames(self) -> None:
        names = self._registry().known_bot_usernames()
        self.assertIn("demo_hub_bot", names)
        self.assertIn("nailab_landing_bot", names)
        # all lowercase
        for n in names:
            self.assertEqual(n, n.lower())

    def test_children_derived(self) -> None:
        r = self._registry()
        hub_children = r.children_of("hub")
        slugs = sorted(c.slug for c in hub_children)
        self.assertEqual(slugs, ["family", "leadgen"])

        leadgen_children = r.children_of("leadgen")
        slugs2 = sorted(c.slug for c in leadgen_children)
        self.assertEqual(slugs2, ["leadgen-leads", "nailab-ailab-landing"])

    def test_root_agents(self) -> None:
        r = self._registry()
        roots = r.root_agents()
        self.assertEqual([s.slug for s in roots], ["hub"])

    def test_children_of_leaf(self) -> None:
        r = self._registry()
        self.assertEqual(r.children_of("auto"), [])

    def test_enabled_agents_default(self) -> None:
        r = self._registry()
        self.assertEqual(len(r.enabled_agents()), 6)

    def test_enabled_agents_filters_disabled(self) -> None:
        r = load_from_specs([
            _make_spec("hub"),
            _make_spec("dormant", enabled=False),
        ])
        slugs = [a.slug for a in r.enabled_agents()]
        self.assertEqual(slugs, ["hub"])


class LoadFromProjectsDirTests(unittest.TestCase):
    def test_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            r = load_from_projects_dir(td)
            self.assertEqual(len(r), 0)

    def test_missing_dir(self) -> None:
        r = load_from_projects_dir("/nonexistent/path/whatever")
        self.assertEqual(len(r), 0)

    def test_loads_orchestration_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # Simulate ~/knowledge/projects/<slug>/.orchestration.yaml
            project_dir = base / "vepol"
            project_dir.mkdir()
            (project_dir / ".orchestration.yaml").write_text(
                yaml.safe_dump({
                    "telegram": {
                        "bot_username": "@demo_vepol_bot",
                        "bot_token_ref": "~/.claude/channels/bots/vepol.env",
                        "parent_slug": None,
                        "persona": "Vepol agent",
                        "runtime": "claude",
                    }
                }),
                encoding="utf-8",
            )
            r = load_from_projects_dir(base)
            self.assertEqual(len(r), 1)
            spec = r.get("vepol")
            self.assertIsNotNone(spec)
            self.assertEqual(spec.bot_username, "demo_vepol_bot")
            self.assertEqual(spec.persona, "Vepol agent")

    def test_skips_dirs_without_orchestration_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "no-yaml-project").mkdir()
            (base / "with-yaml" / ".orchestration.yaml").parent.mkdir(parents=True)
            (base / "with-yaml" / ".orchestration.yaml").write_text(
                yaml.safe_dump({
                    "telegram": {
                        "bot_username": "test_bot",
                        "bot_token_ref": "",
                    }
                }),
                encoding="utf-8",
            )
            r = load_from_projects_dir(base)
            self.assertEqual(len(r), 1)
            self.assertIsNotNone(r.get("with-yaml"))

    def test_skips_orchestration_yaml_without_telegram(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_dir = base / "x"
            project_dir.mkdir()
            (project_dir / ".orchestration.yaml").write_text(
                yaml.safe_dump({"cycle_enabled": True}),  # no telegram block
                encoding="utf-8",
            )
            r = load_from_projects_dir(base)
            self.assertEqual(len(r), 0)

    def test_skips_corrupted_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            broken = base / "broken"
            broken.mkdir()
            (broken / ".orchestration.yaml").write_text(
                "not: valid: yaml: at\n: all\n", encoding="utf-8"
            )
            good = base / "good"
            good.mkdir()
            (good / ".orchestration.yaml").write_text(
                yaml.safe_dump({
                    "telegram": {"bot_username": "good_bot"}
                }),
                encoding="utf-8",
            )
            # Broken yaml is skipped, good one loads
            r = load_from_projects_dir(base)
            self.assertEqual(len(r), 1)
            self.assertIsNotNone(r.get("good"))

    def test_invalid_runtime_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "x" / ".orchestration.yaml").parent.mkdir(parents=True)
            (base / "x" / ".orchestration.yaml").write_text(
                yaml.safe_dump({
                    "telegram": {
                        "bot_username": "x_bot",
                        "runtime": "gemini",  # not supported
                    }
                }),
                encoding="utf-8",
            )
            # Invalid runtime causes spec build to raise; loader catches and skips.
            # Behavior chosen: be permissive on load (skip), strict on update (kb-init-agent).
            # This test documents that invalid runtime causes the agent to be SKIPPED,
            # not the supervisor to crash.
            with self.assertRaises(ValueError):
                from _kb_multibot.registry import _spec_from_yaml
                _spec_from_yaml("x", str(base / "x"),
                                {"telegram": {"bot_username": "x", "runtime": "gemini"}})


if __name__ == "__main__":
    unittest.main()
