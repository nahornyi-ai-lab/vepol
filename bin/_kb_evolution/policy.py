from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyResult:
    allowed: bool
    reason: str
    hitl_required: bool = False


BANNED_EXACT_REL = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "promotions.md",
    "evolution/mutations.md",
    "decisions/autonomy-mode.md",
    "decisions/gemini-review-quorum.md",
    "decisions/file-mutation-verifier.md",
    "decisions/security-model-2026-05-22.md",
    "decisions/context-injection-scanner.md",
}


def _norm_target(surface_target: str) -> str:
    target = surface_target.replace("\\", "/")
    if target.startswith("/"):
        return target
    return target.lstrip("./")


def _is_hub_writer(surface_target: str) -> bool:
    target = _norm_target(surface_target)
    return target.startswith("/Users/macbook/knowledge/") or target == "/Users/macbook/knowledge"


def banned_reason(surface_target: str) -> str | None:
    target = _norm_target(surface_target)
    parts = target.split("/")
    if target in BANNED_EXACT_REL:
        return f"constitutional ban-list: {target}"
    if "/raw/" in f"/{target}/" or target.startswith("raw/") or target.endswith("/raw"):
        return "constitutional ban-list: raw/ is immutable"
    if target.endswith("SECURITY.md") or "/SECURITY.md" in target:
        return "constitutional ban-list: SECURITY.md/security policy"
    if target.endswith("scanner-signatures.md") or "scanner-signatures" in target:
        return "constitutional ban-list: scanner signature catalogue"
    if any(part in {".cursor", ".gemini"} for part in parts):
        return "constitutional ban-list: runtime adapter/config"
    if target.endswith("/AGENTS.md") or target.endswith("/CLAUDE.md") or target.endswith("/GEMINI.md"):
        return "constitutional ban-list: runtime adapter/control file"
    return None


def _sahoo_pass(evaluator: dict[str, Any]) -> bool:
    sahoo = evaluator.get("sahoo") or {}
    return (
        sahoo.get("drift_check") == "pass"
        and sahoo.get("invariant_check") == "pass"
        and sahoo.get("regression_check") == "pass"
    )


def validate_apply_request(
    knowledge_path: pathlib.Path,
    proposal: dict[str, Any],
    *,
    evaluator: dict[str, Any],
    scanner_available: bool = False,
    hitl_approved: bool = False,
) -> PolicyResult:
    """Enforce v0-minimal apply policy before ledger write/apply."""
    del knowledge_path  # reserved for later project-aware checks
    target = str(proposal.get("surface_target", ""))
    ban = banned_reason(target)
    if ban:
        return PolicyResult(False, ban)

    if _is_hub_writer(target) and not scanner_available:
        return PolicyResult(False, "hub-writer never exempt: context-injection scanner required")

    input_origins = proposal.get("input_origins") or []
    if any(origin != "runtime-generated" for origin in input_origins) and not scanner_available:
        return PolicyResult(False, "context-injection scanner required for non-runtime-generated input origin")

    risk_tier = int(proposal.get("risk_tier", 4))
    if risk_tier >= 2:
        if risk_tier == 4:
            return PolicyResult(False, "Tier 4 apply refused via Loop; manual decision spec required")
        return PolicyResult(False, "Tier 2-3 apply refused in v0-minimal; available in v0.1+ after implementation")

    author = (proposal.get("author") or {}).get("identity")
    evaluator_id = evaluator.get("identity")
    if author and evaluator_id and author == evaluator_id:
        return PolicyResult(False, "conflict-of-interest: author cannot be sole evaluator", hitl_required=True)

    metric_objectivity = (proposal.get("rationale") or {}).get("metric_objectivity")
    if metric_objectivity in {"qualitative", "preference"} and not hitl_approved:
        return PolicyResult(False, "ambiguous qualitative/preference metric requires HITL", hitl_required=True)

    if risk_tier >= 1 and not _sahoo_pass(evaluator):
        return PolicyResult(False, "SAHOO drift/invariant/regression checks must all pass")

    return PolicyResult(True, "allowed")
