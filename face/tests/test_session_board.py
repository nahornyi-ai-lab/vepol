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
