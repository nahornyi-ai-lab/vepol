"""Markdown report, JSON document, and the pinned-schema validator.

The validator is a small structural checker (type / required / properties /
additionalProperties / enum / const / items / local $ref) — the hub interpreter
ships no `jsonschema`, and the schema uses only these keywords. `--json`
validates its own output before printing, so a drift between code and schema
is a crash, not a silent emit.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, List

from .derive import humanize_age

SCHEMA_PATH = pathlib.Path(__file__).with_name("schema.json")

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _resolve_ref(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate(doc: Any, schema: dict) -> List[str]:
    """Return a list of violations (empty == valid)."""
    errors: List[str] = []
    _check(doc, schema, schema, "$", errors)
    return errors


def _check(value: Any, node: dict, root: dict, path: str, errors: List[str]) -> None:
    if "$ref" in node:
        node = _resolve_ref(node["$ref"], root)
    if "const" in node and value != node["const"]:
        errors.append(f"{path}: expected const {node['const']!r}, got {value!r}")
        return
    if "enum" in node and value not in node["enum"]:
        errors.append(f"{path}: {value!r} not in enum {node['enum']}")
        return
    if "type" in node:
        types = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(_TYPE_CHECKS[t](value) for t in types):
            errors.append(f"{path}: expected type {types}, got {type(value).__name__}")
            return
    if isinstance(value, dict):
        props = node.get("properties", {})
        for key in node.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key {key!r}")
        if node.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected key {key!r}")
        for key, sub in props.items():
            if key in value:
                _check(value[key], sub, root, f"{path}.{key}", errors)
    if isinstance(value, list) and "items" in node:
        for idx, item in enumerate(value):
            _check(item, node["items"], root, f"{path}[{idx}]", errors)


def render_markdown(doc: dict, cache_path: str, broker_state_path: str, probe_count: int) -> str:
    cols = ["runtime", "installed", "authenticated", "quota_available", "healthy",
            "resumable", "interactive", "web_current", "edit_capable", "available", "observed", "evidence"]
    lines = [f"# Runtime registry — {doc['generated_at']}", ""]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for row in doc["runtimes"]:
        prov = row["provenance"]
        observed = "never"
        if prov["observed_at"]:
            observed = f"{humanize_age(prov['age_seconds'])} ago ({prov['source']})"
        elif prov["source"] == "broker-state-only":
            observed = "never (broker-state-only)"
        evidence = prov["evidence"] or "; ".join(row["reasons"]) or "—"
        evidence = evidence.replace("|", "\\|")
        cells = [row["name"]] + [row[c] for c in cols[1:9]] + [
            "yes" if row["available"] else "no", observed, evidence]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(f"Cache: {cache_path} (probe records: {probe_count}, cache-not-truth). "
                 f"Broker state: {broker_state_path} (read-only).")
    if doc["nested"]["detected"]:
        lines.append(f"Nesting: detected ({', '.join(doc['nested']['markers'])}) — probes refused, nothing recorded.")
    else:
        lines.append("Nesting: none detected.")
    if doc["probe"]["requested"]:
        summary = ", ".join(f"{r['runtime']}={r['outcome']}" for r in doc["probe"]["results"])
        lines.append(f"Probe: {summary or 'none run'}.")
    return "\n".join(lines) + "\n"
