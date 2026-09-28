"""Canonical tmux session transport with human-owned turn completion."""
from __future__ import annotations

import os
import pathlib
import pwd
import shlex
import shutil
import subprocess
import tempfile
import termios
import threading
import time
from typing import Callable

from .sessions import attach_command, build_send_prompt_plan, session_name

TMUX_CANDIDATES = ("/opt/homebrew/bin/tmux", "/usr/local/bin/tmux")
# tmux's own wording when there is nothing to attach to. Anything else is "unknown".
_NOT_RUNNING_MARKERS = ("no server running", "can't find", "no such", "error connecting", "no sessions")
# Set on every session whose pane is a login shell with the agent typed into it; the value is the shell's
# command name. Sessions without it (created before the shell layout) run the agent as the pane process.
SHELL_MARKER = "@vepol-shell"


def foreground_group(pid: int) -> int | None:
    """The foreground process group of the terminal `pid` belongs to, from `ps`."""
    probe = subprocess.run(["/bin/ps", "-o", "tpgid=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
    out = probe.stdout.strip()
    return int(out) if probe.returncode == 0 and out.lstrip("-").isdigit() else None


def tmux_binary(env: dict | None = None) -> str:
    env = dict(os.environ if env is None else env)
    for candidate in TMUX_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("tmux", path=env.get("PATH", ""))
    if found:
        return os.path.abspath(found)
    raise FileNotFoundError("tmux executable is unavailable")


def liveness(name: str, env: dict | None = None) -> dict:
    """Agent state from process evidence only.

    No server, no session or a dead pane PID is `not_running`. A shell-layout pane
    is `shell` while the shell holds the terminal's foreground and `alive` (PID =
    the foreground group) while anything else does; a legacy pane is `alive` while
    its PID answers kill(0). Every other error is `unknown` with the reason. Screen
    output, silence and control-mode events are never consulted.
    """
    env = dict(os.environ if env is None else env)
    try:
        probe = subprocess.run(
            [tmux_binary(env), "display-message", "-p", "-t", name,
             "#{pane_pid}\t#{" + SHELL_MARKER + "}\t#{pane_current_command}"],
            env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"agent": "unknown", "pid": None, "reason": str(exc)}
    if probe.returncode != 0:
        err = probe.stderr.strip() or f"tmux exited {probe.returncode}"
        state = "not_running" if any(marker in err for marker in _NOT_RUNNING_MARKERS) else "unknown"
        return {"agent": state, "pid": None, "reason": err}
    if not probe.stdout.strip():
        # tmux 3.7b exits 0 with empty output for a missing session while the server is up.
        try:
            has = subprocess.run(
                [tmux_binary(env), "has-session", "-t", name],
                env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"agent": "unknown", "pid": None, "reason": str(exc)}
        if has.returncode != 0:
            return {"agent": "not_running", "pid": None, "reason": has.stderr.strip() or "no such session"}
    fields = probe.stdout.strip("\n").split("\t")
    try:
        pid = int(fields[0])
    except (IndexError, ValueError):
        return {"agent": "unknown", "pid": None, "reason": f"unexpected tmux output {probe.stdout.strip()!r}"}
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {"agent": "not_running", "pid": pid, "reason": "process exited"}
    except PermissionError:
        pass  # exists, owned by someone else: still alive
    except OSError as exc:
        return {"agent": "unknown", "pid": pid, "reason": str(exc)}
    shell, current = (fields + ["", "", ""])[1:3]
    if not shell:
        return {"agent": "alive", "pid": pid, "reason": ""}
    try:
        group = foreground_group(pid)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"agent": "unknown", "pid": None, "reason": str(exc)}
    if group is None or group <= 0:
        return {"agent": "unknown", "pid": None, "reason": "no foreground process group"}
    if group != pid:
        return {"agent": "alive", "pid": group, "reason": ""}
    # The pane process holds the terminal: the shell at its prompt, unless it exec'd another program.
    return {"agent": "shell", "pid": None, "reason": ""} if current == shell else {"agent": "alive", "pid": pid, "reason": ""}


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
        self._ready_pid: int | None = None  # the foreground process the owner confirmed
        self._tmux = self._binary("tmux")

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def pending(self) -> list[dict]:
        return []

    @property
    def ready(self) -> bool:
        # A new agent (or any program typed in the shell) needs its own confirmation.
        return self._ready and liveness(self.name, self._env)["pid"] == self._ready_pid

    def confirm_ready(self) -> None:
        """The owner confirms startup/login/trust is complete in the terminal."""
        with self._lock:
            if not self._connected:
                raise RuntimeError("Open the terminal before confirming readiness")
            self._run(["has-session", "-t", self.name])
            self._ready, self._ready_pid = True, liveness(self.name, self._env)["pid"]
        self._on_event({"type": "progress", "text": "Terminal input readiness confirmed by the owner"})

    def start(self) -> dict:
        """Open the terminal if needed and type the agent's command into its shell.

        Only the owner's click calls this. A running program is never typed into.
        """
        with self._lock:
            agent = self._agent_argv()  # a missing CLI fails here, before any terminal opens
            created = self._connect(create=True)
            # Invisible keeper: no status bar, wheel scrolls history, Ctrl-B reaches the agent.
            for option, value in (("status", "off"), ("mouse", "on"), ("prefix", "None")):
                self._run(["set-option", "-t", self.name, option, value])
            # A new shell may still be running its startup files (and their programs): wait for its prompt first.
            if created or liveness(self.name, self._env)["agent"] == "shell":
                self._wait_for_shell_input()
            if liveness(self.name, self._env)["agent"] == "shell":
                self._type_agent_command(agent)
        return liveness(self.name, self._env)

    def _wait_for_shell_input(self) -> None:
        # Until the shell's line editor has the terminal, so the command is not echoed twice.
        deadline = time.monotonic() + 5
        while True:
            ready = self._shell_takes_input()
            if ready is None:
                raise RuntimeError("The terminal closed while starting")
            if ready or time.monotonic() > deadline:
                return  # after 5 s the caller types anyway if the shell holds the terminal
            time.sleep(0.05)

    def _type_agent_command(self, agent: list[str]) -> None:
        # Clear whatever the owner left on the command line, then type the agent.
        self._run(["send-keys", "-t", self.name, "C-e", "C-u"])
        self._run(["send-keys", "-t", self.name, "-l", shlex.join(agent)])
        self._run(["send-keys", "-t", self.name, "Enter"])
        # Return once the agent holds the terminal, so the caller reports it running.
        deadline = time.monotonic() + 3
        while liveness(self.name, self._env)["agent"] == "shell" and time.monotonic() < deadline:
            time.sleep(0.05)

    def _shell_takes_input(self) -> bool | None:
        """True when the shell holds the foreground with its line editor on (tty not canonical); None if gone."""
        probe = self._run(["display-message", "-p", "-t", self.name, "#{pane_pid} #{pane_tty}"], check=False)
        fields = probe.stdout.split()
        if probe.returncode != 0 or len(fields) != 2:
            return None
        pid, tty = int(fields[0]), fields[1]
        try:
            fd = os.open(tty, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError:
            return None
        try:
            canonical = bool(termios.tcgetattr(fd)[3] & termios.ICANON)
        finally:
            os.close(fd)
        return not canonical and foreground_group(pid) == pid

    def liveness(self) -> dict:
        return liveness(self.name, self._env)

    def _binary(self, runtime: str) -> str:
        if runtime == "tmux":
            return tmux_binary(self._env)
        candidates = {
            # Native install first: `claude update` updates it, a Homebrew/npm copy can lag behind.
            "claude": [str(pathlib.Path.home() / ".local/bin/claude"), "/opt/homebrew/bin/claude"],
            "codex": [str(pathlib.Path.home() / ".local/bin/codex"), "/Applications/Codex.app/Contents/Resources/codex"],
            "agy": [str(pathlib.Path.home() / ".local/bin/agy"), "/opt/homebrew/bin/agy"],
            # These open their own interactive TUI in the pane's folder with no extra arguments.
            "hermes": [str(pathlib.Path.home() / ".local/bin/hermes")],
            "opencode": [str(pathlib.Path.home() / ".opencode/bin/opencode")],
            "grok": [str(pathlib.Path.home() / ".grok/bin/grok")],
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

    def _shell_argv(self) -> list[str]:
        """The account's login shell, as a Terminal window opens it."""
        try:
            shell = pwd.getpwuid(os.getuid()).pw_shell
        except KeyError:
            shell = ""
        if not (shell and os.path.isfile(shell) and os.access(shell, os.X_OK)):
            shell = "/bin/zsh"
        return [shell, "-l"]

    def _pane_command(self) -> list[str]:
        # Existing tmux servers retain their own environment. Give this pane a
        # deliberate nonsecret environment instead of inheriting nested-agent
        # markers or putting API credentials into tmux/agent argv. The login
        # shell then reads the owner's own startup files, like any terminal.
        shell = self._shell_argv()
        safe_env = {
            "HOME": self._env.get("HOME", str(pathlib.Path.home())),
            "PATH": self._env.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
            "TERM": "xterm-256color",
        }
        for key in ("USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR", "KB_HUB"):
            if self._env.get(key):
                safe_env[key] = self._env[key]
        safe_env["SHELL"] = shell[0]
        return ["/usr/bin/env", "-i", *[f"{key}={value}" for key, value in safe_env.items()], *shell]

    def _agent_argv(self) -> list[str]:
        """The command typed into the pane's shell."""
        argv = [self._binary(self.runtime)]
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

    def _connect(self, create: bool = False) -> bool:
        """Attach to the canonical session; True when this call created it."""
        exists = self._run(["has-session", "-t", self.name], check=False).returncode == 0
        if self._connected:
            if exists:
                return False
            # The terminal closed and took its tmux session with it: forget the old pane.
            self._connected, self._ready, self._pid = False, False, None
        if exists and self.session_id:
            raise RuntimeError(
                "The canonical terminal already exists; its provider identity cannot be replaced"
            )
        created = not exists
        if not exists:
            if not create:
                # Only the owner's Start click creates a session; never an auto-restart.
                raise RuntimeError("The agent is not running. Click Start to open a new session.")
            self._run([
                "new-session", "-d", "-s", self.name, "-c", self.cwd,
                "-x", "160", "-y", "48", *self._pane_command(),
            ])
            self._run(["set-option", "-t", self.name, SHELL_MARKER, os.path.basename(self._shell_argv()[0])])
        pid = self._run(["display-message", "-p", "-t", self.name, "#{pane_pid}"]).stdout.strip()
        self._pid = int(pid)
        self._connected = True
        self._on_event({
            "type": "progress", "text": f"Terminal connected. {self.command}",
        })
        return created

    def execute(self, prompt: str) -> dict:
        with self._lock:
            try:
                self._connect()
                live = liveness(self.name, self._env)
                if live["agent"] == "shell":
                    # A prompt pasted into the shell would run as shell commands.
                    reason = "The agent is not running in this terminal. Press Start."
                    self._on_event({"type": "progress", "text": reason})
                    return {
                        "ok": False, "submitted": False, "text": "", "reason": reason,
                        "category": "terminal_not_running", "pid": self.pid, "session_id": self.session_id,
                        "name": self.name, "command": self.command,
                    }
                if not self._ready or live["pid"] != self._ready_pid:
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

    def interrupt(self) -> None:
        """Only called after the owner explicitly asks to interrupt this pane."""
        self._run(["send-keys", "-t", self.name, "C-c"])

    def close(self) -> None:
        """Backend quit leaves the canonical, manually owned tmux session alive."""
        return None
