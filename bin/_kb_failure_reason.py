"""Pick the real failure cause out of a provider's stderr or an outcome error text.

Contract (spec decisions/scheduler-honest-failure-2026-10-02.md §A): scan every
non-empty line for a cause class in priority order (quota, model, auth, network,
timeout); the first class that matches any line wins and that line is the reason.
If nothing matches, the LAST non-empty line is the reason, because tools print
informational notes first and causes last. Never the first line.

Keep this module dependency-free: it is copied verbatim into
face/vepol_face/automations.py (the Face cannot import hub modules) and a test
pins the two copies equal.
"""
from __future__ import annotations

import re

REASON_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("quota", (
        r"usage[_ ]limit",
        r"you've hit your (usage )?limit",
        r"quota",
        r"\b429\b",
        r"too many requests",
        r"resource_exhausted",
        r"spending[- ]limit",
    )),
    ("model", (
        r"model is not supported",
        r"not supported when using codex",
        r"unknown model",
        r"model_not_found",
        r"no such model",
    )),
    ("auth", (
        r"\b401\b",
        r"\b403\b",
        r"please login",
        r"authentication failed",
        r"oauth",
        r"unauthorized",
        r"invalid api key",
        r"auth error",
        r"not logged in",
    )),
    ("network", (
        r"connection (refused|reset)",
        r"name or service not known",
        r"nodename nor servname",
        r"network error",
        r"failed to .*resolve",
        r"temporary failure in name resolution",
        r"error sending request",
    )),
    ("timeout", (
        r"timed out",
        r"\btimeout\b",
    )),
)

REASON_CODES: tuple[str, ...] = tuple(code for code, _ in REASON_PATTERNS) + ("other",)


def failure_reason(text: str | None, limit: int = 200) -> tuple[str, str]:
    """Return (code, line). code is one of REASON_CODES; line is clipped to `limit`."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for code, patterns in REASON_PATTERNS:
        for line in lines:
            low = line.lower()
            if any(re.search(p, low) for p in patterns):
                return code, line[:limit]
    if lines:
        return "other", lines[-1][:limit]
    return "other", ""
