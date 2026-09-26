"""Vepol Face local backend.

The backend is the product boundary; the UI is a thin client. Everything here
binds loopback, authenticates with a per-launch in-memory token, and refuses to
present a runtime failure as an answer.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import pathlib
import pty
import struct
import subprocess
import termios
import threading

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import automations as automations_mod
from . import broker as broker_mod
from . import knowledge_files as knowledge_mod
from . import runtimes as runtimes_mod
from . import targets as targets_mod
from . import tasks as tasks_mod
from . import terminal_session as terminal_mod
from . import usage as usage_mod
from .auth import Auth
from .config import Config
from .evidence import diff_kb
from .runs import BOARD_STAGES, Conversation, RunStore
from .sessions import UnsafeSessionName, attach_command, session_name
from .session_manager import SessionManager

STATIC = pathlib.Path(__file__).parent / "static"


def _conversation_summary(conv: Conversation) -> dict:
    running = any(run.status == "running" for run in conv.runs)
    preview = next((m.text.strip() for m in reversed(conv.messages) if m.text.strip()), "")
    timestamps = [conv.created_at]
    timestamps.extend(m.at for m in conv.messages)
    timestamps.extend(run.started_at for run in conv.runs)
    timestamps.extend(run.finished_at for run in conv.runs if run.finished_at)
    return {
        "id": conv.id, "target": conv.target, "runtime": conv.runtime,
        "title": conv.title or "(new conversation)", "created_at": conv.created_at,
        "messages": len(conv.messages), "running": running,
        "board_stage": conv.board_stage, "board_updated_at": conv.board_updated_at,
        "preview": preview[:200],
        "last_activity_at": max((at for at in timestamps if at), default=conv.created_at),
        "activity": "running" if running else (conv.runs[-1].status if conv.runs else "idle"),
    }


class EventBus:
    """Per-conversation fan-out so a refreshed browser can reattach.

    Queues are bounded (review nit 2026-08-20, codex #5): a subscriber that
    stopped draining loses newest events instead of growing the process
    without limit. A reconnecting client reloads state via /api anyway.
    """

    QUEUE_MAX = 1024

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, conv_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_MAX)
        with self._lock:
            self._subs.setdefault(conv_id, set()).add(q)
        return q

    @staticmethod
    def _offer(q: asyncio.Queue, event: dict) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(event)

    def unsubscribe(self, conv_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            if conv_id in self._subs:
                self._subs[conv_id].discard(q)

    def publish(self, conv_id: str, event: dict) -> None:
        with self._lock:
            queues = list(self._subs.get(conv_id, ()))
        loop = self.loop
        for q in queues:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self._offer, q, event)
            else:  # pragma: no cover - only when no client is attached
                with contextlib.suppress(Exception):
                    self._offer(q, event)


def create_app(
    hub: pathlib.Path | None = None,
    config: Config | None = None,
    store_dir: pathlib.Path | None = None,
    auth_token: str | None = None,
) -> FastAPI:
    cfg = config or Config()
    hub_path = pathlib.Path(hub or targets_mod.HUB)
    state_dir = pathlib.Path(
        store_dir
        or os.environ.get("VEPOL_FACE_STATE_DIR")
        or os.path.expanduser("~/.vepol/face")
    )

    @contextlib.asynccontextmanager
    async def lifespan(running: FastAPI):
        running.state.bus.loop = asyncio.get_running_loop()
        yield
        running.state.sessions.close()

    app = FastAPI(
        title="Vepol Face", docs_url=None, redoc_url=None, openapi_url=None,
        lifespan=lifespan,
    )
    app.state.config = cfg
    app.state.auth = Auth(port=cfg.port, token=auth_token)
    app.state.hub = hub_path
    app.state.store = RunStore(state_dir)
    # A backend that died mid-turn would otherwise leave the conversation
    # permanently 409-locked. Close those runs out at startup.
    app.state.interrupted = app.state.store.reconcile_interrupted()
    app.state.bus = EventBus()
    app.state.sessions = SessionManager(app.state.store, app.state.bus, hub_path, cfg.desktop)

    def summary(conv):
        row = _conversation_summary(conv)
        details = app.state.sessions.describe(conv)
        row.update(transport=details["transport"], needs_owner=bool(details["pending"]),
                   continuation_available=details["continuation_available"])
        if details["pending"]:
            row["activity"] = "waiting"
        if details["transport"] == "terminal":
            # Process evidence replaces the run-derived state for terminal conversations.
            row.update(agent=details["agent"], pid=details["pid"], agent_reason=details.get("agent_reason", ""))
            row["activity"] = details["agent"]
        return row

    def desktop_status():
        convs = app.state.store.list_conversations()
        pending = [f"{c.id}:{p['id']}" for c in convs for p in app.state.sessions.describe(c)["pending"]]
        # A pending permission/decision is work in flight too, so Quit explains it as such.
        return {"busy": bool(pending) or app.state.sessions.busy() or any(r.status == "running" for c in convs for r in c.runs),
                "pending": len(pending), "pending_ids": pending}

    # ---------------------------------------------------------- middleware
    @app.middleware("http")
    async def guard(request: Request, call_next):
        raw_len = request.headers.get("content-length")
        if raw_len is not None:
            try:
                if int(raw_len) > cfg.max_body_bytes:
                    return JSONResponse({"detail": "payload too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "bad content-length"}, status_code=400)

        origin = request.headers.get("origin")
        if origin is not None and not app.state.auth.origin_allowed(origin):
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)

        response = await call_next(request)
        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response

    def require_token(x_vepol_token: str | None = Header(default=None)) -> None:
        if not app.state.auth.verify(x_vepol_token):
            raise HTTPException(status_code=401, detail="bad or missing token")

    auth_dep = [Depends(require_token)]

    # -------------------------------------------------------------- routes
    @app.get("/api/health", dependencies=auth_dep)
    def health() -> dict:
        return {
            "ok": True,
            "host": cfg.host,
            "port": cfg.port,
            "hub": str(hub_path),
            "state_dir": str(state_dir),
            "desktop": cfg.desktop,
        }

    @app.get("/api/targets", dependencies=auth_dep)
    def api_targets() -> list[dict]:
        return [t.as_dict() for t in targets_mod.discover_targets(hub=hub_path)]

    @app.get("/api/runtimes", dependencies=auth_dep)
    def api_runtimes() -> list[dict]:
        found = runtimes_mod.load_runtimes()
        return [r.as_dict() for r in found.values()]

    @app.get("/api/knowledge/tree", dependencies=auth_dep)
    def api_knowledge_tree(target: str = "") -> dict:
        try:
            return knowledge_mod.knowledge_tree(hub_path, target)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown target {target!r}")

    @app.get("/api/knowledge/file", dependencies=auth_dep)
    def api_knowledge_file(target: str = "", path: str = "") -> dict:
        try:
            return knowledge_mod.knowledge_file(hub_path, target, path)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown target {target!r}")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such file")
        except knowledge_mod.FileTooLarge:
            raise HTTPException(status_code=413, detail="too large to show")

    @app.get("/api/usage", dependencies=auth_dep)
    def api_usage() -> dict:
        return usage_mod.read_usage(state_dir, os.environ.get("CODEX_HOME"))

    # Read-only views: plain `def` so blocking kb-board calls and ledger scans run in the threadpool.
    @app.get("/api/tasks", dependencies=auth_dep)
    def api_tasks(target: str | None = None) -> dict:
        try:
            return tasks_mod.list_tasks(hub_path, target)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown target {target!r}")

    @app.get("/api/automations", dependencies=auth_dep)
    def api_automations() -> dict:
        return automations_mod.build_automations(hub_path)

    @app.get("/api/automations/{process_id}", dependencies=auth_dep)
    def api_automation(process_id: str, date: str | None = None) -> dict:
        try:
            detail = automations_mod.automation_detail(hub_path, process_id, date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if detail is None:
            raise HTTPException(status_code=404, detail=f"unknown process {process_id!r}")
        return detail

    @app.get("/api/conversations", dependencies=auth_dep)
    def api_conversations() -> list[dict]:
        return [
            summary(c)
            for c in app.state.store.list_conversations()
        ]

    @app.post("/api/conversations", dependencies=auth_dep, status_code=201)
    async def api_create_conversation(request: Request) -> dict:
        body = await _json_body(request, cfg.max_body_bytes)
        target = str(body.get("target") or "hub")
        runtime = str(body.get("runtime") or "claude")
        mode = str(body.get("transport") or ("terminal" if cfg.desktop else "oneshot"))
        title = body.get("title")
        title = title.strip()[:200] if isinstance(title, str) else ""
        if mode not in ({"session", "terminal"} if cfg.desktop else {"oneshot", "session", "terminal"}):
            raise HTTPException(status_code=400, detail="unknown transport")
        if runtime not in cfg.allowed_runtimes:
            raise HTTPException(
                status_code=400,
                detail=f"unknown runtime {runtime!r}; allowed: {list(cfg.allowed_runtimes)}",
            )
        board_stage = body.get("board_stage")
        if board_stage is not None and (not isinstance(board_stage, str) or board_stage not in BOARD_STAGES):
            raise HTTPException(status_code=400, detail="invalid board stage")
        if mode == "terminal":
            for existing in app.state.store.list_conversations():
                if existing.target == target and existing.runtime == runtime and existing.transport == "terminal":
                    # One terminal per (target, runtime): an existing terminal keeps its title and
                    # board stage (owner decision 2026-09-26); the page shows a note.
                    return {"id": existing.id, "target": target, "runtime": runtime, "transport": mode,
                            "existing": True}
        conv = app.state.store.create_conversation(target=target, runtime=runtime, title=title, transport=mode)
        if board_stage is not None:
            conv = app.state.store.update_board_stage(conv.id, board_stage)
        return {"id": conv.id, "target": conv.target, "runtime": conv.runtime, "transport": mode,
                "existing": False}

    @app.get("/api/conversations/{conv_id}", dependencies=auth_dep)
    def api_conversation(conv_id: str) -> dict:
        conv = app.state.store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        return {
            "id": conv.id, "target": conv.target, "runtime": conv.runtime,
            "title": conv.title,
            "board_stage": conv.board_stage, "board_updated_at": conv.board_updated_at,
            **app.state.sessions.describe(conv),
            "messages": [
                {"role": m.role, "text": m.text, "at": m.at, "meta": m.meta}
                for m in conv.messages
            ],
            "runs": [
                {
                    "id": r.id, "status": r.status, "reason": r.reason,
                    "category": r.category, "started_at": r.started_at,
                    "finished_at": r.finished_at, "evidence": r.evidence,
                }
                for r in conv.runs
            ],
        }

    @app.patch("/api/conversations/{conv_id}/board", dependencies=auth_dep)
    async def api_update_board(conv_id: str, request: Request) -> dict:
        body = await _json_body(request, cfg.max_body_bytes)
        try:
            conv = app.state.store.update_board_stage(conv_id, body.get("board_stage"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="no such conversation") from exc
        return summary(conv)

    @app.post("/api/conversations/{conv_id}/messages", dependencies=auth_dep, status_code=202)
    async def api_send(conv_id: str, request: Request) -> dict:
        body = await _json_body(request, cfg.max_body_bytes)
        prompt = str(body.get("text") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="empty prompt")

        conv = app.state.store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        if any(r.status == "running" for r in conv.runs):
            raise HTTPException(status_code=409, detail="a run is already in flight")
        if not app.state.sessions.continuation_available(conv):
            raise HTTPException(status_code=409, detail="The agent's original session was not found. History is kept; it cannot be continued.")

        target = _resolve_target(hub_path, conv.target)
        if cfg.desktop and conv.transport == "oneshot" and not conv.messages and not conv.runs:
            conv = app.state.store.update_transport(conv_id, transport="session")
        app.state.store.append_message(conv_id, role="user", text=prompt)
        run = app.state.store.start_run(conv_id, run_id=broker_mod.new_run_id())
        # Stop intent must be registrable before the worker thread gets around
        # to launching the subprocess (the pre-run KB snapshot takes seconds).
        mode = app.state.sessions.mode(conv)
        if mode == "oneshot":
            broker_mod.begin_face_run(run.id)

        app.state.bus.publish(conv_id, {
            "type": "run_started", "run_id": run.id,
            "target": conv.target, "runtime": conv.runtime,
            "mode": mode,
        })

        threading.Thread(
            target=_execute_run if mode == "oneshot" else _execute_session,
            args=(app, conv_id, run.id, prompt, conv.target, conv.runtime, target),
            daemon=True,
        ).start()
        return {"run_id": run.id, "status": "running"}

    @app.post(
        "/api/conversations/{conv_id}/runs/{run_id}/stop",
        dependencies=auth_dep, status_code=202,
    )
    def api_stop(conv_id: str, run_id: str) -> dict:
        """MVP-10: stop a turn in flight. The executing thread observes the
        kill and finishes the run with status `stopped`."""
        conv = app.state.store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        run = app.state.store.get_run(conv_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        if run.status != "running":
            raise HTTPException(status_code=409, detail=f"run is {run.status}, not running")
        if app.state.sessions.mode(conv) == "oneshot":
            hit = broker_mod.stop_face_run(run_id)
        else:
            client = app.state.sessions.clients.get(conv_id)
            hit = bool(client)
            if client:
                client.interrupt()
            if conv.transport == "terminal":
                app.state.store.finish_run(conv_id, run_id, "stopped", reason="Stopped by the owner")
                app.state.bus.publish(conv_id, {"type": "run_finished", "run_id": run_id, "status": "stopped", "ok": False, "reason": "Stopped by the owner"})
        return {"run_id": run_id, "stopping": hit}

    @app.post("/api/conversations/{conv_id}/retry", dependencies=auth_dep, status_code=202)
    def api_retry(conv_id: str) -> dict:
        """MVP-10: re-run the last user prompt without duplicating it."""
        conv = app.state.store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        if any(r.status == "running" for r in conv.runs):
            raise HTTPException(status_code=409, detail="a run is already in flight")
        last_user = next((m for m in reversed(conv.messages) if m.role == "user"), None)
        if last_user is None:
            raise HTTPException(status_code=400, detail="nothing to retry")
        if not app.state.sessions.continuation_available(conv):
            raise HTTPException(status_code=409, detail="The original session is unavailable; a retry does not start a new conversation.")

        target = _resolve_target(hub_path, conv.target)
        run = app.state.store.start_run(conv_id, run_id=broker_mod.new_run_id())
        mode = app.state.sessions.mode(conv)
        if mode == "oneshot":
            broker_mod.begin_face_run(run.id)
        app.state.bus.publish(conv_id, {
            "type": "run_started", "run_id": run.id,
            "target": conv.target, "runtime": conv.runtime,
            "mode": mode,
        })
        threading.Thread(
            target=_execute_run if mode == "oneshot" else _execute_session,
            args=(app, conv_id, run.id, last_user.text, conv.target, conv.runtime, target),
            daemon=True,
        ).start()
        return {"run_id": run.id, "status": "running"}

    @app.get("/api/conversations/{conv_id}/attach", dependencies=auth_dep)
    def api_attach(conv_id: str) -> dict:
        conv = app.state.store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="no such conversation")
        if conv.runtime not in ("claude", "codex", "agy"):
            raise HTTPException(
                status_code=400,
                detail=f"conversation runtime {conv.runtime!r} has no interactive session form",
            )
        runtime = conv.runtime
        if app.state.sessions.mode(conv) == "session":
            return {"available": False, "mode": "session", "command": "",
                    "reason": "The session runs inside the app. Taking over the same process in a terminal is not available yet."}
        try:
            # Same derivation as Start, liveness and the bridge: one conversation, one session name.
            name = session_name(conv.target, runtime)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"available": True, "session": name, "command": attach_command(name), "mode": "terminal"}

    @app.get("/api/desktop/status", dependencies=auth_dep)
    def api_desktop_status():
        return desktop_status()

    @app.post("/api/desktop/shutdown", dependencies=auth_dep, status_code=202)
    def api_shutdown():
        status = desktop_status()
        if status["busy"] or status["pending"]:
            raise HTTPException(status_code=409, detail="Sessions are still working. Vepol will keep running.")
        shutdown = getattr(app.state, "shutdown", None)
        if shutdown is None:
            raise HTTPException(status_code=409, detail="This backend is not owned by Vepol Desktop")
        shutdown()
        return {"stopping": True}

    @app.post("/api/conversations/{conv_id}/permissions/{request_id}", dependencies=auth_dep)
    async def api_permission(conv_id: str, request_id: str, request: Request):
        body = await _json_body(request, cfg.max_body_bytes)
        if body.get("decision") not in {"allow", "deny"}:
            raise HTTPException(status_code=400, detail="explicit decision required")
        try:
            app.state.sessions.respond(conv_id, request_id, body)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"answered": True}

    @app.post("/api/conversations/{conv_id}/terminal/start", dependencies=auth_dep)
    def api_terminal_start(conv_id: str) -> dict:
        """Create or reuse the agent's tmux session. Only an explicit click calls this."""
        conv = app.state.store.get_conversation(conv_id)
        if conv is None or conv.transport != "terminal":
            raise HTTPException(status_code=404, detail="No terminal session")
        target = _resolve_target(hub_path, conv.target)
        try:
            result = app.state.sessions.client(conv, target).start()
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            reason = str(exc)
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                reason = exc.stderr.strip()
            raise HTTPException(status_code=409, detail=reason) from exc
        # A note left by a Send before Start ("Click Start…") no longer applies.
        app.state.store.update_transport(conv_id, note="")
        return result

    @app.post("/api/conversations/{conv_id}/terminal/ready", dependencies=auth_dep)
    def api_terminal_ready(conv_id: str):
        conv = app.state.store.get_conversation(conv_id)
        if conv is None or conv.transport != "terminal":
            raise HTTPException(status_code=404, detail="No terminal session")
        client = app.state.sessions.clients.get(conv_id)
        if client is None:
            raise HTTPException(status_code=409, detail="Open the terminal session first")
        try:
            client.confirm_ready()
        except subprocess.CalledProcessError:
            raise HTTPException(status_code=409, detail="The agent is not running. Click Start to open a new session.")
        app.state.store.update_transport(conv_id, note="")
        return {"ready": True}

    @app.websocket("/ws/{conv_id}/terminal")
    async def ws_terminal(websocket: WebSocket, conv_id: str) -> None:
        """Bytes between the agent's PTY and the window. Attach never creates,
        kills or signals the agent: two sockets are simply two tmux clients."""
        token = websocket.query_params.get("token")
        origin = websocket.headers.get("origin")
        if not app.state.auth.verify(token):
            await websocket.close(code=4401)
            return
        if not app.state.auth.origin_allowed(origin):
            await websocket.close(code=4403)
            return
        # 4404 closes after the handshake: a pre-handshake close reaches the
        # browser as 1006, which the page retries forever.
        conv = app.state.store.get_conversation(conv_id)
        if conv is None or conv.transport != "terminal":
            await websocket.accept()
            await websocket.close(code=4404)
            return
        try:
            name = session_name(conv.target, conv.runtime)
        except UnsafeSessionName:
            await websocket.accept()
            await websocket.close(code=4404)
            return

        env = broker_mod.clean_env()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env["TERM"] = "xterm-256color"
        loop = asyncio.get_running_loop()
        await websocket.accept()
        try:
            tmux = terminal_mod.tmux_binary(env)
            exists = (await loop.run_in_executor(
                None, lambda: subprocess.run([tmux, "has-session", "-t", name], env=env, capture_output=True),
            )).returncode == 0
        except (OSError, subprocess.SubprocessError) as exc:
            await websocket.send_json({"type": "not_running", "reason": str(exc)})
            await websocket.close()
            return
        if not exists:
            await websocket.send_json({"type": "not_running"})
            await websocket.close()
            return

        master, slave = pty.openpty()
        # login_tty makes the PTY the client's controlling terminal (setsid +
        # TIOCSCTTY + dup2): resize reaches it as SIGWINCH and closing the
        # master hangs it up. CPython closes inherited fds after preexec_fn.
        proc = subprocess.Popen(
            [tmux, "-u", "attach-session", "-t", name],
            preexec_fn=lambda: os.login_tty(slave), env=env, close_fds=True,
        )
        os.close(slave)
        queue: asyncio.Queue = asyncio.Queue()

        def pump() -> None:
            while True:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    data = b""
                loop.call_soon_threadsafe(queue.put_nowait, data)
                if not data:
                    return

        threading.Thread(target=pump, daemon=True).start()
        receiving = asyncio.create_task(websocket.receive())
        reading = asyncio.create_task(queue.get())
        try:
            while True:
                done, _ = await asyncio.wait({receiving, reading}, return_when=asyncio.FIRST_COMPLETED)
                if reading in done:
                    data = reading.result()
                    if not data:
                        # Our tmux client ended. An external detach leaves the agent alive:
                        # close without "exited" so the page reconnects. Otherwise it is gone.
                        live = await loop.run_in_executor(None, terminal_mod.liveness, name, env)
                        if live["agent"] != "alive":
                            await websocket.send_json({"type": "exited"})
                        break
                    await websocket.send_bytes(data)
                    reading = asyncio.create_task(queue.get())
                if receiving in done:
                    message = receiving.result()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message.get("bytes"):
                        os.write(master, message["bytes"])
                    elif message.get("text"):
                        _apply_resize(master, message["text"])
                    receiving = asyncio.create_task(websocket.receive())
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            receiving.cancel()
            reading.cancel()
            await asyncio.gather(receiving, reading, return_exceptions=True)
            await loop.run_in_executor(None, _release_client, proc, master)
            with contextlib.suppress(Exception):
                await websocket.close()

    @app.websocket("/ws/{conv_id}")
    async def ws(websocket: WebSocket, conv_id: str) -> None:
        token = websocket.query_params.get("token")
        origin = websocket.headers.get("origin")
        if not app.state.auth.verify(token):
            await websocket.close(code=4401)
            return
        if origin is not None and not app.state.auth.origin_allowed(origin):
            await websocket.close(code=4403)
            return

        await websocket.accept()
        q = app.state.bus.subscribe(conv_id)
        receiving = asyncio.create_task(websocket.receive())
        event_task = asyncio.create_task(q.get())
        try:
            conv = app.state.store.get_conversation(conv_id)
            if conv is not None:
                await websocket.send_json({
                    "type": "reattach",
                    "running": [r.id for r in conv.runs if r.status == "running"],
                    "messages": len(conv.messages),
                })
            while True:
                done, _ = await asyncio.wait({receiving, event_task}, return_when=asyncio.FIRST_COMPLETED)
                if receiving in done:
                    if receiving.result()["type"] == "websocket.disconnect":
                        break
                    receiving = asyncio.create_task(websocket.receive())
                if event_task in done:
                    await websocket.send_json(event_task.result())
                    event_task = asyncio.create_task(q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            receiving.cancel()
            event_task.cancel()
            await asyncio.gather(receiving, event_task, return_exceptions=True)
            app.state.bus.unsubscribe(conv_id, q)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    # xterm.js and its fit add-on, vendored (MIT); no CDN, same origin as the page.
    app.mount("/vendor", StaticFiles(directory=STATIC / "vendor"), name="vendor")

    @app.get("/boot.js")
    def boot() -> JSONResponse:
        # The token is injected into the served page at launch, not persisted.
        return JSONResponse({"ok": True})

    return app


async def _json_body(request: Request, limit: int) -> dict:
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail="payload too large")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad json")
    return parsed if isinstance(parsed, dict) else {}


def _apply_resize(master: int, text: str) -> None:
    """Only a well-formed resize frame touches the PTY; any other text is ignored."""
    try:
        message = json.loads(text)
    except ValueError:
        return
    if not isinstance(message, dict) or message.get("type") != "resize":
        return
    cols, rows = message.get("cols"), message.get("rows")
    if not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 1000 for v in (cols, rows)):
        return
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _release_client(proc: subprocess.Popen, master: int) -> None:
    """Detach the tmux client (never the agent), then close the PTY.

    Order matters on macOS: closing the master while the pump thread is
    blocked in read() stalls close() for seconds. Ending the client first
    ends that read, so the close is immediate. The tmux server and the
    agent in its pane are untouched.
    """
    if proc.poll() is None:
        with contextlib.suppress(OSError):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
    with contextlib.suppress(OSError):
        os.close(master)


