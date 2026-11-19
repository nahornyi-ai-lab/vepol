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
OUT="$ROOT/new-wiki.out"
mkdir -p "$HUB/projects" "$PROJECT"
cp -R "$REPO_ROOT/_template" "$HUB/_template"
: > "$HUB/log.md"
cat > "$HUB/projects.md" <<'EOF'
# Projects

| project | path | description |
|---|---|---|
EOF

KNOWLEDGE_HUB="$HUB" "$REPO_ROOT/bin/new-wiki" "$PROJECT" synthetic lab "synthetic project" >"$OUT"

# The registry path cell new-wiki writes: ~-relative under $HOME, else absolute.
cell() {
  local p="$1"
  [[ "$p" == "$HOME"/* ]] && p="~${p#"$HOME"}"
  printf '%s' "$p"
}

fail() {
  echo "FAIL: $*" >&2
  echo "--- new-wiki output ---" >&2
  cat "$OUT" >&2
  exit 1
}

[[ -f "$PROJECT/AGENTS.md" ]] || fail "new project missing AGENTS.md"
grep -Fq "project — local wiki schema" "$PROJECT/AGENTS.md" || fail "AGENTS.md title not rendered with the project name"
! grep -Fq "{{PROJECT_NAME}}" "$PROJECT/AGENTS.md" || fail "AGENTS.md still has the {{PROJECT_NAME}} placeholder"
grep -Fq "~/knowledge/AGENTS.md" "$PROJECT/AGENTS.md" || fail "AGENTS.md does not point to the hub contract"
# Project CLAUDE.md adapter retired 2026-10-01: Claude Code reads AGENTS.md
# natively, so new-wiki creates none (the hub keeps ~/knowledge/CLAUDE.md).
[[ ! -e "$PROJECT/CLAUDE.md" ]] || fail "unexpected CLAUDE.md created (project adapter retired 2026-10-01)"
[[ -d "$PROJECT/knowledge" ]] || fail "new project missing knowledge/"
# Agent-card example must exist (agent-card-schema 2026-05-12 contract).
[[ -f "$PROJECT/knowledge/agents/_example.md" ]] || fail "new project missing knowledge/agents/_example.md"
# Antigravity CLI (`agy`) reads project AGENTS.md natively via `agy --add-dir`;
# project-level GEMINI.md adapter removed 2026-05-22 (Gemini CLI deprecation
# 2026-06-18). No GEMINI.md is created or expected at project root.
[[ ! -f "$PROJECT/GEMINI.md" ]] || fail "unexpected GEMINI.md created (removed 2026-05-22)"
[[ "$(readlink "$HUB/projects/synthetic")" == "$PROJECT/knowledge" ]] || fail "hub symlink projects/synthetic missing"

# ── Registry ────────────────────────────────────────────────────────────
# No registry.md yet (a fresh hub): nothing is created, the output says how.
[[ ! -e "$HUB/registry.md" ]] || fail "new-wiki created registry.md on its own"
grep -Fq "does not exist yet" "$OUT" || fail "no registry.md: output does not say how to register"
grep -Fq "| synthetic | seeded | \`$(cell "$PROJECT")\` | synthetic project |" "$OUT" || fail "no registry.md: output lacks the row to add"

# Hand-written registry (the layout kb-rebuild-registry bootstrap reads): the
# row lands in the table under the project's category heading, once. A pipe in
# the description becomes "/" (registry readers split rows on "|").
reg_project() {
  local dir="$ROOT/$1"
  mkdir -p "$dir"
  KNOWLEDGE_HUB="$HUB" "$REPO_ROOT/bin/new-wiki" "$dir" "$1" "$2" "${3:-}" >"$OUT"
}
cat > "$HUB/registry.md" <<'EOF'
# Project registry

## lab — <work>

| slug | status | path | description |
|---|---|---|---|
| alpha | live | `~/work/alpha` | first lab project |

## pet — PetProjects

| slug | status | path | description |
|---|---|---|---|
| zeta | seeded | `~/pet/zeta` | a pet project |

Notes below the tables stay where they are.
EOF
reg_project beta lab "beta | lab"
row="| beta | seeded | \`$(cell "$ROOT/beta")\` | beta / lab |"
grep -Fxq "$row" "$HUB/registry.md" || fail "hand-written registry: row not added (want: $row)"
after_alpha="$(grep -A1 -F '| alpha | live |' "$HUB/registry.md" | tail -1)"
[[ "$after_alpha" == "$row" ]] || fail "hand-written registry: row not placed in the lab table (got: $after_alpha)"
tail -1 "$HUB/registry.md" | grep -Fq "Notes below the tables" || fail "hand-written registry: text after the tables moved"
grep -Fq "registry.md += beta" "$OUT" || fail "hand-written registry: output does not report the new row"

# Re-running new-wiki on the same project adds no second row.
reg_project beta lab "beta | lab"
[[ "$(grep -c -F '| beta |' "$HUB/registry.md")" == 1 ]] || fail "re-run added a second registry row"
grep -Fq "already lists beta" "$OUT" || fail "re-run: output does not say the project is already listed"

# kb-rebuild-registry bootstrap reads the row: status, category and description.
KB_HUB="$HUB" python3 "$REPO_ROOT/bin/kb-rebuild-registry" bootstrap --out "$ROOT/migration.yaml" >/dev/null
python3 - "$ROOT/migration.yaml" <<'PY' || fail "kb-rebuild-registry bootstrap does not see the beta row"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
block = text.split("  - slug: beta\n", 1)[1].split("\n  - slug:", 1)[0]
for want in ("status: seeded", "category: lab", "description: beta / lab"):
    assert want in block, (want, block)
PY

# No heading for the category: the row goes into the last projects table, and a
# table with other columns (the demo's 5-column layout) gets matching cells.
cat > "$HUB/registry.md" <<'EOF'
# Registry

| slug | status | category | path | description |
|---|---|---|---|---|
| family | live | personal | `projects/family/` | Household |

---
Footer.
EOF
reg_project gamma order "gamma app"
grep -Fxq "| gamma | seeded | order | \`$(cell "$ROOT/gamma")\` | gamma app |" "$HUB/registry.md" || fail "5-column registry: row not added with matching columns"
[[ "$(sed -n 6p "$HUB/registry.md")" == "| gamma | seeded | order | \`$(cell "$ROOT/gamma")\` | gamma app |" ]] || fail "5-column registry: row not placed right after the table"

# A registry generated by kb-rebuild-registry is left untouched (editing its
# blocks would make `kb-rebuild-registry check` fail the orchestrator cycle).
cat > "$HUB/registry.md" <<'EOF'
# Project registry

<!-- DERIVED-BEGIN -->
| slug | status | category | parent | path | description |
|---|---|---|---|---|---|
| alpha | live | lab | hub | `~/work/alpha` | first lab project |
<!-- DERIVED-END -->

<!-- HUB-MANAGED-BEGIN -->
<!-- HUB-MANAGED-END -->
EOF
cp "$HUB/registry.md" "$ROOT/registry.before"
reg_project delta pet
cmp -s "$HUB/registry.md" "$ROOT/registry.before" || fail "generated registry was modified"
grep -Fq "kb-rebuild-registry apply" "$OUT" || fail "generated registry: output does not say how to register"
# This hub has no migration table: new-wiki says so instead of sending the
# user to append to a file that does not exist (apply would then regenerate
# the registry without the other projects).
grep -Fq "$HUB/migration-2026-04-25.yaml is missing" "$OUT" || fail "generated registry, no table: output does not say the table is missing"
! grep -Fq "Append these lines" "$OUT" || fail "generated registry, no table: output says to append to a missing table"
[[ ! -e "$HUB/migration-2026-04-25.yaml" ]] || fail "new-wiki created a migration table"
# ... even when the project is already listed in it (its rows change through
# the migration table, never by hand).
reg_project alpha lab
cmp -s "$HUB/registry.md" "$ROOT/registry.before" || fail "generated registry listing the slug was modified"
! grep -Fq "set the status to live" "$OUT" || fail "generated registry: output says to edit a generated row"

# ── A project that already has its own AGENTS.md ────────────────────────
# Its text stays as it is; one marked Vepol block with the startup-context
# line (worded as in _template/AGENTS.md) is appended, and never a second one.
STARTUP='~/knowledge/bin/kb-session-start --print --cwd "$PWD"'
grep -Fq "\`$STARTUP\`" "$REPO_ROOT/_template/AGENTS.md" || fail "template no longer words the startup line as the block does"
OWN="$ROOT/own-agents"
mkdir -p "$OWN"
printf '# Team rules\nUse pnpm.' > "$OWN/AGENTS.md"   # no trailing newline
KNOWLEDGE_HUB="$HUB" "$REPO_ROOT/bin/new-wiki" "$OWN" own-agents >"$OUT"
[[ "$(head -2 "$OWN/AGENTS.md")" == $'# Team rules\nUse pnpm.' ]] || fail "own AGENTS.md: the user's text changed"
grep -Fxq '<!-- BEGIN VEPOL — added by new-wiki; edit the text freely, keep these markers -->' "$OWN/AGENTS.md" \
  || fail "own AGENTS.md: no Vepol begin marker"
grep -Fxq '<!-- END VEPOL -->' "$OWN/AGENTS.md" || fail "own AGENTS.md: no Vepol end marker"
grep -Fq "\`$STARTUP\`" "$OWN/AGENTS.md" || fail "own AGENTS.md: no startup-context line"
grep -Fq '`knowledge/`' "$OWN/AGENTS.md" || fail "own AGENTS.md: no pointer to knowledge/"
grep -Fq "Vepol block appended" "$OUT" || fail "own AGENTS.md: output does not say what was done"
! grep -Fq "fill in the project description and categories" "$OUT" || fail "own AGENTS.md: step 1 points at template sections"
cp "$OWN/AGENTS.md" "$ROOT/own-agents.after-first"
KNOWLEDGE_HUB="$HUB" "$REPO_ROOT/bin/new-wiki" "$OWN" own-agents >"$OUT"
cmp -s "$OWN/AGENTS.md" "$ROOT/own-agents.after-first" || fail "own AGENTS.md: re-run changed it (block added twice?)"
grep -Fq "already loads Vepol's startup context" "$OUT" || fail "own AGENTS.md re-run: output does not say it was left as is"
# An AGENTS.md new-wiki rendered already carries the line: no block.
! grep -Fq "BEGIN VEPOL" "$PROJECT/AGENTS.md" || fail "rendered AGENTS.md got a Vepol block"
grep -Fq "$STARTUP" "$PROJECT/AGENTS.md" || fail "rendered AGENTS.md has no startup-context line"
# A linked AGENTS.md is not written through; step 1 gives the line to add.
LINKED="$ROOT/linked-agents"
mkdir -p "$LINKED"
printf '# Shared rules\n' > "$ROOT/shared-rules.md"
ln -s "$ROOT/shared-rules.md" "$LINKED/AGENTS.md"
KNOWLEDGE_HUB="$HUB" "$REPO_ROOT/bin/new-wiki" "$LINKED" linked-agents >"$OUT"
[[ "$(cat "$ROOT/shared-rules.md")" == "# Shared rules" ]] || fail "linked AGENTS.md: the link target was changed"
grep -Fq "not changed" "$OUT" && grep -Fq "$STARTUP" "$OUT" || fail "linked AGENTS.md: output does not give the line to add"

# ── .gitignore ──────────────────────────────────────────────────────────
# Outside git the exact lines are what counts: added once, never twice.
gi_count() { grep -c -Fx -- "$2" "$1/.gitignore" || true; }
[[ "$(gi_count "$OWN" "knowledge/")" == 1 && "$(gi_count "$OWN" ".kb-ignore")" == 1 ]] \
  || fail ".gitignore outside git: want one knowledge/ and one .kb-ignore line after two runs"
# In a git repo, git's own rules decide. Only the repo's rules are read here:
# no global or system excludes from the machine that runs the test.
nw_git() {
  env -u XDG_CONFIG_HOME HOME="$ROOT/git-home" GIT_CONFIG_NOSYSTEM=1 KNOWLEDGE_HUB="$HUB" \
    "$REPO_ROOT/bin/new-wiki" "$@" >"$OUT"
}
mkdir -p "$ROOT/git-home"
# A repo that ignores the wiki another way (as the Vepol repo does) keeps its
# tracked .gitignore byte for byte.
GIT_OWN="$ROOT/git-own-rules"
mkdir -p "$GIT_OWN"
git -C "$GIT_OWN" init --quiet 2>/dev/null
printf 'knowledge/*\n!knowledge/AGENTS.md\n.kb-ignore\n' > "$GIT_OWN/.gitignore"
cp "$GIT_OWN/.gitignore" "$ROOT/gitignore.before"
nw_git "$GIT_OWN" git-own-rules
cmp -s "$GIT_OWN/.gitignore" "$ROOT/gitignore.before" \
  || fail ".gitignore: a repo that already ignores knowledge/ another way got a redundant line ($(tr '\n' ' ' < "$GIT_OWN/.gitignore"))"
! grep -Fq ".gitignore +=" "$OUT" || fail ".gitignore: output reports a line that was not needed"
# A repo that does not ignore the wiki gets both lines, once.
GIT_PLAIN="$ROOT/git-plain"
mkdir -p "$GIT_PLAIN"
git -C "$GIT_PLAIN" init --quiet 2>/dev/null
printf 'node_modules/\n' > "$GIT_PLAIN/.gitignore"
nw_git "$GIT_PLAIN" git-plain
nw_git "$GIT_PLAIN" git-plain
[[ "$(gi_count "$GIT_PLAIN" "knowledge/")" == 1 && "$(gi_count "$GIT_PLAIN" ".kb-ignore")" == 1 ]] \
  || fail ".gitignore in a git repo without the rules: want one knowledge/ and one .kb-ignore line"
[[ "$(head -1 "$GIT_PLAIN/.gitignore")" == "node_modules/" ]] || fail ".gitignore: the repo's own lines changed"

# ── Registry flow: new-wiki → bootstrap → apply → check ─────────────────
# The English headings install.sh writes; a project added without a
# description (the template README has `description: ""`, and Desktop
# «Add project…» passes none) must not crash apply.
H2="$ROOT/hub2"
mkdir -p "$H2/projects"
cp -R "$REPO_ROOT/_template" "$H2/_template"
: > "$H2/log.md"
{
  printf '# Project registry\n'
  for sec in "## lab — research and experiments" "## order — client work" "## pet — side projects" \
             "## job — employment" "## personal / other"; do
    printf '\n%s\n\n| slug | status | path | description |\n|---|---|---|---|\n' "$sec"
  done
} > "$H2/registry.md"
nw2() { local dir="$ROOT/$1"; shift; mkdir -p "$dir"; KNOWLEDGE_HUB="$H2" "$REPO_ROOT/bin/new-wiki" "$dir" "$@" >"$OUT"; }
rr() { KB_HUB="$H2" python3 "$REPO_ROOT/bin/kb-rebuild-registry" "$@"; }
MIG="$H2/migration-2026-04-25.yaml"
nw2 p-lab p-lab lab "Lab project"
nw2 p-order p-order order "Client work"
nw2 p-nodesc                               # no slug, category or description
rr bootstrap >/dev/null || fail "bootstrap on the English registry failed"
python3 - "$MIG" <<'PY' || fail "bootstrap: the new English headings are not read"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
for slug, cat in (("p-lab", "lab"), ("p-order", "order"), ("p-nodesc", "personal")):
    block = text.split(f"  - slug: {slug}\n", 1)[1].split("\n  - slug:", 1)[0]
    assert f"category: {cat}" in block, (slug, block)
PY
rr apply >"$ROOT/apply.out" 2>&1 || { cat "$ROOT/apply.out" >&2; fail "apply crashed for a project without a description"; }
rr check >/dev/null || fail "check not clean after apply"
grep -Fxq 'description: ""' "$ROOT/p-nodesc/knowledge/README.md" || fail "apply dropped the README's own description line"
! grep -Fq "<work>" "$H2/registry.md" || fail "generated English registry still has the <work> placeholder"
# A registry generated before the English header changed is not drift.
python3 - "$H2/registry.md" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
new = ("**Categories:** `lab` (research and experiments), `order` (client work), `pet` (side projects),\n"
       "`job` (employment), `personal` (everything else).")
old = ("**Categories:** `lab` (<work>), `order` (client orders), `pet` (personal experiments),\n"
       "`job` (employment), `personal` (personal projects).")
assert new in text, "new categories line missing"
open(path, "w", encoding="utf-8").write(text.replace(new, old, 1))
PY
rr check >/dev/null || fail "check reports drift for a registry with the older English header"
rr apply >/dev/null && rr check >/dev/null || fail "apply/check after the older header"

# bootstrap never overwrites an existing migration table without --force.
cp "$MIG" "$ROOT/mig.before"
if rr bootstrap >"$ROOT/boot.out" 2>&1; then fail "bootstrap overwrote an existing migration table"; fi
cmp -s "$MIG" "$ROOT/mig.before" || fail "refused bootstrap still changed the migration table"
grep -Fq -- "--force" "$ROOT/boot.out" || fail "refused bootstrap does not name --force"

# A new project on the generated hub: new-wiki prints the table entry; appended
# as printed, apply registers it and every other entry keeps its values.
cp "$H2/registry.md" "$ROOT/reg2.before"
nw2 p-new p-new pet 'New "pet" | project'
cmp -s "$H2/registry.md" "$ROOT/reg2.before" || fail "new-wiki edited the generated registry"
grep -Fq "not bootstrap" "$OUT" || fail "generated registry: output does not warn off bootstrap"
sed -n '/^  - slug: p-new$/,/^     then run/p' "$OUT" | grep -v '^     then run' > "$ROOT/entry.yaml"
grep -Fq "category: \"pet\"" "$ROOT/entry.yaml" || fail "printed entry lacks the category ($(cat "$ROOT/entry.yaml"))"
cat "$ROOT/entry.yaml" >> "$MIG"
rr apply >/dev/null || fail "apply with the printed entry failed"
rr check >/dev/null || fail "check not clean after adding the printed entry"
grep -Fq '| p-new | seeded | pet | hub |' "$H2/registry.md" || fail "p-new not in the generated registry"
grep -A6 '^  - slug: p-lab$' "$MIG" | grep -Fq 'category: lab' || fail "p-lab lost its category"
grep -Fq 'description: "New \"pet\" / project"' "$ROOT/p-new/knowledge/README.md" \
  || fail "p-new description not applied ($(grep description "$ROOT/p-new/knowledge/README.md"))"
nw2 p-new p-new pet
grep -Fq "already lists p-new" "$OUT" || fail "re-run: output does not say the table already lists the project"

# --force rebuilds the table and keeps the old one as a .bak copy.
cp "$MIG" "$ROOT/mig.before-force"
rr bootstrap --force >/dev/null || fail "bootstrap --force failed"
bak="$(ls "$H2"/migration-2026-04-25.yaml.bak-* 2>/dev/null | head -1)"
[[ -n "$bak" ]] && cmp -s "$bak" "$ROOT/mig.before-force" || fail "bootstrap --force kept no copy of the old table"

echo "agent-entrypoint synthetic OK"
