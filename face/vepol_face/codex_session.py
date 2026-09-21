"""One persistent Codex app-server process and provider thread per conversation.

The wire shapes follow the installed Codex 0.153.4 app-server v2 schema.
Only an explicit turn/completed notification completes a healthy turn; waiting
for output or a human answer has no deadline. CLI authentication remains owned
by Codex, and the caller owns persistence and the lifetime of this client.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import threading
from collections import deque
from typing import Callable


class CodexSessionError(RuntimeError):
    def __init__(self, reason: str, category: str = "protocol_error") -> None:
        super().__init__(reason)
        self.category = category


class CodexSession:
    def __init__(
        self, cwd: str, session_id: str | None,
        on_event: Callable[[dict], None], on_session: Callable[[str], None],
        env: dict | None = None,
    ) -> None:
        self.cwd = str(pathlib.Path(cwd).expanduser().resolve())
        self._session_id = session_id
        self._on_event = on_event
        self._on_session = on_session
        self._env = dict(os.environ if env is None else env)
        self._process: subprocess.Popen | None = None
        self._output_thread: threading.Thread | None = None
        self._error_thread: threading.Thread | None = None
        self._state = threading.Condition(threading.RLock())
        self._write_lock = threading.Lock()
        self._execute_lock = threading.Lock()
        self._replies: dict[str, dict | None] = {}
        self._next_id = 0
        self._pending: dict[str, dict] = {}
        self._stderr: deque[str] = deque(maxlen=12)
        self._initialized = False
        self._thread_ready = False
        self._session_saved = False
        self._closed = False
        self._busy = False
        self._turn_requested = False
        self._turn_id: str | None = None
        self._completed: dict | None = None
        self._items: dict[str, dict] = {}
        self._messages: dict[str, dict] = {}
        self._failure: CodexSessionError | None = None
        self._turn_problem = ""
        self._interrupt_requested = False

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    @property
    def session_id(self) -> str | None:
        with self._state:
            return self._session_id

    @property
    def pending(self) -> list[dict]:
        """Pending human requests survive a view disconnect inside this host."""
        with self._state:
            return copy.deepcopy([entry["request"] for entry in self._pending.values()])

    @property
    def busy(self) -> bool:
        """A returned transport error does not imply that provider work ended."""
        with self._state:
            alive = self._process is not None and self._process.poll() is None
            return bool(self._busy or (alive and (self._turn_requested or self._turn_id)))

    def execute(self, prompt: str) -> dict:
        if not self._execute_lock.acquire(blocking=False):
            return self._result(False, "", "A Codex turn is already running", "busy")
        try:
            with self._state:
                if self._closed:
                    raise CodexSessionError("Codex session is closed", "session_closed")
                if self._turn_id or self._turn_requested:
                    raise CodexSessionError("The previous Codex turn is still active", "busy")
                self._busy = True
                self._completed = None
                self._items = {}
                self._messages = {}
                self._turn_problem = ""
                self._interrupt_requested = False
            self._ensure_session()
            with self._state:
                if self._turn_problem:
                    raise CodexSessionError(self._turn_problem)
                self._turn_requested = True
            started = self._rpc("turn/start", {
                "threadId": self.session_id,
                "input": [{"type": "text", "text": prompt}],
            })
            turn_id = (started.get("turn") or {}).get("id")
            if not isinstance(turn_id, str) or not turn_id:
                raise CodexSessionError("Codex turn/start returned no turn identity")
            with self._state:
                if self._turn_id and self._turn_id != turn_id:
                    raise CodexSessionError("Codex returned a different active turn identity")
                self._turn_id = turn_id
                interrupt_requested = self._interrupt_requested
            if interrupt_requested and self._completed is None:
                self.interrupt()
            with self._state:
                while self._completed is None and self._failure is None:
                    self._state.wait()
                if self._completed is None:
                    raise self._failure
                turn = self._completed
                if turn.get("id") != turn_id:
                    raise CodexSessionError("Codex completed an unexpected turn identity")
                text = self._answer_text()
                self._turn_id = None
                self._turn_requested = False
                self._busy = False
                problem = self._turn_problem
            self._clear_pending()
            return self._completed_result(turn, text, problem)
        except CodexSessionError as exc:
            with self._state:
                if exc.category == "request_rejected" and self._turn_id is None:
                    self._turn_requested = False
                self._busy = False
                if self.busy and not self._turn_problem:
                    self._turn_problem = str(exc)
                text = self._answer_text()
            return self._result(False, text, str(exc), exc.category)
        except (OSError, ValueError) as exc:
            with self._state:
                self._busy = False
            return self._result(False, "", self._safe(str(exc)), "process_error")
        finally:
            with self._state:
                self._busy = False
            self._execute_lock.release()

    def wait_for_completion(self) -> dict:
        """Finish observing a turn after execute() reported still_running.

        A protocol error is already visible to the owner, but it is not an end
        event. Wait for the retained turn's completion or actual process exit,
        with no polling, silence timeout, replacement turn, or process kill.
        """
        if not self._execute_lock.acquire(blocking=False):
            return self._result(False, "", "A Codex turn is already being observed", "busy")
        try:
            with self._state:
                expected_turn = self._turn_id
                while (
                    self._completed is None
                    and (self._turn_requested or self._turn_id)
                    and self._process is not None
                    and self._process.poll() is None
                ):
                    self._state.wait()
                text = self._answer_text()
                turn = self._completed
                problem = self._turn_problem
                failure = self._failure
                if turn is not None:
                    if expected_turn and turn.get("id") != expected_turn:
                        return self._result(False, text, "Codex completed an unexpected turn identity", "protocol_error")
                    self._turn_id = None
                    self._turn_requested = False
                elif failure is not None:
                    return self._result(False, text, str(failure), failure.category)
                elif self._process is not None and self._process.poll() is not None:
                    return self._result(False, text, f"Codex app-server exited with status {self._process.returncode}", "process_exit")
                else:
                    return self._result(False, text, "No active Codex turn is being observed", "no_active_turn")
            self._clear_pending()
            return self._completed_result(turn, text, problem)
        finally:
            self._execute_lock.release()

    def _completed_result(self, turn: dict, text: str, problem: str) -> dict:
        if problem:
            return self._result(False, text, problem, "protocol_error")
        status = turn.get("status")
        if status == "completed":
            if not text.strip():
                return self._result(False, text, "Codex completed without an assistant reply", "empty_output")
            return self._result(True, text, "", None)
        if status == "interrupted":
            return self._result(False, text, "Codex turn was interrupted", "interrupted")
        reason = self._error_reason(turn.get("error") or {}, "Codex turn failed")
        return self._result(False, text, reason, "runtime_error")

    def respond(self, request_id: str, response: dict) -> None:
        """Translate an explicit UI response without granting persistent policy."""
        if not isinstance(response, dict) or response.get("decision") not in {"allow", "deny"}:
            raise ValueError("decision must be allow or deny")
        key = str(request_id)
        with self._state:
            entry = self._pending.get(key)
            if entry is None:
                raise KeyError("This Codex request is no longer pending")
            method, params = entry["method"], entry["params"]
            allowed = response["decision"] == "allow"
            if method == "item/tool/requestUserInput":
                supplied = response.get("answers") or {}
                if not isinstance(supplied, dict):
                    raise ValueError("answers must map questions to text")
                answers = {}
                if allowed:
                    for question in params["questions"]:
                        value = supplied.get(question["question"], supplied.get(question["id"]))
                        if not isinstance(value, str):
                            raise ValueError("Provide a text answer for every question")
                        answers[question["id"]] = {"answers": [value]}
                payload = {"answers": answers}
            elif method == "item/permissions/requestApproval":
                payload = {"permissions": params["permissions"] if allowed else {}, "scope": "turn"}
            else:
                decision = "accept" if allowed else "decline"
                choices = params.get("availableDecisions")
                if choices is not None and decision not in choices:
                    if not allowed and "cancel" in choices:
                        decision = "cancel"
                    else:
                        raise ValueError("Codex does not offer this single-action decision")
                payload = {"decision": decision}
            # Keep the entry until the response has actually reached stdin. A
            # failed write must never make an unanswered request look resolved.
            self._write({"id": entry["raw_id"], "result": payload})
            self._pending.pop(key, None)
        self._emit({"type": "permission_resolved", "request_id": key})

    def interrupt(self) -> None:
        """Interrupt the current turn, keeping its process and thread alive."""
        with self._state:
            self._interrupt_requested = True
            turn_id, session_id = self._turn_id, self._session_id
            if not turn_id or self._completed is not None:
                return
        self._rpc("turn/interrupt", {"threadId": session_id, "turnId": turn_id})

    def close(self) -> None:
        """Called only for an explicit idle application quit; never a timeout."""
        with self._state:
            if self.busy:
                raise RuntimeError("Cannot close an active Codex session; interrupt it explicitly first")
            self._closed = True
            process = self._process
        if process and process.poll() is None:
            with self._write_lock:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            # EOF is app-server's orderly stdio shutdown. There is no force-kill
            # or wall-clock deadline, including when lifecycle hooks are active.
            process.wait()

    def _ensure_session(self) -> None:
        if self._failure:
            raise self._failure
        if self._process is None:
            home = pathlib.Path(self._env.get("HOME", str(pathlib.Path.home())))
            candidate = home / ".local/bin/codex"
            binary = str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else shutil.which(
                "codex", path=self._env.get("PATH", "")
            )
            if not binary:
                raise CodexSessionError("Codex executable was not found in the application PATH", "runtime_unavailable")
            binary = str(pathlib.Path(binary).resolve())
            self._process = subprocess.Popen(
                [binary, "app-server"], cwd=self.cwd, env=self._env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            self._output_thread = threading.Thread(target=self._read_stdout, name="vepol-codex-output", daemon=True)
            self._error_thread = threading.Thread(target=self._read_stderr, name="vepol-codex-errors", daemon=True)
            self._output_thread.start()
            self._error_thread.start()
            threading.Thread(target=self._wait_exit, name="vepol-codex-exit", daemon=True).start()
            self._emit({"type": "progress", "text": "Codex: подключение к постоянной сессии"})
        if not self._initialized:
            self._rpc("initialize", {
                "clientInfo": {"name": "vepol_desktop", "title": "Vepol", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            })
            self._write({"method": "initialized", "params": {}})
            self._initialized = True
        if not self._thread_ready:
            previous_id = self.session_id
            params = {"cwd": self.cwd, "sandbox": "workspace-write", "approvalPolicy": "on-request", "approvalsReviewer": "user"}
            method = "thread/resume" if previous_id else "thread/start"
            if previous_id:
                params["threadId"] = previous_id
            try:
                result = self._rpc(method, params)
            except CodexSessionError as exc:
                if previous_id:
                    raise CodexSessionError("Original Codex session could not be resumed: " + str(exc), "continuation_unavailable") from exc
                raise
            actual_id = (result.get("thread") or {}).get("id")
            if not isinstance(actual_id, str) or not actual_id or (previous_id and actual_id != previous_id):
                raise CodexSessionError("Codex did not confirm the original provider session identity", "continuation_unavailable")
            with self._state:
                self._session_id = actual_id
                self._thread_ready = True
            if result.get("approvalPolicy") != "on-request" or result.get("approvalsReviewer") != "user" or (result.get("sandbox") or {}).get("type") != "workspaceWrite":
                self._fail("Codex did not apply the requested workspace sandbox and human approvals", "protocol_error")
                raise self._failure
        if not self._session_saved:
            try:
                self._on_session(self.session_id)
            except Exception as exc:
                # Retain the real identity in memory so a persistence retry
                # saves this same thread, rather than creating another one.
                raise CodexSessionError("Could not persist Codex session identity", "persistence_error") from exc
            self._session_saved = True

    def _rpc(self, method: str, params: dict) -> dict:
        with self._state:
            self._next_id += 1
            request_id = f"vepol-{self._next_id}"
            self._replies[request_id] = None
        try:
            self._write({"id": request_id, "method": method, "params": params})
            with self._state:
                while self._replies[request_id] is None and self._failure is None:
                    self._state.wait()
                reply = self._replies[request_id]
                if reply is None:
                    raise self._failure
            if "error" in reply:
                raise CodexSessionError(f"{method}: {self._error_reason(reply['error'], 'request failed')}", "request_rejected")
            result = reply.get("result")
            if not isinstance(result, dict):
                raise CodexSessionError(f"{method}: invalid response payload")
            return result
        finally:
            with self._state:
                self._replies.pop(request_id, None)

    def _write(self, message: dict) -> None:
        try:
            with self._write_lock:
                process = self._process
                if process is None or process.poll() is not None or not process.stdin or process.stdin.closed:
                    raise CodexSessionError("Codex app-server is not connected", "process_exit")
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()
        except (OSError, ValueError) as exc:
            # Acquire state only after releasing the write lock: respond() can
            # legitimately hold state while sending a human answer.
            self._fail("Codex app-server input closed", "process_exit")
            raise CodexSessionError("Codex app-server input closed", "process_exit") from exc

    def _read_stdout(self) -> None:
        try:
            for line in self._process.stdout:
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("not an object")
                except (ValueError, TypeError):
                    self._fail("Codex emitted an invalid JSON protocol message", "protocol_error")
                    continue
                if "method" in message:
                    if "id" in message:
                        try:
                            self._handle_request(message)
                        except (KeyError, TypeError, ValueError):
                            self._unsupported_request(message, "Malformed Codex server request", -32602)
                    else:
                        self._handle_notification(message["method"], message.get("params") or {})
                elif "id" in message:
                    with self._state:
                        if message["id"] in self._replies:
                            self._replies[message["id"]] = message
                            self._state.notify_all()
            if not self._closed and self._process.poll() is None:
                self._fail("Codex app-server closed its protocol output", "protocol_error")
        except Exception as exc:
            self._fail("Codex protocol reader failed: " + self._safe(str(exc)), "protocol_error")

    def _read_stderr(self) -> None:
        for line in self._process.stderr:
            with self._state:
                self._stderr.append(self._safe(line.strip())[:1000])

    def _wait_exit(self) -> None:
        code = self._process.wait()
        # Drain already-written completion/reply messages before reporting the
        # process exit. Otherwise a fast natural exit can hide a valid result.
        self._output_thread.join()
        self._error_thread.join()
        with self._state:
            detail = "\n".join(self._stderr)[-2000:]
            self._turn_id = None
            self._turn_requested = False
        reason = f"Codex app-server exited with status {code}"
        if detail:
            reason += ": " + detail
        self._fail(reason, "process_exit")
        self._clear_pending()

    def _handle_request(self, message: dict) -> None:
        method, raw_id = message["method"], message["id"]
        params = message.get("params") or {}
        titles = {
            "item/commandExecution/requestApproval": "Разрешить выполнение команды",
            "item/fileChange/requestApproval": "Разрешить изменение файлов",
            "item/permissions/requestApproval": "Разрешить доступ на время этого запроса",
            "item/tool/requestUserInput": "Ответьте агенту",
        }
        if method not in titles:
            self._unsupported_request(message, "Unsupported Codex server request: " + self._safe(str(method)))
            return
        key = str(raw_id)
        is_questions = method == "item/tool/requestUserInput"
        if is_questions:
            for question in params["questions"]:
                if not all(isinstance(question[key], str) for key in ("id", "question")):
                    raise ValueError("invalid question")
        if method == "item/permissions/requestApproval" and not isinstance(params["permissions"], dict):
            raise ValueError("invalid permissions")
        request = {
            "id": key, "kind": "questions" if is_questions else "tool",
            "title": titles[method], "details": self._approval_details(method, params),
        }
        if is_questions:
            request["questions"] = copy.deepcopy(params["questions"])
        if params.get("networkApprovalContext"):
            request["title"] = "Разрешить доступ к сети"
        with self._state:
            self._pending[key] = {"raw_id": raw_id, "method": method, "params": params, "request": request}
        self._emit({"type": "permission", "request": copy.deepcopy(request)})

    def _unsupported_request(self, message: dict, reason: str, code: int = -32601) -> None:
        self._write({"id": message["id"], "error": {"code": code, "message": reason}})
        with self._state:
            self._turn_problem = reason
        self._emit({"type": "progress", "text": reason})

    def _approval_details(self, method: str, params: dict) -> str:
        parts = []
        for key in ("reason", "cwd", "command", "grantRoot"):
            if params.get(key):
                parts.append(f"{key}: {params[key]}")
        for key in ("networkApprovalContext", "additionalPermissions", "permissions"):
            if params.get(key):
                parts.append(f"{key}: {json.dumps(params[key], ensure_ascii=False)}")
        if method == "item/fileChange/requestApproval":
            with self._state:
                changes = (self._items.get(params.get("itemId")) or {}).get("changes")
            if changes:
                parts.append(json.dumps(changes, ensure_ascii=False))
        return self._safe("\n".join(parts))

    def _handle_notification(self, method: str, params: dict) -> None:
        if method == "serverRequest/resolved":
            key = str(params.get("requestId"))
            with self._state:
                removed = self._pending.pop(key, None)
            if removed:
                self._emit({"type": "permission_resolved", "request_id": key})
            return
        thread_id = params.get("threadId")
        if thread_id and self.session_id and thread_id != self.session_id:
            return
        if method == "turn/started":
            with self._state:
                self._turn_id = params["turn"]["id"]
                self._turn_requested = True
            return
        if method == "turn/completed":
            with self._state:
                turn = params["turn"]
                for item in turn.get("items", []):
                    if item.get("type") == "agentMessage":
                        self._messages[item["id"]] = item
                self._completed = turn
                self._turn_id = None
                self._turn_requested = False
                self._state.notify_all()
            return
        if method in {"item/started", "item/completed"}:
            item = params["item"]
            with self._state:
                self._items[item["id"]] = item
            if item.get("type") == "agentMessage":
                with self._state:
                    previous = self._messages.get(item["id"], {}).get("text", "")
                    self._messages[item["id"]] = item
                text = item.get("text", "")
                if text.startswith(previous) and len(text) > len(previous):
                    self._emit({"type": "text_delta", "text": text[len(previous):]})
            else:
                self._item_progress(item, method == "item/completed")
            return
        if method == "item/agentMessage/delta":
            delta = params.get("delta", "")
            with self._state:
                item = self._messages.setdefault(params["itemId"], {"text": "", "phase": None})
                item["text"] += delta
            self._emit({"type": "text_delta", "text": delta})
        elif method in {"item/commandExecution/outputDelta", "item/fileChange/outputDelta"}:
            self._emit({"type": "progress", "text": self._safe(params.get("delta", ""))})
        elif method == "item/mcpToolCall/progress":
            self._emit({"type": "progress", "text": self._safe(params.get("message", ""))})
        elif method == "turn/plan/updated":
            text = "\n".join(f"{step.get('status', '')}: {step.get('step', '')}" for step in params.get("plan", []))
            self._emit({"type": "progress", "text": text})
        elif method == "error":
            text = self._error_reason(params.get("error") or {}, "Codex error")
            if params.get("willRetry"):
                text += " (Codex will retry)"
            self._emit({"type": "progress", "text": text})
        elif method == "thread/status/changed":
            status = params.get("status") or {}
            if status.get("type") == "systemError":
                self._emit({"type": "progress", "text": "Codex reports a session error"})

    def _item_progress(self, item: dict, completed: bool) -> None:
        kind = item.get("type")
        if kind == "commandExecution":
            text = item.get("command", "")
        elif kind == "fileChange":
            text = ", ".join(change.get("path", "") for change in item.get("changes", []))
        elif kind in {"mcpToolCall", "dynamicToolCall"}:
            text = "/".join(str(item[key]) for key in ("server", "namespace", "tool") if item.get(key))
        elif kind == "webSearch":
            text = item.get("query", "")
        else:
            return
        status = item.get("status", "completed" if completed else "inProgress")
        self._emit({"type": "progress", "text": self._safe(f"{kind} ({status}): {text}")})

    def _answer_text(self) -> str:
        messages = list(self._messages.values())
        final = [item for item in messages if item.get("phase") == "final_answer"]
        selected = final or [item for item in messages if item.get("phase") != "commentary"] or messages
        return "\n\n".join(item.get("text", "") for item in selected if item.get("text"))

    def _clear_pending(self) -> None:
        with self._state:
            keys = list(self._pending)
            self._pending.clear()
        for key in keys:
            self._emit({"type": "permission_resolved", "request_id": key})

    def _fail(self, reason: str, category: str) -> None:
        with self._state:
            if self._failure is None:
                self._failure = CodexSessionError(self._safe(reason), category)
            self._state.notify_all()
        if not self._closed:
            self._emit({"type": "progress", "text": self._safe(reason)})

    def _result(self, ok: bool, text: str, reason: str, category: str | None) -> dict:
        return {"ok": ok, "text": text, "reason": self._safe(reason), "category": category,
                "pid": self.pid, "session_id": self.session_id, "still_running": self.busy}

    def _error_reason(self, error: dict, fallback: str) -> str:
        reason = str(error.get("message") or fallback)
        info = error.get("codexErrorInfo")
        if info:
            reason += " (" + (info if isinstance(info, str) else json.dumps(info)) + ")"
        if error.get("code") is not None:
            reason += f" [code {error['code']}]"
        return self._safe(reason)

    def _safe(self, text: str) -> str:
        """Redact credential-shaped diagnostics without exposing process env."""
        text = str(text)
        for key, value in self._env.items():
            if re.search(r"(?:TOKEN|SECRET|PASSWORD|API_KEY)", key, re.I) and isinstance(value, str) and len(value) >= 8:
                text = text.replace(value, "[redacted]")
        text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[redacted]", text)
        text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[redacted]", text)
        text = re.sub(r'''(?i)((?:access_token|refresh_token|api_key|password)["']?\s*[:=]\s*["']?)[^\s,"'&]+''', r"\1[redacted]", text)
        return re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[redacted]", text)

    def _emit(self, event: dict) -> None:
        try:
            self._on_event(event)
        except Exception:
            # A disconnected view must not terminate the provider process or
            # answer a permission request. Reconnection reads pending state.
            pass
