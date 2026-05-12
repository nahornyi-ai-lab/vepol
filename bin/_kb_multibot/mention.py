"""Mention parsing — extract bot usernames from message text.

Concept §7.4: supervisor parses incoming events (from humans) and outbound
events (from our own sendMessage echoed back by Telethon listener) for
@bot_username mentions. The parser is text-only — no Telegram entity API
needed because Telethon Message.text contains @-handles inline.

This module also exposes a tiny /stop command detector for kill-switch
(concept §7.4 + ).
"""

from __future__ import annotations

import re

# Telegram bot username rules (BotFather):
#  - 5..32 chars
#  - starts with a letter
#  - [a-zA-Z0-9_], case-insensitive
#  - must end in "bot" (case-insensitive)
# Mention regex is liberal on the end (any [a-z0-9_]) and case-insensitive;
# we validate "ends with bot" semantically downstream against registry.
_MENTION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{4,31})")

# /stop command form 1: "/stop @some_bot"   (text-based, may have multiple @s)
# /stop command form 2: bare "/stop" — only valid if message is a reply to a bot
# (caller resolves bot identity from reply_to context, not from this regex).
_STOP_RE = re.compile(r"(?i)(?:^|\s)/stop\b")


def extract_mentions(text: str) -> list[str]:
    """Return list of mentioned usernames (without @), in left-to-right order.

    Duplicates removed but order of first occurrence preserved (relevant for
    fan-out cap accounting — first F=10 mentions get spawned in parallel,
    rest queue).

    Lowercased so registry lookups can normalize Telegram's case-insensitive
    usernames. Validation of "is this a real bot we know" happens against
    the agent registry, not here.

    >>> extract_mentions("@vepol_bot статус? @kb_mail_bot тоже")
    ['vepol_bot', 'kb_mail_bot']
    >>> extract_mentions("@Vepol_Bot @vepol_bot")
    ['vepol_bot']
    >>> extract_mentions("no mentions here")
    []
    >>> extract_mentions("email me at test@example.com — @real_bot")
    ['example', 'real_bot']
    """
    if not text:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _MENTION_RE.finditer(text):
        name = m.group(1).lower()
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def filter_bot_mentions(mentions: list[str], known_bots: set[str]) -> list[str]:
    """Drop mentions that aren't in our agent registry.

    Avoids spawning on `@example` (from an email) or `@some_random_user` —
    only mentions matching known bot usernames trigger spawn.

    `known_bots` should be a set of lowercase bot usernames stripped of @.

    >>> filter_bot_mentions(["vepol_bot", "example", "kb_mail_bot"],
    ...                    {"vepol_bot", "kb_mail_bot"})
    ['vepol_bot', 'kb_mail_bot']
    """
    return [m for m in mentions if m in known_bots]


def has_stop_command(text: str) -> bool:
    """Detect /stop command in text.

    Used together with reply context (mention.py is text-only; caller passes
    Telegram reply_to_message_id resolution separately) — see kill_switch.py.

    >>> has_stop_command("/stop @vepol_bot")
    True
    >>> has_stop_command("please /STOP @bot")
    True
    >>> has_stop_command("/stoplight")
    False
    >>> has_stop_command("no stop here")
    False
    """
    if not text:
        return False
    return bool(_STOP_RE.search(text))


def extract_stop_targets(text: str) -> list[str]:
    """For text-based /stop, return bots to be killed (lowercase, no @).

    If `/stop` present and mentions follow, return mentions.
    If `/stop` present but no mentions, return empty list — caller resolves
    target from reply_to_message_id via state.runs.

    >>> extract_stop_targets("/stop @vepol_bot @kb_mail_bot")
    ['vepol_bot', 'kb_mail_bot']
    >>> extract_stop_targets("/stop")
    []
    >>> extract_stop_targets("not a stop command")
    []
    """
    if not has_stop_command(text):
        return []
    return extract_mentions(text)


__all__ = [
    "extract_mentions",
    "filter_bot_mentions",
    "has_stop_command",
    "extract_stop_targets",
]
