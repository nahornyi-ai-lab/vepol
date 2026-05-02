#!/usr/bin/env bash
# install.sh — bootstrap Vepol on a fresh macOS machine.
#
# Idempotent: safe to re-run. Asks before doing anything invasive.
# Detect-only for prerequisites: never auto-installs system package managers.
#
# Layout after install:
#   ~/vepol/                                  — this repo (cloned by user)
#   ~/knowledge/                              — user's KB hub (created here)
#   ~/.claude/CLAUDE.md                       — global methodology (include-pattern)
#   ~/.claude/.vepol/CLAUDE.managed.md        — managed copy (overwritten on upgrade)
#   ~/.claude/skills/init-kb/                 — first-project skill
#   ~/Library/LaunchAgents/com.knowledge.*    — opt-in scheduled tasks
#
# Spec: README.md in this repo.
# Project: https://github.com/nahornyi-ai-lab/vepol

set -euo pipefail

VEPOL_DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${HOME}"
HUB="${VEPOL_HUB:-$HOME_DIR/knowledge}"
LOG="${VEPOL_DIR}/install.log"

VEPOL_VERSION="$(cat "$VEPOL_DIR/VERSION" 2>/dev/null || echo 'unknown')"

# ─────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────
if [[ -t 1 ]]; then
  C_OK=$'\033[1;32m'
  C_INFO=$'\033[1;36m'
  C_WARN=$'\033[1;33m'
  C_ERR=$'\033[1;31m'
  C_DIM=$'\033[2m'
  C_OFF=$'\033[0m'
else
  C_OK=''; C_INFO=''; C_WARN=''; C_ERR=''; C_DIM=''; C_OFF=''
fi

# Truncate log on each fresh run (keep last run only)
: > "$LOG"

