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
[[ -f "$PROJECT/GEMINI.md" ]] || fail "new project missing GEMINI.md"
[[ -d "$PROJECT/knowledge" ]] || fail "new project missing knowledge/"

grep -Fq "AGENTS.md" "$PROJECT/CLAUDE.md" || fail "CLAUDE.md does not reference AGENTS.md"
grep -Fq "@./AGENTS.md" "$PROJECT/GEMINI.md" || fail "GEMINI.md does not import @./AGENTS.md"

non_empty_claude=$(grep -v '^[[:space:]]*$' "$PROJECT/CLAUDE.md" | wc -l | tr -d ' ')
non_empty_gemini=$(grep -v '^[[:space:]]*$' "$PROJECT/GEMINI.md" | wc -l | tr -d ' ')
[[ "$non_empty_claude" -le 30 ]] || fail "CLAUDE.md adapter too long: $non_empty_claude non-empty lines"
[[ "$non_empty_gemini" -le 30 ]] || fail "GEMINI.md adapter too long: $non_empty_gemini non-empty lines"

echo "agent-entrypoint synthetic OK"
