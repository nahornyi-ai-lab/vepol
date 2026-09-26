"""Critical positive journey: the owner's board organization survives restart."""
from __future__ import annotations

from fastapi.testclient import TestClient

from vepol_face.app import create_app


def test_board_stages_preserve_conversation_across_app_restart(tmp_path):
    """Losing saved stages would lose the board's central organizing value."""
    state_dir = tmp_path / "state"
    app = create_app(hub=tmp_path / "knowledge", store_dir=state_dir)
    with TestClient(app) as client:
        client.headers["X-Vepol-Token"] = app.state.auth.token
        created = client.post("/api/conversations", json={"target": "hub", "runtime": "codex"})
        assert created.status_code == 201
        conv_id = created.json()["id"]
        path = f"/api/conversations/{conv_id}"
        store = app.state.store
        store.append_message(conv_id, "user", "Research the session board")
        run = store.start_run(conv_id)

        card = client.get("/api/conversations").json()[0]
        assert card["id"] == conv_id
        assert card["board_stage"] == "queued"
        assert card["preview"] == "Research the session board"
        moved = client.patch(f"{path}/board", json={"board_stage": "research"})
        assert moved.status_code == 200
        assert moved.json()["board_stage"] == "research"
        assert moved.json()["activity"] == "running"
        assert moved.json()["running"] is True
        assert client.get(path).json()["runs"][0]["id"] == run.id

        store.finish_run(conv_id, run.id, "done", text="The research is ready")
        before = client.get(path).json()
        completed = client.patch(f"{path}/board", json={"board_stage": "completed"})
        assert completed.status_code == 200
        card = completed.json()
        assert card["board_stage"] == "completed"
        assert card["board_updated_at"]
        assert card["activity"] == "done"
        assert card["running"] is False
        assert card["preview"] == "The research is ready"
        assert card["last_activity_at"] == before["messages"][-1]["at"]

    reopened = create_app(hub=tmp_path / "knowledge", store_dir=state_dir)
    with TestClient(reopened) as client:
        client.headers["X-Vepol-Token"] = reopened.state.auth.token
        detail = client.get(path).json()
        assert detail["id"] == conv_id
        assert detail["target"] == "hub"
        assert detail["runtime"] == "codex"
        assert detail["board_stage"] == "completed"
        assert detail["board_updated_at"] == card["board_updated_at"]
        assert detail["messages"] == before["messages"]
        assert detail["runs"] == before["runs"]
        assert client.get("/api/conversations").json()[0] == card


def test_terminal_bridge_moves_bytes_and_resizes_without_touching_the_agent(tmp_path, monkeypatch):
    """The bridge is the only path from keys to the agent: if it drops or
    alters bytes, resizes wrongly, or takes the agent down with the socket, the
    in-app terminal is decoration. Real tmux and a real socket (starlette's
    TestClient cannot speak websocket with this httpx); no agent CLI: cat."""
    import json
    import os
    import shutil
    import socket
    import subprocess
    import tempfile
    import threading
    import time

    import httpx
    import uvicorn
    from websockets.sync.client import connect

    from vepol_face import terminal_session
    from vepol_face.config import Config

    # macOS caps a unix socket path at 104 bytes; pytest's tmp_path is longer.
    sock_dir = tempfile.mkdtemp(prefix="vt-")
    monkeypatch.setenv("TMUX_TMPDIR", sock_dir)
    # Inside tmux, TMUX/TMUX_PANE would point new-session and kill-server at the owner's server.
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    tmux = terminal_session.tmux_binary()
    env = dict(os.environ)
    name = "kb-hub-claude"

    def display(fmt):
        return subprocess.run([tmux, "display-message", "-p", "-t", name, fmt],
                              env=env, capture_output=True, text=True).stdout.strip()

    subprocess.run([tmux, "new-session", "-d", "-s", name, "-x", "160", "-y", "48", "/bin/cat"], env=env, check=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(hub=tmp_path / "knowledge", config=Config(port=port), store_dir=tmp_path / "state")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        pid = int(display("#{pane_pid}"))
        base = f"http://127.0.0.1:{port}"
        token = app.state.auth.token
        with httpx.Client(base_url=base, headers={"X-Vepol-Token": token}, timeout=5) as client:
            deadline = time.monotonic() + 10
            while True:
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "server did not start"
                time.sleep(0.05)
            created = client.post("/api/conversations", json={"target": "hub", "runtime": "claude", "transport": "terminal"})
            assert created.status_code == 201
            conv_id = created.json()["id"]

            before = client.get(f"/api/conversations/{conv_id}").json()
            assert (before["agent"], before["pid"]) == ("alive", pid)

            with connect(f"ws://127.0.0.1:{port}/ws/{conv_id}/terminal?token={token}",
                         additional_headers={"Origin": base}) as ws:
                ws.send(b"vepol-echo\r")
                seen = b""
                while b"vepol-echo" not in seen:
                    frame = ws.recv(timeout=5)
                    assert isinstance(frame, bytes), frame
                    seen += frame
                ws.send(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
                deadline = time.monotonic() + 5
                width = display("#{window_width}")
                while width != "100" and time.monotonic() < deadline:
                    time.sleep(0.1)
                    width = display("#{window_width}")
                assert width == "100"

            # The socket is gone; the session and the agent PID are not.
            assert subprocess.run([tmux, "has-session", "-t", name], env=env).returncode == 0
            os.kill(pid, 0)
            after = client.get(f"/api/conversations/{conv_id}").json()
            assert (after["agent"], after["pid"]) == ("alive", pid)
            card = next(c for c in client.get("/api/conversations").json() if c["id"] == conv_id)
            assert (card["agent"], card["pid"], card["activity"]) == ("alive", pid, "alive")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        subprocess.run([tmux, "kill-server"], env=env)
        shutil.rmtree(sock_dir, ignore_errors=True)


def test_knowledge_panel_reads_project_files_and_stays_inside_the_root(tmp_path):
    """Without this route the Knowledge panel shows nothing of the project's knowledge."""
    hub = tmp_path / "hub"
    (hub / "projects").mkdir(parents=True)
    kb = tmp_path / "proj" / "knowledge"
    (kb / "decisions").mkdir(parents=True)
    (kb / "log.md").write_text("# Log\n- first entry\n")
    (kb / "decisions" / "a.md").write_text("Decision A\n")
    (hub / "projects" / "proj").symlink_to(kb)
    app = create_app(hub=hub, store_dir=tmp_path / "state")
    with TestClient(app) as client:
        client.headers["X-Vepol-Token"] = app.state.auth.token
        tree = client.get("/api/knowledge/tree", params={"target": "proj"}).json()
        paths = {e["path"]: e["kind"] for e in tree["entries"]}
        assert paths == {"decisions": "dir", "decisions/a.md": "file", "log.md": "file"}
        assert tree["truncated"] is False
        got = client.get("/api/knowledge/file", params={"target": "proj", "path": "log.md"})
        assert got.status_code == 200 and got.json()["text"] == "# Log\n- first entry\n"
        escape = client.get("/api/knowledge/file", params={"target": "proj", "path": "../../etc/hosts"})
        assert escape.status_code == 404