say()  { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$1" | tee -a "$LOG"; }
ok()   { printf '%s ✓%s  %s\n'  "$C_OK"   "$C_OFF" "$1" | tee -a "$LOG"; }
warn() { printf '%s !%s  %s\n'  "$C_WARN" "$C_OFF" "$1" | tee -a "$LOG" >&2; }
die()  { printf '%s ✘%s  %s\n'  "$C_ERR"  "$C_OFF" "$1" >&2; exit 1; }

ask() {
  # ask <prompt> — returns 0 if user answers y/Y, 1 otherwise.
  # Defaults to N (safer). VEPOL_NONINTERACTIVE=1 forces all answers to N.
  if [[ "${VEPOL_NONINTERACTIVE:-0}" == "1" ]]; then
    return 1
  fi
  local prompt="$1" answer
  printf '%s ?%s  %s [y/N] ' "$C_INFO" "$C_OFF" "$prompt"
  read -r answer
  [[ "$answer" =~ ^[Yy]$ ]]
}

# ─────────────────────────────────────────
# Header
# ─────────────────────────────────────────
cat <<HEADER
${C_INFO}┌──────────────────────────────────────────┐
│  Vepol installer · v${VEPOL_VERSION}
│  Many agents, one field.
└──────────────────────────────────────────┘${C_OFF}

  VEPOL_DIR: $VEPOL_DIR
  HOME_DIR:  $HOME_DIR
  HUB:       $HUB
  Started:   $(date -Iseconds 2>/dev/null || date)

HEADER

say "Vepol install started — log: $LOG"

# ─────────────────────────────────────────
# Step 1. Preconditions (detect-only)
# ─────────────────────────────────────────
say "Step 1 · Checking prerequisites (detect-only — no auto-install)"

# Platform
if [[ "$(uname)" != "Darwin" ]]; then
  die "Vepol v0.1 supports macOS only. Linux support is on the roadmap."
fi
OS_VER="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
ok "  macOS $OS_VER detected"

# Required tools
MISSING=()
for cmd in git claude node bun rg; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    MISSING+=("$cmd")
  fi
done

# bash 5+ (macOS ships 3.2 by default)
USER_BASH_MAJ=0
if [[ -x /opt/homebrew/bin/bash ]]; then
  USER_BASH_MAJ=$(/opt/homebrew/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 0)
elif [[ -x /usr/local/bin/bash ]]; then
  USER_BASH_MAJ=$(/usr/local/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 0)
fi
if [[ "$USER_BASH_MAJ" -lt 5 ]]; then
  MISSING+=("bash-5+")
fi

# Node 18+
NODE_OK=1
if command -v node >/dev/null 2>&1; then
  NODE_MAJ=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
  if [[ -n "${NODE_MAJ:-}" && "$NODE_MAJ" -lt 18 ]]; then
    warn "  node version is $NODE_MAJ — Vepol needs 18 or higher"
    NODE_OK=0
  fi
fi

# Optional tools
OPTIONAL_MISSING=()
for cmd in codex uv jq gh; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    OPTIONAL_MISSING+=("$cmd")
  fi
done

# Block install if required missing
if [[ ${#MISSING[@]} -gt 0 || "$NODE_OK" -eq 0 ]]; then
  echo
  warn "Required tools missing or out of date: ${MISSING[*]:-} ${NODE_OK:+}"
  cat <<HELP

${C_INFO}Install commands:${C_OFF}

  ${C_DIM}# If Homebrew is not installed yet:${C_OFF}
  /bin/bash -c "\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  ${C_DIM}# Required tools (via Homebrew):${C_OFF}
  brew install bash node bun ripgrep git

  ${C_DIM}# Claude CLI:${C_OFF}
  Download from https://claude.ai/download

After installing, re-run: ./install.sh

(${C_DIM}Vepol intentionally does not auto-install Homebrew or any system package
manager — that decision should be yours.${C_OFF})
HELP
  die "Required tools missing — please install then re-run."
fi

# Optional warnings
if [[ ${#OPTIONAL_MISSING[@]} -gt 0 ]]; then
  warn "  Optional tools missing: ${OPTIONAL_MISSING[*]}"
  warn "    These enable extras (cross-agent review, session auto-capture, etc.)"
  warn "    Install: brew install ${OPTIONAL_MISSING[*]}"
fi

# Python 3.10+ for People module + future Python-side tooling
if command -v python3 >/dev/null 2>&1; then
  PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)' 2>/dev/null || echo 0)
  if [[ "$PY_OK" != "1" ]]; then
    warn "  python3 < 3.10 detected — Vepol People module requires 3.10+"
  fi
else
  warn "  python3 not found — Vepol People module needs it"
fi

# Python deps — checked, NOT installed (per detect-only policy)
if [[ -f "$VEPOL_DIR/requirements.txt" ]]; then
  MISSING_PY=()
  python3 -c "import frontmatter" 2>/dev/null || MISSING_PY+=(python-frontmatter)
  python3 -c "import click" 2>/dev/null || MISSING_PY+=(click)
  if [[ ${#MISSING_PY[@]} -gt 0 ]]; then
    warn "  Python deps missing: ${MISSING_PY[*]}"
    warn "    Install with: pip3 install -r \"$VEPOL_DIR/requirements.txt\""
    warn "    (Or in a venv — see requirements.txt for the full list)"
  fi
fi

ok "  All required prerequisites present"

# ─────────────────────────────────────────
# Step 2. Hub scaffolding
# ─────────────────────────────────────────
say "Step 2 · Setting up knowledge hub at $HUB"

if [[ ! -d "$HUB" ]]; then
  mkdir -p "$HUB"/{bin,raw,concepts,people,companies,solutions,projects,personal,daily,sources}
  ok "  created $HUB"
else
  ok "  $HUB already exists — preserving"
fi

mkdir -p "$HUB/_template/knowledge"

# Symlink bin scripts (overwrite — these are managed by repo)
for script in "$VEPOL_DIR"/bin/kb-* "$VEPOL_DIR"/bin/new-wiki; do
  [[ -f "$script" ]] || continue
  scriptname="$(basename "$script")"
  ln -sf "$script" "$HUB/bin/$scriptname"
done
# Internal Python packages — symlink directories
if [[ -d "$VEPOL_DIR/bin/_kb_backlog" ]]; then
  ln -sfn "$VEPOL_DIR/bin/_kb_backlog" "$HUB/bin/_kb_backlog"
fi
if [[ -d "$VEPOL_DIR/bin/_kb_people" ]]; then
  ln -sfn "$VEPOL_DIR/bin/_kb_people" "$HUB/bin/_kb_people"
fi
# Prompt templates
if [[ -d "$VEPOL_DIR/bin/templates" ]]; then
  ln -sfn "$VEPOL_DIR/bin/templates" "$HUB/bin/templates"
fi
ok "  bin/ symlinks point at $VEPOL_DIR/bin/"

# Templates (always overwrite — schema is canonical)
cp "$VEPOL_DIR/_template/CLAUDE.md" "$HUB/_template/CLAUDE.md"
cp -R "$VEPOL_DIR/_template/knowledge/." "$HUB/_template/knowledge/"
ok "  _template/ refreshed"

# Hub-level master schema CLAUDE.md
if [[ ! -f "$HUB/CLAUDE.md" ]]; then
  cp "$VEPOL_DIR/knowledge/CLAUDE.md" "$HUB/CLAUDE.md"
  ok "  $HUB/CLAUDE.md installed (master schema)"
else
  warn "  $HUB/CLAUDE.md already exists — not overwritten"
  warn "    Compare with $VEPOL_DIR/knowledge/CLAUDE.md if you want updates"
fi

# Hub-level triad / state files — only if missing
for f in registry.md log.md state.md index.md backlog.md escalations.md incidents.md strategies.md; do
  if [[ ! -f "$HUB/$f" ]]; then
    src="$VEPOL_DIR/_template/knowledge/$f"
    if [[ -f "$src" ]]; then
      cp "$src" "$HUB/$f"
      ok "    $HUB/$f created from template"
    fi
  fi
done

# Personal overlay (user-owned)
mkdir -p "$HUB/personal/daily-inbox"
if [[ ! -f "$HUB/personal/.secrets" ]]; then
  cat > "$HUB/personal/.secrets" <<'SECEOF'
# Vepol secrets file. Mode 600 enforced.
# Empty values are safe — Vepol simply skips features that need them.

# Telegram channel (opt-in feature):
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Personalization (used by kb-brief / kb-retro prompts):
USER_NAME=
USER_CITY=

# Fallback geolocation (used by kb-planner if system location unavailable):
KB_FALLBACK_LAT=
KB_FALLBACK_LON=
KB_FALLBACK_TZ=
SECEOF
  chmod 600 "$HUB/personal/.secrets"
  ok "  $HUB/personal/.secrets created (mode 600)"
fi

# ─────────────────────────────────────────
# Step 3. Global ~/.claude/CLAUDE.md (include-pattern)
# ─────────────────────────────────────────
# Vepol installs its global methodology as a separate "managed" file in
# ~/.claude/.vepol/CLAUDE.managed.md and adds an include reference to
# ~/.claude/CLAUDE.md. Result: user content in ~/.claude/CLAUDE.md is
# preserved verbatim across upgrades — only the managed file gets
# overwritten.
say "Step 3 · Installing global methodology (~/.claude/CLAUDE.md)"

mkdir -p "$HOME_DIR/.claude/.vepol"

# Always overwrite the managed copy (owned by repo)
cp "$VEPOL_DIR/claude/CLAUDE.md" "$HOME_DIR/.claude/.vepol/CLAUDE.managed.md"
ok "  managed copy: $HOME_DIR/.claude/.vepol/CLAUDE.managed.md"

INCLUDE_BEGIN="<!-- BEGIN VEPOL MANAGED — do not edit. Source: ~/.claude/.vepol/CLAUDE.managed.md -->"
INCLUDE_END="<!-- END VEPOL MANAGED -->"
INCLUDE_INNER="<!-- @include ~/.claude/.vepol/CLAUDE.managed.md -->"

if [[ ! -f "$HOME_DIR/.claude/CLAUDE.md" ]]; then
  cat > "$HOME_DIR/.claude/CLAUDE.md" <<MDEOF
$INCLUDE_BEGIN
$INCLUDE_INNER
$INCLUDE_END

## My personal additions

(Add your own preferences and notes below. They will not be touched by
 Vepol upgrades — only the managed block above is overwritten.)
MDEOF
  ok "  $HOME_DIR/.claude/CLAUDE.md created with include block"
elif grep -qF "BEGIN VEPOL MANAGED" "$HOME_DIR/.claude/CLAUDE.md"; then
  ok "  $HOME_DIR/.claude/CLAUDE.md already has Vepol include block — left alone"
else
  TMPFILE="$(mktemp)"
  cat > "$TMPFILE" <<MDEOF
$INCLUDE_BEGIN
$INCLUDE_INNER
$INCLUDE_END

MDEOF
  cat "$HOME_DIR/.claude/CLAUDE.md" >> "$TMPFILE"
  mv "$TMPFILE" "$HOME_DIR/.claude/CLAUDE.md"
  ok "  prepended Vepol include block to existing $HOME_DIR/.claude/CLAUDE.md"
fi

# Statusline script (optional)
if [[ -f "$VEPOL_DIR/claude/statusline-command.sh" && ! -f "$HOME_DIR/.claude/statusline-command.sh" ]]; then
  cp "$VEPOL_DIR/claude/statusline-command.sh" "$HOME_DIR/.claude/statusline-command.sh"
  chmod +x "$HOME_DIR/.claude/statusline-command.sh"
  ok "  statusline script installed"
fi

# Settings template (only if user has none)
if [[ -f "$VEPOL_DIR/claude/settings.json.template" && ! -f "$HOME_DIR/.claude/settings.json" ]]; then
  sed "s|__HOME__|$HOME_DIR|g" "$VEPOL_DIR/claude/settings.json.template" > "$HOME_DIR/.claude/settings.json"
  ok "  $HOME_DIR/.claude/settings.json created from template"
fi

# ─────────────────────────────────────────
# Step 4. init-kb skill
# ─────────────────────────────────────────
say "Step 4 · Installing init-kb skill"
mkdir -p "$HOME_DIR/.claude/skills/init-kb"
cp "$VEPOL_DIR/claude/skills/init-kb/SKILL.md" "$HOME_DIR/.claude/skills/init-kb/SKILL.md"
ok "  init-kb skill ready (use: /init-kb in any project to bootstrap a wiki)"

# ─────────────────────────────────────────
# Step 5. Optional · LaunchAgents (opt-in)
# ─────────────────────────────────────────
say "Step 5 · Optional features (opt-in)"
echo "  Vepol can run scheduled background tasks via macOS LaunchAgents:"
echo "    • daily morning brief (sunrise+45min)"
echo "    • orchestrator tick (every 15 min, light pulse)"
echo "    • cycle launch (twice a day — brief + retro)"
echo "    • People follow-up reminders (daily at 9:00)"

if ask "Install scheduled tasks?"; then
  LA_DIR="$HOME_DIR/Library/LaunchAgents"
  mkdir -p "$LA_DIR"
  for name in com.knowledge.tick com.knowledge.planner com.knowledge.orchestrator-cycle com.knowledge.people-remind; do
    DEST="$LA_DIR/$name.plist"
    SRC="$VEPOL_DIR/launchd/$name.plist.template"
    if [[ ! -f "$SRC" ]]; then
      warn "    template missing: $SRC — skipping $name"
      continue
    fi
    if [[ -f "$DEST" ]]; then
      ok "    $name already installed — keeping existing"
      continue
    fi
    sed "s|__HOME__|$HOME_DIR|g" "$SRC" > "$DEST"
    if launchctl bootstrap "gui/$(id -u)" "$DEST" 2>/dev/null \
       || launchctl load "$DEST" 2>/dev/null; then
      ok "    loaded $name"
    else
      warn "    failed to auto-load $name — load manually: launchctl load $DEST"
    fi
  done
else
  ok "  Skipped scheduled tasks (re-run install.sh anytime to enable)"
fi

# ─────────────────────────────────────────
# Step 6. Optional · Telegram channel
# ─────────────────────────────────────────
echo
echo "  Vepol can send daily briefs and accept commands via a Telegram bot."
echo "  Setup: create bot via @BotFather, paste token into a config file."

if ask "Set up Telegram channel scaffold (you can fill the token later)?"; then
  TG_DIR="$HOME_DIR/.claude/channels/telegram"
  mkdir -p "$TG_DIR/approved"
  if [[ ! -f "$TG_DIR/.env" ]]; then
    cat > "$TG_DIR/.env" <<'TGEOF'
TELEGRAM_BOT_TOKEN=
TGEOF
    chmod 600 "$TG_DIR/.env"
    ok "  $TG_DIR/.env created — paste your bot token from @BotFather"
  fi
fi

# ─────────────────────────────────────────
# Step 7. Optional · claude-memory-compiler (auto session capture)
# ─────────────────────────────────────────
echo
echo "  Vepol can auto-capture every Claude Code session into your daily log"
echo "  via a small open-source companion tool (claude-memory-compiler)."

if ask "Install claude-memory-compiler for automatic session capture?"; then
  COMPILER="$HOME_DIR/claude-memory-compiler"
  if [[ ! -d "$COMPILER/.git" ]]; then
    say "  cloning claude-memory-compiler…"
    git clone --quiet https://github.com/coleam00/claude-memory-compiler.git "$COMPILER" 2>/dev/null \
      && ok "  cloned to $COMPILER" \
      || warn "  clone failed — install manually later"
  fi
  if [[ -d "$COMPILER/.git" && -f "$VEPOL_DIR/patches/claude-memory-compiler.diff" ]]; then
    say "  applying Vepol patches to flush.py…"
    if (cd "$COMPILER" && git apply --check "$VEPOL_DIR/patches/claude-memory-compiler.diff" 2>/dev/null); then
      (cd "$COMPILER" && git apply "$VEPOL_DIR/patches/claude-memory-compiler.diff") \
        && ok "    patches applied"
    else
      warn "    patches already applied or out of date — see $VEPOL_DIR/patches/"
    fi
    if command -v uv >/dev/null 2>&1; then
      (cd "$COMPILER" && uv sync 2>/dev/null) \
        && ok "    Python deps synced via uv" \
        || warn "    uv sync failed — run manually later"
    fi
  fi
fi

# ─────────────────────────────────────────
# Step 8. First-run aha sequence
# ─────────────────────────────────────────
echo
cat <<INTRO
${C_INFO}══════════════════════════════════════════════════════
  Installation complete · v${VEPOL_VERSION}
══════════════════════════════════════════════════════${C_OFF}

Now let's verify everything works and get you to a useful
interaction in under 5 minutes.

INTRO

# 8a. kb-doctor
if [[ -x "$HUB/bin/kb-doctor" ]]; then
  say "Running kb-doctor (system health check)…"
  set +e
  "$HUB/bin/kb-doctor" install-health 2>&1 | tee -a "$LOG" | tail -15
  RC=$?
  set -e
  if [[ "$RC" -eq 0 ]]; then
    ok "kb-doctor passed"
  else
    warn "kb-doctor reported issues (exit $RC) — review above"
  fi
else
  warn "kb-doctor not executable — check $HUB/bin/kb-doctor"
fi

# 8b. Suggested next steps
cat <<NEXT

${C_INFO}━━━ Try these next ━━━${C_OFF}

  ${C_DIM}# Write your first task into the knowledge base:${C_OFF}
  $HUB/bin/kb-task "My first Vepol task"

  ${C_DIM}# Confirm retrieval works:${C_OFF}
  $HUB/bin/kb-search "first Vepol"

  ${C_DIM}# Get the morning brief (synthesizes from your KB):${C_OFF}
  $HUB/bin/kb-brief

${C_INFO}━━━ Read next ━━━${C_OFF}

  ${C_DIM}# Project schema (how the knowledge base is organized):${C_OFF}
  $HUB/CLAUDE.md

  ${C_DIM}# Global Claude Code conventions (your edits stay; managed block updates):${C_OFF}
  $HOME_DIR/.claude/CLAUDE.md

  ${C_DIM}# Methodology pages (if shipped):${C_OFF}
  $VEPOL_DIR/docs/methodology/

${C_INFO}━━━ Manual steps remaining ━━━${C_OFF}

  1. Authenticate Claude Code (if not yet):
       claude login

  2. Optional — enable cross-agent review with Codex CLI:
       codex login                      # or place API key in ~/.codex/auth.json

  3. Optional — paste Telegram bot token into:
       $HOME_DIR/.claude/channels/telegram/.env

  4. To start a wiki in your first project:
       cd <your-project>
       claude -p "/init-kb"

${C_INFO}━━━ Stay in touch ━━━${C_OFF}

  Issues / questions:  https://github.com/nahornyi-ai-lab/vepol/issues
  Discussions:         https://github.com/nahornyi-ai-lab/vepol/discussions
  Sponsor:             https://github.com/sponsors/nahornyi-ai-lab

  Vepol is alpha (v0.x). Your feedback shapes the API.

NEXT

ok "Bootstrap complete — full log: $LOG"
