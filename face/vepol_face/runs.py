"""Conversation + run persistence under ~/.vepol/face/.

MVP-6: a browser refresh, a reconnect, or a backend restart must be able to
reattach to an active run or show its final transcript. This store is a
discardable runtime cache — durable truth stays in KB files.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import threading
import uuid
from dataclasses import asdict, dataclass, field

DEFAULT_DIR = pathlib.Path(os.path.expanduser("~/.vepol/face"))
BOARD_STAGES = frozenset({"queued", "research", "working", "review", "completed"})


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class Message:
    role: str
    text: str
    at: str = field(default_factory=_now)
    meta: dict = field(default_factory=dict)


@dataclass
class Run:
    id: str
    status: str = "running"          # running | done | failed | degraded
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    reason: str = ""
    category: str | None = None
    evidence: dict = field(default_factory=dict)


@dataclass
class Conversation:
    id: str
    target: str
    runtime: str
    seq: int = 0
    created_at: str = field(default_factory=_now)
    title: str = ""
    messages: list[Message] = field(default_factory=list)
    runs: list[Run] = field(default_factory=list)
    board_stage: str = "queued"
    board_updated_at: str | None = None
    transport: str = "oneshot"
    provider_session_id: str | None = None
    transport_note: str = ""


class RunStore:
    def __init__(self, root: pathlib.Path | None = None) -> None:
        self.root = pathlib.Path(root or DEFAULT_DIR)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- paths
    def _path(self, conv_id: str) -> pathlib.Path:
        safe = "".join(c for c in conv_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("bad conversation id")
        return self.root / f"conv-{safe}.json"

    def _next_seq(self) -> int:
        counter = self.root / "seq"
        with self._lock:
            try:
                current = int(counter.read_text().strip())
            except (OSError, ValueError):
                current = 0
            current += 1
            counter.write_text(str(current))
            return current

    # -------------------------------------------------------------- write
    def create_conversation(self, target: str, runtime: str, title: str = "", transport: str = "oneshot") -> Conversation:
        conv = Conversation(
            id=uuid.uuid4().hex[:12], target=target, runtime=runtime,
            seq=self._next_seq(), title=title, transport=transport,
        )
        self._save(conv)
        return conv

    def append_message(self, conv_id: str, role: str, text: str, meta: dict | None = None) -> Message:
        with self._lock:
            conv = self.get_conversation(conv_id)
            if conv is None:
                raise KeyError(conv_id)
            msg = Message(role=role, text=text, meta=meta or {})
            conv.messages.append(msg)
            if not conv.title and role == "user":
                conv.title = text.strip().splitlines()[0][:60] if text.strip() else ""
            self._save(conv)
            return msg

    def start_run(self, conv_id: str, run_id: str | None = None) -> Run:
        with self._lock:
            conv = self.get_conversation(conv_id)
            if conv is None:
                raise KeyError(conv_id)
            run = Run(id=run_id or uuid.uuid4().hex[:12])
            conv.runs.append(run)
            self._save(conv)
            return run

    def set_title(self, conv_id: str, title: str) -> Conversation:
        with self._lock:
            conv = self.get_conversation(conv_id)
            if conv is None:
                raise KeyError(conv_id)
            conv.title = title
            self._save(conv)
            return conv

    def update_board_stage(self, conv_id: str, stage: str) -> Conversation:
        """Move a conversation without changing its transcript or runtime state."""
        if not isinstance(stage, str) or stage not in BOARD_STAGES:
            raise ValueError("invalid board stage")
        with self._lock:
            conv = self.get_conversation(conv_id)
            if conv is None:
                raise KeyError(conv_id)
            conv.board_stage = stage
            conv.board_updated_at = _now()
            self._save(conv)
            return conv

    def finish_run(
        self, conv_id: str, run_id: str, status: str, text: str = "",
        reason: str = "", category: str | None = None, evidence: dict | None = None,
    ) -> Run:
        with self._lock:
            conv = self.get_conversation(conv_id)
            if conv is None:
                raise KeyError(conv_id)
            for run in conv.runs:
                if run.id == run_id:
                    run.status = status
                    run.finished_at = _now()
                    run.reason = reason
                    run.category = category
                    run.evidence = evidence or {}
                    if text:
                        conv.messages.append(
                            Message(role="assistant", text=text,
                                    meta={"run_id": run_id, "status": status})
                        )
                    self._save(conv)
                    return run
            raise KeyError(run_id)

    def update_transport(self, conv_id: str, *, transport: str | None = None,
                         provider_session_id: str | None = None, note: str | None = None) -> Conversation:
        with self._lock:
            conv = self.get_conversation(conv_id)
            if conv is None:
                raise KeyError(conv_id)
            if transport is not None:
                conv.transport = transport
            if provider_session_id is not None:
                conv.provider_session_id = provider_session_id
            if note is not None:
                conv.transport_note = note
            self._save(conv)
            return conv

    def _save(self, conv: Conversation) -> None:
        path = self._path(conv.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(conv), indent=2, ensure_ascii=False))
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass

    # --------------------------------------------------------------- read
    def get_conversation(self, conv_id: str) -> Conversation | None:
        try:
            blob = json.loads(self._path(conv_id).read_text())
        except (OSError, ValueError):
            return None
        return Conversation(
            id=blob["id"], target=blob["target"], runtime=blob["runtime"],
            seq=blob.get("seq", 0), created_at=blob.get("created_at", ""),
            title=blob.get("title", ""),
            messages=[Message(**m) for m in blob.get("messages", [])],
            runs=[Run(**r) for r in blob.get("runs", [])],
            board_stage=blob.get("board_stage", "queued"),
            board_updated_at=blob.get("board_updated_at"),
            transport=blob.get("transport", "oneshot"),
            provider_session_id=blob.get("provider_session_id"),
            transport_note=blob.get("transport_note", ""),
        )

    def get_run(self, conv_id: str, run_id: str) -> Run | None:
        conv = self.get_conversation(conv_id)
        if conv is None:
            return None
        for run in conv.runs:
            if run.id == run_id:
                return run
        return None

    def reconcile_interrupted(self) -> list[str]:
        """Close out runs left `running` by a backend that died mid-flight.

        Without this, Ctrl-C during a long turn leaves the conversation
        permanently 409-locked: `api_send` refuses while any run is running, and
        nothing else would ever clear it. Returns the run ids it closed.
        """
        closed: list[str] = []
        with self._lock:
            for conv in self.list_conversations():
                dirty = False
                for run in conv.runs:
                    if run.status == "running":
                        run.status = "interrupted"
                        run.finished_at = _now()
                        run.reason = (
                            "the backend stopped while this run was in flight; "
                            "no answer was received"
                        )
                        closed.append(run.id)
                        dirty = True
                if dirty:
                    self._save(conv)
        return closed

    def list_conversations(self) -> list[Conversation]:
        out = []
        for path in self.root.glob("conv-*.json"):
            conv = self.get_conversation(path.stem.replace("conv-", "", 1))
            if conv is not None:
                out.append(conv)
        out.sort(key=lambda c: (c.seq, c.created_at), reverse=True)
        return out
