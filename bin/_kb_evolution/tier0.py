from __future__ import annotations

import difflib
import pathlib
import re
from dataclasses import dataclass


HIGH_IMPACT = {
    "not", "no", "never", "always", "must", "forbidden", "required",
    "refused", "approved", "autonomous", "invoked", "low", "medium",
    "high", "critical", "tier", "may",
}
KNOWN_TYPO_PAIRS = {("recieve", "receive"), ("teh", "the"), ("adress", "address")}

TOKEN_RE = re.compile(r"[A-Za-z0-9_@./:%+-]+")
IDENTIFIER_RE = re.compile(
    r"https?://\S+|[\w.+-]+@[\w.-]+|\b[0-9]+(?:\.[0-9]+)?%?\b|"
    r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9:]+Z?)?\b|"
    r"(?:^|\s)(?:/|~/|[A-Za-z0-9_.-]+/)[A-Za-z0-9_./-]+"
)


@dataclass
class Tier0Result:
    ok: bool
    reason: str


def _frontmatter(text: str) -> str | None:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return "__unterminated__"
    return "\n".join(lines[: end + 1])


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = cur
    return prev[-1]


def _changed_tokens(before: str, after: str) -> tuple[list[str], list[str]]:
    before_tokens = TOKEN_RE.findall(before)
    after_tokens = TOKEN_RE.findall(after)
    removed: list[str] = []
    added: list[str] = []
    for item in difflib.ndiff(before_tokens, after_tokens):
        if item.startswith("- "):
            removed.append(item[2:])
        elif item.startswith("+ "):
            added.append(item[2:])
    return removed, added


def _changed_line_count(before: str, after: str) -> int:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    count = 0
    for item in difflib.ndiff(before_lines, after_lines):
        if item.startswith("- ") or item.startswith("+ "):
            count += 1
    return count


def validate_tier0_typo(
    before: str,
    after: str,
    path: pathlib.Path,
    *,
    public_safe: str | bool,
) -> Tier0Result:
    """Deterministic Tier 0 typo validator from spec §5."""
    path = pathlib.Path(path)
    if public_safe != "reviewed":
        return Tier0Result(False, "public-bound artifact requires public_safe: reviewed")
    if before == after:
        return Tier0Result(False, "no diff")
    changed_bytes = abs(len(after.encode("utf-8")) - len(before.encode("utf-8")))
    if changed_bytes > 200 or _changed_line_count(before, after) > 5:
        return Tier0Result(False, "diff too large for Tier 0")
    if _frontmatter(before) != _frontmatter(after):
        return Tier0Result(False, "frontmatter changed")
    before_ids = set(IDENTIFIER_RE.findall(before))
    after_ids = set(IDENTIFIER_RE.findall(after))
    if before_ids != after_ids:
        return Tier0Result(False, "identifier/URL/number/timestamp/path changed")
    if path.name == "log.md":
        before_control = {line for line in before.splitlines() if line.startswith("## [")}
        after_control = {line for line in after.splitlines() if line.startswith("## [")}
        if before_control != after_control:
            return Tier0Result(False, "log.md control row changed")
    removed, added = _changed_tokens(before, after)
    changed_lower = {token.lower() for token in removed + added}
    if changed_lower & HIGH_IMPACT:
        return Tier0Result(False, "high-impact semantic token changed")
    pairs = list(zip(removed, added))
    if len(pairs) != max(len(removed), len(added)):
        return Tier0Result(False, "token insertion/deletion is not a typo pair")
    for old, new in pairs:
        old_l = old.lower()
        new_l = new.lower()
        if old_l == new_l:
            continue
        if (old_l, new_l) in KNOWN_TYPO_PAIRS:
            continue
        if _levenshtein(old_l, new_l) > 2:
            return Tier0Result(False, "edit distance > 2 and not in typo allowlist")
    return Tier0Result(True, "tier0-typo")
