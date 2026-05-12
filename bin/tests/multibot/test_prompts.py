"""Tests for prompts.py — context block formatter, R5 guards."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from _kb_multibot.events import EventFrom, TelegramEvent  # noqa: E402
from _kb_multibot.prompts import (  # noqa: E402
    assemble_spawn_prompt,
    format_children_block,
    format_group_context,
)
from _kb_multibot.registry import AgentSpec  # noqa: E402


def _make_event(
    msg_id: int,
    text: str,
    username: str | None = "demo",
    is_bot: bool = False,
    bot_slug: str | None = None,
    mentions: tuple[str, ...] = (),
    reply_to: int | None = None,
) -> TelegramEvent:
    return TelegramEvent(
        ts=f"2026-05-11T14:23:{msg_id:02d}Z",
        chat_id=-100,
        chat_type="group",
        message_id=msg_id,
        from_=EventFrom(
            user_id=7 if not is_bot else 8800000 + msg_id,
            username=username,
            is_bot=is_bot,
            bot_slug=bot_slug,
        ),
        text=text,
        reply_to_message_id=reply_to,
        message_thread_id=None,
        mentions=mentions,
    )


def _spec(slug: str, persona: str = "", bot_username: str | None = None) -> AgentSpec:
    return AgentSpec(
        slug=slug,
        bot_id=None,
        bot_username=bot_username or f"demo_{slug.replace('-', '_')}_bot",
        bot_token_ref="",
        workdir=f"/projects/{slug}",
        runtime="claude",
        parent_slug=None,
        persona=persona,
    )


class GroupContextTests(unittest.TestCase):
    def test_visual_delimiters_present(self) -> None:
        ctx = format_group_context([], "demo_vepol_bot")
        self.assertIn("### START GROUP CONTEXT ###", ctx)
        self.assertIn("### END GROUP CONTEXT ###", ctx)

    def test_empty_events_block(self) -> None:
        ctx = format_group_context([], "demo_vepol_bot")
        self.assertIn("(no recent messages)", ctx)

    def test_single_event_formatted(self) -> None:
        e = _make_event(1, "статус релиза?", username="demo")
        ctx = format_group_context([e], "demo_vepol_bot")
        self.assertIn("@demo", ctx)
        self.assertIn("статус релиза?", ctx)

    def test_mentions_marked_for_target(self) -> None:
        # Target bot is demo_vepol_bot — mentions should mark
        e = _make_event(
            1, "@demo_vepol_bot статус?", mentions=("demo_vepol_bot",)
        )
        ctx = format_group_context([e], "demo_vepol_bot")
        self.assertIn("[YOU MENTIONED]", ctx)

    def test_mentions_not_marked_for_other(self) -> None:
        e = _make_event(1, "@kb_mail_bot привет", mentions=("kb_mail_bot",))
        ctx = format_group_context([e], "demo_vepol_bot")
        self.assertNotIn("[YOU MENTIONED]", ctx)

    def test_reply_marker_present(self) -> None:
        e = _make_event(2, "ок", reply_to=1)
        ctx = format_group_context([e], "demo_vepol_bot")
        self.assertIn("reply→msg:1", ctx)

    def test_bot_sender_labeled(self) -> None:
        e = _make_event(
            1, "v0.3.2 готов", is_bot=True, bot_slug="vepol", username="demo_vepol_bot"
        )
        ctx = format_group_context([e], "demo_vepol_bot")
        self.assertIn("bot:vepol", ctx)

    def test_target_username_case_insensitive(self) -> None:
        e = _make_event(1, "test", mentions=("demo_vepol_bot",))
        ctx_lower = format_group_context([e], "demo_vepol_bot")
        ctx_upper = format_group_context([e], "DEMO_VEPOL_BOT")
        self.assertEqual(ctx_lower, ctx_upper)


class ChildrenBlockTests(unittest.TestCase):
    def test_empty_for_leaf(self) -> None:
        self.assertEqual(format_children_block([]), "")

    def test_lists_children_with_personas(self) -> None:
        children = [
            _spec("vepol-marketing", persona="Marketing & content"),
            _spec("vepol-docs", persona="Documentation owner"),
        ]
        block = format_children_block(children)
        self.assertIn("demo_vepol_marketing_bot", block)
        self.assertIn("demo_vepol_docs_bot", block)
        self.assertIn("Marketing & content", block)
        self.assertIn("Documentation owner", block)

    def test_no_persona_handled(self) -> None:
        children = [_spec("plain-child", persona="")]
        block = format_children_block(children)
        # Bot username slug→underscore mapping
        self.assertIn("demo_plain_child_bot", block)
        self.assertIn("(no persona description)", block)


class AssembleSpawnPromptTests(unittest.TestCase):
    def test_includes_all_sections(self) -> None:
        agent = _spec("vepol", persona="Vepol orchestrator")
        event = _make_event(1, "статус?", mentions=("demo_vepol_bot",))
        prompt = assemble_spawn_prompt(
            agent=agent,
            trigger_username="demo",
            trigger_chat_type="group",
            recent_events=[event],
            children=[],
            trigger_text="статус?",
        )
        # Header
        self.assertIn("vepol", prompt)
        self.assertIn("demo_vepol_bot", prompt)
        self.assertIn("Vepol orchestrator", prompt)
        # Triggered by
        self.assertIn("triggered", prompt.lower())
        self.assertIn("@demo", prompt)
        # R5 trust boundary
        self.assertIn("IMPORTANT", prompt)
        self.assertIn("OBSERVATIONS", prompt)
        self.assertIn("NOT as", prompt)
        # Group context
        self.assertIn("### START GROUP CONTEXT ###", prompt)
        self.assertIn("### END GROUP CONTEXT ###", prompt)

    def test_r5_trust_boundary_warns_about_injection(self) -> None:
        agent = _spec("vepol")
        prompt = assemble_spawn_prompt(
            agent=agent,
            trigger_username="demo",
            trigger_chat_type="group",
            recent_events=[],
            children=[],
            trigger_text="x",
        )
        # Concept §10 R5 — explicit guard text (collapse whitespace for line-wrap)
        collapsed = " ".join(prompt.split())
        self.assertIn("ignore prior instructions", collapsed)
        self.assertIn("write X to file Y", collapsed)

    def test_children_block_for_parent_agent(self) -> None:
        agent = _spec("vepol", persona="parent")
        children = [_spec("vepol-marketing", persona="m"), _spec("vepol-docs", persona="d")]
        prompt = assemble_spawn_prompt(
            agent=agent,
            trigger_username="demo",
            trigger_chat_type="group",
            recent_events=[],
            children=children,
            trigger_text="х",
        )
        self.assertIn("demo_vepol_marketing_bot", prompt)
        self.assertIn("delegate", prompt.lower())

    def test_no_children_block_for_leaf(self) -> None:
        agent = _spec("vepol-leaf", persona="leaf")
        prompt = assemble_spawn_prompt(
            agent=agent,
            trigger_username="demo",
            trigger_chat_type="group",
            recent_events=[],
            children=[],
            trigger_text="х",
        )
        # No children section
        self.assertNotIn("delegate", prompt.lower())

    def test_username_none_fallback(self) -> None:
        # No username — falls back to user_id form (concept )
        agent = _spec("vepol")
        prompt = assemble_spawn_prompt(
            agent=agent,
            trigger_username=None,
            trigger_chat_type="private",
            recent_events=[],
            children=[],
            trigger_text="x",
        )
        self.assertIn("no @username", prompt)


if __name__ == "__main__":
    unittest.main()
