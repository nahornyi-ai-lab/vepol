"""Canonical tmux session transport with human-owned turn completion."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

from .sessions import attach_command, build_send_prompt_plan, session_name


class TerminalSession:
    def __init__(
        self, cwd: str, project: str, runtime: str,
        on_event: Callable[[dict], None], env: dict | None = None,
        session_id: str | None = None, prompt_dir: str | pathlib.Path | None = None,
    ) -> None:
        self.cwd = cwd
        self.runtime = runtime
        self.name = session_name(project, runtime)
        self.command = attach_command(self.name)
        self.session_id = session_id
        self._on_event = on_event
        self._env = dict(os.environ if env is None else env)
        self._prompt_dir = pathlib.Path(prompt_dir) if prompt_dir is not None else None
        self._pid: int | None = None
        self._lock = threading.Lock()
        self._connected = False
        self._ready = False
        self._tmux = self._binary("tmux")

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def pending(self) -> list[dict]:
        return []

    @property
    def ready(self) -> bool:
        return self._ready

    def confirm_ready(self) -> None:
        """The owner confirms startup/login/trust is complete in the terminal."""
        with self._lock:
            if not self._connected:
                raise RuntimeError("Open the terminal before confirming readiness")
            self._run(["has-session", "-t", self.name])
            self._ready = True
        self._on_event({"type": "progress", "text": "Terminal input readiness confirmed by the owner"})

    def _binary(self, runtime: str) -> str:
        candidates = {
            "tmux": ["/opt/homebrew/bin/tmux"],
            "claude": ["/opt/homebrew/bin/claude", str(pathlib.Path.home() / ".local/bin/claude")],
            "codex": [str(pathlib.Path.home() / ".local/bin/codex"), "/Applications/Codex.app/Contents/Resources/codex"],
            "agy": [str(pathlib.Path.home() / ".local/bin/agy"), "/opt/homebrew/bin/agy"],
        }.get(runtime, [])
        for candidate in candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        found = shutil.which(runtime, path=self._env.get("PATH", ""))
        if found:
            return os.path.abspath(found)
        raise FileNotFoundError(f"{runtime} executable is unavailable")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._tmux, *args], env=self._env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=check,
        )

    def _runtime_command(self) -> list[str]:
        # Existing tmux servers retain their own environment. Give this pane a
        # deliberate nonsecret environment instead of inheriting nested-agent
        # markers or putting API credentials into tmux/agent argv.
        safe_env = {
            "HOME": self._env.get("HOME", str(pathlib.Path.home())),
            "PATH": self._env.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
            "TERM": "xterm-256color",
        }
        for key in ("USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR"):
            if self._env.get(key):
                safe_env[key] = self._env[key]
        argv = ["/usr/bin/env", "-i", *[f"{key}={value}" for key, value in safe_env.items()]]
        argv.append(self._binary(self.runtime))
        if self.runtime == "codex":
            # User config may default to bypass mode. Keep this invocation in
            # a workspace sandbox with the CLI's normal human approval path.
            argv += ["--sandbox", "workspace-write", "--ask-for-approval", "on-request"]
        if self.session_id:
            if self.runtime == "claude":
                argv += ["--resume", self.session_id, "--permission-mode", "manual"]
            elif self.runtime == "codex":
                argv += ["resume", self.session_id]
            else:
                raise ValueError("This terminal runtime has no verified session resume command")
        elif self.runtime == "claude":
            argv += ["--permission-mode", "manual"]
        elif self.runtime == "agy":
            argv += ["--add-dir", self.cwd]
        return argv

    def _connect(self) -> None:
        if self._connected:
            return
        exists = self._run(["has-session", "-t", self.name], check=False).returncode == 0
        if exists and self.session_id:
            raise RuntimeError(
                "The canonical terminal already exists; its provider identity cannot be replaced"
            )
        if not exists:
            self._run([
                "new-session", "-d", "-s", self.name, "-c", self.cwd,
                "-x", "160", "-y", "48", *self._runtime_command(),
            ])
        pid = self._run(["display-message", "-p", "-t", self.name, "#{pane_pid}"]).stdout.strip()
        self._pid = int(pid)
        self._connected = True
        self._on_event({
            "type": "progress", "text": f"Terminal connected. {self.command}",
        })

    def execute(self, prompt: str) -> dict:
        with self._lock:
            try:
                self._connect()
                if not self._ready:
                    reason = (
                        "Terminal opened; the prompt has not been sent. "
                        f"Open {self.command}, finish startup/login/trust, "
                        "then confirm that the terminal is ready and retry."
                    )
                    self._on_event({"type": "progress", "text": reason})
                    return {
                        "ok": False, "submitted": False, "waiting_for_input": True,
                        "text": "", "reason": reason, "category": "terminal_not_ready",
                        "pid": self.pid, "session_id": self.session_id,
                        "name": self.name, "command": self.command,
                    }
                parent = str(self._prompt_dir) if self._prompt_dir is not None else None
                if self._prompt_dir is not None:
                    self._prompt_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                # The helper writes before chmod. A private temporary directory
                # protects the prompt throughout that existing helper's flow.
                with tempfile.TemporaryDirectory(prefix="vepol-terminal-", dir=parent) as directory:
                    plan = build_send_prompt_plan(self.name, prompt, pathlib.Path(directory))
                    for command in plan.commands:
                        args = command[1:]
                        if args[0] == "paste-buffer":
                            # Respect bracketed-paste mode when the CLI enables
                            # it, so embedded newlines remain one prompt.
                            args = [args[0], "-p", *args[1:]]
                        self._run(args)
                    self._run(["send-keys", "-t", self.name, "Enter"])
                return {
                    "ok": True, "submitted": True, "text": "",
                    "reason": "Prompt sent; completion is confirmed by the owner",
                    "category": "submitted", "pid": self.pid,
                    "session_id": self.session_id, "name": self.name, "command": self.command,
                }
            except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
                reason = str(exc)
                if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                    reason = exc.stderr.strip()
                return {
                    "ok": False, "submitted": False, "text": "", "reason": reason,
                    "category": "terminal_error", "pid": self.pid,
                    "session_id": self.session_id, "name": self.name, "command": self.command,
                }

    def capture(self) -> str:
        """Rendered terminal output for display only; never a completion signal."""
        return self._run(["capture-pane", "-p", "-t", self.name, "-S", "-200"]).stdout

    def interrupt(self) -> None:
        """Only called after the owner explicitly asks to interrupt this pane."""
        self._run(["send-keys", "-t", self.name, "C-c"])

    def close(self) -> None:
        """Backend quit leaves the canonical, manually owned tmux session alive."""
        return None
