"""Critical positive: several sessions of one agent in one project, and a task's session that follows the task."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

from fastapi.testclient import TestClient

from vepol_face.app import create_app

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_two_new_sessions_of_one_agent_get_two_live_terminals(tmp_path, monkeypatch):
    """Without it a second session of the same agent in a project silently reopens the first one.
    Real tmux on a private socket; `zsh -f` stands in for the login shell and `cat` for the agent."""
    from vepol_face import terminal_session
    from vepol_face.terminal_session import TerminalSession

    sock_dir = tempfile.mkdtemp(prefix="vt-")
    monkeypatch.setenv("TMUX_TMPDIR", sock_dir)
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setenv("VEPOL_AGENT_HOME_HERMES", str(tmp_path / "hermes-home"))
    real_binary = TerminalSession._binary
    monkeypatch.setattr(TerminalSession, "_binary", lambda self, rt: real_binary(self, rt) if rt == "tmux" else "/bin/cat")
    monkeypatch.setattr(TerminalSession, "_shell_argv", lambda self: ["/bin/zsh", "-f"])
    tmux = terminal_session.tmux_binary()
    app = create_app(hub=tmp_path / "knowledge", store_dir=tmp_path / "state")
    try:
        with TestClient(app) as client:
            client.headers["X-Vepol-Token"] = app.state.auth.token
            ids = []
            for _ in range(2):
                created = client.post("/api/conversations", json={"target": "hub", "runtime": "hermes", "transport": "terminal"})
                assert created.status_code == 201 and created.json()["existing"] is False, created.text
                ids.append(created.json()["id"])
                started = client.post(f"/api/conversations/{ids[-1]}/terminal/start")
                assert started.status_code == 200 and started.json()["agent"] == "alive", started.text
            assert ids[0] != ids[1]

            cards = {c["id"]: c for c in client.get("/api/conversations").json()}
            names = {cards[i]["terminal_name"] for i in ids}
            assert names == {f"kb-hub-{i}-hermes" for i in ids}
            assert all(cards[i]["agent"] == "alive" for i in ids)
            assert cards[ids[0]]["pid"] != cards[ids[1]]["pid"]
            for name in names:
                assert subprocess.run([tmux, "has-session", "-t", name], capture_output=True).returncode == 0
    finally:
        subprocess.run([tmux, "kill-server"], capture_output=True)
        shutil.rmtree(sock_dir, ignore_errors=True)


def test_task_session_moves_to_done_once_when_its_task_is_done(tmp_path, monkeypatch):
    """Without it a finished task's session stays in its column until the owner finds and moves it by hand.
    A real kb-board board (this repo's own tool) in a temporary hub."""
    hub = tmp_path / "hub"
    (hub / "bin").mkdir(parents=True)
    (hub / "bin" / "kb-board").symlink_to(REPO / "bin" / "kb-board")
    board = hub / "projects" / "alpha" / "backlog.md"
    board.parent.mkdir(parents=True)
    template = (REPO / "_template" / "knowledge" / "backlog.md").read_text(encoding="utf-8")
    board.write_text(template.replace("{{PROJECT_NAME}}", "alpha"), encoding="utf-8")

    def kb_board(*args):
        return subprocess.run([str(hub / "bin" / "kb-board"), *args], capture_output=True, text=True, check=True).stdout

    kb_board("append", str(board), "Wire the export button", "--plan-item-id", "alpha-1", "--status", "Ready", "--actor", "test")
    monkeypatch.setenv("VEPOL_TASK_SYNC_SECONDS", "0")
    app = create_app(hub=hub, store_dir=tmp_path / "state")
    with TestClient(app) as client:
        client.headers["X-Vepol-Token"] = app.state.auth.token
        task = {"project": "alpha", "plan_item_id": "alpha-1"}
        created = client.post("/api/conversations", json={"target": "alpha", "runtime": "claude", "task": task,
                                                          "board_stage": "working"}).json()
        assert created["existing"] is False
        again = client.post("/api/conversations", json={"target": "alpha", "runtime": "claude", "task": task}).json()
        assert (again["id"], again["existing"]) == (created["id"], True)

        def card():
            return next(c for c in client.get("/api/conversations").json() if c["id"] == created["id"])

        assert (card()["task"], card()["task_status"], card()["board_stage"]) == (task, "Ready", "working")

        kb_board("claim", str(board), "--plan-item-id", "alpha-1", "--actor", "codex")
        claim_id = json.loads(kb_board("list", str(board), "--all", "--json"))[0]["claim_id"]
        kb_board("request-review", str(board), "--plan-item-id", "alpha-1", "--claim-id", claim_id, "--actor", "codex")
        kb_board("close", str(board), "--plan-item-id", "alpha-1", "--claim-id", claim_id, "--actor", "codex",
                 "--outcome", "closed")
        done = card()
        assert (done["task_status"], done["board_stage"]) == ("Done", "completed")

        # The owner moves it back: it stays there, the task is not touched.
        assert client.patch(f"/api/conversations/{created['id']}/board", json={"board_stage": "review"}).status_code == 200
        assert card()["board_stage"] == "review"
        assert card()["board_stage"] == "review"  # a later sync does not move it again
        assert json.loads(kb_board("list", str(board), "--all", "--json"))[0]["status"] == "Done"
