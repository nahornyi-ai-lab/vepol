"""Persistent Claude stream-json transport owned by one conversation.

The stdout reader remains active while the owner answers a permission request.
A result ends a turn, never the process or the owner's manual board stage.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import threading
import uuid
from typing import Callable


def _runtime_env(base: dict | None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key.startswith(("CLAUDE", "CODEX_COMPANION_")) or key in {
            "OPENAI_API_KEY", "AI_AGENT", "ANTHROPIC_BASE_URL",
        }:
            env.pop(key, None)
    return env


def _claude_binary(env: dict) -> str:
    for candidate in (
        "/opt/homebrew/bin/claude",
        str(pathlib.Path.home() / ".local/bin/claude"),
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("claude", path=env.get("PATH", ""))
    if found:
        return os.path.abspath(found)
    raise FileNotFoundError("Claude executable is unavailable")


class ClaudeSession:
    def __init__(
        self, cwd: str, session_id: str | None,
        on_event: Callable[[dict], None], on_session: Callable[[str], None],
        env: dict | None = None,
    ) -> None:
        self.cwd = cwd
        self._resume_id = session_id
        self._session_id = session_id
        self._new_id = str(uuid.uuid4())
        self._on_event = on_event
        self._on_session = on_session
        self._env = _runtime_env(env)
        self._proc: subprocess.Popen | None = None
        self._condition = threading.Condition(threading.RLock())
        self._write_lock = threading.Lock()
        self._execute_lock = threading.Lock()
        self._ready = False
        self._closed = False
        self._failure: tuple[str, str] | None = None
        self._init_id: str | None = None
        self._controls: set[str] = set()
        self._requests: dict[str, dict] = {}
        self._turn_running = False
        self._result: dict | None = None
        self._assistant_text: list[str] = []
        self._deltas: list[str] = []
        self._tools_seen: set[str] = set()
        self._protocol_issue = ""
        self._stderr = ""
        self._interrupt_requested = False
        self._identity_reported = False

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def pending(self) -> list[dict]:
        with self._condition:
            return [dict(entry["public"]) for entry in self._requests.values()]

    @property
    def busy(self) -> bool:
        """Keep lifecycle ownership while setup, a turn, or a decision is active."""
        with self._condition:
            return bool(
                self._turn_running or self._execute_lock.locked() or self._requests
            )

    def _emit(self, event: dict) -> None:
        try:
            self._on_event(event)
        except Exception as exc:
            self._fail(f"Could not publish Claude activity: {exc}", "backend_error")

    def _fail(self, reason: str, category: str = "protocol_error") -> None:
        with self._condition:
            if self._failure is None:
                self._failure = (reason, category)
            self._condition.notify_all()

    def _write(self, message: dict) -> None:
        with self._write_lock:
            proc = self._proc
            if proc is None or proc.stdin is None or proc.poll() is not None:
                raise RuntimeError("Claude session is not connected")
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            proc.stdin.flush()

    def _start(self) -> None:
        if self._proc is not None:
            return
        argv = [
            _claude_binary(self._env), "-p",
            "--input-format", "stream-json", "--output-format", "stream-json",
            "--verbose", "--replay-user-messages", "--include-partial-messages",
            "--permission-mode", "manual", "--permission-prompt-tool", "stdio",
        ]
        argv += ["--resume", self._resume_id] if self._resume_id else [
            "--session-id", self._new_id,
        ]
        self._init_id = f"init-{uuid.uuid4().hex}"
        self._controls.add(self._init_id)
        self._proc = subprocess.Popen(
            argv, cwd=self.cwd, env=self._env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            start_new_session=True,
        )
        threading.Thread(target=self._read_stderr, daemon=True).start()
        threading.Thread(target=self._read_stdout, daemon=True).start()
        self._write({
            "type": "control_request", "request_id": self._init_id,
            "request": {"subtype": "initialize", "hooks": None},
        })

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for line in self._proc.stderr:
            with self._condition:
                self._stderr = (self._stderr + line)[-12000:]

    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("expected a JSON object")
                    self._handle(message)
                except Exception as exc:
                    # Keep draining the process; a protocol fault is never a
                    # reason to kill a live agent or silently start a fresh one.
                    self._fail(f"Invalid Claude protocol output: {exc}")
        except OSError as exc:
            self._fail(f"Claude output channel failed: {exc}")
        finally:
            returncode = self._proc.wait()
            with self._condition:
                self._turn_running = False
                requests = list(self._requests)
                self._requests.clear()
                if not self._closed and self._failure is None:
                    reason = self._stderr.strip() or f"Claude exited with code {returncode}"
                    if self._resume_id and not self._identity_reported:
                        reason = f"Continuation unavailable: {reason}"
                    self._failure = (reason, self._category(reason))
                self._condition.notify_all()
            for request_id in requests:
                self._emit({"type": "permission_resolved", "request_id": request_id})

    @staticmethod
    def _category(reason: str) -> str:
        lowered = reason.lower()
        if any(word in lowered for word in ("oauth", "not logged", "authenticate", "authentication")):
            return "auth"
        if "continuation unavailable" in lowered or "session not found" in lowered:
            return "continuation_unavailable"
        if "rate limit" in lowered or "usage limit" in lowered:
            return "rate_limit"
        if "interrupt" in lowered:
            return "stopped"
        return "runtime_error"

    def _record_session(self, session_id: str) -> None:
        expected = self._resume_id or self._new_id
        if session_id != expected:
            self._fail(
                "Continuation unavailable: Claude returned a different session identity",
                "continuation_unavailable",
            )
            return
        if self._session_id != session_id or not self._identity_reported:
            self._session_id = session_id
            self._on_session(session_id)
            self._identity_reported = True

    def _handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "control_response":
            response = message.get("response", {})
            request_id = response.get("request_id")
            with self._condition:
                if request_id not in self._controls:
                    # Replay can echo a host permission reply. The official
                    # SDK likewise consumes replies only for awaited controls.
                    return
                self._controls.discard(request_id)
                if response.get("subtype") == "error":
                    self._fail(f"Claude control request failed: {response.get('error', 'unknown error')}")
                elif response.get("subtype") != "success":
                    self._fail("Claude returned an invalid control response subtype")
                elif request_id == self._init_id:
                    self._ready = True
                    self._condition.notify_all()
            return
        if kind == "control_request":
            self._permission(message)
            return
        if kind == "control_cancel_request":
            request_id = message.get("request_id")
            with self._condition:
                removed = self._requests.pop(request_id, None)
            if removed:
                self._emit({"type": "permission_resolved", "request_id": request_id})
            return

        sid = message.get("session_id")
        if isinstance(sid, str) and sid and sid != "default":
            self._record_session(sid)
        if kind == "stream_event":
            event = message.get("event", {})
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                    self._deltas.append(delta["text"])
                    self._emit({"type": "text_delta", "text": delta["text"]})
            elif event.get("type") == "content_block_start":
                self._tool_progress(event.get("content_block", {}))
        elif kind == "assistant":
            for block in message.get("message", {}).get("content", []):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    self._assistant_text.append(block["text"])
                    if not self._deltas:
                        self._emit({"type": "text_delta", "text": block["text"]})
                else:
                    self._tool_progress(block)
        elif kind == "result":
            text = message.get("result")
            if not isinstance(text, str) or not text.strip():
                text = "\n".join(self._assistant_text) or "".join(self._deltas)
            ok = message.get("subtype") == "success" and not message.get("is_error")
            errors = message.get("errors") or []
            reason = "ok" if ok else "; ".join(str(error) for error in errors)
            if not ok and not reason:
                reason = text or str(message.get("subtype") or "Claude turn failed")
            if self._resume_id and not ok:
                lowered = reason.lower()
                if "no conversation found" in lowered or (
                    "session" in lowered and ("not found" in lowered or "does not exist" in lowered)
                ):
                    reason = f"Continuation unavailable: {reason}"
            if ok and not text.strip():
                ok, reason = False, "Claude completed the turn without an answer"
            if self._protocol_issue:
                ok, reason = False, self._protocol_issue
            with self._condition:
                self._turn_running = False
                requests = list(self._requests)
                self._requests.clear()
                self._result = self._outcome(
                    ok, text if ok else "", reason,
                    "ok" if ok else self._category(reason),
                )
                self._condition.notify_all()
            for request_id in requests:
                self._emit({"type": "permission_resolved", "request_id": request_id})
        elif kind == "system" and message.get("subtype") == "init":
            self._emit({"type": "progress", "text": "Claude session connected"})
        # user echoes and other system lifecycle messages are not turn results.

    def _tool_progress(self, block: dict) -> None:
        if block.get("type") != "tool_use":
            return
        tool_id = str(block.get("id") or "")
        if tool_id and tool_id in self._tools_seen:
            return
        if tool_id:
            self._tools_seen.add(tool_id)
        self._emit({"type": "progress", "text": f"Using {block.get('name', 'tool')}"})

    def _permission(self, message: dict) -> None:
        request_id = message.get("request_id")
        data = message.get("request", {})
        if not isinstance(request_id, str) or not isinstance(data, dict):
            raise ValueError("invalid control request")
        if data.get("subtype") != "can_use_tool":
            reason = f"Unsupported Claude control request: {data.get('subtype')}"
            self._protocol_issue = reason
            self._write({
                "type": "control_response", "response": {
                    "subtype": "error", "request_id": request_id, "error": reason,
                },
            })
            self._emit({"type": "progress", "text": reason})
            return
        original = data.get("input")
        if not isinstance(original, dict):
            raise ValueError("permission request input must be an object")
        tool_name = str(data.get("tool_name") or "Tool")
        public = {
            "id": request_id,
            "kind": "questions" if tool_name == "AskUserQuestion" else "tool",
            "title": tool_name,
            "details": json.dumps(original, ensure_ascii=False, indent=2),
        }
        if tool_name == "AskUserQuestion":
            public["questions"] = original.get("questions", [])
        with self._condition:
            self._requests[request_id] = {"public": public, "input": original}
        self._emit({"type": "permission", "request": public})

    def respond(self, request_id: str, response: dict) -> None:
        decision = response.get("decision")
        if decision not in ("allow", "deny"):
            raise ValueError("permission decision must be allow or deny")
        with self._condition:
            entry = self._requests.get(request_id)
            if entry is None:
                raise KeyError("permission request is no longer pending")
            if decision == "deny":
                answer = {"behavior": "deny", "message": "The owner declined this action."}
            else:
                updated = dict(entry["input"])
                if entry["public"]["kind"] == "questions":
                    answers = response.get("answers")
                    if not isinstance(answers, dict) or not all(
                        isinstance(key, str) and isinstance(value, str)
                        for key, value in answers.items()
                    ):
                        raise ValueError("question answers must map question text to strings")
                    expected = [q.get("question") for q in updated.get("questions", [])]
                    if any(question not in answers for question in expected):
                        raise ValueError("an answer is required for each question")
                    updated["answers"] = answers
                answer = {"behavior": "allow", "updatedInput": updated}
            self._write({
                "type": "control_response", "response": {
                    "subtype": "success", "request_id": request_id, "response": answer,
                },
            })
            self._requests.pop(request_id, None)
        self._emit({"type": "permission_resolved", "request_id": request_id})

    def _outcome(self, ok: bool, text: str, reason: str, category: str) -> dict:
        return {
            "ok": ok, "text": text, "reason": reason, "category": category,
            "pid": self.pid, "session_id": self.session_id,
            "still_running": self._turn_running,
        }

    def execute(self, prompt: str) -> dict:
        if not self._execute_lock.acquire(blocking=False):
            return self._outcome(False, "", "A Claude turn is already active", "busy")
        try:
            with self._condition:
                if self._closed:
                    return self._outcome(False, "", "Claude session is closed", "closed")
                if self._failure:
                    return self._outcome(False, "", *self._failure)
                if self._interrupt_requested:
                    self._interrupt_requested = False
                    return self._outcome(False, "", "Stopped by the owner before the turn started", "stopped")
                self._result = None
                self._assistant_text = []
                self._deltas = []
                self._tools_seen = set()
                self._protocol_issue = ""
            try:
                self._start()
                with self._condition:
                    self._condition.wait_for(lambda: self._ready or self._failure is not None)
                    if self._failure:
                        return self._outcome(False, "", *self._failure)
                    if self._interrupt_requested:
                        self._interrupt_requested = False
                        return self._outcome(False, "", "Stopped by the owner before the turn started", "stopped")
                    self._turn_running = True
                    self._write({
                        "type": "user", "message": {"role": "user", "content": prompt},
                        "parent_tool_use_id": None,
                        "session_id": self._session_id or self._new_id,
                    })
                with self._condition:
                    self._condition.wait_for(lambda: self._result is not None or
                                             (self._failure is not None and not self._turn_running))
                    if self._failure:
                        return self._outcome(False, "", *self._failure)
                    return dict(self._result)
            except (OSError, RuntimeError) as exc:
                self._fail(f"Claude transport failed: {exc}")
                return self._outcome(False, "", *self._failure)
        finally:
            self._execute_lock.release()

    def wait_for_completion(self) -> dict:
        """Retain the run until a typed result or process exit ends it."""
        with self._condition:
            self._condition.wait_for(lambda: not self._turn_running)
            if self._failure:
                return self._outcome(False, (self._result or {}).get("text", ""), *self._failure)
            return dict(self._result) if self._result else self._outcome(False, "", "No active Claude turn", "no_active_turn")

    def interrupt(self) -> None:
        request_id = f"interrupt-{uuid.uuid4().hex}"
        with self._condition:
            if self._proc is None or not self._ready:
                self._interrupt_requested = True
                return
            if not self._turn_running:
                return
            self._controls.add(request_id)
            self._write({
                "type": "control_request", "request_id": request_id,
                "request": {"subtype": "interrupt"},
            })

    def close(self) -> None:
        """Explicit idle shutdown: close input and await natural process exit."""
        with self._condition:
            if self._turn_running or self._requests or self._execute_lock.locked():
                raise RuntimeError("Claude still has work in flight; keep the app running")
            self._closed = True
        with self._write_lock:
            if self._proc is not None and self._proc.stdin is not None:
                self._proc.stdin.close()
        if self._proc is not None:
            self._proc.wait()
