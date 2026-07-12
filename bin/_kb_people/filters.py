"""Shared identity filters for the people notebook.

Owner directive (chat, 2026-07-05): «Ботов мне в записною книгу не
предлагай» — bot accounts are never people and must never reach the
review queue, regardless of the source that saw them.
"""

from __future__ import annotations

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def is_bot_identity(name: str = "", email: str = "",
                    telegram: str = "") -> bool:
    """True when the identity is a bot account, not a person.

    Signals (deterministic, source-independent):
      - telegram handle ending in "bot" — Telegram requires every bot
        username to end with it;
      - a name that normalizes to a "…bot" token (weather_alerts_bot,
        fitness_tracker_bot), but ONLY when the candidate has no email:
        an email is a strong human identifier and surnames like
        "Talbot" must never be dropped by a name heuristic. Bot-like
        email LOCAL PARTS stay covered by each source's own
        _BOT_LOCAL_PART_RE — not here.

    Known tradeoff: a bare name ending in "bot" with no other identity
    (e.g. a lone "Talbot" in a project log) is dropped too — such
    candidates are too weak to stage anyway and can always be added
    manually via `kb-contact add`.
    """
    tg = (telegram or "").strip().lstrip("@").lower()
    if tg.endswith("bot"):
        return True
    if not (email or "").strip():
        normalized = _NON_ALNUM_RE.sub("", (name or "").strip().lower())
        if normalized.endswith("bot"):
            return True
    return False


# ---------------------------------------------------------------------------
# Email junk classes shared by extraction sources (2026-07-05 dogfood gap:
# documentation fixtures and org mailboxes in project logs minted junk cards).
# ---------------------------------------------------------------------------

# RFC 2606 / RFC 6761 reserved names. An address on a documentation
# domain is a doc snippet or a fixture, never a reachable person — and
# Pass-1 hits can create LIVE cards without review (the 2026-07-05
# dogfood junk was exactly example.com addresses quoted in project
# logs). The `.test` / `.example` TLDs are deliberately NOT filtered:
# they are the sanctioned fixture-space for our own public test suites
# (fixtures must use RFC-reserved domains, and positive-extraction
# fixtures must survive this filter).
_RESERVED_EXAMPLE_DOMAINS = frozenset({
    "example.com", "example.org", "example.net",
})
_RESERVED_EXAMPLE_TLDS = frozenset({
    "invalid", "localhost",
})

# Role/system mailboxes that address an organisation or a function, not a
# person. Complements each source's own _BOT_LOCAL_PART_RE (bot / noreply /
# notification classes stay there); a genuine person behind a role address
# can always be added manually via `kb-contact add`.
_ROLE_LOCAL_PART_RE = re.compile(
    r"^(receipts?|owners?|orders?|payments?|purchases?|"
    r"subscriptions?|newsletters?|news|updates?|digests?|"
    r"marketing|promo(?:tions)?|offers?|"
    r"security|abuse|postmaster|webmaster|mailer-daemon|root|"
    r"careers|jobs|hr|press|media|privacy|legal|"
    r"feedback|surveys?|events|community|store|shop|services?)"
    r"[\d_.-]*@",
    re.IGNORECASE,
)


def is_reserved_example_email(email: str) -> bool:
    """True when the address lives on an RFC-reserved example domain
    (example.com/org/net incl. subdomains) or a reserved TLD
    (.test/.example/.invalid/.localhost)."""
    addr = (email or "").strip().lower()
    if "@" not in addr:
        return False
    domain = addr.rsplit("@", 1)[1]
    if not domain:
        return False
    if domain in _RESERVED_EXAMPLE_DOMAINS:
        return True
    if any(domain.endswith("." + d) for d in _RESERVED_EXAMPLE_DOMAINS):
        return True
    return domain.rsplit(".", 1)[-1] in _RESERVED_EXAMPLE_TLDS


def is_role_email(email: str) -> bool:
    """True when the local part is a role/system mailbox (receipts@,
    owner@, orders@, …) — an organisation function, not a person."""
    return bool(_ROLE_LOCAL_PART_RE.match((email or "").strip()))
