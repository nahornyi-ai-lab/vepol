"""User-facing text of the multibot CLIs names only things that exist."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

PKG = BIN / "_kb_multibot"


def _load_script(name: str):
    path = BIN / name
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SetupNextStepTests(unittest.TestCase):
    def test_final_message_points_at_kb_multibot_add(self) -> None:
        setup = _load_script("kb-multibot-setup")
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            session = home / ".orchestrator" / "multibot-supervisor.session"
            session.parent.mkdir(parents=True)
            session.write_text("", encoding="utf-8")
            existing = {
                "TG_API_ID": "123",
                "TG_API_HASH": "hash",
                "KB_MULTIBOT_GROUP_CHAT_ID": "-100123",
            }
            out = io.StringIO()
            with mock.patch.object(setup, "_read_existing_env", return_value=existing), \
                    mock.patch.object(setup, "_write_env") as write_env, \
                    mock.patch.object(setup, "cmd_check", return_value=0), \
                    mock.patch.object(setup.Path, "home", return_value=home), \
                    contextlib.redirect_stdout(out):
                rc = setup.cmd_full()
        self.assertEqual(rc, 0)
        write_env.assert_called_once()
        text = out.getvalue()
        self.assertIn("kb-multibot-add <token>", text)
        self.assertNotIn("kb-init-agent", text)
        self.assertTrue((BIN / "kb-multibot-add").is_file())


class ReferencedNamesExistTests(unittest.TestCase):
    def _unit_files(self) -> list[Path]:
        return sorted(PKG.glob("*.py")) + sorted(BIN.glob("kb-multibot-*"))

    def test_kb_commands_named_in_unit_exist(self) -> None:
        missing: dict[str, list[str]] = {}
        for path in self._unit_files():
            for name in set(re.findall(r"\bkb-[a-z0-9]+(?:-[a-z0-9]+)*", path.read_text())):
                if name == "kb-multibot":  # package / logger name, not a command
                    continue
                if not (BIN / name).exists():
                    missing.setdefault(name, []).append(path.name)
        self.assertEqual(missing, {})

    def test_package_layout_matches_files(self) -> None:
        doc = (PKG / "__init__.py").read_text(encoding="utf-8")
        listed = set(re.findall(r"^\s+(\w+\.py)\s+—", doc, flags=re.M))
        actual = {p.name for p in PKG.glob("*.py")} - {"__init__.py"}
        self.assertEqual(listed, actual)
        commands = set(re.findall(r"^\s+(kb-[a-z-]+)\s+—", doc, flags=re.M))
        self.assertEqual(commands, {p.name for p in BIN.glob("kb-multibot-*")})

    def test_concept_doc_link_resolves(self) -> None:
        text = (BIN / "kb-multibot-supervisor").read_text(encoding="utf-8")
        self.assertIn("docs/methodology/multibot-agent-runtime.md", text)
        self.assertNotIn("concepts/multibot-agent-runtime.md", text)
        if not (BIN.parent / "docs").is_dir():
            self.skipTest("docs/ is only present in a repo checkout")
        self.assertTrue(
            (BIN.parent / "docs" / "methodology" / "multibot-agent-runtime.md").is_file()
        )


if __name__ == "__main__":
    unittest.main()