def _resolve_target(hub: pathlib.Path, slug: str):
    for t in targets_mod.discover_targets(hub=hub):
        if t.slug == slug:
            return t
    return targets_mod.discover_targets(hub=hub)[0]


def _execute_run(app, conv_id, run_id, prompt, target_slug, runtime, target) -> None:
    """Runs off the event loop. Never raises into the server."""
    bus = app.state.bus
    store = app.state.store
    kb = pathlib.Path(target.knowledge)

    try:
        before = diff_kb.snapshot(kb)
        bus.publish(conv_id, {"type": "progress", "run_id": run_id, "text": f"routing to {runtime}…"})

        verdict = broker_mod.execute(
            prompt=prompt, cwd=target.cwd, conversation_id=conv_id,
            target_slug=target_slug, runtime=runtime, face_run_id=run_id,
        )

        evidence = diff_kb.compare(before, diff_kb.snapshot(kb)).as_dict()
        if verdict.ok:
            status = "done"
        elif verdict.category == "stopped":
            status = "stopped"
        else:
            status = "degraded"

        store.finish_run(
            conv_id, run_id, status=status,
            text=verdict.text if verdict.ok else "",
            reason=verdict.reason, category=verdict.category,
            evidence={**evidence, "lane": verdict.lane, "lane_note": verdict.lane_note},
        )
        bus.publish(conv_id, {
            "type": "run_finished", "run_id": run_id, "status": status,
            "ok": verdict.ok, "degraded": verdict.degraded,
            "reason": verdict.reason, "category": verdict.category,
            "lane": verdict.lane, "lane_note": verdict.lane_note,
            "text": verdict.text if verdict.ok else "",
            "evidence": evidence,
        })
    except Exception as exc:  # pragma: no cover - defensive
        with contextlib.suppress(Exception):
            store.finish_run(conv_id, run_id, status="failed", reason=f"backend error: {exc}")
        bus.publish(conv_id, {
            "type": "run_finished", "run_id": run_id, "status": "failed",
            "ok": False, "degraded": True, "reason": f"backend error: {exc}",
        })


