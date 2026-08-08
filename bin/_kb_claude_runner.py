#!/usr/bin/env python3
"""Durable, unbounded process runner used for Claude Code invocations.

The observer is intentionally disposable. A detached worker owns the child,
waits for natural exit, and publishes append-only streams plus terminal state.
No elapsed-time or stdout-silence path terminates the child.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import secrets
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator, Sequence
from typing import Any


TERMINAL = {
    "succeeded",
    "failed",
    "cancelled",
    "orphaned_unknown",
    "resolved_orphan",
}
ACTIVE = {"created", "starting", "running", "claim_degraded"}


@dataclasses.dataclass(frozen=True)
class RunResult:
    run_id: str
    returncode: int
    stdout: str
    stderr: str
    status: str
    state: dict[str, Any]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run_root() -> pathlib.Path:
    override = os.environ.get("KB_CLAUDE_RUN_ROOT")
    root = pathlib.Path(override).expanduser() if override else pathlib.Path.home() / "knowledge" / ".orchestrator" / "claude-runs"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def fsync_dir(path: pathlib.Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    fsync_dir(path.parent)


def load_json(path: pathlib.Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read durable state {path}: {exc}") from exc


@contextlib.contextmanager
def file_lock(path: pathlib.Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def run_dir(run_id: str) -> pathlib.Path:
    if not run_id.startswith("kbcr-") or "/" in run_id or ".." in run_id:
        raise ValueError(f"invalid run_id: {run_id!r}")
    return run_root() / run_id


def state_path(run_id: str) -> pathlib.Path:
    return run_dir(run_id) / "state.json"


def read_state(run_id: str) -> dict[str, Any]:
    value = load_json(state_path(run_id))
    if not isinstance(value, dict) or value.get("run_id") != run_id:
        raise RuntimeError(f"invalid state for {run_id}")
    return value


def mutate_state(run_id: str, mutator) -> dict[str, Any]:
    directory = run_dir(run_id)
    with file_lock(directory / "state.lock"):
        state = read_state(run_id)
        mutator(state)
        state["updated_at"] = utc_now()
        atomic_json(directory / "state.json", state)
        return state


def pid_start_identity(pid: int | None) -> str | None:
    if not pid or pid <= 0:
        return None
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and value else None


def pid_matches(pid: int | None, expected_start: str | None) -> bool:
    actual = pid_start_identity(pid)
    return bool(actual and expected_start and actual == expected_start)


def command_digest(command: Sequence[str]) -> str:
    encoded = json.dumps(list(command), ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _normalise_claim(claim: dict[str, Any] | None) -> dict[str, Any] | None:
    if claim is None:
        return None
    required = ("backlog_path", "plan_item_id", "claim_id", "actor")
    missing = [key for key in required if not str(claim.get(key) or "").strip()]
    if missing:
        raise ValueError(f"claim metadata missing: {', '.join(missing)}")
    backlog = pathlib.Path(str(claim["backlog_path"])).expanduser().resolve()
    if not backlog.is_file():
        raise ValueError(f"claim backlog is not a file: {backlog}")
    return {
        "backlog_path": str(backlog),
        "plan_item_id": str(claim["plan_item_id"]),
        "claim_id": str(claim["claim_id"]),
        "actor": str(claim["actor"]),
        "claim_expires_at": claim.get("claim_expires_at"),
        "state": "active",
        "renewal_failures": 0,
        "escalated": False,
        "rebind_audit": [],
    }


def _claim_identity(claim: dict[str, Any]) -> tuple[str, str]:
    return str(claim.get("backlog_path")), str(claim.get("plan_item_id"))


def _rebind_claim(run_id: str, claim: dict[str, Any]) -> None:
    """Move a live logical task run to a newly minted valid board claim."""

    def rebind(value: dict[str, Any]) -> None:
        current = value.get("claim")
        if not isinstance(current, dict):
            value["claim"] = claim
            return
        if _claim_identity(current) != _claim_identity(claim):
            raise RuntimeError("dedup collision has different board task identity")
        if current.get("claim_id") == claim.get("claim_id"):
            return
        audit = list(current.get("rebind_audit") or [])
        audit.append(
            {
                "rebound_at": utc_now(),
                "from_claim_id": current.get("claim_id"),
                "to_claim_id": claim.get("claim_id"),
                "actor": claim.get("actor"),
            }
        )
        replacement = dict(claim)
        replacement["rebind_audit"] = audit
        value["claim"] = replacement
        if value.get("status") == "claim_degraded":
            value["status"] = "running"

    mutate_state(run_id, rebind)


def _new_run_id() -> str:
    return "kbcr-" + uuid.uuid4().hex


def _index_path() -> pathlib.Path:
    return run_root() / "index.json"


def _load_index() -> dict[str, str]:
    value = load_json(_index_path(), {})
    return value if isinstance(value, dict) else {}


def _release_index(dedup_key: str | None, run_id: str) -> None:
    if not dedup_key:
        return
    root = run_root()
    with file_lock(root / "index.lock"):
        index = _load_index()
        if index.get(dedup_key) == run_id:
            index.pop(dedup_key, None)
            atomic_json(_index_path(), index)


def launch_run(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    managed: bool = False,
    dedup_key: str | None = None,
    output_mode: str = "text",
    kind: str = "claude",
    metadata: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    claim: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """Create a durable run or attach to its existing logical occurrence.

    Returns ``(run_id, created)``. Managed runs require an explicit key.
    Ad-hoc runs are unique unless the caller explicitly provides a key.
    """
    if not command:
        raise ValueError("command is required")
    if managed and not dedup_key:
        raise ValueError("--managed requires --dedup-key")
    if output_mode not in {"text", "json", "stream-json", "raw"}:
        raise ValueError(f"invalid output mode: {output_mode}")
    cwd_path = pathlib.Path(cwd or os.getcwd()).expanduser().resolve()
    if not cwd_path.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd_path}")
    command_list = [str(item) for item in command]
    claim_value = _normalise_claim(claim)
    if claim_value is not None:
        _claim_renewal_delay(claim_value)
    root = run_root()
    effective_key = dedup_key if dedup_key else f"adhoc:{uuid.uuid4().hex}"

    with file_lock(root / "index.lock"):
        index = _load_index()
        if dedup_key and (existing := index.get(effective_key)):
            try:
                state = read_state(existing)
            except (RuntimeError, ValueError):
                raise RuntimeError(
                    f"dedup reservation {effective_key!r} has unreadable run {existing}; "
                    "explicit operator resolution required"
                )
            if state.get("status") in ACTIVE:
                if claim_value is not None:
                    _rebind_claim(existing, claim_value)
                return existing, False
            if state.get("status") == "succeeded":
                return existing, False
            if state.get("status") == "orphaned_unknown":
                raise RuntimeError(
                    f"dedup reservation {effective_key!r} is orphaned in {existing}; "
                    "explicit --resolve is required"
                )
            index.pop(effective_key, None)

        run_id = _new_run_id()
        staging = root / f".new-{run_id}-{secrets.token_hex(4)}"
        staging.mkdir(mode=0o700)
        for name in ("stdout", "stderr", "metadata.log", "state.lock"):
            fd = os.open(staging / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        atomic_json(staging / "command.json", {"argv": command_list})
        token = secrets.token_hex(24)
        now = utc_now()
        state: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "kind": kind,
            "status": "created",
            "managed": managed,
            "dedup_key": effective_key,
            "owner_uid": os.getuid(),
            "cwd": str(cwd_path),
            "argv_digest": command_digest(command_list),
            "worker_token": token,
            "worker_pid": None,
            "worker_lstart": None,
            "child_pid": None,
            "child_lstart": None,
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "returncode": None,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
            "stdout_path": str(root / run_id / "stdout"),
            "stderr_path": str(root / run_id / "stderr"),
            "status_path": str(root / run_id / "state.json"),
            "output_mode": output_mode,
            "metadata": metadata or {},
            "claim": claim_value,
            "cancel_audit": [],
            "resolution_audit": [],
        }
        atomic_json(staging / "state.json", state)
        os.rename(staging, root / run_id)
        fsync_dir(root)
        if dedup_key:
            index[effective_key] = run_id
            atomic_json(_index_path(), index)

        worker_env = dict(env) if env is not None else os.environ.copy()
        worker_env["KB_CLAUDE_WORKER_TOKEN"] = token
        worker = subprocess.Popen(
            [sys.executable, str(pathlib.Path(__file__).resolve()), "_worker", run_id],
            cwd=str(cwd_path),
            env=worker_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    # The detached worker writes its own identity. If it cannot even start,
    # publish a typed failure rather than leaving an ambiguous created run.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        state = read_state(run_id)
        if state.get("worker_pid"):
            break
        if worker.poll() is not None:
            def failed(value: dict[str, Any]) -> None:
                value.update(
                    status="failed",
                    returncode=127,
                    completed_at=utc_now(),
                    launch_error=f"worker exited rc={worker.returncode} before identity publication",
                )

            mutate_state(run_id, failed)
            _release_index(dedup_key, run_id)
            break
        time.sleep(0.02)
    return run_id, True


def _validate_output(mode: str, stdout_path: pathlib.Path) -> str | None:
    if mode in {"raw", "text"}:
        if mode == "text" and not stdout_path.read_bytes().strip():
            return "empty text result"
        return None
    raw = stdout_path.read_text(encoding="utf-8", errors="strict")
    if mode == "json":
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            return f"invalid JSON result: {exc}"
        if not isinstance(value, (dict, list)):
            return "JSON result must be an object or array"
        return None
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return "empty stream-json result"
    try:
        events = [json.loads(line) for line in lines]
    except json.JSONDecodeError as exc:
        return f"invalid stream-json event: {exc}"
    if not any(
        isinstance(event, dict)
        and (
            event.get("type") == "result"
            or event.get("subtype") in {"success", "error"}
        )
        for event in events
    ):
        return "stream-json has no terminal result event"
    return None


def _claim_lease_seconds() -> int:
    # One source of truth: the board mutation layer owns lease duration.
    from _kb_board.mutation import LEASE_SECONDS

    return int(LEASE_SECONDS)


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _claim_renewal_delay(claim: dict[str, Any]) -> float:
    override = os.environ.get("KB_CLAUDE_CLAIM_PING_SEC")
    if override is not None:
        try:
            value = float(override)
        except ValueError as exc:
            raise ValueError("KB_CLAUDE_CLAIM_PING_SEC must be positive") from exc
        if value <= 0:
            raise ValueError("KB_CLAUDE_CLAIM_PING_SEC must be positive")
        return value
    expires = _parse_timestamp(claim.get("claim_expires_at"))
    remaining = (
        (expires - dt.datetime.now(dt.timezone.utc)).total_seconds()
        if expires is not None
        else float(_claim_lease_seconds())
    )
    return max(1.0, min(300.0, remaining / 3.0))


def _append_claim_escalation(claim: dict[str, Any], run_id: str, error: str) -> None:
    backlog = pathlib.Path(str(claim["backlog_path"]))
    path = backlog.with_name("escalations.md")
    entry = (
        f"\n## [{dt.date.today().isoformat()}] claude-claim-renewal | {run_id}\n"
        f"- plan_item_id: `{claim['plan_item_id']}`\n"
        f"- claim_id: `{claim['claim_id']}`\n"
        f"- error: {error[:500]}\n"
        "- effect: Claude remains alive; durable dedup reservation blocks duplicate execution.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(path.suffix + ".lock")):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(entry)
            fh.flush()
            os.fsync(fh.fileno())


def _renew_claim(run_id: str) -> bool:
    state = read_state(run_id)
    claim = state.get("claim")
    if not isinstance(claim, dict):
        return True
    error: str | None = None
    try:
        from _kb_board.mutation import mutate_file

        mutate_file(
            path=pathlib.Path(str(claim["backlog_path"])),
            op="heartbeat",
            plan_item_id=str(claim["plan_item_id"]),
            actor=str(claim["actor"]),
            claim_id=str(claim["claim_id"]),
        )
    except Exception as exc:  # noqa: BLE001 - typed durable degradation below
        error = f"{type(exc).__name__}: {exc}"

    if error is None:
        expires = (
            dt.datetime.now(dt.timezone.utc)
            + dt.timedelta(seconds=_claim_lease_seconds())
        ).isoformat(timespec="seconds")

        def renewed(value: dict[str, Any]) -> None:
            current = value.get("claim")
            if not isinstance(current, dict):
                return
            # A concurrent attach may have rebound to a new claim while the old
            # heartbeat was in flight. Never overwrite the replacement.
            if current.get("claim_id") != claim.get("claim_id"):
                return
            current.update(
                state="active",
                claim_expires_at=expires,
                last_renewed_at=utc_now(),
                last_error=None,
            )
            if value.get("status") == "claim_degraded":
                value["status"] = "running"

        mutate_state(run_id, renewed)
        return True

    escalate = not bool(claim.get("escalated"))

    def degraded(value: dict[str, Any]) -> None:
        current = value.get("claim")
        if not isinstance(current, dict):
            return
        if current.get("claim_id") != claim.get("claim_id"):
            return
        current["state"] = "degraded"
        current["renewal_failures"] = int(current.get("renewal_failures") or 0) + 1
        current["last_error"] = error
        current["last_failure_at"] = utc_now()
        if escalate:
            current["escalated"] = True
        if value.get("status") not in TERMINAL:
            value["status"] = "claim_degraded"

    mutate_state(run_id, degraded)
    if escalate:
        try:
            _append_claim_escalation(claim, run_id, error)
        except OSError as exc:
            with open(run_dir(run_id) / "metadata.log", "a", encoding="utf-8") as fh:
                fh.write(f"{utc_now()} claim escalation write failed: {exc}\n")
    return False


def _publish_followup_outbox(run_id: str, state: dict[str, Any]) -> None:
    metadata = state.get("metadata")
    followup = metadata.get("followup") if isinstance(metadata, dict) else None
    if not isinstance(followup, dict):
        return
    required = ("hub", "producer_process_id", "target_process_id", "occurrence_date")
    missing = [key for key in required if not str(followup.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"follow-up metadata missing: {', '.join(missing)}")
    hub = pathlib.Path(str(followup["hub"])).expanduser().resolve()
    root = hub / ".orchestrator" / "process-outbox"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    target = str(followup["target_process_id"])
    identity = f"{run_id}:{target}"
    outbox_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    path = root / f"{outbox_id}.json"
    value = {
        "schema": "process-followup/v1",
        "outbox_id": outbox_id,
        "producer_run_id": run_id,
        "producer_process_id": str(followup["producer_process_id"]),
        "target_process_id": target,
        "occurrence_date": str(followup["occurrence_date"]),
        "occurrence_slot": str(followup.get("occurrence_slot") or "default"),
        "status": "open",
        "catchup_run_id": None,
        "attempts": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    with file_lock(root / "outbox.lock"):
        existing = load_json(path)
        if existing is not None:
            if not isinstance(existing, dict) or (
                existing.get("producer_run_id"),
                existing.get("target_process_id"),
            ) != (run_id, target):
                raise RuntimeError(f"follow-up outbox identity collision: {path}")
            return
        atomic_json(path, value)


def worker_main(run_id: str) -> int:
    directory = run_dir(run_id)
    state = read_state(run_id)
    token = os.environ.get("KB_CLAUDE_WORKER_TOKEN")
    if not token or token != state.get("worker_token"):
        return 126
    command_doc = load_json(directory / "command.json")
    command = command_doc.get("argv") if isinstance(command_doc, dict) else None
    if not isinstance(command, list) or not command:
        return 126
    worker_pid = os.getpid()

    def publish_worker(value: dict[str, Any]) -> None:
        value.update(
            status="starting",
            worker_pid=worker_pid,
            worker_lstart=pid_start_identity(worker_pid),
            worker_pgid=os.getpgrp(),
        )

    mutate_state(run_id, publish_worker)
    stdout_path = directory / "stdout"
    stderr_path = directory / "stderr"
    try:
        with open(stdout_path, "ab", buffering=0) as stdout_fh, open(
            stderr_path, "ab", buffering=0
        ) as stderr_fh:
            child = subprocess.Popen(
                command,
                cwd=state["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=stdout_fh,
                stderr=stderr_fh,
                close_fds=True,
            )

            def publish_child(value: dict[str, Any]) -> None:
                value.update(
                    status="running",
                    child_pid=child.pid,
                    child_lstart=pid_start_identity(child.pid),
                    child_pgid=os.getpgrp(),
                )

            mutate_state(run_id, publish_child)
            claim = state.get("claim")
            observed_claim_id = (
                str(claim.get("claim_id")) if isinstance(claim, dict) else None
            )
            next_claim_renewal = (
                time.monotonic() + _claim_renewal_delay(claim)
                if isinstance(claim, dict)
                else None
            )
            next_claim_refresh = time.monotonic() + 1.0
            while True:
                polled = child.poll()
                if polled is not None:
                    returncode = polled
                    break
                now_mono = time.monotonic()
                if next_claim_refresh is not None and now_mono >= next_claim_refresh:
                    live_claim = read_state(run_id).get("claim")
                    live_claim_id = (
                        str(live_claim.get("claim_id"))
                        if isinstance(live_claim, dict)
                        else None
                    )
                    if live_claim_id != observed_claim_id:
                        observed_claim_id = live_claim_id
                        next_claim_renewal = now_mono if live_claim_id else None
                    next_claim_refresh = now_mono + 1.0
                if next_claim_renewal is not None and now_mono >= next_claim_renewal:
                    _renew_claim(run_id)
                    refreshed = read_state(run_id).get("claim")
                    if isinstance(refreshed, dict):
                        next_claim_renewal = now_mono + _claim_renewal_delay(refreshed)
                    else:
                        next_claim_renewal = None
                time.sleep(0.1)
    except OSError as exc:
        with open(stderr_path, "ab", buffering=0) as stderr_fh:
            stderr_fh.write(f"launch failed: {exc}\n".encode())
        returncode = 127

    stdout_bytes = stdout_path.stat().st_size
    stderr_bytes = stderr_path.stat().st_size
    output_error = None
    if returncode == 0:
        try:
            output_error = _validate_output(str(state.get("output_mode", "text")), stdout_path)
        except (OSError, UnicodeError) as exc:
            output_error = f"cannot validate output: {exc}"
    final_rc = returncode if returncode != 0 or not output_error else 65
    if final_rc == 0:
        try:
            _publish_followup_outbox(run_id, read_state(run_id))
        except Exception as exc:  # noqa: BLE001 - wrapper success is not acknowledged
            output_error = f"follow-up outbox publish failed: {type(exc).__name__}: {exc}"
            final_rc = 74

    def publish_terminal(value: dict[str, Any]) -> None:
        # An explicit cancel owns its typed terminal result.
        if value.get("status") == "cancelled":
            value.update(
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                completed_at=value.get("completed_at") or utc_now(),
            )
            return
        value.update(
            status="succeeded" if final_rc == 0 else "failed",
            returncode=final_rc,
            child_returncode=returncode,
            output_error=output_error,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            completed_at=utc_now(),
        )

    terminal = mutate_state(run_id, publish_terminal)
    if terminal.get("status") != "succeeded":
        _release_index(
            terminal.get("dedup_key") if terminal.get("managed") else None,
            run_id,
        )
    return 0


def parse_ping_interval() -> float:
    raw = os.environ.get("KB_CLAUDE_PING_SEC")
    if raw is None:
        return 60.0
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("KB_CLAUDE_PING_SEC must be a positive number") from exc
    if value <= 0:
        raise ValueError("KB_CLAUDE_PING_SEC must be a positive number")
    return value


def _read_from(path: pathlib.Path, offset: int) -> tuple[bytes, int]:
    size = path.stat().st_size
    if offset < 0 or offset > size:
        raise ValueError(f"offset {offset} outside stream length {size} for {path.name}")
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    return data, offset + len(data)


def wait_result(
    run_id: str,
    *,
    stdout_offset: int = 0,
    stderr_offset: int = 0,
    emit: bool = False,
    heartbeat: bool = False,
) -> RunResult:
    directory = run_dir(run_id)
    ping = parse_ping_interval()
    fixed_ping = os.environ.get("KB_CLAUDE_PING_SEC") is not None
    observed_since = time.monotonic()
    next_ping = time.monotonic() + ping
    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []
    while True:
        state = read_state(run_id)
        out, stdout_offset = _read_from(directory / "stdout", stdout_offset)
        err, stderr_offset = _read_from(directory / "stderr", stderr_offset)
        if out:
            stdout_parts.append(out)
            if emit:
                sys.stdout.buffer.write(out)
                sys.stdout.buffer.flush()
        if err:
            stderr_parts.append(err)
            if emit:
                sys.stderr.buffer.write(err)
                sys.stderr.buffer.flush()
        status = str(state.get("status"))
        if status in TERMINAL:
            # Re-read once after observing terminal publication so bytes
            # appended immediately before the state rename cannot be missed.
            out, stdout_offset = _read_from(directory / "stdout", stdout_offset)
            err, stderr_offset = _read_from(directory / "stderr", stderr_offset)
            stdout_parts.append(out)
            stderr_parts.append(err)
            if emit and out:
                sys.stdout.buffer.write(out)
                sys.stdout.buffer.flush()
            if emit and err:
                sys.stderr.buffer.write(err)
                sys.stderr.buffer.flush()
            rc = state.get("returncode")
            return RunResult(
                run_id=run_id,
                returncode=int(rc if rc is not None else 1),
                stdout=b"".join(stdout_parts).decode("utf-8", errors="replace"),
                stderr=b"".join(stderr_parts).decode("utf-8", errors="replace"),
                status=status,
                state=state,
            )

        worker_pid = state.get("worker_pid")
        worker_start = state.get("worker_lstart")
        if worker_pid and worker_start and not pid_matches(int(worker_pid), str(worker_start)):
            def orphan(value: dict[str, Any]) -> None:
                if value.get("status") not in TERMINAL:
                    value.update(
                        status="orphaned_unknown",
                        returncode=70,
                        completed_at=utc_now(),
                        orphan_reason="worker identity disappeared before terminal publication",
                    )

            mutate_state(run_id, orphan)
            continue

        now = time.monotonic()
        if heartbeat and now >= next_ping:
            message = (
                f"[kb-claude-run] alive run_id={run_id} status={status} "
                f"stdout_offset={stdout_offset} stderr_offset={stderr_offset}\n"
            )
            sys.stderr.write(message)
            sys.stderr.flush()
            with open(directory / "metadata.log", "a", encoding="utf-8") as fh:
                fh.write(f"{utc_now()} {message}")
            interval = ping if fixed_ping or now - observed_since < 600 else 300.0
            next_ping = now + interval
        time.sleep(min(0.1, ping / 2))


def run_command(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    managed: bool = False,
    dedup_key: str | None = None,
    output_mode: str = "text",
    kind: str = "claude",
    metadata: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    claim: dict[str, Any] | None = None,
) -> RunResult:
    run_id, _ = launch_run(
        command,
        cwd=cwd,
        managed=managed,
        dedup_key=dedup_key,
        output_mode=output_mode,
        kind=kind,
        metadata=metadata,
        env=env,
        claim=claim,
    )
    return wait_result(run_id)


def run_claude(
    prompt: str,
    *,
    cwd: str | os.PathLike[str] | None = None,
    model: str | None = None,
    add_dirs: Sequence[str] = (),
    extra_args: Sequence[str] = (),
    managed: bool = False,
    dedup_key: str | None = None,
    output_mode: str = "text",
    metadata: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    claim: dict[str, Any] | None = None,
) -> RunResult:
    binary = os.environ.get("KB_CLAUDE_BIN", "claude")
    command = [binary, "-p", prompt]
    if model:
        command.extend(["--model", model])
    for path in add_dirs:
        command.extend(["--add-dir", str(path)])
    command.extend(extra_args)
    return run_command(
        command,
        cwd=cwd,
        managed=managed,
        dedup_key=dedup_key,
        output_mode=output_mode,
        kind="claude",
        metadata=metadata,
        env=env,
        claim=claim,
    )


def cancel_run(run_id: str, reason: str) -> int:
    if not reason.strip():
        raise ValueError("--reason is required")
    state = read_state(run_id)
    if int(state.get("owner_uid", -1)) != os.getuid():
        raise PermissionError("run owner uid does not match caller")
    if state.get("status") in TERMINAL:
        return int(state.get("returncode") or 0)
    worker_pid = int(state.get("worker_pid") or 0)
    worker_start = state.get("worker_lstart")
    if not pid_matches(worker_pid, worker_start):
        raise RuntimeError("worker identity mismatch; use explicit --resolve")

    requested_at = utc_now()

    def requested(value: dict[str, Any]) -> None:
        value.setdefault("cancel_audit", []).append(
            {
                "requested_at": requested_at,
                "requested_by_uid": os.getuid(),
                "reason": reason,
                "signal": "TERM",
            }
        )

    mutate_state(run_id, requested)
    pgid = int(state.get("worker_pgid") or worker_pid)
    os.killpg(pgid, signal.SIGTERM)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and pid_matches(worker_pid, worker_start):
        time.sleep(0.1)
    escalated = False
    if pid_matches(worker_pid, worker_start):
        os.killpg(pgid, signal.SIGKILL)
        escalated = True

    def cancelled(value: dict[str, Any]) -> None:
        if value.get("status") not in {"succeeded", "failed"}:
            value.update(status="cancelled", returncode=130, completed_at=utc_now())
            value.setdefault("cancel_audit", []).append(
                {"completed_at": utc_now(), "kill_escalated": escalated}
            )

    final = mutate_state(run_id, cancelled)
    _release_index(final.get("dedup_key") if final.get("managed") else None, run_id)
    return int(final.get("returncode") or 130)


def resolve_run(run_id: str, reason: str) -> int:
    if not reason.strip():
        raise ValueError("--reason is required")
    state = read_state(run_id)
    if int(state.get("owner_uid", -1)) != os.getuid():
        raise PermissionError("run owner uid does not match caller")
    if state.get("status") != "orphaned_unknown":
        raise RuntimeError("--resolve is only valid for orphaned_unknown runs")
    child_pid = int(state.get("child_pid") or 0)
    child_start = state.get("child_lstart")
    signal_audit = "skipped_not_running"
    if pid_matches(child_pid, child_start):
        pgid = int(state.get("child_pgid") or child_pid)
        os.killpg(pgid, signal.SIGTERM)
        signal_audit = "term_sent"
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and pid_matches(child_pid, child_start):
            time.sleep(0.1)
        if pid_matches(child_pid, child_start):
            os.killpg(pgid, signal.SIGKILL)
            signal_audit = "kill_sent"
    elif child_pid:
        signal_audit = "signal_skipped_identity_mismatch"

    def resolved(value: dict[str, Any]) -> None:
        value.update(status="resolved_orphan", returncode=70, completed_at=utc_now())
        value.setdefault("resolution_audit", []).append(
            {
                "resolved_at": utc_now(),
                "resolved_by_uid": os.getuid(),
                "reason": reason,
                "signal": signal_audit,
            }
        )

    final = mutate_state(run_id, resolved)
    _release_index(final.get("dedup_key") if final.get("managed") else None, run_id)
    return 70


def list_running() -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for path in sorted(run_root().glob("kbcr-*/state.json")):
        try:
            state = load_json(path)
        except RuntimeError:
            continue
        if isinstance(state, dict) and state.get("status") in ACTIVE:
            values.append(state)
    return values


def _claim_still_open(state: dict[str, Any]) -> bool:
    claim = state.get("claim")
    if not isinstance(claim, dict):
        return False
    try:
        text = pathlib.Path(str(claim["backlog_path"])).read_text(encoding="utf-8")
    except OSError:
        return True
    return str(claim.get("claim_id") or "") in text


def cleanup_runs(days: int = 7) -> dict[str, int]:
    if days < 1:
        raise ValueError("--cleanup-days must be at least 1")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    cleaned = 0
    skipped = 0
    for path in sorted(run_root().glob("kbcr-*/state.json")):
        try:
            state = load_json(path)
        except RuntimeError:
            skipped += 1
            continue
        if not isinstance(state, dict):
            skipped += 1
            continue
        status = state.get("status")
        completed = _parse_timestamp(state.get("completed_at"))
        if (
            status not in {"succeeded", "failed", "cancelled", "resolved_orphan"}
            or completed is None
            or completed > cutoff
            or state.get("payload_cleaned_at")
            or _claim_still_open(state)
        ):
            skipped += 1
            continue
        run_id = str(state.get("run_id"))
        directory = run_dir(run_id)
        for name in ("stdout", "stderr"):
            with open(directory / name, "r+b") as fh:
                fh.truncate(0)
                fh.flush()
                os.fsync(fh.fileno())

        def cleaned_state(value: dict[str, Any]) -> None:
            value.update(
                stdout_bytes=0,
                stderr_bytes=0,
                payload_cleaned_at=utc_now(),
            )

        mutate_state(run_id, cleaned_state)
        cleaned += 1
    return {"cleaned": cleaned, "skipped": skipped}


def cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kb-claude-run",
        description=(
            "Run Claude (or a supplied command) under a detached durable worker. "
            "Duration and stdout silence never terminate the child."
        ),
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--attach", metavar="RUN_ID")
    actions.add_argument("--list-running", action="store_true")
    actions.add_argument("--cancel", metavar="RUN_ID")
    actions.add_argument("--resolve", metavar="RUN_ID")
    actions.add_argument("--cleanup", action="store_true")
    parser.add_argument("--reason")
    parser.add_argument("--cleanup-days", type=int, default=7)
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--managed", action="store_true")
    parser.add_argument("--dedup-key")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--output-mode", choices=["text", "json", "stream-json", "raw"], default="text")
    parser.add_argument("--kind", default="claude")
    parser.add_argument("--claim-backlog")
    parser.add_argument("--plan-item-id")
    parser.add_argument("--claim-id")
    parser.add_argument("--actor")
    parser.add_argument("--claim-expires-at")
    parser.add_argument("--stdout-offset", type=int, default=0)
    parser.add_argument("--stderr-offset", type=int, default=0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = cli_parser().parse_args(argv)
    try:
        parse_ping_interval()
        if args.list_running:
            print(json.dumps(list_running(), ensure_ascii=False, indent=2))
            return 0
        if args.cleanup:
            print(json.dumps(cleanup_runs(args.cleanup_days), sort_keys=True))
            return 0
        if args.cancel:
            return cancel_run(args.cancel, args.reason or "")
        if args.resolve:
            return resolve_run(args.resolve, args.reason or "")
        if args.attach:
            sys.stderr.write(f"[kb-claude-run] run_id={args.attach} attached=true\n")
            sys.stderr.flush()
            result = wait_result(
                args.attach,
                stdout_offset=args.stdout_offset,
                stderr_offset=args.stderr_offset,
                emit=True,
                heartbeat=True,
            )
            return result.returncode
        command = list(args.command)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise ValueError("command is required after --")
        claim_args = (
            args.claim_backlog,
            args.plan_item_id,
            args.claim_id,
            args.actor,
        )
        if any(claim_args) and not all(claim_args):
            raise ValueError(
                "claim renewal requires --claim-backlog, --plan-item-id, "
                "--claim-id, and --actor"
            )
        claim = (
            {
                "backlog_path": args.claim_backlog,
                "plan_item_id": args.plan_item_id,
                "claim_id": args.claim_id,
                "actor": args.actor,
                "claim_expires_at": args.claim_expires_at,
            }
            if all(claim_args)
            else None
        )
        run_id, created = launch_run(
            command,
            cwd=args.cwd,
            managed=args.managed,
            dedup_key=args.dedup_key,
            output_mode=args.output_mode,
            kind=args.kind,
            claim=claim,
        )
        sys.stderr.write(
            f"[kb-claude-run] run_id={run_id} created={str(created).lower()}\n"
        )
        sys.stderr.flush()
        if args.detach:
            return 0
        result = wait_result(run_id, emit=True, heartbeat=True)
        return result.returncode
    except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as exc:
        print(f"kb-claude-run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "_worker":
        raise SystemExit(worker_main(sys.argv[2]))
    raise SystemExit(main())
