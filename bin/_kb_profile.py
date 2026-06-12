#!/usr/bin/env python3
"""_kb_profile — reader for personal/profile.yaml, the set-once user profile.

Spec: user-language-setting-2026-06-12 (KB decisions; cross-reviewed round 2:
agy approve, codex approve-with-nits).

The profile is the single source of truth for the user's language. Every
user-facing process resolves it the same way:

    KB_LANG env override (tests/debug) -> profile.yaml `language` -> "en"

Hard rules:
- Values are normalized (lowercase, strip) and MUST match ^[a-z]{2,3}$.
  Anything else — malformed YAML, injection-shaped strings, empty/over-long
  values — falls back to "en" with a log line. A 2-3-lowercase-letter token
  cannot carry prompt injection, so it is safe to interpolate into LLM
  prompts after this check.
- Fail-open: a missing or broken profile never blocks delivery; language is
  presentation, not safety.

CLI (used by shell runners like kb-brief/kb-retro):
    python3 _kb_profile.py <hub>            -> prints the language code
    python3 _kb_profile.py <hub> --name     -> prints the prompt-ready name
    python3 _kb_profile.py <hub> --ensure   -> create default profile, print code
"""
from __future__ import annotations

import datetime
import os
import re
import sys
import tempfile

_CODE_RE = re.compile(r"^[a-z]{2,3}$")

# Prompt-ready English names. A regex-valid code missing here is still
# allowed — it renders as a safe ISO-639 phrase (see language_directive).
LANGUAGE_NAMES = {
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
    "uk": "Ukrainian",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "nl": "Dutch",
    "tr": "Turkish",
    "cs": "Czech",
    "sv": "Swedish",
    "ro": "Romanian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "hi": "Hindi",
    "he": "Hebrew",
    "el": "Greek",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
}

DEFAULT_PROFILE_YAML = """\
# Vepol user profile — set once, read by every user-facing process.
# language: short code (en, ru, es, uk, de, ...). Change it any time;
# the next scheduled run delivers in the new language.
language: en
"""


def _log(hub, msg: str) -> None:
    try:
        log_path = os.path.join(os.fspath(hub), "logs", "profile.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] profile: {msg}\n")
    except OSError:
        pass


def _normalize(raw, hub, source: str):
    """Return a validated code or None (caller falls back)."""
    if raw is None:
        return None
    code = str(raw).strip()
    # Strip quotes only when BALANCED: an unbalanced quote means a mangled/
    # multi-line value (e.g. the first physical line of an injection-shaped
    # string) and must fail closed to en, not be silently half-honored.
    if len(code) >= 2 and code[0] == code[-1] and code[0] in ("'", '"'):
        code = code[1:-1].strip()
    code = code.lower()
    if _CODE_RE.match(code):
        return code
    if code:
        _log(hub, f"invalid language value from {source}: {raw!r}; falling back to en")
    return None


def get_language(hub=None) -> str:
    hub = os.fspath(hub) if hub is not None else os.environ.get(
        "KB_HUB", os.path.expanduser("~/knowledge"))
    raw_env = os.environ.get("KB_LANG")
    env_code = _normalize(raw_env, hub, "KB_LANG")
    if env_code:
        return env_code
    # Empty KB_LANG ("") means "no override" — fall through to the profile.
    # A NON-empty invalid value fails closed to en (already logged): the
    # override must stay deterministic, never silently fall to the profile.
    if raw_env:
        return "en"
    path = os.path.join(hub, "personal", "profile.yaml")
    if not os.path.isfile(path):
        return "en"
    try:
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                # Inline comments must not poison values.
                line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                if key.strip() == "language":
                    code = _normalize(val, hub, "profile.yaml")
                    return code or "en"
    except OSError as exc:
        _log(hub, f"profile read failed: {exc}; falling back to en")
    return "en"


def language_name(code: str):
    return LANGUAGE_NAMES.get(code)


def language_directive(code: str) -> str:
    """Prompt-ready phrase. Safe for interpolation: `code` has passed
    ^[a-z]{2,3}$ by construction when it came from get_language()."""
    name = LANGUAGE_NAMES.get(code)
    if name:
        return name
    if _CODE_RE.match(code or ""):
        return f"the language with ISO 639 code '{code}'"
    return "English"


def ensure_default(path) -> None:
    """Create the profile with the en default when missing; never overwrite."""
    path = os.fspath(path)
    if os.path.exists(path):
        return
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".profile.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROFILE_YAML)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv) -> int:
    if len(argv) < 2:
        print("usage: _kb_profile.py <hub> [--name|--ensure]", file=sys.stderr)
        return 2
    hub = argv[1]
    if "--ensure" in argv[2:]:
        ensure_default(os.path.join(hub, "personal", "profile.yaml"))
    code = get_language(hub)
    if "--name" in argv[2:]:
        print(language_directive(code))
    else:
        print(code)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