def _execute_session(app, conv_id, run_id, prompt, target_slug, runtime, target):
    store, bus = app.state.store, app.state.bus
    try:
        conv = store.get_conversation(conv_id)
        client = app.state.sessions.client(conv, target)
        before = diff_kb.snapshot(pathlib.Path(target.knowledge))
        result = client.execute(prompt)
        if result.get("still_running"):
            store.update_transport(conv_id, note=result.get("reason") or "The protocol was interrupted, but the process is still running")
            bus.publish(conv_id, {"type": "progress", "run_id": run_id, "text": result.get("reason") or "The process is still running; automatic completion is not available."})
            result = client.wait_for_completion()
        if result.get("submitted"):
            # The paste is the whole job: the terminal shows the rest, so the
            # run closes now and never marks the app busy.
            reason = result.get("reason") or "Message sent to the terminal."
            store.finish_run(conv_id, run_id, "submitted", reason=reason, category="submitted",
                             evidence={"pid": result.get("pid"), "lane": "terminal"})
            bus.publish(conv_id, {"type": "run_finished", "run_id": run_id, "status": "submitted",
                                  "ok": True, "reason": reason})
            return
        evidence = diff_kb.compare(before, diff_kb.snapshot(pathlib.Path(target.knowledge))).as_dict()
        status = "done" if result.get("ok") else ("stopped" if result.get("category") == "stopped" else "degraded")
        store.finish_run(conv_id, run_id, status, text=result.get("text", ""),
                         reason=result.get("reason", ""), category=result.get("category"),
                         evidence={**evidence, "pid": result.get("pid"), "provider_session_id": result.get("session_id"), "lane": app.state.sessions.mode(conv)})
        if not result.get("ok"):
            store.update_transport(conv_id, note=result.get("reason") or "Session transport failed")
        bus.publish(conv_id, {**result, "type": "run_finished", "run_id": run_id, "status": status, "evidence": evidence})
    except Exception as exc:
        reason = f"Session unavailable: {exc}"
        store.finish_run(conv_id, run_id, "degraded", reason=reason)
        store.update_transport(conv_id, note=reason)
        bus.publish(conv_id, {"type": "run_finished", "run_id": run_id, "status": "degraded", "ok": False, "reason": reason})
