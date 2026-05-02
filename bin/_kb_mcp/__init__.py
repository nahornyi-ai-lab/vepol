"""_kb_mcp — Vepol's MCP host abstraction.

Single point of contact between Vepol modules and the configured MCP
host (Claude Code in v1; pluggable in future). All source-ingestion
modules go through `runner.McpHostRunner`.

See docs/methodology/mcp-first-sources.md for the principle.
"""
