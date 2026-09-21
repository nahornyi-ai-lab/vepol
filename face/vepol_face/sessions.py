"""tmux session boundary. MVP-9.

Session names are validated against the canonical regex from
~/knowledge/concepts/full-interactive-agent-runtime.md. Prompt text NEVER
travels through argv or a shell string: it is written to a file, loaded into a
tmux buffer, and pasted.
"""
from __future__ import annotations

import pathlib
import re
import uuid
from dataclasses import dataclass

SESSION_RE = re.compile(r"^kb-[a-z0-9][a-z0-9_-]*-(claude|codex|agy)$")
RUNTIME_SUFFIX = ("claude", "codex", "agy")


class UnsafeSessionName(ValueError):
    """Raised for anything that is not a canonical session name."""


def validate_session_name(name: str) -> str:
    if not isinstance(name, str) or not SESSION_RE.match(name):
        raise UnsafeSessionName(
            f"refusing non-canonical tmux session name {name!r}; "
            f"expected {SESSION_RE.pattern}"
        )
    return name


def session_name(agent_slug: str, runtime: str) -> str:
    return validate_session_name(f"kb-{agent_slug}-{runtime}")


def attach_command(name: str) -> str:
    """Human-copyable attach command. Name is validated first."""
    return f"tmux attach -t {validate_session_name(name)}"


@dataclass
class SendPromptPlan:
    session: str
    prompt_file: pathlib.Path
    buffer_name: str
    commands: list[list[str]]


def build_send_prompt_plan(
    session: str, prompt: str, workdir: pathlib.Path
) -> SendPromptPlan:
    """File-backed paste. No shell, no interpolation, argv lists only."""
    session = validate_session_name(session)
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    buffer_name = f"vepolface-{uuid.uuid4().hex[:12]}"
    prompt_file = workdir / f"{buffer_name}.prompt"
    prompt_file.write_text(prompt)
    prompt_file.chmod(0o600)

    commands = [
        ["tmux", "load-buffer", "-b", buffer_name, str(prompt_file)],
        ["tmux", "paste-buffer", "-b", buffer_name, "-t", session, "-d"],
    ]
    return SendPromptPlan(session, prompt_file, buffer_name, commands)
