"""Dedup logic: email-first deterministic → Jaro-Winkler fuzzy → draft flag."""

from . import index


# Jaro-Winkler thresholds tuned 2026-05-02 against real first-import
# data (25 calendar attendees). Old SCORE_DRAFT_THRESHOLD=0.50 produced
# 21/25 false-positive drafts — names like "corina stefanescu" matched
# "azingis" at ~0.5, which is meaningless at that distance. Raising
# the floor to 0.85 keeps near-duplicates (e.g. "Alice" vs "Alice C")
# while letting unrelated names pass to clean auto-create.
SCORE_AUTO_MERGE = 0.92
SCORE_DRAFT_THRESHOLD = 0.85
# Skip fuzzy matching entirely when the name is too short to carry
# meaningful signal — Jaro-Winkler treats 1-2 char names as similar
# to almost anything.
MIN_NAME_LEN_FOR_FUZZY = 4


def find_existing(name: str, email: str = "", telegram: str = "") -> tuple[str | None, str]:
    """
    Returns (uuid_or_None, strategy).
    strategy: 'email-match' | 'name-match-high' | 'name-match-ambiguous' | 'new'
    """
    # 1. Email-first deterministic (~65% of cases)
    if email:
        uid = index.lookup_by_email(email)
        if uid:
            return uid, "email-match"

    # 2. Jaro-Winkler name fuzzy — only when the name is long enough
    # to give the metric meaningful signal.
    if name and len(name.strip()) >= MIN_NAME_LEN_FOR_FUZZY:
        matches = index.lookup_by_name(name)
        if matches:
            top_uid, top_score = matches[0]
            if top_score >= SCORE_AUTO_MERGE:
                return top_uid, "name-match-high"
            if top_score >= SCORE_DRAFT_THRESHOLD:
                slug = index.get_slug(top_uid)
                return None, f"name-match-ambiguous:{slug}"

    return None, "new"


def resolve(name: str, email: str = "", telegram: str = "") -> dict:
    """
    Returns action dict:
      action: 'update' | 'create' | 'create-draft'
      uid: existing UUID (for update) or None (create will generate)
      possible_duplicate_of: slug if ambiguous (for draft note)
    """
    uid, strategy = find_existing(name, email, telegram)

    if strategy == "email-match" or strategy == "name-match-high":
        return {"action": "update", "uid": uid, "possible_duplicate_of": ""}

    if strategy.startswith("name-match-ambiguous:"):
        candidate_slug = strategy.split(":", 1)[1]
        return {"action": "create-draft", "uid": None, "possible_duplicate_of": candidate_slug}

    return {"action": "create", "uid": None, "possible_duplicate_of": ""}
