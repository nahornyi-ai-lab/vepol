"""Critical positive: planning the day opens one hub session per day, and a Claude one cannot reach the calendar."""
from __future__ import annotations

from fastapi.testclient import TestClient

from vepol_face import targets as targets_mod
from vepol_face.app import create_app
from vepol_face.terminal_session import TerminalSession


def test_day_plan_session_is_reopened_and_claude_starts_without_the_calendar_connector(tmp_path, monkeypatch):
    """Without it a second click on Plan my day starts a second dialog, or the agent writes the owner's calendar
    around kb-dayplan, which is the only thing allowed to do it after the owner's explicit request."""
    monkeypatch.setattr(TerminalSession, "_binary", lambda self, rt: f"/fake/{rt}")
    app = create_app(hub=tmp_path / "knowledge", store_dir=tmp_path / "state")
    with TestClient(app) as client:
        client.headers["X-Vepol-Token"] = app.state.auth.token
        first = client.post("/api/conversations", json={"runtime": "claude", "transport": "terminal",
                                                        "day_plan": "2026-10-15"})
        assert first.status_code == 201 and first.json()["existing"] is False, first.text
        again = client.post("/api/conversations", json={"runtime": "claude", "transport": "terminal",
                                                        "day_plan": "2026-10-15"}).json()
        assert (again["id"], again["existing"]) == (first.json()["id"], True)
        # Another day is another session.
        other = client.post("/api/conversations", json={"runtime": "claude", "transport": "terminal",
                                                        "day_plan": "2026-10-16"}).json()
        assert other["id"] != first.json()["id"] and other["existing"] is False

        detail = client.get(f"/api/conversations/{first.json()['id']}").json()
        assert (detail["target"], detail["title"], detail["day_plan"]) == ("hub", "Plan my day · Oct 15", "2026-10-15")

        conv = app.state.store.get_conversation(first.json()["id"])
        target = next(t for t in targets_mod.discover_targets(tmp_path / "knowledge") if t.slug == "hub")
        flag = ["--disallowedTools", "mcp__claude_ai_Google_Calendar"]
        # First start and a resume of the agent's own session both carry the flag.
        assert app.state.sessions.client(conv, target)._agent_argv() == ["/fake/claude", "--permission-mode", "manual", *flag]
        app.state.sessions.clients.clear()
        app.state.store.update_transport(conv.id, provider_session_id="agent-session-1")
        conv = app.state.store.get_conversation(conv.id)
        assert app.state.sessions.client(conv, target)._agent_argv() == [
            "/fake/claude", "--resume", "agent-session-1", "--permission-mode", "manual", *flag]

        # An ordinary Claude session is unchanged.
        plain = client.post("/api/conversations", json={"target": "hub", "runtime": "claude", "transport": "terminal"}).json()
        plain_conv = app.state.store.get_conversation(plain["id"])
        assert app.state.sessions.client(plain_conv, target)._agent_argv() == ["/fake/claude", "--permission-mode", "manual"]
