"""Critical positive: a Claude terminal card shows Claude's own session name and last message."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from vepol_face.app import create_app


def test_terminal_card_takes_title_and_preview_from_claude_transcript(tmp_path, monkeypatch):
    """Without it every terminal card reads "(new conversation)" — the one visible result of this change."""
    home = tmp_path / "claude"
    sid = "11111111-2222-3333-4444-555555555555"
    (home / "sessions").mkdir(parents=True)
    (home / "sessions" / "4242.json").write_text(json.dumps({"pid": 4242, "sessionId": sid}))
    transcript = home / "projects" / "-tmp-garmin" / f"{sid}.jsonl"
    transcript.parent.mkdir(parents=True)
    records = [
        {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
        {"type": "user", "isMeta": True, "message": {"content": "hook context"}},
        {"type": "user", "message": {"content": "привет, что у нас тут ?\nвторая строка"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Garmin data plan"}]}},
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in records) + "not json\n")
    monkeypatch.setenv("VEPOL_CLAUDE_HOME", str(home))

    app = create_app(hub=tmp_path / "knowledge", store_dir=tmp_path / "state")
    live = {"agent": "alive", "pid": 4242}
    real_describe = app.state.sessions.describe
    monkeypatch.setattr(app.state.sessions, "describe",
                        lambda conv: {**real_describe(conv), "transport": "terminal", **live, "agent_reason": ""})
    with TestClient(app) as client:
        client.headers["X-Vepol-Token"] = app.state.auth.token
        conv_id = client.post("/api/conversations", json={"target": "hub", "runtime": "claude"}).json()["id"]
        # A test prompt pasted by the app earlier must not beat Claude's own name.
        app.state.store.set_title(conv_id, "Reply with exactly VEPOL-PASTE-CLAUDE")

        card = client.get("/api/conversations").json()[0]
        assert card["title"] == "привет, что у нас тут ?"
        assert card["preview"] == "Garmin data plan"

        with transcript.open("a") as fh:
            fh.write(json.dumps({"type": "ai-title", "aiTitle": "Garmin morning data"}) + "\n")
        assert client.get("/api/conversations").json()[0]["title"] == "Garmin morning data"

        with transcript.open("a") as fh:
            fh.write(json.dumps({"type": "custom-title", "customTitle": "Test name"}) + "\n")
            fh.write(json.dumps({"type": "user", "message": {"content": "last question"}}) + "\n")
        card = client.get("/api/conversations").json()[0]
        assert card["title"] == "Test name"
        assert card["preview"] == "last question"

        # The agent exits: the card keeps the stored session's name.
        live.update(agent="shell", pid=None)
        assert client.get("/api/conversations").json()[0]["title"] == "Test name"
        assert app.state.store.get_conversation(conv_id).title == "Reply with exactly VEPOL-PASTE-CLAUDE"
