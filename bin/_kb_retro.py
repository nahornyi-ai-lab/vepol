"""Strict parsing, hashing, and transactional persistence for Evening Retro."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
import fcntl
import hashlib
import os
from pathlib import Path
import re
import tempfile


class RetroError(RuntimeError):
    """Base error for the durable Retro boundary."""


class ProducerOutputError(RetroError):
    """The producer did not return one complete Retro/Reflection payload."""


class RetroPersistenceError(RetroError):
    """A complete producer payload could not be committed and validated."""


@dataclass(frozen=True)
class ParsedRetro:
    """One valid trusted Retro body parsed from a day file."""

    heading: str
    time_hm: str
    body: str
    sha256: str


@dataclass(frozen=True)
class ProducerSections:
    """Normalized non-empty sections accepted from the Retro producer."""

    retro: str
    reflection: str


__all__ = [
    "ParsedRetro",
    "ProducerOutputError",
    "ProducerSections",
    "RetroError",
    "RetroPersistenceError",
    "load_retro",
    "normalize_body",
    "parse_producer_output",
    "parse_retro",
    "persist_retro",
    "retro_sha256",
]


_TIME_PATTERN = r"(?:[01]\d|2[0-3]):[0-5]\d"
_RETRO_CANONICAL_RE = re.compile(
    rf"^## Retro \(({_TIME_PATTERN})\)[ \t]*$", re.MULTILINE
)
_REFLECTION_CANONICAL_RE = re.compile(
    rf"^## Reflection \(({_TIME_PATTERN})\)[ \t]*$", re.MULTILINE
)
_RETRO_SECTION_RE = re.compile(
    r"^## Retro(?:[ \t(]|$)[^\n]*$", re.MULTILINE
)
_REFLECTION_SECTION_RE = re.compile(
    r"^## Reflection(?:[ \t(]|$)[^\n]*$", re.MULTILINE
)
_SUFFIX_BOUNDARY_RE = re.compile(
    r"^## (?:Retro|Reflection)(?:[ \t(]|$)[^\n]*$", re.MULTILINE
)
_UNTRUSTED_OR_BOUNDARY_RE = re.compile(
    r"<(?P<close>/?)untrusted-source-[^>]*>"
    r"|(?P<boundary>^## (?:Retro|Reflection)(?:[ \t(]|$)[^\n]*$)",
    re.IGNORECASE | re.MULTILINE,
)
_EXACT_RETRO_DELIMITER = "---RETRO---"
_EXACT_REFLECTION_DELIMITER = "---REFLECTION---"
_DIAGNOSTIC_PREFIXES = (
    "error",
    "unavailable",
    "diagnostic",
    "traceback",
    "producer error",
    "producer failed",
    "codex executable unavailable",
    "orchestrator failed",
    "retro could not be assembled",
    "ошибка",
    "недоступ",
    "не удалось",
    "ретро не собралось",
)
_DIAGNOSTIC_SHAPE_WORDS = (
    "empty",
    "failed",
    "failure",
    "пусто",
    "сбой",
)


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_body(body: str) -> str:
    """Return the canonical body representation used by every Retro hash."""

    lines = [line.rstrip(" \t") for line in _normalize_line_endings(body).split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def retro_sha256(body: str) -> str:
    """Hash only the canonical trusted Retro body, never its heading."""

    normalized = normalize_body(body)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _append_trusted_chunk(output: list[str], chunk: str) -> None:
    if not chunk:
        return
    cut = chunk.casefold().find("<untrusted-source-")
    output.append(chunk if cut == -1 else chunk[:cut])


def _strip_untrusted_spans(text: str) -> str:
    """Drop balanced, nested, orphaned, and truncated untrusted-source spans."""

    text = _normalize_line_endings(text)
    output: list[str] = []
    position = 0
    depth = 0
    for match in _UNTRUSTED_OR_BOUNDARY_RE.finditer(text):
        if match.group("boundary") is not None:
            if depth == 0:
                _append_trusted_chunk(output, text[position:match.start()])
                output.append(match.group(0))
            # A heading inside an open untrusted span is attacker-controlled;
            # strip it without closing or resynchronizing the span.
            position = match.end()
            continue

        if depth == 0:
            _append_trusted_chunk(output, text[position:match.start()])
        if match.group("close") != "/":
            depth += 1
        elif depth > 0:
            depth -= 1
        position = match.end()

    if depth == 0:
        _append_trusted_chunk(output, text[position:])
    # An unclosed opening tag makes the remaining tail untrusted.
    return "".join(output)


def _trusted_suffix_boundary_start(text: str) -> int | None:
    """Return the first Retro/Reflection boundary outside untrusted spans."""

    depth = 0
    for match in _UNTRUSTED_OR_BOUNDARY_RE.finditer(text):
        if match.group("boundary") is not None:
            if depth == 0:
                return match.start()
            continue
        if match.group("close") != "/":
            depth += 1
        elif depth > 0:
            depth -= 1
    return None


def _truncate_unclosed_untrusted_tail(text: str) -> str:
    """Drop the malformed tail beginning at the first still-open source tag."""

    open_starts: list[int] = []
    for match in _UNTRUSTED_OR_BOUNDARY_RE.finditer(text):
        if match.group("boundary") is not None:
            continue
        if match.group("close") != "/":
            open_starts.append(match.start())
        elif open_starts:
            open_starts.pop()
    return text[:open_starts[0]] if open_starts else text


def _is_diagnostic_placeholder(body: str) -> bool:
    normalized = normalize_body(body)
    if not normalized:
        return False
    lines = normalized.rstrip("\n").split("\n")
    first = lines[0].strip().casefold()
    first = first.lstrip(" \t>*_`#-[](){}:;,.!\ufe0f⚠❌🚫✅📋⏸💡☀🌙")
    for prefix in _DIAGNOSTIC_PREFIXES:
        if first == prefix or first.startswith(
            (prefix + ":", prefix + " ", prefix + "(", prefix + "-", prefix + "—")
        ):
            return True
    for word in _DIAGNOSTIC_SHAPE_WORDS:
        if first.startswith((word + ":", word + "(")):
            return True
        if len(lines) == 1 and first == word:
            return True
    return False


def parse_retro(day_text: str) -> ParsedRetro | None:
    """Parse one canonical, non-placeholder trusted Retro from day-file text."""

    cleaned = _strip_untrusted_spans(day_text)
    retro_sections = list(_RETRO_SECTION_RE.finditer(cleaned))
    canonical = list(_RETRO_CANONICAL_RE.finditer(cleaned))
    if len(retro_sections) != 1 or len(canonical) != 1:
        return None
    heading = canonical[0]
    if heading.start() != retro_sections[0].start():
        return None

    reflection = _REFLECTION_CANONICAL_RE.search(cleaned, heading.end())
    stop = reflection.start() if reflection is not None else len(cleaned)
    body = normalize_body(cleaned[heading.end():stop])
    if not body or _is_diagnostic_placeholder(body):
        return None
    return ParsedRetro(
        heading=heading.group(0).rstrip(" \t"),
        time_hm=heading.group(1),
        body=body,
        sha256=retro_sha256(body),
    )


def _validate_date(date_iso: str) -> str:
    try:
        parsed = dt.date.fromisoformat(date_iso)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Retro date: {date_iso!r}") from exc
    if parsed.isoformat() != date_iso:
        raise ValueError(f"invalid Retro date: {date_iso!r}")
    return date_iso


def load_retro(
    hub: str | os.PathLike[str],
    date_iso: str,
) -> ParsedRetro | None:
    """Load Retro authority only from ``<hub>/briefs/<date_iso>.md``."""

    date_iso = _validate_date(date_iso)
    day_file = Path(hub) / "briefs" / f"{date_iso}.md"
    try:
        day_text = day_file.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return None
    return parse_retro(day_text)


def parse_producer_output(
    output: str,
    *,
    producer_rc: int = 0,
) -> ProducerSections:
    """Accept exactly one ordered delimiter pair with two non-empty bodies."""

    if producer_rc != 0:
        raise ProducerOutputError(f"Retro producer failed with rc={producer_rc}")

    lines = _normalize_line_endings(output).split("\n")
    retro_delimiters = [
        index for index, line in enumerate(lines) if line == _EXACT_RETRO_DELIMITER
    ]
    reflection_delimiters = [
        index for index, line in enumerate(lines) if line == _EXACT_REFLECTION_DELIMITER
    ]
    if len(retro_delimiters) != 1 or len(reflection_delimiters) != 1:
        raise ProducerOutputError("producer output requires each exact delimiter once")

    retro_index = retro_delimiters[0]
    reflection_index = reflection_delimiters[0]
    if retro_index >= reflection_index:
        raise ProducerOutputError("producer delimiters are out of order")

    retro = normalize_body(
        _strip_untrusted_spans("\n".join(lines[retro_index + 1:reflection_index]))
    )
    reflection = normalize_body(
        _strip_untrusted_spans("\n".join(lines[reflection_index + 1:]))
    )
    if not retro or not reflection:
        raise ProducerOutputError("producer Retro and Reflection bodies must be non-empty")
    if _is_diagnostic_placeholder(retro):
        raise ProducerOutputError("producer Retro body is a diagnostic placeholder")
    if _SUFFIX_BOUNDARY_RE.search(retro) or _SUFFIX_BOUNDARY_RE.search(reflection):
        raise ProducerOutputError("producer bodies contain a Retro/Reflection boundary")
    return ProducerSections(retro=retro, reflection=reflection)


def _complete_pair(day_text: str, parsed: ParsedRetro | None) -> bool:
    if parsed is None:
        return False
    cleaned = _strip_untrusted_spans(day_text)
    retro_sections = list(_RETRO_SECTION_RE.finditer(cleaned))
    reflections = list(_REFLECTION_SECTION_RE.finditer(cleaned))
    canonical_retro = list(_RETRO_CANONICAL_RE.finditer(cleaned))
    canonical_reflection = list(_REFLECTION_CANONICAL_RE.finditer(cleaned))
    if not (
        len(retro_sections)
        == len(reflections)
        == len(canonical_retro)
        == len(canonical_reflection)
        == 1
    ):
        return False
    if canonical_retro[0].start() != retro_sections[0].start():
        return False
    if canonical_reflection[0].start() != reflections[0].start():
        return False
    if canonical_reflection[0].start() <= canonical_retro[0].end():
        return False
    reflection_body = normalize_body(
        cleaned[canonical_reflection[0].end():]
    )
    return bool(reflection_body)


def _minimal_day_file(date_iso: str) -> str:
    return f"---\ndate: {date_iso}\nreflection: pending\n---\n\n"


def _render_pair(time_hm: str, sections: ProducerSections) -> str:
    return (
        f"## Retro ({time_hm})\n\n"
        f"{sections.retro}\n"
        f"## Reflection ({time_hm})\n\n"
        f"{sections.reflection}"
    )


def _join_prefix(prefix: str, pair: str) -> str:
    if not prefix:
        return pair
    if prefix.endswith("\n\n") or prefix.endswith("\r\n\r\n"):
        separator = ""
    elif prefix.endswith("\n") or prefix.endswith("\r"):
        separator = "\n"
    else:
        separator = "\n\n"
    return prefix + separator + pair


def _atomic_replace(path: Path, content: str, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(content.encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def _validate_time(time_hm: str) -> str:
    if re.fullmatch(_TIME_PATTERN, time_hm) is None:
        raise ValueError(f"invalid Retro time: {time_hm!r}")
    return time_hm


def persist_retro(
    hub: str | os.PathLike[str],
    date_iso: str,
    producer_output: str,
    *,
    producer_rc: int = 0,
    time_hm: str | None = None,
) -> ParsedRetro:
    """Atomically persist or idempotently reuse one complete day-file pair."""

    date_iso = _validate_date(date_iso)
    sections = parse_producer_output(producer_output, producer_rc=producer_rc)
    if time_hm is None:
        time_hm = dt.datetime.now().astimezone().strftime("%H:%M")
    time_hm = _validate_time(time_hm)

    hub_path = Path(hub)
    day_file = hub_path / "briefs" / f"{date_iso}.md"
    lock_file = hub_path / ".orchestrator" / f"retro-{date_iso}.lock"
    try:
        day_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        with lock_file.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if day_file.exists():
                original_bytes = day_file.read_bytes()
                original = original_bytes.decode("utf-8")
                mode = day_file.stat().st_mode & 0o777
            else:
                original = _minimal_day_file(date_iso)
                mode = 0o600

            existing = parse_retro(original)
            if _complete_pair(original, existing):
                return existing  # type: ignore[return-value]

            boundary_start = _trusted_suffix_boundary_start(original)
            prefix = original[:boundary_start] if boundary_start is not None else original
            prefix = _truncate_unclosed_untrusted_tail(prefix)
            committed_text = _join_prefix(prefix, _render_pair(time_hm, sections))
            _atomic_replace(day_file, committed_text, mode)

            # Re-read durable bytes and validate through the same public parser
            # used by planner/consumer callers; rc=0 is impossible before this.
            committed = day_file.read_bytes().decode("utf-8")
            parsed = parse_retro(committed)
            if not _complete_pair(committed, parsed):
                raise RetroPersistenceError("committed Retro failed post-validation")
            return parsed  # type: ignore[return-value]
    except ProducerOutputError:
        raise
    except RetroPersistenceError:
        raise
    except (OSError, UnicodeError) as exc:
        raise RetroPersistenceError(
            f"could not persist Retro for {date_iso}: {exc}"
        ) from exc
