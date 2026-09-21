"""kb-runtime-registry — which agent CLIs can actually do work right now.

Spec: decision page "Runtime capability registry" (2026-08-15) in the project knowledge base
(contract sha256 3f323b89…). Every field is tri-state (yes/no/unknown); a
runtime becomes available only on a successful observation.
"""

SCHEMA_VERSION = "kb-runtime-registry/v1"
CACHE_SCHEMA = "kb-runtime-registry-cache/v1"
TRISTATE = ("yes", "no", "unknown")
