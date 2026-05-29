from __future__ import annotations

import pathlib
import datetime as dt
from typing import Any

import yaml
from jsonschema import Draft202012Validator

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
    validator = Draft202012Validator(PROPOSAL_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        err = errors[0]
        loc = ".".join(str(p) for p in err.path) or "<root>"
        raise ProposalError(f"{path}: schema error at {loc}: {err.message}")
    return data
