#!/usr/bin/env python3
"""Crash-safe exact multipart planner for kb-brief.

This module is the only owner of UTF-8 hashing, UTF-16 accounting, slicing,
temporary part files, and delivery-sidecar state transitions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "brief-delivery/v1"
MAX_LIMIT = 3500
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
VALID_PART_STATES = {"pending", "sending", "sent", "failed", "ambiguous"}
VALID_TOP_STATES = {"pending", "sending", "failed", "ambiguous", "completed"}
TAIL_EXACT_RE = re.compile(r"^## (?:Retro|Reflection) \([^\n]*\)$")
TAIL_LOOKALIKE_RE = re.compile(r"^## (?:Retro|Reflection)(?:\s|:|$)")


class DeliveryError(RuntimeError):
    def __init__(self, message: str, *, code: int = 1, status: str = "error"):
        super().__init__(message)
        self.code = code
        self.status = status


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def validate_limit(raw: str | int) -> int:
    value = str(raw)
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("part limit must be a base-10 integer")
    parsed = int(value, 10)
    if not 1 <= parsed <= MAX_LIMIT:
        raise ValueError(f"part limit must be in 1..{MAX_LIMIT}")
    return parsed


def _largest_safe_index(text: str, start: int, limit: int) -> int:
    units = 0
    index = start
    while index < len(text):
        char_units = utf16_units(text[index])
        if units + char_units > limit:
            break
        units += char_units
        index += 1
    return index


def split_text(text: str, limit: int) -> list[str]:
    limit = validate_limit(limit)
    if not text:
        raise ValueError("brief body is empty")
    parts: list[str] = []
    start = 0
    while start < len(text):
        safe = _largest_safe_index(text, start, limit)
        if safe == len(text):
            parts.append(text[start:])
            break
        if safe == start:
            raise ValueError("one code point exceeds the transport limit")

        boundary: int | None = None
        window = text[start:safe]
        for delimiter in ("\n\n", "\n", " ", "\t"):
            found = window.rfind(delimiter)
            if found >= 0:
                candidate = start + found + len(delimiter)
                if candidate > start:
                    boundary = candidate
                    break
        if boundary is None:
            raise ValueError("a whitespace-free token exceeds the transport limit")
        part = text[start:boundary]
        if not part or utf16_units(part) > limit:
            raise ValueError("invalid split boundary")
        parts.append(part)
        start = boundary

    if "".join(parts) != text or any(utf16_units(part) > limit for part in parts):
        raise ValueError("multipart split is not exact")
    return parts


def _ensure_private_parent(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def atomic_json(path: Path | str, value: Any) -> None:
    path = Path(path)
    _ensure_private_parent(path.parent)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def atomic_private_text(path: Path | str, text: str) -> None:
    path = Path(path)
    _ensure_private_parent(path.parent)
    raw = text.encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _frontmatter_parts(path: Path) -> tuple[list[str], bytes, bytes]:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DeliveryError("day file is not valid UTF-8") from exc
    if not raw.startswith(b"---\n"):
        raise DeliveryError("day file has no YAML frontmatter")
    end = raw.find(b"\n---\n", 4)
    if end < 0:
        raise DeliveryError("day file has unterminated YAML frontmatter")
    fm_raw = raw[4:end]
    body_raw = raw[end + len(b"\n---\n") :]
    try:
        fm = fm_raw.decode("utf-8").split("\n") if fm_raw else []
    except UnicodeDecodeError as exc:
        raise DeliveryError("frontmatter is not valid UTF-8") from exc
    return fm, body_raw, raw


def _frontmatter_map(path: Path) -> dict[str, str]:
    fm, _, _ = _frontmatter_parts(path)
    result: dict[str, str] = {}
    for line in fm:
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def update_frontmatter(path: Path, values: dict[str, Any]) -> None:
    fm, body_raw, _ = _frontmatter_parts(path)
    for key, value in values.items():
        rendered = f"{key}: {value}"
        for idx, line in enumerate(fm):
            if line.startswith(f"{key}:"):
                fm[idx] = rendered
                break
        else:
            fm.append(rendered)
    raw = b"---\n" + "\n".join(fm).encode("utf-8") + b"\n---\n" + body_raw
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def extract_body(path: Path | str) -> str:
    path = Path(path)
    _, body_raw, _ = _frontmatter_parts(path)
    text = body_raw.decode("utf-8", errors="strict")
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        visible = line.rstrip("\r\n")
        if TAIL_EXACT_RE.fullmatch(visible):
            break
        if TAIL_LOOKALIKE_RE.match(visible):
            raise DeliveryError(f"malformed evening tail heading: {visible}")
        kept.append(line)
    body = "".join(kept).strip("\r\n")
    if not body:
        raise DeliveryError("day file body is empty")
    return body


def immutable_part_record(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": part["index"],
        "text_sha256": part["text_sha256"],
        "utf16_units": part["utf16_units"],
    }


def immutable_plan_fields(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": plan["schema"],
        "date": plan["date"],
        "language": plan["language"],
        "body_sha256": plan["body_sha256"],
        "body_utf16_units": plan["body_utf16_units"],
        "part_limit_utf16": plan["part_limit_utf16"],
        "parts": [immutable_part_record(part) for part in plan["parts"]],
    }


def plan_sha256(plan: dict[str, Any]) -> str:
    raw = json.dumps(
        immutable_plan_fields(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def make_plan(body: str, date: str, language: str, limit: int) -> dict[str, Any]:
    parts = split_text(body, limit)
    plan: dict[str, Any] = {
        "schema": SCHEMA,
        "date": date,
        "language": language,
        "body_sha256": sha256_bytes(body.encode("utf-8")),
        "body_utf16_units": utf16_units(body),
        "part_limit_utf16": limit,
        "parts": [
            {
                "index": index,
                "text_sha256": sha256_bytes(part.encode("utf-8")),
                "utf16_units": utf16_units(part),
                "status": "pending",
                "message_id": None,
            }
            for index, part in enumerate(parts, start=1)
        ],
        "status": "pending",
        "updated_at": now_iso(),
    }
    plan["plan_sha256"] = plan_sha256(plan)
    return plan


def _sidecar_permissions_safe(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def load_plan(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not _sidecar_permissions_safe(path):
        raise DeliveryError("delivery sidecar permissions are unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError("delivery sidecar is unreadable or invalid") from exc
    validate_plan_shape(value)
    return value


def validate_plan_shape(plan: Any) -> None:
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise DeliveryError("unsupported delivery sidecar schema")
    if plan.get("status") not in VALID_TOP_STATES:
        raise DeliveryError("invalid top-level delivery status")
    if not isinstance(plan.get("date"), str) or not isinstance(plan.get("language"), str):
        raise DeliveryError("invalid delivery identity")
    if not HASH_RE.fullmatch(str(plan.get("body_sha256", ""))):
        raise DeliveryError("invalid body hash")
    if not isinstance(plan.get("body_utf16_units"), int) or plan["body_utf16_units"] < 1:
        raise DeliveryError("invalid body length")
    try:
        validate_limit(plan.get("part_limit_utf16"))
    except ValueError as exc:
        raise DeliveryError("invalid part limit") from exc
    parts = plan.get("parts")
    if not isinstance(parts, list) or not parts:
        raise DeliveryError("delivery plan has no parts")
    for expected, part in enumerate(parts, start=1):
        if not isinstance(part, dict) or part.get("index") != expected:
            raise DeliveryError("invalid part index")
        if not HASH_RE.fullmatch(str(part.get("text_sha256", ""))):
            raise DeliveryError("invalid part hash")
        if not isinstance(part.get("utf16_units"), int) or not 1 <= part["utf16_units"] <= plan["part_limit_utf16"]:
            raise DeliveryError("invalid part length")
        if part.get("status") not in VALID_PART_STATES:
            raise DeliveryError("invalid part status")
        message_id = part.get("message_id")
        if part["status"] == "sent" and (
            isinstance(message_id, bool) or not isinstance(message_id, int)
            or message_id <= 0
        ):
            raise DeliveryError("sent part lacks a valid positive message id")
        if part["status"] != "sent" and part.get("message_id") is not None:
            raise DeliveryError("unsent part has a message id")
    statuses = [part["status"] for part in parts]
    first_unsent = next((idx for idx, value in enumerate(statuses) if value != "sent"), len(statuses))
    if any(value == "sent" for value in statuses[first_unsent:]):
        raise DeliveryError("sent parts do not form an ordered prefix")
    active = [value for value in statuses if value in {"sending", "failed", "ambiguous"}]
    if len(active) > 1:
        raise DeliveryError("delivery plan has multiple active outcomes")
    expected_top = (
        "completed" if all(value == "sent" for value in statuses)
        else "ambiguous" if "ambiguous" in statuses
        else "sending" if "sending" in statuses
        else "failed" if "failed" in statuses
        else "pending"
    )
    if plan["status"] != expected_top:
        raise DeliveryError("top-level status disagrees with part states")
    if not HASH_RE.fullmatch(str(plan.get("plan_sha256", ""))) or plan_sha256(plan) != plan["plan_sha256"]:
        raise DeliveryError("delivery plan hash mismatch")


def _parts_for_body(plan: dict[str, Any], body: str) -> list[str]:
    if sha256_bytes(body.encode("utf-8")) != plan["body_sha256"]:
        raise DeliveryError("day body differs from frozen delivery plan", code=21, status="ambiguous")
    if utf16_units(body) != plan["body_utf16_units"]:
        raise DeliveryError("day body UTF-16 length differs", code=21, status="ambiguous")
    try:
        pieces = split_text(body, plan["part_limit_utf16"])
    except ValueError as exc:
        raise DeliveryError("frozen body cannot reproduce parts", code=21, status="ambiguous") from exc
    if len(pieces) != len(plan["parts"]):
        raise DeliveryError("part count differs from frozen plan", code=21, status="ambiguous")
    for piece, record in zip(pieces, plan["parts"]):
        if sha256_bytes(piece.encode("utf-8")) != record["text_sha256"] or utf16_units(piece) != record["utf16_units"]:
            raise DeliveryError("part hash differs from frozen plan", code=21, status="ambiguous")
    return pieces


def _sync_top_status(plan: dict[str, Any]) -> None:
    statuses = [part["status"] for part in plan["parts"]]
    if all(state == "sent" for state in statuses):
        plan["status"] = "completed"
    elif "ambiguous" in statuses:
        plan["status"] = "ambiguous"
    elif "sending" in statuses:
        plan["status"] = "sending"
    elif "failed" in statuses:
        plan["status"] = "failed"
    else:
        plan["status"] = "pending"
    plan["updated_at"] = now_iso()


def _persist_ambiguous(day_path: Path, sidecar: Path, plan: dict[str, Any],
                       reason: str) -> None:
    """Freeze attempted delivery as ambiguous before returning an error."""
    target = next(
        (part for part in plan["parts"] if part["status"] != "sent"),
        None,
    )
    if target is None:
        raise DeliveryError("completed plan cannot become ambiguous")
    target["status"] = "ambiguous"
    target["message_id"] = None
    plan["error"] = reason
    _sync_top_status(plan)
    atomic_json(sidecar, plan)
    reconcile_day(day_path, plan)


def _frontmatter_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    sent = [part for part in plan["parts"] if part["status"] == "sent"]
    delivery = {
        "completed": "telegram_ok",
        "ambiguous": "telegram_ambiguous",
        "sending": "telegram_sending",
        "failed": "telegram_failed",
        "pending": "pending",
    }[plan["status"]]
    values: dict[str, Any] = {
        "delivery": delivery,
        "delivery_parts_total": len(plan["parts"]),
        "delivery_parts_sent": len(sent),
        "delivery_plan_sha256": plan["plan_sha256"],
    }
    if sent:
        values["delivery_message_id"] = sent[0]["message_id"]
    return values


def reconcile_day(path: Path, plan: dict[str, Any]) -> None:
    update_frontmatter(path, _frontmatter_evidence(plan))


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def command_plan(args: argparse.Namespace) -> int:
    day_path, sidecar = Path(args.day_file), Path(args.sidecar)
    try:
        limit = validate_limit(args.limit)
    except ValueError as exc:
        raise DeliveryError(str(exc)) from exc
    fm = _frontmatter_map(day_path)
    if not sidecar.exists():
        if fm.get("delivery") == "telegram_ok":
            emit({"status": "completed", "legacy": True})
            return 0
        try:
            legacy_sent = int(fm.get("delivery_parts_sent", "0") or "0")
        except ValueError:
            legacy_sent = 0
        if legacy_sent > 0:
            raise DeliveryError("legacy partial delivery lacks sidecar", code=21, status="ambiguous")
        body = extract_body(day_path)
        plan = make_plan(body, args.date, args.language, limit)
        atomic_json(sidecar, plan)
        reconcile_day(day_path, plan)
        emit({"status": plan["status"], "parts": len(plan["parts"]), "plan_sha256": plan["plan_sha256"]})
        return 0

    plan = load_plan(sidecar)
    if any(part["status"] == "sending" for part in plan["parts"]):
        for part in plan["parts"]:
            if part["status"] == "sending":
                part["status"] = "ambiguous"
        _sync_top_status(plan)
        atomic_json(sidecar, plan)
        reconcile_day(day_path, plan)
        emit({"status": "ambiguous", "reason": "restart_from_sending"})
        return 21
    if plan["status"] == "ambiguous":
        emit({"status": "ambiguous", "reason": "manual_reconciliation_required"})
        return 21
    if plan["status"] == "completed":
        reconcile_day(day_path, plan)
        emit({"status": "completed", "parts": len(plan["parts"])})
        return 0
    if plan["date"] != args.date or plan["language"] != args.language or plan["part_limit_utf16"] != limit:
        attempted = any(part["status"] != "pending" for part in plan["parts"])
        if attempted:
            _persist_ambiguous(
                day_path, sidecar, plan,
                "delivery identity or limit drift after attempt",
            )
            raise DeliveryError("delivery identity or limit drift after attempt", code=21, status="ambiguous")
        body = extract_body(day_path)
        plan = make_plan(body, args.date, args.language, limit)
        atomic_json(sidecar, plan)
        reconcile_day(day_path, plan)
        emit({"status": "pending", "parts": len(plan["parts"]), "replaced": True})
        return 0
    body = extract_body(day_path)
    try:
        _parts_for_body(plan, body)
    except DeliveryError as exc:
        if any(part["status"] != "pending" for part in plan["parts"]):
            _persist_ambiguous(day_path, sidecar, plan, str(exc))
            raise
        plan = make_plan(body, args.date, args.language, limit)
        atomic_json(sidecar, plan)
        reconcile_day(day_path, plan)
        emit({"status": "pending", "parts": len(plan["parts"]), "replaced": True})
        return 0
    reconcile_day(day_path, plan)
    emit({"status": plan["status"], "parts": len(plan["parts"]), "plan_sha256": plan["plan_sha256"]})
    return 0


def command_begin(args: argparse.Namespace) -> int:
    day_path, sidecar, part_path = Path(args.day_file), Path(args.sidecar), Path(args.part_file)
    plan = load_plan(sidecar)
    if any(part["status"] == "sending" for part in plan["parts"]):
        raise DeliveryError("part is already sending", code=21, status="ambiguous")
    if plan["status"] == "completed":
        reconcile_day(day_path, plan)
        emit({"status": "completed"})
        return 3
    if plan["status"] == "ambiguous":
        raise DeliveryError("delivery is ambiguous", code=21, status="ambiguous")
    body = extract_body(day_path)
    pieces = _parts_for_body(plan, body)
    chosen: dict[str, Any] | None = None
    for part in plan["parts"]:
        if part["status"] in {"pending", "failed"}:
            chosen = part
            break
    if chosen is None:
        raise DeliveryError("delivery plan has no sendable part")
    chosen["status"] = "sending"
    chosen["message_id"] = None
    _sync_top_status(plan)
    atomic_json(sidecar, plan)
    reconcile_day(day_path, plan)
    text = pieces[chosen["index"] - 1]
    atomic_private_text(part_path, text)
    emit({"status": "sending", "index": chosen["index"], "utf16_units": chosen["utf16_units"]})
    return 0


def command_finish(args: argparse.Namespace) -> int:
    day_path, sidecar, part_path = Path(args.day_file), Path(args.sidecar), Path(args.part_file)
    plan = load_plan(sidecar)
    sending = [part for part in plan["parts"] if part["status"] == "sending"]
    if len(sending) != 1:
        raise DeliveryError("delivery plan does not have exactly one sending part", code=21, status="ambiguous")
    part = sending[0]
    try:
        raw = part_path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeliveryError("temporary part is unavailable", code=21, status="ambiguous") from exc
    if stat.S_IMODE(part_path.stat().st_mode) != 0o600:
        raise DeliveryError("temporary part permissions are unsafe", code=21, status="ambiguous")
    if sha256_bytes(raw) != part["text_sha256"] or utf16_units(text) != part["utf16_units"]:
        raise DeliveryError("temporary part does not match frozen plan", code=21, status="ambiguous")

    if args.outcome == "success":
        if args.message_id is None or not re.fullmatch(r"[1-9][0-9]*", str(args.message_id)):
            part["status"] = "ambiguous"
            part["message_id"] = None
            plan["error"] = "success outcome has invalid message id"
            _sync_top_status(plan)
            atomic_json(sidecar, plan)
            reconcile_day(day_path, plan)
            try:
                part_path.unlink()
            except FileNotFoundError:
                pass
            emit({"status": "ambiguous", "index": part["index"], "outcome": "ambiguous"})
            return 21
        part["status"] = "sent"
        part["message_id"] = int(args.message_id)
    elif args.outcome == "known_rejection":
        part["status"] = "failed"
        part["message_id"] = None
    else:
        part["status"] = "ambiguous"
        part["message_id"] = None
    _sync_top_status(plan)
    atomic_json(sidecar, plan)
    reconcile_day(day_path, plan)
    try:
        part_path.unlink()
    except FileNotFoundError:
        pass
    emit({"status": plan["status"], "index": part["index"], "outcome": args.outcome})
    return 0 if args.outcome == "success" else (20 if args.outcome == "known_rejection" else 21)


def command_rollback(args: argparse.Namespace) -> int:
    sidecar = Path(args.sidecar)
    day_path = Path(args.day_file)
    if not sidecar.exists():
        fm = _frontmatter_map(day_path)
        if fm.get("delivery") == "telegram_ok":
            emit({"status": "safe", "reason": "legacy_completed"})
            return 0
        try:
            sent = int(fm.get("delivery_parts_sent", "0") or "0")
        except ValueError:
            sent = 0
        if sent:
            raise DeliveryError("legacy partial delivery blocks rollback", code=21, status="ambiguous")
        emit({"status": "safe", "reason": "no_sidecar"})
        return 0
    plan = load_plan(sidecar)
    if plan["status"] == "completed":
        reconcile_day(day_path, plan)
        emit({"status": "safe", "reason": "completed"})
        return 0
    if plan["status"] == "pending" and all(part["status"] == "pending" for part in plan["parts"]):
        sidecar.unlink()
        emit({"status": "safe", "reason": "discarded_unattempted"})
        return 0
    raise DeliveryError("active or attempted delivery blocks rollback", code=21, status=plan["status"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--day-file", required=True)
    plan.add_argument("--sidecar", required=True)
    plan.add_argument("--date", required=True)
    plan.add_argument("--language", required=True)
    plan.add_argument("--limit", required=True)
    plan.set_defaults(handler=command_plan)
    begin = sub.add_parser("begin")
    begin.add_argument("--day-file", required=True)
    begin.add_argument("--sidecar", required=True)
    begin.add_argument("--part-file", required=True)
    begin.set_defaults(handler=command_begin)
    finish = sub.add_parser("finish")
    finish.add_argument("--day-file", required=True)
    finish.add_argument("--sidecar", required=True)
    finish.add_argument("--outcome", choices=("success", "known_rejection", "ambiguous"), required=True)
    finish.add_argument("--message-id")
    finish.add_argument("--part-file", required=True)
    finish.set_defaults(handler=command_finish)
    rollback = sub.add_parser("rollback-preflight")
    rollback.add_argument("--day-file", required=True)
    rollback.add_argument("--sidecar", required=True)
    rollback.set_defaults(handler=command_rollback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except DeliveryError as exc:
        emit({"status": exc.status, "error": str(exc)})
        return exc.code
    except Exception as exc:  # fail closed without a traceback or sensitive data
        emit({"status": "error", "error": exc.__class__.__name__})
        return 1


if __name__ == "__main__":
    sys.exit(main())
