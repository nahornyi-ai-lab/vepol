"""Own persistent protocol clients independently of page/window connections."""
from __future__ import annotations

import json
import os
import pathlib
import threading

from .broker import clean_env, resume_key


class SessionManager:
    def __init__(self, store, bus, hub: pathlib.Path, desktop: bool):
        self.store, self.bus, self.hub, self.desktop = store, bus, hub, desktop
        self.clients: dict = {}
        self._lock = threading.RLock()
        self.events: dict[str, list[dict]] = {}

    def mode(self, conv):
        return "session" if self.desktop and conv.transport == "oneshot" else conv.transport

    def legacy_id(self, conv):
        if conv.provider_session_id:
            return conv.provider_session_id
        path = pathlib.Path(os.environ.get("KB_ORCHESTRATOR_STATE_FILE") or
                            str(pathlib.Path(os.environ.get("KB_ORCHESTRATOR_STATE_DIR") or self.hub / ".orchestrator") / "state.json"))
        try:
            row = json.loads(path.read_text()).get("sessions", {}).get(resume_key(conv.id, conv.target, conv.runtime), {})
            return row.get(f"{conv.runtime}_session_id")
        except (OSError, ValueError, AttributeError):
            return None

    def continuation_available(self, conv):
        if conv.runs and conv.runs[-1].category == "continuation_unavailable":
            return False
        return not (self.desktop and conv.transport == "oneshot" and
                    (conv.messages or conv.runs) and not self.legacy_id(conv))

    def describe(self, conv):
        with self._lock:
            client = self.clients.get(conv.id)
            steps = list(self.events.get(conv.id, []))
        pending = list(client.pending) if client else []
        agent = {"agent": None, "pid": client.pid if client else None}
        if self.mode(conv) == "terminal":
            # Liveness from process evidence, with or without a client object,
            # so a relaunched app reports the truth before anything is opened.
            from .sessions import UnsafeSessionName, session_name
            from .terminal_session import liveness
            try:
                live = liveness(session_name(conv.target, conv.runtime), clean_env())
            except UnsafeSessionName as exc:
                live = {"agent": "unknown", "pid": None, "reason": str(exc)}
            agent = {"agent": live["agent"], "pid": live["pid"], "agent_reason": live["reason"]}
        return {
                **agent,
                "transport": self.mode(conv),
                "provider_session_id": client.session_id if client else conv.provider_session_id,
                "pending": pending,
                "steps": steps,
                "continuation_available": self.continuation_available(conv),
                "transport_note": conv.transport_note,
                "takeover_available": self.mode(conv) == "terminal",
                "terminal_ready": bool(getattr(client, "ready", False)),
        }

    def busy(self):
        with self._lock:
            clients = list(self.clients.values())
        return any(getattr(client, "busy", False) for client in clients)

    def client(self, conv, target):
        with self._lock:
            if conv.id in self.clients:
                return self.clients[conv.id]
            if not self.continuation_available(conv):
                raise ValueError("The agent's original session was not found. History is kept; it cannot be continued.")
            mode = self.mode(conv)
            session_id = self.legacy_id(conv)
            env = clean_env()
            env.pop("OPENAI_API_KEY", None)
            env["KB_HUB"] = str(self.hub)

            def event(item):
                with self._lock:
                    items = self.events.setdefault(conv.id, [])
                    if item.get("type") in {"progress", "permission", "permission_resolved"}:
                        items.append(item)
                        del items[:-100]
                self.bus.publish(conv.id, item)

            def identified(value):
                self.store.update_transport(conv.id, transport=mode, provider_session_id=value, note="")

            if mode == "terminal":
                from .terminal_session import TerminalSession
                client = TerminalSession(cwd=target.cwd, project=conv.target, runtime=conv.runtime,
                                         on_event=event, env=env, session_id=session_id,
                                         prompt_dir=self.store.root / "prompts")
            elif conv.runtime == "claude":
                from .claude_session import ClaudeSession
                client = ClaudeSession(target.cwd, session_id, event, identified, env)
            elif conv.runtime == "codex":
                from .codex_session import CodexSession
                client = CodexSession(target.cwd, session_id, event, identified, env)
            else:
                raise ValueError("Only terminal mode is available for this agent.")
            self.clients[conv.id] = client
            return client

    def respond(self, conv_id, request_id, response):
        with self._lock:
            client = self.clients.get(conv_id)
        if client is None:
            raise ValueError("The session is not running")
        client.respond(request_id, response)

    def close(self):
        with self._lock:
            clients = list(self.clients.values())
        for client in clients:
            client.close()
