"""Critical positive: every terminal agent's card gets its title and last message from the agent's own store."""
from __future__ import annotations

import datetime
import json
import sqlite3
import urllib.parse

from vepol_face import agent_titles

START_MS = 1_790_000_000_000  # the stand-in agent process start


def _iso(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat()


def _db(path, ddl, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(ddl)
    for row in rows:
        conn.execute(f"INSERT INTO {ddl.split()[2]} VALUES ({','.join('?' * len(row))})", row)
    conn.commit()
    conn.close()


def test_each_agent_reader_returns_its_session_title_and_preview(tmp_path, monkeypatch):
    """Without it every non-Claude terminal card reads "(new conversation)" — the visible result of section D."""
    cwd = str(tmp_path / "proj")
    monkeypatch.setattr(agent_titles, "process_start_ms", lambda pid: START_MS)
    for agent in ("codex", "grok", "agy", "hermes", "opencode"):
        monkeypatch.setenv(f"VEPOL_AGENT_HOME_{agent.upper()}", str(tmp_path / agent))

    # Codex: threads row + rollout; an older thread (before the process) and a claimed one are not picked.
    rollout = tmp_path / "codex" / "sessions" / "rollout-new.jsonl"
    rollout.parent.mkdir(parents=True)
    events = [
        {"type": "event_msg", "payload": {"type": "item_completed",
                                          "item": {"type": "AgentMessage", "content": [{"type": "Text", "text": "x"}]}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "Plan is ready"}},
    ]
    rollout.write_text("".join(json.dumps(e) + "\n" for e in events))
    _db(tmp_path / "codex" / "state_5.sqlite",
        "CREATE TABLE threads (id TEXT, source TEXT, cwd TEXT, created_at_ms INTEGER, name TEXT,"
        " first_user_message TEXT, rollout_path TEXT)",
        [("old", "cli", cwd, START_MS - 60_000, "Old thread", "old", ""),
         ("taken", "cli", cwd, START_MS + 1_000, "Someone else's", "x", ""),
         ("mine", "cli", cwd, START_MS + 2_000, None, "fix the login page\nmore", str(rollout))])
    assert agent_titles.card("codex", 1, cwd, None, {"taken"}) == {
        "id": "mine", "title": "fix the login page", "preview": "Plan is ready"}
    assert agent_titles.card("codex", 1, cwd, None, set())["id"] == "taken"

    summary = (tmp_path / "grok" / "sessions" / urllib.parse.quote(cwd, safe="") / "g-1" / "summary.json")
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({"info": {"id": "g-1", "cwd": cwd}, "generated_title": "Grok title",
                                   "session_summary": "Grok summary", "created_at": _iso(START_MS + 10_000)}))
    assert agent_titles.card("grok", 1, cwd, None, set()) == {
        "id": "g-1", "title": "Grok title", "preview": "Grok summary"}

    _db(tmp_path / "agy" / "conversation_summaries.db",
        "CREATE TABLE conversation_summaries (conversation_id TEXT, title TEXT, preview TEXT,"
        " workspace_uris TEXT, last_modified_time TEXT, last_user_input_time TEXT)",
        [("a-1", "", "review the API\nplease", json.dumps([f"file://{cwd}"]),
          _iso(START_MS + 70_000), _iso(START_MS + 60_000))])
    assert agent_titles.card("agy", 1, cwd, None, set()) == {
        "id": "a-1", "title": "review the API", "preview": "review the API\nplease"}

    _db(tmp_path / "hermes" / "state.db",
        "CREATE TABLE sessions (id TEXT, source TEXT, title TEXT, display_name TEXT,"
        " last_activity_description TEXT, cwd TEXT, started_at REAL)",
        [("h-1", "cli", "Hermes title", None, "Reading files", cwd, START_MS / 1000 + 3)])
    assert agent_titles.card("hermes", 1, cwd, None, set()) == {
        "id": "h-1", "title": "Hermes title", "preview": "Reading files"}

    _db(tmp_path / "opencode" / "opencode.db",
        "CREATE TABLE session (id TEXT, parent_id TEXT, directory TEXT, title TEXT, time_created INTEGER)",
        [("o-1", None, cwd, "OpenCode title", START_MS + 4_000)])
    assert agent_titles.card("opencode", 1, cwd, None, set()) == {
        "id": "o-1", "title": "OpenCode title", "preview": None}

    # The agent exits: the stored id still gives the card its title.
    assert agent_titles.card("codex", None, cwd, "mine", set())["title"] == "fix the login page"
