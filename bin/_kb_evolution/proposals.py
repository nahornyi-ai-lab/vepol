from __future__ import annotations

import pathlib
import datetime as dt
import re
from typing import Any

import yaml

from .errors import EvolutionError


class ProposalError(EvolutionError):
    pass


PROPOSAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "proposal_id", "type", "status", "created", "author",
        "surface_type", "surface_target", "scope", "mutation_diff",
        "rationale", "risk_tier", "risk_justification", "reversibility",
        "input_origins", "public_safe", "evaluation_plan", "related",
    ],
    "properties": {
        "proposal_id": {"type": "string", "pattern": "^prop-[A-Za-z0-9_-]+-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}$"},
        "type": {"const": "mutation-proposal"},
        "status": {"enum": ["pending", "evaluating", "promoted", "rolled-back", "rejected"]},
        "created": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"},
        "author": {
            "type": "object",
            "required": ["type", "identity"],
            "properties": {
                "type": {"enum": ["orchestrator", "human"]},
                "identity": {"type": "string", "minLength": 1},
            },
            "additionalProperties": True,
        },
        "surface_type": {"enum": ["prompt", "rule", "skill", "workflow", "kb-structure"]},
        "surface_target": {"type": "string", "minLength": 1},
        "scope": {
            "type": "object",
            "required": ["affected_section", "unit_of_mutation", "blast_radius"],
            "properties": {
                "affected_section": {"type": "string"},
                "unit_of_mutation": {"enum": ["section", "frontmatter-field", "markdown-block", "skill-dir", "workflow-config"]},
                "blast_radius": {
                    "type": "object",
                    "required": ["files", "bytes", "runtimes_affected"],
                    "properties": {
                        "files": {"type": "integer", "minimum": 0},
                        "bytes": {"type": "integer", "minimum": 0},
                        "runtimes_affected": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
        "mutation_diff": {"type": "string"},
        "rationale": {
            "type": "object",
            "required": ["observation_signal", "hypothesis", "expected_metric", "metric_objectivity"],
            "properties": {
                "observation_signal": {"type": "string"},
                "hypothesis": {"type": "string"},
                "expected_metric": {"type": "string"},
                "metric_objectivity": {"enum": ["objective", "qualitative", "preference"]},
            },
            "additionalProperties": True,
        },
        "risk_tier": {"type": "integer", "minimum": 0, "maximum": 4},
        "risk_justification": {"type": "string"},
        "reversibility": {
            "type": "object",
            "required": ["type", "atomicity_unit", "test_executed", "test_evidence"],
            "properties": {
                "type": {"enum": ["git-revert", "kb-revert", "composite"]},
                "atomicity_unit": {"type": "string"},
                "test_executed": {"type": "boolean"},
                "test_evidence": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "input_origins": {
            "type": "array",
            "items": {
                "enum": [
                    "runtime-generated", "user-typed-here", "external-pasted",
                    "external-api", "message-channel", "cross-project-shared",
                ]
            },
            "minItems": 1,
        },
        "public_safe": {"enum": [False, "reviewed"]},
        "evaluation_plan": {"type": "object"},
        "related": {"type": "object"},
    },
    "additionalProperties": True,
}


def _fail(path: pathlib.Path, loc: str, message: str) -> None:
    raise ProposalError(f"{path}: schema error at {loc}: {message}")


def _require_mapping(path: pathlib.Path, data: dict[str, Any], key: str, loc: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        _fail(path, loc, f"{key} is required and must be an object")
    return value


def _require_string(path: pathlib.Path, data: dict[str, Any], key: str, loc: str, *, nonempty: bool = False) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        _fail(path, loc, f"{key} is required and must be a string")
    if nonempty and not value:
        _fail(path, loc, f"{key} must be non-empty")
    return value


def _require_int(path: pathlib.Path, data: dict[str, Any], key: str, loc: str, *, minimum: int, maximum: int | None = None) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, loc, f"{key} is required and must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" between {minimum} and {maximum}" if maximum is not None else f" >= {minimum}"
        _fail(path, loc, f"{key} must be{suffix}")
    return value


def _require_enum(path: pathlib.Path, value: Any, loc: str, allowed: set[Any]) -> None:
    if value not in allowed:
        allowed_s = ", ".join(repr(v) for v in sorted(allowed, key=repr))
        _fail(path, loc, f"value must be one of: {allowed_s}")


def _validate_proposal_data(path: pathlib.Path, data: dict[str, Any]) -> None:
    required = PROPOSAL_SCHEMA["required"]
    for key in required:
        if key not in data:
            _fail(path, key, f"{key} is a required property")

    proposal_id = _require_string(path, data, "proposal_id", "proposal_id")
    if not re.fullmatch(r"prop-[A-Za-z0-9_-]+-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}", proposal_id):
        _fail(path, "proposal_id", "proposal_id must match prop-<slug>-YYYY-MM-DD-NNN")

    if data.get("type") != "mutation-proposal":
        _fail(path, "type", "type must be 'mutation-proposal'")
    _require_enum(path, data.get("status"), "status", {"pending", "evaluating", "promoted", "rolled-back", "rejected"})

    created = _require_string(path, data, "created", "created")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", created):
        _fail(path, "created", "created must be UTC YYYY-MM-DDTHH:MM:SSZ")

    author = _require_mapping(path, data, "author", "author")
    _require_enum(path, author.get("type"), "author.type", {"orchestrator", "human"})
    _require_string(path, author, "identity", "author.identity", nonempty=True)

    _require_enum(path, data.get("surface_type"), "surface_type", {"prompt", "rule", "skill", "workflow", "kb-structure"})
    _require_string(path, data, "surface_target", "surface_target", nonempty=True)

    scope = _require_mapping(path, data, "scope", "scope")
    _require_string(path, scope, "affected_section", "scope.affected_section")
    _require_enum(path, scope.get("unit_of_mutation"), "scope.unit_of_mutation", {"section", "frontmatter-field", "markdown-block", "skill-dir", "workflow-config"})
    blast = _require_mapping(path, scope, "blast_radius", "scope.blast_radius")
    _require_int(path, blast, "files", "scope.blast_radius.files", minimum=0)
    _require_int(path, blast, "bytes", "scope.blast_radius.bytes", minimum=0)
    runtimes = blast.get("runtimes_affected")
    if not isinstance(runtimes, list) or any(not isinstance(item, str) for item in runtimes):
        _fail(path, "scope.blast_radius.runtimes_affected", "runtimes_affected must be an array of strings")

    _require_string(path, data, "mutation_diff", "mutation_diff")
    rationale = _require_mapping(path, data, "rationale", "rationale")
    for key in ("observation_signal", "hypothesis", "expected_metric"):
        _require_string(path, rationale, key, f"rationale.{key}")
    _require_enum(path, rationale.get("metric_objectivity"), "rationale.metric_objectivity", {"objective", "qualitative", "preference"})

    _require_int(path, data, "risk_tier", "risk_tier", minimum=0, maximum=4)
    _require_string(path, data, "risk_justification", "risk_justification")

    reversibility = _require_mapping(path, data, "reversibility", "reversibility")
    _require_enum(path, reversibility.get("type"), "reversibility.type", {"git-revert", "kb-revert", "composite"})
    _require_string(path, reversibility, "atomicity_unit", "reversibility.atomicity_unit")
    if not isinstance(reversibility.get("test_executed"), bool):
        _fail(path, "reversibility.test_executed", "test_executed must be boolean")
    _require_string(path, reversibility, "test_evidence", "reversibility.test_evidence")

    origins = data.get("input_origins")
    allowed_origins = {
        "runtime-generated", "user-typed-here", "external-pasted",
        "external-api", "message-channel", "cross-project-shared",
    }
    if not isinstance(origins, list) or not origins:
        _fail(path, "input_origins", "input_origins must be a non-empty array")
    for idx, origin in enumerate(origins):
        _require_enum(path, origin, f"input_origins.{idx}", allowed_origins)

    if data.get("public_safe") not in {False, "reviewed"}:
        _fail(path, "public_safe", "public_safe must be false or 'reviewed'")
    if not isinstance(data.get("evaluation_plan"), dict):
        _fail(path, "evaluation_plan", "evaluation_plan must be an object")
    if not isinstance(data.get("related"), dict):
        _fail(path, "related", "related must be an object")


def _extract_frontmatter(text: str, source: pathlib.Path) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ProposalError(f"{source}: missing YAML frontmatter")
    try:
        end = lines[1:].index("---") + 1
    except ValueError as exc:
        raise ProposalError(f"{source}: unterminated YAML frontmatter") from exc
    raw = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ProposalError(f"{source}: YAML parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise ProposalError(f"{source}: frontmatter must be a mapping")
    if isinstance(data.get("created"), dt.datetime):
        created = data["created"].astimezone(dt.timezone.utc).replace(tzinfo=None)
        data["created"] = created.strftime("%Y-%m-%dT%H:%M:%SZ")
    return data


def validate_proposal_file(path: pathlib.Path) -> dict[str, Any]:
    """Validate proposal frontmatter against the v0-minimal JSON Schema."""
    path = pathlib.Path(path)
    data = _extract_frontmatter(path.read_text(encoding="utf-8"), path)
    _validate_proposal_data(path, data)
    return data
