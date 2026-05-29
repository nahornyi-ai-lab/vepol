#!/usr/bin/env bash
# Synthetic acceptance fixture for universal agent entrypoint rollout.
set -euo pipefail

ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "$ROOT"
}
trap cleanup EXIT

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HUB="$ROOT/hub"
PROJECT="$ROOT/project"
mkdir -p "$HUB/projects" "$PROJECT"
cp -R "$REPO_ROOT/_template" "$HUB/_template"
: > "$HUB/log.md"
cat > "$HUB/projects.md" <<'EOF'
# Projects

| проект | путь | описание |
|---|---|---|
EOF

KNOWLEDGE_HUB="$HUB" "$REPO_ROOT/bin/new-wiki" "$PROJECT" synthetic lab "synthetic project" >/tmp/agent-entrypoint-new-wiki.out

fail() {
  echo "FAIL: $*" >&2
  echo "--- new-wiki output ---" >&2
  cat /tmp/agent-entrypoint-new-wiki.out >&2
  exit 1
}

[[ -f "$PROJECT/AGENTS.md" ]] || fail "new project missing AGENTS.md"
[[ -f "$PROJECT/CLAUDE.md" ]] || fail "new project missing CLAUDE.md"
[[ -d "$PROJECT/knowledge" ]] || fail "new project missing knowledge/"
# Agent-card example must exist (agent-card-schema 2026-05-12 contract).
[[ -f "$PROJECT/knowledge/agents/_example.md" ]] || fail "new project missing knowledge/agents/_example.md"
# Antigravity CLI (`agy`) reads project AGENTS.md natively via `agy --add-dir`;
# project-level GEMINI.md adapter removed 2026-05-22 (Gemini CLI deprecation
# 2026-06-18). No GEMINI.md is created or expected at project root.
[[ ! -f "$PROJECT/GEMINI.md" ]] || fail "unexpected GEMINI.md created (removed 2026-05-22)"

grep -Fq "AGENTS.md" "$PROJECT/CLAUDE.md" || fail "CLAUDE.md does not reference AGENTS.md"

non_empty_claude=$(grep -v '^[[:space:]]*$' "$PROJECT/CLAUDE.md" | wc -l | tr -d ' ')
[[ "$non_empty_claude" -le 30 ]] || fail "CLAUDE.md adapter too long: $non_empty_claude non-empty lines"

echo "agent-entrypoint synthetic OK"
