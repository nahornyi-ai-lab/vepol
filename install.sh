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

# Prerequisites, shared by the apply check, --probe and --capabilities.
# Required tools block the install (python3 must be 3.10+, bash 5+). Optional
# tools only enable extras. node and bun are optional: no kb-* script runs
# them; bun is used only by Claude Code's own Telegram plugin.
REQUIRED_TOOLS="git claude rg python3"
OPTIONAL_TOOLS_INFO="codex|cross-agent review, second opinions and mail reading (Codex CLI)
uv|session auto-capture (claude-memory-compiler) and the local Qwen audio install
jq|the Claude Code status line
gh|GitHub operations from agent sessions (PRs, issues, releases)
node|installing agent CLIs with npm (for example Codex); no kb-* script runs it
bun|Claude Code's Telegram plugin (chatting with Claude through Telegram)
agy|Antigravity CLI: an independent third opinion
grok|Grok CLI: current social and news research"
CODEX_INSTALL_HINT="npm i -g @openai/codex, brew install --cask codex, or the standalone installer https://chatgpt.com/codex/install.sh"
CODEX_LOOKUP_HINT="Vepol looks for codex at \$KB_CODEX_BIN, ~/.local/bin/codex, your PATH, /opt/homebrew/bin/codex, /usr/local/bin/codex"

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

# ─────────────────────────────────────────
# Agent-mode dispatch (prompt-first install)
# Read-only modes (probe/dry-run/verify/capabilities) emit JSON and exit BEFORE
# any mutation or log truncation. Unknown flags exit 2 with EMPTY stdout, so an
# agent can detect "this installer is too old for prompt-first install" instead
# of silently running a full install. (spec: agent-self-install, blockers B1/B2/B3)
# ─────────────────────────────────────────
MODE=""; WANT_JSON=0; AUDIO_BACKEND=""
_set_mode() {  # reject conflicting mode flags (e.g. --probe --apply) — exit 2, empty stdout
  if [[ -n "$MODE" && "$MODE" != "$1" ]]; then
    printf 'install.sh: conflicting mode flags (%s and %s)\n' "$MODE" "$1" >&2
    exit 2
  fi
  MODE="$1"
}
while [[ $# -gt 0 ]]; do
  arg="$1"
  case "$arg" in
    --probe)        _set_mode probe ;;
    --dry-run)      _set_mode dry-run ;;
    --verify)       _set_mode verify ;;
    --capabilities) _set_mode capabilities ;;
    --apply)        _set_mode apply ;;
    --json)         WANT_JSON=1 ;;
    --audio-backend)
      [[ $# -ge 2 ]] || { printf 'install.sh: --audio-backend requires notebooklm or local_qwen\n' >&2; exit 2; }
      AUDIO_BACKEND="$2"; shift ;;
    --audio-backend=*) AUDIO_BACKEND="${arg#*=}" ;;
    -h|--help)      _set_mode help ;;
    *) printf 'install.sh: unknown option: %s\n' "$arg" >&2
       printf 'Run "./install.sh --capabilities --json" to see supported modes.\n' >&2
       exit 2 ;;
  esac
  shift
done
if [[ -n "$AUDIO_BACKEND" && "$AUDIO_BACKEND" != "notebooklm" \
      && "$AUDIO_BACKEND" != "local_qwen" ]]; then
  printf 'install.sh: invalid --audio-backend: %s (expected notebooklm or local_qwen)\n' "$AUDIO_BACKEND" >&2
  exit 2
fi
[[ -z "$MODE" ]] && MODE="apply-interactive"

_json_esc() {  # minimal JSON string escaping for shell-emitted JSON (backslash, quote)
  local s="$1"; s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; printf '%s' "$s"
}

_optional_tools_json() {  # {"name": "what it enables", ...} — shell-only
  local first=1 name what
  printf '{'
  while IFS='|' read -r name what; do
    [[ -n "$name" ]] || continue
    [[ $first -eq 1 ]] || printf ', '
    first=0
    printf '"%s": "%s"' "$(_json_esc "$name")" "$(_json_esc "$what")"
  done <<< "$OPTIONAL_TOOLS_INFO"
  printf '}'
}

_emit_capabilities() {
  # Shell-only (no python3 dependency) — capabilities must work on a bare machine
  # so an agent can detect support before any prereq is installed.
  local _req="" t
  for t in $REQUIRED_TOOLS bash; do _req="${_req:+$_req, }\"$t\""; done
  cat <<CAPS
{
  "tool": "vepol-install",
  "version": "$VEPOL_VERSION",
  "schema_version": 1,
  "modes": ["--probe", "--dry-run", "--apply", "--verify", "--capabilities", "--help"],
  "json_modes": ["--probe", "--dry-run", "--verify", "--capabilities"],
  "audio_backends": ["notebooklm", "local_qwen"],
  "opt_in_env": ["VEPOL_ENABLE_LAUNCHD", "VEPOL_ENABLE_TELEGRAM", "VEPOL_ENABLE_MEMORY_COMPILER", "VEPOL_APPLY_C01", "VEPOL_MERGE_HOOKS"],
  "required_tools": [$_req],
  "min_versions": {"python3": "3.10", "bash": "5"},
  "optional_tools": $(_optional_tools_json),
  "exit_codes": {"0": "ok", "2": "unknown-option", "10": "missing-required-prereq", "11": "partial-install", "12": "plan-conflict", "13": "verify-failed"}
}
CAPS
}

_probe_or_verify() {
  # $1 = probe|verify. Emits JSON to stdout only; reads nothing it shouldn't,
  # writes nothing. Returns a typed exit code.
  if ! command -v python3 >/dev/null 2>&1; then
    # python3 is a required prereq; without it, still emit minimal JSON so the
    # agent sees the gap instead of an empty failure.
    local _rc=10; [[ "$1" == "verify" ]] && _rc=13
    local _hub; _hub="$(_json_esc "$HUB")"
    cat <<PJ
{
  "mode": "$1",
  "os": "$(uname)",
  "arch": "$(uname -m)",
  "vepol_version": "$(_json_esc "$VEPOL_VERSION")",
  "prereqs_missing_required": ["python3"],
  "hub_path": "$_hub",
  "hub_exists": $([[ -d "$HUB" ]] && echo true || echo false),
  "note": "python3 not found — install it (see docs/dependency-matrix.md), then re-run"
}
PJ
    return "$_rc"
  fi
  KIND="$1" HUB="$HUB" HOME_DIR="$HOME_DIR" VEPOL_DIR="$VEPOL_DIR" \
  REQUIRED_TOOLS="$REQUIRED_TOOLS" OPTIONAL_TOOLS_INFO="$OPTIONAL_TOOLS_INFO" \
  VEPOL_VERSION="$VEPOL_VERSION" python3 <<'PY'
import json, os, re, shutil, subprocess, sys
hub  = os.environ["HUB"]; home = os.environ["HOME_DIR"]; kind = os.environ["KIND"]
def _exe(p): return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)
def find(c):
    # Agent CLIs: the same lookup order Vepol's scheduled jobs use (launchd's
    # PATH lacks ~/.local/bin, so the fixed fallbacks matter). Others: PATH.
    local = os.path.join(home, ".local/bin", c)
    if c == "claude":
        cands = [os.environ.get("KB_CLAUDE_BIN", ""), shutil.which(c) or "", local,
                 "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]
    elif c == "codex":
        cands = [os.environ.get("KB_CODEX_BIN", ""), local, shutil.which(c) or "",
                 "/opt/homebrew/bin/codex", "/usr/local/bin/codex"]
    else:
        return shutil.which(c)
    return next((p for p in cands if _exe(p)), None)
def have(c): return find(c) is not None
req = os.environ["REQUIRED_TOOLS"].split()
missing = [c for c in req if not have(c)]
opt_info = dict(line.split("|", 1) for line in os.environ["OPTIONAL_TOOLS_INFO"].splitlines()
                if "|" in line)
opt = [c for c in opt_info if not have(c)]
# Versions that --apply enforces, reported here so an agent sees them first.
versions = {}; version_problems = []
if "python3" not in missing:
    versions["python3"] = "%d.%d.%d" % sys.version_info[:3]
    if sys.version_info < (3, 10): version_problems.append("python-3.10+")
bash_best = (0, "")
for cand in [shutil.which("bash") or "", "/opt/homebrew/bin/bash", "/usr/local/bin/bash"]:
    if not _exe(cand): continue
    try:
        v = subprocess.run([cand, "-c", 'echo "${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}.${BASH_VERSINFO[2]}"'],
                           capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        continue
    m = re.match(r"^(\d+)\.", v)
    if m and int(m.group(1)) > bash_best[0]: bash_best = (int(m.group(1)), v)
versions["bash"] = bash_best[1] or "unknown"
if bash_best[0] < 5: version_problems.append("bash-5+")
def sw():
    try:
        return (subprocess.run(["sw_vers", "-productVersion"], capture_output=True,
                               text=True).stdout.strip() or "unknown")
    except Exception:
        return "unknown"
hub_exists = os.path.isdir(hub)
managed = os.path.isfile(os.path.join(home, ".claude/.vepol/CLAUDE.managed.md"))
cm = os.path.join(home, ".claude/CLAUDE.md"); include_ok = False
if os.path.isfile(cm):
    try: include_ok = "BEGIN VEPOL MANAGED" in open(cm, encoding="utf-8", errors="ignore").read()
    except Exception: include_ok = False
needs_sec = False
sj = os.path.join(home, ".claude/settings.json")
if os.path.isfile(sj):
    try:
        d = json.loads(open(sj, encoding="utf-8-sig").read())
        p = d.get("permissions") if isinstance(d, dict) else None
        if isinstance(p, dict) and p.get("defaultMode") == "bypassPermissions": needs_sec = True
        if isinstance(d, dict) and d.get("skipDangerousModePermissionPrompt") is True: needs_sec = True
    except Exception:
        needs_sec = False
bin_linked = os.path.islink(os.path.join(hub, "bin", "kb-doctor"))
out = {
    "mode": kind, "os": os.uname().sysname, "os_version": sw(), "arch": os.uname().machine,
    "vepol_version": os.environ["VEPOL_VERSION"],
    "prereqs_missing_required": missing, "prereqs_missing_optional": opt,
    "prereqs_version_problems": version_problems, "prereq_versions": versions,
    "optional_tools": opt_info,
    "hub_path": hub, "hub_exists": hub_exists,
    "claude_managed_present": managed, "claude_include_block": include_ok,
    "bin_symlinked": bin_linked, "needs_security_migration": needs_sec,
}
rc = 0
if kind == "probe":
    if missing or version_problems: rc = 10
    elif hub_exists and not bin_linked: rc = 11
else:  # verify
    problems = []
    if not hub_exists: problems.append("hub-missing")
    if not bin_linked: problems.append("bin-not-symlinked")
    # Integrity, not just existence: a managed bin symlink must RESOLVE to the seed.
    # A retargeted/replaced link ("is a symlink" but points elsewhere) is a tamper
    # that the existence check alone would pass. Seed-existence-guarded so the core
    # list can't produce false positives if the seed drops a tool.
    seed = os.environ.get("VEPOL_DIR", "")
    if seed:
        for n in ("kb-doctor", "kb-task", "kb-search", "kb-board", "_kb_backlog"):
            want = os.path.join(seed, "bin", n)
            if not os.path.exists(want):
                continue
            link = os.path.join(hub, "bin", n)
            if not os.path.islink(link):
                problems.append("bin-missing:" + n)
            elif os.path.realpath(link) != os.path.realpath(want):
                problems.append("bin-tampered:" + n)
        # orchestrator-seed pointer ($HUB/orchestrator-seed -> seed) — how agents
        # locate the seed. install creates it, uninstall removes it; verify it too.
        sp = os.path.join(hub, "orchestrator-seed")
        if not os.path.islink(sp):
            # A correctly wired install has this as a symlink to the seed. Anything
            # else — absent, or replaced by a real file/dir — means agents can't
            # follow it to the seed, so verify must flag it (not "is a symlink"
            # but "resolves to the seed").
            problems.append("seed-pointer-missing" if not os.path.exists(sp)
                            else "seed-pointer-not-symlink")
        elif os.path.realpath(sp) != os.path.realpath(seed):
            problems.append("seed-pointer-tampered")
    if not managed:
        problems.append("claude-managed-missing")
    else:
        try:
            if os.path.getsize(os.path.join(home, ".claude/.vepol/CLAUDE.managed.md")) == 0:
                problems.append("claude-managed-empty")
        except OSError:
            problems.append("claude-managed-unreadable")
    if not include_ok: problems.append("claude-include-missing")
    out["verify_problems"] = problems
    out["verify_scope"] = ("core operating substrate: hub, bin->seed links, "
                           "orchestrator-seed pointer, claude managed file + include block. "
                           "For full manifest/skills/launchd health run: kb-doctor install-health")
    rc = 0 if not problems else 13
print(json.dumps(out, indent=2))
sys.exit(rc)
PY
}

_dry_run() {
  # Plan only — no mutation, writes nothing. Shell-only (no python3 dependency).
  local hub; hub="$(_json_esc "$HUB")"
  cat <<DRY
{
  "mode": "dry-run",
  "mutates": false,
  "hub_path": "$hub",
  "planned_actions": [
    "ensure hub dirs under $hub (bin, raw, sources, personal, ...)",
    "symlink $hub/bin/* -> seed bin/ (managed)",
    "install ~/.claude/.vepol/CLAUDE.managed.md + include block in ~/.claude/CLAUDE.md",
    "install Claude skills",
    "optional, OFF unless VEPOL_ENABLE_* set: scheduled tasks, telegram scaffold, memory-compiler",
    "existing ~/.claude/settings.json: add Vepol's session hooks only with VEPOL_MERGE_HOOKS=1 (backup kept)",
    "write install manifest, run kb-doctor, first-run aha, write receipt"
  ]
}
DRY
}

_print_help() {
  cat <<'HLP'
Vepol installer.

Usage:
  ./install.sh                       Interactive install (asks before optional features).
  ./install.sh --apply               Non-interactive core install; opt-ins via env (below).
  ./install.sh --probe --json        Read-only environment/state report (writes nothing).
  ./install.sh --dry-run --json      Plan only (no mutation).
  ./install.sh --verify --json       Check an existing install.
  ./install.sh --capabilities --json List supported modes.
  ./install.sh --apply --audio-backend notebooklm|local_qwen
                                      Select the managed digest audio route.

Opt-in env for --apply (all default OFF):
  VEPOL_ENABLE_LAUNCHD=1   scheduled background tasks
  VEPOL_ENABLE_TELEGRAM=1  Claude Code Telegram plugin scaffold (chat with Claude)
  VEPOL_ENABLE_MEMORY_COMPILER=1  auto session capture
  VEPOL_APPLY_C01=1        apply the settings.json security migration
  VEPOL_MERGE_HOOKS=1      add Vepol's session hooks to an existing
                           ~/.claude/settings.json (a backup is kept)

Required tools: git, claude (Claude Code CLI), rg (ripgrep), python3 3.10+, bash 5+.
HLP
  printf 'Optional tools (each enables an extra; the install never needs them):\n'
  local name what
  while IFS='|' read -r name what; do
    [[ -n "$name" ]] && printf '  %-6s %s\n' "$name" "$what"
  done <<< "$OPTIONAL_TOOLS_INFO"
}

_want() {
  # _want <ENV_VAR> <ask-prompt> → 0 if the feature is requested.
  # Non-interactive apply (MODE=apply): truthy env var. Interactive: ask the user.
  local var="$1" prompt="$2"
  if [[ "$MODE" == "apply" ]]; then
    local val
    val="$(printf '%s' "${!var:-}" | tr '[:upper:]' '[:lower:]')"
    [[ -n "$val" && "$val" != "0" && "$val" != "no" && "$val" != "false" && "$val" != "off" ]]
    return
  fi
  ask "$prompt"
}

_unset_in_apply() {
  # _unset_in_apply <ENV_VAR> → 0 when --apply runs without an explicit answer for this
  # extra (the variable is unset or empty), as upgrade.sh does. An extra that is already
  # installed is then kept as it is, not recorded as declined.
  local var="$1"
  [[ "$MODE" == "apply" && -z "${!var:-}" ]]
}

case "$MODE" in
  capabilities) _emit_capabilities; exit 0 ;;
  probe)        set +e; _probe_or_verify probe;  rc=$?; set -e; exit "$rc" ;;
  verify)       set +e; _probe_or_verify verify; rc=$?; set -e; exit "$rc" ;;
  dry-run)      _dry_run; exit 0 ;;
  help)         _print_help; exit 0 ;;
esac

# ── Apply path (MODE=apply or apply-interactive) only, below this line ──
NEEDS_SECURITY_MIGRATION=0
# Track actual opt-in decisions (works for both env and interactive) for the receipt.
OPT_LAUNCHD=off; OPT_TELEGRAM=off; OPT_MEMORY=off

# v1 scope: installation supports the DEFAULT hub (~/knowledge) only. A custom
# VEPOL_HUB is not yet threaded through the CLAUDE.md/settings/launchd/manifest
# templates, so installing into one would leave runtime files pointing at the
# default hub. Refuse fast rather than produce a half-wired install. (Read-only
# --probe/--dry-run/--verify still accept VEPOL_HUB.) Follow-up: full custom-hub plumbing.
if [[ "$HUB" != "$HOME_DIR/knowledge" ]]; then
  # NB: use inline printf+exit, not die() — die() is defined further below and is
  # not yet in scope at this point in the apply path.
  printf 'install.sh: custom VEPOL_HUB (%s) is not supported for install in v1 — ' "$HUB" >&2
  printf 'unset VEPOL_HUB to install into ~/knowledge. (read-only --probe/--dry-run/--verify still accept VEPOL_HUB.)\n' >&2
  exit 1
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

# A new interactive install offers one simple route choice — asked with the
# other opt-ins (Step 6), after the core install. Existing installs are never
# switched or prompted on upgrade unless --audio-backend is explicit.
ASK_AUDIO_BACKEND=0
if [[ "$MODE" == "apply-interactive" && -z "$AUDIO_BACKEND" \
      && ! -f "$HUB/personal/processes.yaml" ]]; then
  ASK_AUDIO_BACKEND=1
fi
AUDIO_RESULT="preserved"   # for the receipt: preserved | notebooklm | local_qwen | local_qwen-failed

# Agent CLI lookup (shared contract): first executable hit wins. Scheduled
# jobs run under launchd, whose PATH lacks ~/.local/bin, so the fixed
# fallbacks matter.
_find_agent_cli() {
  local name="$1" c
  local -a cands
  if [[ "$name" == "claude" ]]; then
    cands=("${KB_CLAUDE_BIN:-}" "$(command -v claude 2>/dev/null || true)" "$HOME_DIR/.local/bin/claude" \
           /opt/homebrew/bin/claude /usr/local/bin/claude)
  else
    cands=("${KB_CODEX_BIN:-}" "$HOME_DIR/.local/bin/codex" "$(command -v codex 2>/dev/null || true)" \
           /opt/homebrew/bin/codex /usr/local/bin/codex)
  fi
  for c in "${cands[@]}"; do
    if [[ -n "$c" && -f "$c" && -x "$c" ]]; then printf '%s\n' "$c"; return 0; fi
  done
  return 1
}
_have_tool() {
  case "$1" in
    claude|codex) _find_agent_cli "$1" >/dev/null ;;
    *) command -v "$1" >/dev/null 2>&1 ;;
  esac
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
  die "Vepol supports macOS only. Linux support is on the roadmap."
fi
OS_VER="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
OS_MAJ="${OS_VER%%.*}"
if [[ "$OS_MAJ" =~ ^[0-9]+$ && "$OS_MAJ" -lt 13 ]]; then
  die "Vepol needs macOS 13 (Ventura) or newer — detected $OS_VER."
fi
ok "  macOS $OS_VER detected"

# Required tools (python3 is version-checked below)
MISSING=()
for cmd in $REQUIRED_TOOLS; do
  [[ "$cmd" == "python3" ]] && continue
  if ! _have_tool "$cmd"; then
    MISSING+=("$cmd")
  fi
done
if CLAUDE_FOUND="$(_find_agent_cli claude)" && ! command -v claude >/dev/null 2>&1; then
  warn "  claude found at $CLAUDE_FOUND but not on your PATH — open a new terminal (or add its folder to PATH) to run it yourself"
fi

# bash 5+ (macOS ships 3.2 by default). Check the bash on PATH (what hooks run)
# as well as the common Homebrew locations; take the highest major found.
USER_BASH_MAJ=0
for cand in "$(command -v bash 2>/dev/null)" /opt/homebrew/bin/bash /usr/local/bin/bash; do
  [[ -n "$cand" && -x "$cand" ]] || continue
  maj=$("$cand" -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 0)
  [[ "$maj" =~ ^[0-9]+$ ]] && (( maj > USER_BASH_MAJ )) && USER_BASH_MAJ=$maj
done
if [[ "$USER_BASH_MAJ" -lt 5 ]]; then
  MISSING+=("bash-5+")
fi

# node and bun are optional (see OPTIONAL_TOOLS_INFO): no kb-* script runs
# them, so they are neither required nor version-checked here.

# Python 3.10+ is REQUIRED — the SessionStart hook (kb-session-start) needs it.
PY_OK=1
if command -v python3 >/dev/null 2>&1; then
  PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)' 2>/dev/null || echo 0)
else
  PY_OK=0
fi

# Optional tools (agy/grok and other agent CLIs are offered in Step 2)
OPTIONAL_MISSING=()
for cmd in codex uv jq gh node bun; do
  if ! _have_tool "$cmd"; then
    OPTIONAL_MISSING+=("$cmd")
  fi
done

# Build a clear list of what's wrong, then block if anything is.
PROBLEMS=(${MISSING[@]+"${MISSING[@]}"})
[[ "$PY_OK"   != "1" ]] && PROBLEMS+=("python-3.10+")
if [[ ${#PROBLEMS[@]} -gt 0 ]]; then
  echo
  warn "Required tools missing or out of date: ${PROBLEMS[*]}"
  cat <<HELP

${C_INFO}Install commands:${C_OFF}

  ${C_DIM}# If Homebrew is not installed yet:${C_OFF}
  /bin/bash -c "\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  ${C_DIM}# Required tools (via Homebrew):${C_OFF}
  brew install bash ripgrep git python@3

  ${C_DIM}# Claude Code — the command-line tool (the Claude desktop app does not provide it):${C_OFF}
  curl -fsSL https://claude.ai/install.sh | bash
  ${C_DIM}# or: brew install --cask claude-code
  # then open a new terminal and check: claude --version (needs a paid Claude plan)${C_OFF}

After installing, re-run: ./install.sh

(${C_DIM}Vepol intentionally does not auto-install Homebrew or any system package
manager — that decision should be yours.${C_OFF})
HELP
  die "Required tools missing — please install then re-run."
fi

# Optional warnings — name what each missing tool enables.
if [[ ${#OPTIONAL_MISSING[@]} -gt 0 ]]; then
  warn "  Optional tools missing: ${OPTIONAL_MISSING[*]} (Vepol works without them)"
  BREW_OPT=()
  for cmd in "${OPTIONAL_MISSING[@]}"; do
    what="$(printf '%s\n' "$OPTIONAL_TOOLS_INFO" | awk -F'|' -v n="$cmd" '$1 == n { print $2; exit }')"
    warn "    $cmd — $what"
    [[ "$cmd" == "codex" ]] || BREW_OPT+=("$cmd")
  done
  if [[ ${#BREW_OPT[@]} -gt 0 ]]; then
    warn "    Install: brew install ${BREW_OPT[*]}"
  fi
  if [[ " ${OPTIONAL_MISSING[*]} " == *" codex "* ]]; then
    warn "    Codex: $CODEX_INSTALL_HINT"
    warn "      ($CODEX_LOOKUP_HINT)"
  fi
fi
# Agent CLIs (codex/agy/grok/notebooklm/opencode) are OFFERED in Step 2, after the
# hub is scaffolded — Vepol uses whichever you install and never blocks on them.

# (python3 3.10+ is enforced as a required prerequisite above — the SessionStart
# hook and People module both need it, so reaching here means it's present.)

# Python deps — checked, NOT installed (per detect-only policy)
if [[ -f "$VEPOL_DIR/requirements.txt" ]]; then
  MISSING_PY=()
  python3 -c "import frontmatter" 2>/dev/null || MISSING_PY+=(python-frontmatter)
  python3 -c "import click" 2>/dev/null || MISSING_PY+=(click)
  python3 -c "import yaml" 2>/dev/null || MISSING_PY+=(PyYAML)
  python3 -c "import jellyfish" 2>/dev/null || MISSING_PY+=(jellyfish)
  if [[ ${#MISSING_PY[@]} -gt 0 ]]; then
    warn "  Python deps missing for $(command -v python3): ${MISSING_PY[*]}"
    warn "    kb-idea, kb-contact and other tools fail until they are installed. Run:"
    warn "      python3 -m pip install --user -r \"$VEPOL_DIR/requirements.txt\""
    warn "    If pip reports \"externally-managed-environment\" (Homebrew Python), run instead:"
    warn "      python3 -m pip install --break-system-packages -r \"$VEPOL_DIR/requirements.txt\""
    warn "    (kb-* scripts run the python3 on your PATH, so a separate venv is not picked up.)"
  fi
fi

ok "  All required prerequisites present"

# ─────────────────────────────────────────
# Step 2. Hub scaffolding
# ─────────────────────────────────────────
say "Step 2 · Setting up knowledge hub at $HUB"

HUB_EXISTED=1; [[ -d "$HUB" ]] || HUB_EXISTED=0
# Always (re)create managed dirs — an existing hub may be missing bin/ (e.g. a
# partial/older install), and the bin symlinks below would otherwise abort under set -e.
# logs/: every LaunchAgent writes its stdout/stderr there.
mkdir -p "$HUB"/{bin,raw,concepts,people,companies,solutions,projects,personal,daily,sources,logs}
mkdir -p "$HUB/_template/knowledge" "$HUB/.orchestrator"
if [[ $HUB_EXISTED -eq 1 ]]; then ok "  $HUB already exists — preserving"; else ok "  created $HUB"; fi

# Symlink bin scripts (overwrite — these are managed by repo).
# _kb_*.py shared modules are linked too: shell runners invoke them as
# files ($HUB/bin/_kb_profile.py), and Python runners that are executed
# through the $HUB/bin symlink expect them next to the script.
for script in "$VEPOL_DIR"/bin/kb-* "$VEPOL_DIR"/bin/new-wiki "$VEPOL_DIR"/bin/_kb_*.py; do
  [[ -f "$script" ]] || continue
  scriptname="$(basename "$script")"
  ln -sf "$script" "$HUB/bin/$scriptname"
done
# Agent CLI roster — install the declarative registry, offer the optional agent
# CLIs, and generate the per-machine cheatsheet that agents read at startup.
mkdir -p "$HUB/.orchestrator"
CLI_REG="$HUB/.orchestrator/cli-tools.tsv"
if [[ -f "$VEPOL_DIR/bin/cli-tools.tsv" && ! -f "$CLI_REG" ]]; then
  cp "$VEPOL_DIR/bin/cli-tools.tsv" "$CLI_REG"
  ok "  agent CLI registry: $CLI_REG"
elif [[ -f "$VEPOL_DIR/bin/cli-tools.tsv" ]]; then
  # Existing registry: never change the user's rows; only append rows for
  # agents it does not know yet (matched on the first column). A commented-out
  # row ("# name | ...") counts as known, so a disabled agent stays disabled.
  # FILENAME, not NR == FNR: an empty registry must still get every agent.
  NEW_ROWS="$(awk -F'|' '
    function name(s) { sub(/^[ \t#]+/, "", s); sub(/[ \t]+$/, "", s); return s }
    FILENAME == ARGV[1] { if ($0 ~ /\|/) known[name($1)] = 1; next }
    $0 ~ /^[ \t]*(#|$)/ || $0 !~ /\|/ { next }
    !(name($1) in known) { print }
  ' "$CLI_REG" "$VEPOL_DIR/bin/cli-tools.tsv")"
  if [[ -n "$NEW_ROWS" ]]; then
    [[ -s "$CLI_REG" && -n "$(tail -c1 "$CLI_REG")" ]] && printf '\n' >> "$CLI_REG"
    printf '%s\n' "$NEW_ROWS" >> "$CLI_REG"
    ok "  agent CLI registry: added $(printf '%s\n' "$NEW_ROWS" | awk -F'|' '{ gsub(/[ \t]/, "", $1); printf "%s%s", sep, $1; sep=", " }') to $CLI_REG"
  else
    ok "  agent CLI registry up to date: $CLI_REG"
  fi
fi
if [[ -x "$VEPOL_DIR/bin/kb-cli-offer" ]]; then
  # --list: detect-only, non-interactive — prints each agent CLI + its install
  # command, never prompts and never auto-installs (honors the installer's
  # detect-only contract). The user installs what they want; kb-cli-roster then
  # uses whatever is present.
  bash "$VEPOL_DIR/bin/kb-cli-offer" --list || true
fi
if [[ -x "$HUB/bin/kb-cli-roster" ]]; then
  # KB_HUB pins the registry lookup to THIS install's hub (not a stray ~/knowledge).
  # Report success only if it actually generated — don't claim a roster that isn't there.
  if KB_HUB="$HUB" "$HUB/bin/kb-cli-roster" --out "$HUB/.active-roster.md" >/dev/null 2>&1; then
    ok "  agent CLI roster generated (agents now know which CLIs are installed)"
  else
    warn "  agent CLI roster generation failed — agents fall back to AGENTS.md pointer"
  fi
fi

# Internal Python packages + prompt templates — symlink directories. If an older
# install left a REAL directory at a managed target, replace it: `ln -sfn` onto an
# existing real dir would create the link nested inside it, not replace it.
for pkg in _kb_backlog _kb_board _kb_people _kb_ideas _kb_mcp _kb_scanner _kb_mail _kb_calendar _kb_evolution _kb_multibot _kb_orchestrator _kb_tts _kb_runtime_registry templates; do
  [[ -d "$VEPOL_DIR/bin/$pkg" ]] || continue
  if [[ -d "$HUB/bin/$pkg" && ! -L "$HUB/bin/$pkg" ]]; then
    # Never DELETE a real directory — we can't be sure we own this hub. Move it
    # aside to a timestamped backup so nothing is lost, then place the symlink.
    bak="$HUB/bin/$pkg.pre-vepol.$(date +%Y%m%d%H%M%S)"
    if mv "$HUB/bin/$pkg" "$bak" 2>/dev/null; then
      warn "  moved existing $HUB/bin/$pkg aside to $(basename "$bak") (was a real dir, not a Vepol symlink)"
    else
      warn "  $HUB/bin/$pkg exists as a real dir and could not be moved — skipping symlink"
      continue
    fi
  fi
  ln -sfn "$VEPOL_DIR/bin/$pkg" "$HUB/bin/$pkg"
done
ok "  bin/ symlinks point at $VEPOL_DIR/bin/"

if [[ -L "$HUB/orchestrator-seed" || ! -e "$HUB/orchestrator-seed" ]]; then
  ln -sfn "$VEPOL_DIR" "$HUB/orchestrator-seed"
  ok "  orchestrator-seed pointer: $HUB/orchestrator-seed -> $VEPOL_DIR"
else
  # A real (non-symlink) file/dir is in the way. A correctly wired install needs a
  # symlink-to-seed here (verify requires it), so move the conflict aside to a
  # timestamped backup and place the pointer — same self-heal pattern as the _kb_*
  # managed dirs above. Never DELETE the user's file.
  bak="$HUB/orchestrator-seed.pre-vepol.$(date +%Y%m%d%H%M%S)"
  if mv "$HUB/orchestrator-seed" "$bak" 2>/dev/null; then
    warn "  moved existing non-symlink $HUB/orchestrator-seed aside to $(basename "$bak")"
    ln -sfn "$VEPOL_DIR" "$HUB/orchestrator-seed"
    ok "  orchestrator-seed pointer: $HUB/orchestrator-seed -> $VEPOL_DIR"
  else
    warn "  $HUB/orchestrator-seed is not a symlink and could not be moved — leaving it (verify will flag)"
  fi
fi

# Scanner signatures (context-injection detector) — copy so user hub
# has writable working dir for catalogue updates without touching repo.
mkdir -p "$HUB/security/scanner-signatures" "$HUB/security/scanner-cache"
if [[ -d "$VEPOL_DIR/security/scanner-signatures" ]]; then
  cp -p "$VEPOL_DIR/security/scanner-signatures/"*.md "$HUB/security/scanner-signatures/" 2>/dev/null || true
  cp -p "$VEPOL_DIR/security/scanner-signatures/"*.yaml "$HUB/security/scanner-signatures/" 2>/dev/null || true
fi
if [[ -f "$VEPOL_DIR/security/scanner-signatures-ledger.md" ]] \
   && [[ ! -f "$HUB/security/scanner-signatures-ledger.md" ]]; then
  cp -p "$VEPOL_DIR/security/scanner-signatures-ledger.md" "$HUB/security/scanner-signatures-ledger.md"
fi
ok "  security/scanner-signatures/ seeded"

# Templates (always overwrite — schema is canonical)
cp "$VEPOL_DIR/_template/AGENTS.md" "$HUB/_template/AGENTS.md"
cp "$VEPOL_DIR/_template/CLAUDE.md" "$HUB/_template/CLAUDE.md"
if [[ -f "$VEPOL_DIR/_template/GEMINI.md" ]]; then
  cp "$VEPOL_DIR/_template/GEMINI.md" "$HUB/_template/GEMINI.md"
else
  rm -f "$HUB/_template/GEMINI.md"
fi
cp -R "$VEPOL_DIR/_template/knowledge/." "$HUB/_template/knowledge/"
ok "  _template/ refreshed"

# Hub-level master contract AGENTS.md + Claude adapter. An existing file is
# never overwritten; a re-run compares it with what this version would write
# and warns only when they differ.
if [[ ! -f "$HUB/AGENTS.md" ]]; then
  sed "s|__HOME__|$HOME_DIR|g" "$VEPOL_DIR/knowledge/AGENTS.md" > "$HUB/AGENTS.md"
  ok "  $HUB/AGENTS.md installed (master contract)"
elif sed "s|__HOME__|$HOME_DIR|g" "$VEPOL_DIR/knowledge/AGENTS.md" | cmp -s - "$HUB/AGENTS.md"; then
  ok "  $HUB/AGENTS.md up to date"
else
  warn "  $HUB/AGENTS.md differs from this version's — not overwritten"
  warn "    To see what changed: sed \"s|__HOME__|$HOME_DIR|g\" $VEPOL_DIR/knowledge/AGENTS.md | diff $HUB/AGENTS.md -"
fi
if [[ ! -f "$HUB/CLAUDE.md" ]]; then
  cp "$VEPOL_DIR/knowledge/CLAUDE.md" "$HUB/CLAUDE.md"
  ok "  $HUB/CLAUDE.md installed (Claude Code adapter)"
elif cmp -s "$VEPOL_DIR/knowledge/CLAUDE.md" "$HUB/CLAUDE.md"; then
  ok "  $HUB/CLAUDE.md up to date"
else
  warn "  $HUB/CLAUDE.md differs from this version's — not overwritten"
  warn "    To see what changed: diff $HUB/CLAUDE.md $VEPOL_DIR/knowledge/CLAUDE.md"
fi
if [[ -f "$VEPOL_DIR/knowledge/GEMINI.md" && ! -f "$HUB/GEMINI.md" ]]; then
  cp "$VEPOL_DIR/knowledge/GEMINI.md" "$HUB/GEMINI.md"
  ok "  $HUB/GEMINI.md installed (Gemini CLI adapter)"
elif [[ -f "$HUB/GEMINI.md" ]]; then
  warn "  $HUB/GEMINI.md already exists — legacy adapter left in place"
else
  ok "  Gemini CLI hub adapter not shipped — AGENTS.md is canonical"
fi

# Hub-level triad / state files — only if missing. The templates are the
# per-project ones new-wiki renders; fill their placeholders for the hub.
HUB_TODAY="$(date +%Y-%m-%d)"
for f in log.md state.md index.md backlog.md escalations.md incidents.md strategies.md; do
  if [[ ! -f "$HUB/$f" ]]; then
    src="$VEPOL_DIR/_template/knowledge/$f"
    if [[ -f "$src" ]]; then
      sed -e "s|{{PROJECT_NAME}}|Hub|g" \
          -e "s|{{PROJECT_SLUG}}|hub|g" \
          -e "s|{{CATEGORY}}|hub|g" \
          -e "s|{{DATE}}|$HUB_TODAY|g" \
          -e 's|Wiki created via `new-wiki`|Hub created by `install.sh`|' \
          "$src" > "$HUB/$f"
      ok "    $HUB/$f created from template"
    fi
  fi
done

# Personal overlay (user-owned)
mkdir -p "$HUB/personal/daily-inbox"
if [[ ! -f "$HUB/personal/.secrets" ]]; then
  cat > "$HUB/personal/.secrets" <<'SECEOF'
# Vepol secrets file. Mode 600 enforced. Plain KEY=value lines.
# An empty value turns its feature off; nothing breaks.

# Telegram delivery of the morning brief, evening retro, digests and
# people-review buttons. While either value is empty these are still saved
# under ~/knowledge but NOT delivered.
#   Bot token: create a bot with @BotFather and paste its token.
#   Chat id:   send your bot any message, then open
#              https://api.telegram.org/bot<token>/getUpdates
#              and copy the number at "chat":{"id": ...}.
# Use a different bot than Claude Code's Telegram plugin
# (~/.claude/channels/telegram/.env): two listeners on one bot steal
# each other's updates.
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

# User language — set once, every user-facing process delivers in it
# (spec: user-language-setting-2026-06-12). Derived from the system locale
# with an English fallback; an existing profile is never overwritten —
# edit personal/profile.yaml to change the language any time.
if [[ ! -f "$HUB/personal/profile.yaml" ]]; then
  _locale_lang="${LANG:-}"            # unset LANG -> en fallback below
  _locale_lang="${_locale_lang%%.*}"  # e.g. ru_RU.UTF-8 -> ru_RU
  _locale_lang="${_locale_lang%%_*}"  # ru_RU -> ru
  _locale_lang=$(printf '%s' "$_locale_lang" | tr '[:upper:]' '[:lower:]')
  if [[ ! "$_locale_lang" =~ ^[a-z]{2,3}$ || "$_locale_lang" == "c" || "$_locale_lang" == "posix" ]]; then
    _locale_lang="en"
  fi
  cat > "$HUB/personal/profile.yaml" <<PROFEOF
# Vepol user profile — set once, read by every user-facing process.
# language: short code (en, ru, es, uk, de, ...). Change it any time;
# the next scheduled run delivers in the new language.
language: $_locale_lang
PROFEOF
  chmod 600 "$HUB/personal/profile.yaml"
  ok "  $HUB/personal/profile.yaml created (language: $_locale_lang — edit to change)"
fi

# Project registry — read by init-kb, new-wiki, kb-brief, kb-doctor and
# `kb-rebuild-registry bootstrap`. Created only when missing, in the
# hand-written layout bootstrap parses: the category headings and table
# columns must match REGISTRY_CATEGORY_HEADINGS / REGISTRY_LABELS in
# bin/kb-rebuild-registry (Russian forms for a ru profile, English otherwise).
if [[ ! -f "$HUB/registry.md" ]]; then
  REG_LANG="$(python3 "$HUB/bin/_kb_profile.py" "$HUB" 2>/dev/null || echo en)"
  if [[ "$REG_LANG" == "ru" ]]; then
    REG_COLS="| slug | статус | путь | описание |"
    REG_HEAD="# Реестр проектов

Какие проекты есть, где они лежат и в каком состоянии их вики. Новый проект
добавляется строкой в раздел своей категории (\`/init-kb\` делает это сам).
Заголовки разделов читает \`kb-rebuild-registry bootstrap\` — не меняйте их.

Статусы: \`live\`, \`seeded\`, \`no-wiki\`, \`archived\`, \`pointer\`."
    REG_SECTIONS=("## lab — <work>" "## order — клиентские заказы" "## pet — PetProjects" \
                  "## job — работа по найму" "## personal / прочее")
  else
    REG_COLS="| slug | status | path | description |"
    REG_HEAD="# Project registry

Which projects exist, where they live and what state their wikis are in. Add
a row for each new project under its category (\`/init-kb\` does this for you).
Each category groups projects of one kind, named in its heading: pick the one
that fits (\`new-wiki\` takes it as its third argument; the default is personal).
\`kb-rebuild-registry bootstrap\` reads the section headings — keep them as written.

Statuses: \`live\` (wiki maintained), \`seeded\` (skeleton, no content yet),
\`no-wiki\`, \`archived\`, \`pointer\`."
    REG_SECTIONS=("## lab — research and experiments" "## order — client work" "## pet — side projects" \
                  "## job — employment" "## personal / other")
  fi
  {
    printf '%s\n' "$REG_HEAD"
    for sec in "${REG_SECTIONS[@]}"; do
      printf '\n%s\n\n%s\n|---|---|---|---|\n' "$sec" "$REG_COLS"
    done
  } > "$HUB/registry.md"
  ok "  $HUB/registry.md created (no projects yet)"
fi

# Managed digest route. Creating the default config is safe and idempotent;
# upgrades without an explicit selection preserve the existing outputs exactly.
PROCESSES_FILE="$HUB/personal/processes.yaml"
PROCESSES_CREATED=0
if [[ ! -f "$PROCESSES_FILE" ]]; then
  PROCESSES_CREATED=1
  python3 - "$HUB/bin" "$PROCESSES_FILE" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from _kb_processes import load_processes
load_processes(pathlib.Path(sys.argv[2]), create_default=True)
PY
  ok "  $PROCESSES_FILE created (audio backend: notebooklm)"
  AUDIO_RESULT="notebooklm"   # receipt: a new install starts on NotebookLM
fi
# The digest audio route is chosen and installed with the other opt-ins (Step 6).

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

# Always overwrite the managed copy (owned by repo). Render __HOME__ placeholders
# so the include path (@__HOME__/knowledge/AGENTS.md) resolves to a real path
# instead of being copied verbatim.
sed "s|__HOME__|$HOME_DIR|g" "$VEPOL_DIR/claude/CLAUDE.md" > "$HOME_DIR/.claude/.vepol/CLAUDE.managed.md"
ok "  managed copy: $HOME_DIR/.claude/.vepol/CLAUDE.managed.md"

# The inner line is a real Claude Code import (a line starting with @path).
# BEGIN/END markers stay HTML comments so upgrade/uninstall can find the block.
# Blocks written by older installers carry the inert LEGACY_INCLUDE_INNER
# line instead; they are left as they are (see the hint below).
INCLUDE_BEGIN="<!-- BEGIN VEPOL MANAGED — do not edit. Source: ~/.claude/.vepol/CLAUDE.managed.md -->"
INCLUDE_END="<!-- END VEPOL MANAGED -->"
INCLUDE_INNER="@~/.claude/.vepol/CLAUDE.managed.md"
LEGACY_INCLUDE_INNER="<!-- @include ~/.claude/.vepol/CLAUDE.managed.md -->"

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
  if grep -qxF "$LEGACY_INCLUDE_INNER" "$HOME_DIR/.claude/CLAUDE.md"; then
    warn "  its include line is the old HTML comment, which Claude Code does not load."
    warn "    To load Vepol's global adapter, replace that line in $HOME_DIR/.claude/CLAUDE.md with:"
    warn "      $INCLUDE_INNER"
  fi
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
SETTINGS_MERGEABLE=0   # 1 = a pre-existing, parseable settings.json (hooks step below)
if [[ -f "$VEPOL_DIR/claude/settings.json.template" && ! -f "$HOME_DIR/.claude/settings.json" ]]; then
  sed "s|__HOME__|$HOME_DIR|g" "$VEPOL_DIR/claude/settings.json.template" > "$HOME_DIR/.claude/settings.json"
  ok "  $HOME_DIR/.claude/settings.json created from template"
elif [[ -f "$HOME_DIR/.claude/settings.json" ]]; then
  # ─────────────────────────────────────────
  # Step 3b. C-01 — detect+migrate legacy bypass keys.
  # security-model v2 § P0 C-01.
  # python3 (required prereq); atomic write; preserves original mode.
  # ─────────────────────────────────────────
  detect_script="$(cat <<'PYEOF'
import json, os, sys
p = os.path.expanduser(sys.argv[1])
try:
    # v2.1: utf-8-sig handles UTF-8 BOM (Gemini concern #2, Codex concern #5a).
    with open(p, 'r', encoding='utf-8-sig') as f:
        raw = f.read()
except Exception as exc:
    print(f"READ_ERR:{exc!r}", end='')
    sys.exit(4)
def has_jsonc_comment(text):
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '/' and i + 1 < len(text) and text[i + 1] in ('/', '*'):
                return True
        i += 1
    return False
# v2.1: explicit JSONC pre-scan (Codex concern #5b).
# Reject //-comments and /*-block-comments outside strings; require strict JSON.
if has_jsonc_comment(raw):
    print("JSONC_ERR:settings.json contains // or /* — strict JSON required; manual fix needed", end='')
    sys.exit(5)
try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    # v2.1: covers trailing-comma JSON (Codex concern #5c). Fail-fast, no auto-fix.
    print(f"PARSE_ERR:{exc!r}", end='')
    sys.exit(3)
findings = []
if isinstance(data, dict):
    perms = data.get('permissions')
    if isinstance(perms, dict) and perms.get('defaultMode') == 'bypassPermissions':
        findings.append('permissions.defaultMode=bypassPermissions')
    if data.get('skipDangerousModePermissionPrompt') is True:
        findings.append('skipDangerousModePermissionPrompt=true')
print('|'.join(findings), end='')
sys.exit(0 if not findings else 2)
PYEOF
)"
  set +e
  detect_out=$(python3 -c "$detect_script" "$HOME_DIR/.claude/settings.json" 2>/dev/null)
  detect_rc=$?
  set -e
  [[ "$detect_rc" -eq 0 || "$detect_rc" -eq 2 ]] && SETTINGS_MERGEABLE=1
  if [[ "$detect_rc" -eq 3 ]] || [[ "$detect_rc" -eq 4 ]]; then
    warn "  $HOME_DIR/.claude/settings.json unparseable (${detect_out})"
    warn "  Skipping C-01 migration — fix the file manually, then re-run install."
  elif [[ "$detect_rc" -eq 5 ]]; then
    warn "  ${detect_out}"
    warn "  Strict JSON only — remove comments from ~/.claude/settings.json and re-run."
    exit 1
  elif [[ "$detect_rc" -eq 2 ]]; then
    say "Step 3b · Legacy bypass-mode keys detected in $HOME_DIR/.claude/settings.json"
    echo "  Found: $detect_out"
    echo ""
    echo "  Security impact: in this state, an injected prompt can trigger arbitrary"
    echo "  Bash/Gmail/Telegram tool calls without your approval. See:"
    echo "    SECURITY.md (threat model: prompt injection × bypass mode)"
    echo ""
    echo "  Migration will:"
    echo "    1. snapshot to ~/.claude/settings.json.bak-<timestamp> (mode preserved)"
    echo "    2. set permissions.defaultMode = \"default\""
    echo "    3. remove skipDangerousModePermissionPrompt"
    echo "  Atomic write: tempfile → chmod to ORIGINAL mode → rename."
    echo "  Original file mode is preserved (not silently downgraded to 0600)."
    echo ""
    # In non-interactive --apply, ONLY the explicit VEPOL_APPLY_C01=1 applies the
    # migration (VEPOL_YES is a legacy interactive convenience, never a silent
    # apply-mode trigger). Interactive install asks.
    if [[ "${VEPOL_APPLY_C01:-}" == "1" ]] \
       || { [[ "$MODE" != "apply" ]] && { [[ "${VEPOL_YES:-}" == "1" ]] || ask "Apply this migration now?"; }; }; then
      snapshot="$HOME_DIR/.claude/settings.json.bak-$(date +%Y-%m-%d-%H%M%S)"
      cp -p "$HOME_DIR/.claude/settings.json" "$snapshot"
      ok "  snapshot: $snapshot"
      migrate_script="$(cat <<'PYEOF'
import json, os, stat, sys, tempfile
src = os.path.expanduser(sys.argv[1])
with open(src, 'r', encoding='utf-8-sig') as f:
    raw = f.read()
def has_jsonc_comment(text):
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '/' and i + 1 < len(text) and text[i + 1] in ('/', '*'):
                return True
        i += 1
    return False
if has_jsonc_comment(raw):
    print(f"JSONC_ERR:{src} contains // or /* — strict JSON required", file=sys.stderr); sys.exit(5)
data = json.loads(raw)
changed = []
if isinstance(data.get('permissions'), dict) and \
   data['permissions'].get('defaultMode') == 'bypassPermissions':
    data['permissions']['defaultMode'] = 'default'
    changed.append('permissions.defaultMode=default')
if data.get('skipDangerousModePermissionPrompt') is True:
    del data['skipDangerousModePermissionPrompt']
    changed.append('removed:skipDangerousModePermissionPrompt')
# Capture original mode BEFORE write (Codex concern #6 — preserve perms).
orig_mode = stat.S_IMODE(os.stat(src).st_mode)
src_dir = os.path.dirname(src) or '.'
fd, tmp = tempfile.mkstemp(prefix='.settings-migrate-', dir=src_dir)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False); f.write('\n')
    os.chmod(tmp, orig_mode)        # preserve original perm bits
    os.replace(tmp, src)            # atomic same-FS swap (POSIX)
except Exception:
    if os.path.exists(tmp): os.unlink(tmp)
    raise
print('|'.join(changed), end='')
PYEOF
)"
      python3 -c "$migrate_script" "$HOME_DIR/.claude/settings.json"
      ok "  $HOME_DIR/.claude/settings.json migrated (original mode preserved)"
    else
      warn "  security migration deferred — legacy bypass keys still present."
      warn "  apply later with: VEPOL_APPLY_C01=1 ./install.sh --apply"
      warn "  (or fix ~/.claude/settings.json manually). Install continues."
      NEEDS_SECURITY_MIGRATION=1
    fi
  fi
fi

# ─────────────────────────────────────────
# Step 3c. Session hooks for a pre-existing ~/.claude/settings.json.
# A settings.json created from the template above already has them; an
# existing one gets only the missing SessionStart/SessionEnd/PreCompact
# entries, through kb-claude-hooks (backup kept, everything else untouched).
# ─────────────────────────────────────────
HOOKS_TOOL="$HUB/bin/kb-claude-hooks"
HOOKS_CMD="~/knowledge/bin/kb-claude-hooks --apply"
if [[ "$SETTINGS_MERGEABLE" -eq 1 ]]; then
  if [[ -x "$HOOKS_TOOL" ]]; then
    set +e
    hooks_check="$("$HOOKS_TOOL" --check --settings "$HOME_DIR/.claude/settings.json" 2>&1)"
    hooks_rc=$?
    set -e
    if [[ "$hooks_rc" -eq 0 ]]; then
      ok "  Vepol session hooks present in $HOME_DIR/.claude/settings.json"
    elif [[ "$hooks_rc" -eq 1 ]]; then
      say "Step 3c · Vepol's session hooks are missing from your existing settings.json"
      [[ -n "$hooks_check" ]] && printf '%s\n' "$hooks_check" | sed 's/^/    /'
      echo "  Without them agents start without the knowledge-base context and"
      echo "  sessions are not captured."
      if _want VEPOL_MERGE_HOOKS "Add Vepol's session hooks to your existing settings.json? A backup is kept."; then
        if "$HOOKS_TOOL" --apply --settings "$HOME_DIR/.claude/settings.json"; then
          ok "  session hooks added to $HOME_DIR/.claude/settings.json"
        else
          warn "  could not add the session hooks — run later: $HOOKS_CMD"
        fi
      else
        warn "  session hooks not added — add them any time with: $HOOKS_CMD"
      fi
    else
      warn "  could not check the session hooks (kb-claude-hooks exit $hooks_rc) — run: ~/knowledge/bin/kb-claude-hooks --check"
    fi
  else
    warn "  kb-claude-hooks not found — compare the hooks in $HOME_DIR/.claude/settings.json"
    warn "    with $VEPOL_DIR/claude/settings.json.template (SessionStart, SessionEnd, PreCompact)"
  fi
fi
# For the receipt: are all three hooks in settings.json after this run? on = yes
# (written with the template, already there, or merged now), off = at least one
# is missing, unknown = the file could not be checked.
OPT_HOOKS=unknown
if [[ -x "$HOOKS_TOOL" && -f "$HOME_DIR/.claude/settings.json" ]]; then
  set +e
  "$HOOKS_TOOL" --check --settings "$HOME_DIR/.claude/settings.json" >/dev/null 2>&1
  case $? in 0) OPT_HOOKS=on ;; 1) OPT_HOOKS=off ;; esac
  set -e
fi

# ─────────────────────────────────────────
# Step 4. Optional legacy ~/.gemini/GEMINI.md
# ─────────────────────────────────────────
say "Step 4 · Checking optional Gemini CLI adapter (~/.gemini/GEMINI.md)"
# Nothing Vepol ships needs ~/.gemini; it is created only to hold a shipped adapter.
if [[ -f "$VEPOL_DIR/gemini/GEMINI.md" && ! -f "$HOME_DIR/.gemini/GEMINI.md" ]]; then
  mkdir -p "$HOME_DIR/.gemini"
  sed "s|__HOME__|$HOME_DIR|g" "$VEPOL_DIR/gemini/GEMINI.md" > "$HOME_DIR/.gemini/GEMINI.md"
  ok "  $HOME_DIR/.gemini/GEMINI.md created"
elif [[ -f "$VEPOL_DIR/gemini/GEMINI.md" && -f "$HOME_DIR/.gemini/GEMINI.md" ]]; then
  warn "  $HOME_DIR/.gemini/GEMINI.md already exists — merge $VEPOL_DIR/gemini/GEMINI.md manually"
elif [[ -f "$HOME_DIR/.gemini/GEMINI.md" ]]; then
  ok "  existing legacy Gemini CLI adapter left unchanged"
else
  ok "  Gemini CLI global adapter not shipped — AGENTS.md is canonical"
fi

# ─────────────────────────────────────────
# Step 5. Claude skills
# ─────────────────────────────────────────
say "Step 5 · Installing Claude skills"
if [[ -d "$VEPOL_DIR/claude/skills" ]]; then
  for skill_dir in "$VEPOL_DIR"/claude/skills/*; do
    [[ -d "$skill_dir" && -f "$skill_dir/SKILL.md" ]] || continue
    skill_name="$(basename "$skill_dir")"
    dest="$HOME_DIR/.claude/skills/$skill_name"
    mkdir -p "$dest"
    # Ownership marker: only SKILL.md files Vepol installed carry .vepol-managed.
    # Never clobber a pre-existing user SKILL.md we don't own — back it up first.
    if [[ -f "$dest/SKILL.md" && ! -f "$dest/.vepol-managed" ]]; then
      bak="$dest/SKILL.md.pre-vepol.$(date +%Y%m%d%H%M%S)"
      mv "$dest/SKILL.md" "$bak"
      warn "  preserved your existing $skill_name/SKILL.md as $(basename "$bak")"
    fi
    cp "$skill_dir/SKILL.md" "$dest/SKILL.md"
    : > "$dest/.vepol-managed"
    ok "  $skill_name skill ready"
  done
fi

# ─────────────────────────────────────────
# Step 6. Optional · LaunchAgents (opt-in)
# ─────────────────────────────────────────
say "Step 6 · Optional features (opt-in)"
echo "  Vepol can run scheduled background tasks via macOS LaunchAgents:"
echo "    • tick (every 15 min) — runs the routines in knowledge/personal/processes.yaml"
echo "      when they are due: morning brief, evening retro, mail, learning and audio"
echo "      digests, people reminders, …"
echo "    • planner (daily at 00:05) — writes the day's schedule that tick follows"
echo "      (knowledge/logs/today-plan.json)"
echo "    • orchestrator-cycle (07:30 and 20:45, experimental) — dispatches an approved"
echo "      multi-project plan in the morning and runs the project retro cycle in the"
echo "      evening, only for projects you opt in (cycle_enabled: true)"
echo "    • people-review-bot (always on) — listens for Telegram review buttons on"
echo "      staged contacts; idle until TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set"
echo "      in personal/.secrets"

# Note: People follow-up reminders run as a kb-tick process (processes.yaml)
# since the 2026-06-10 processes release — no standalone people-remind
# LaunchAgent is installed anymore (its /usr/bin/env python3 invocation broke
# under launchd's default PATH: no frontmatter/click in system Python).
if _want VEPOL_ENABLE_LAUNCHD "Install scheduled tasks?"; then
  OPT_LAUNCHD=on
  rm -f "$HUB/.orchestrator/launchagents.opted-out"
  LA_DIR="$HOME_DIR/Library/LaunchAgents"
  mkdir -p "$LA_DIR"
  for name in com.knowledge.tick com.knowledge.planner com.knowledge.orchestrator-cycle com.knowledge.people-review-bot; do
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
elif _unset_in_apply VEPOL_ENABLE_LAUNCHD \
     && compgen -G "$HOME_DIR/Library/LaunchAgents/com.knowledge.*.plist" >/dev/null; then
  OPT_LAUNCHD=on
  ok "  Scheduled tasks already installed — kept as they are"
else
  printf 'declined_at=%s\n' "$(date -Iseconds 2>/dev/null || date)" > "$HUB/.orchestrator/launchagents.opted-out"
  ok "  Skipped scheduled tasks (re-run install.sh anytime to enable)"
fi

# ─────────────────────────────────────────
# Step 6. Optional · Telegram channel
# ─────────────────────────────────────────
echo
echo "  Telegram delivery (morning brief, evening retro, digests, review buttons):"
echo "    put TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in $HUB/personal/.secrets."
echo "    Token: create a bot with @BotFather. Chat id: send the bot a message, then open"
echo "    https://api.telegram.org/bot<token>/getUpdates and read chat.id."
echo "    Until both are set, briefs and digests are saved in $HUB but not sent."
echo "  Separately, Claude Code's own Telegram plugin lets you chat with Claude through"
echo "  Telegram (needs bun). Its token goes in $HOME_DIR/.claude/channels/telegram/.env"
echo "  and must be a DIFFERENT bot: two listeners on one bot steal each other's updates."

if _want VEPOL_ENABLE_TELEGRAM "Create the Claude Code Telegram plugin scaffold (a second bot; token filled later)?"; then
  OPT_TELEGRAM=on
  TG_DIR="$HOME_DIR/.claude/channels/telegram"
  mkdir -p "$TG_DIR/approved"
  if [[ ! -f "$TG_DIR/.env" ]]; then
    cat > "$TG_DIR/.env" <<'TGEOF'
TELEGRAM_BOT_TOKEN=
TGEOF
    chmod 600 "$TG_DIR/.env"
    ok "  $TG_DIR/.env created — paste the token of a bot used only for chatting with Claude"
  fi
fi

# ─────────────────────────────────────────
# Step 6 · Digest audio route (local Qwen or NotebookLM)
# A failed local Qwen install never aborts the install: the NotebookLM route
# stays as it is and the reason is printed.
# ─────────────────────────────────────────
if [[ "$ASK_AUDIO_BACKEND" -eq 1 ]]; then
  echo
  echo "  Audio digests: local Qwen renders MP3 on this Mac and sends it to Telegram"
  echo "  (Apple Silicon, uv, ffmpeg and ~10 GiB free disk; downloads the model now)."
  echo "  NotebookLM needs no download but does not deliver audio to Telegram."
  if ask "Use local Qwen for digest audio and send MP3 to Telegram? (No keeps NotebookLM)"; then
    AUDIO_BACKEND="local_qwen"
  else
    AUDIO_BACKEND="notebooklm"
  fi
fi
AUDIO_FAILED=0
if [[ "$AUDIO_BACKEND" == "local_qwen" ]]; then
  say "Installing local Qwen audio (kb-tts-install)…"
  tts_out="$(mktemp)"
  set +e
  "$HUB/bin/kb-tts-install" 2>&1 | tee "$tts_out" | tee -a "$LOG"
  tts_rc=${PIPESTATUS[0]}
  set -e
  tts_reason="$(grep -v '^[[:space:]]*$' "$tts_out" | tail -1 || true)"
  rm -f "$tts_out"
  if [[ "$tts_rc" -eq 0 ]]; then
    "$HUB/bin/kb-digest-migrate" --file "$PROCESSES_FILE" --audio-backend local_qwen
    ok "  digest audio backend: local Qwen → Telegram"
    AUDIO_RESULT="local_qwen"
  else
    AUDIO_FAILED=1
    AUDIO_RESULT="local_qwen-failed"
    warn "  local Qwen audio was not installed (kb-tts-install exit $tts_rc): ${tts_reason:-no reason printed}"
    warn "    the digest audio route is unchanged (NotebookLM on a new install); the install continues."
    warn "    Fix the cause, then run: ~/knowledge/bin/kb-tts-install && ~/knowledge/bin/kb-digest-migrate --file $PROCESSES_FILE --audio-backend local_qwen"
  fi
elif [[ "$AUDIO_BACKEND" == "notebooklm" ]]; then
  "$HUB/bin/kb-digest-migrate" --file "$PROCESSES_FILE" --audio-backend notebooklm
  ok "  digest audio backend: NotebookLM"
  AUDIO_RESULT="notebooklm"
elif [[ "$PROCESSES_CREATED" -eq 1 ]]; then
  ok "  digest audio backend: NotebookLM (the default for a new install)"
else
  ok "  existing digest audio backend preserved"
fi

# ─────────────────────────────────────────
# Step 6b. C-02 (extended) — enforce mode on secret-bearing paths.
# security-model v2 § P0 C-02 extended scope.
# Refuses symlinks. Idempotent. Skips absent paths.
# ─────────────────────────────────────────
say "Step 6b · Enforcing modes on secret-bearing paths (security-model v2 C-02)"
enforced=0; skipped=0

_enforce_mode() {
  local target="$1" mode="$2"
  [[ -e "$target" ]] || return 0
  if [[ -L "$target" ]]; then
    warn "  refusing symlink: $target (C-02 forbids symlinked secret paths)"
    skipped=$((skipped + 1)); return 0
  fi
  chmod "$mode" "$target"; enforced=$((enforced + 1))
}

BOTS_DIR="$HOME_DIR/.claude/channels/bots"
if [[ -d "$BOTS_DIR" && ! -L "$BOTS_DIR" ]]; then
  _enforce_mode "$BOTS_DIR" 700
  for env_file in "$BOTS_DIR"/*.env; do
    [[ -e "$env_file" ]] || continue
    if [[ -L "$env_file" ]]; then warn "  refusing symlink: $env_file"; skipped=$((skipped+1)); continue; fi
    chmod 600 "$env_file"; enforced=$((enforced + 1))
  done
fi

_enforce_mode "$HUB/personal" 700
_enforce_mode "$HUB/personal/.secrets" 600
_enforce_mode "$HUB/personal/daily-research.yaml" 600
_enforce_mode "$HUB/personal/processes.yaml" 600
_enforce_mode "$HUB/personal/profile.yaml" 600

_enforce_mode "$HOME_DIR/.orchestrator" 700
_enforce_mode "$HOME_DIR/.orchestrator/multibot" 700
_enforce_mode "$HOME_DIR/.orchestrator/multibot.env" 600
_enforce_mode "$HOME_DIR/.orchestrator/multibot-supervisor.session" 600

[[ "$enforced" -gt 0 ]] && ok "  enforced modes on $enforced path(s)"
[[ "$skipped"  -gt 0 ]] && warn "  skipped $skipped symlinked entry(ies) — review manually"

# ─────────────────────────────────────────
# Step 7. Optional · claude-memory-compiler (auto session capture)
# ─────────────────────────────────────────
echo
echo "  Vepol can auto-capture every Claude Code session into your daily log"
echo "  via a small open-source companion tool (claude-memory-compiler)."

if _want VEPOL_ENABLE_MEMORY_COMPILER "Install claude-memory-compiler for automatic session capture?"; then
  OPT_MEMORY=on
  rm -f "$HUB/.orchestrator/memory-compiler.opted-out"
  COMPILER="$HOME_DIR/claude-memory-compiler"
  # Pinned to the upstream commit patches/claude-memory-compiler.diff was
  # tested against, so upstream changes cannot make the patch drift.
  COMPILER_PIN="54eddd709e83d3be244e9c56c9fc3a6cf375d534"
  if [[ ! -d "$COMPILER/.git" ]]; then
    say "  cloning claude-memory-compiler…"
    if git clone --quiet https://github.com/coleam00/claude-memory-compiler.git "$COMPILER" 2>/dev/null; then
      if git -C "$COMPILER" -c advice.detachedHead=false checkout --quiet "$COMPILER_PIN" 2>/dev/null; then
        ok "  cloned to $COMPILER (pinned to ${COMPILER_PIN:0:7})"
      else
        warn "  cloned to $COMPILER, but could not check out the tested commit ${COMPILER_PIN:0:7} — the patch may not apply"
      fi
    else
      warn "  clone failed — install manually later"
    fi
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
    else
      warn "    uv not found — session capture needs it: brew install uv, then: cd $COMPILER && uv sync"
    fi
  fi
elif _unset_in_apply VEPOL_ENABLE_MEMORY_COMPILER && [[ -d "$HOME_DIR/claude-memory-compiler" ]]; then
  OPT_MEMORY=on
  ok "  Session capture already installed — kept as it is"
else
  printf 'declined_at=%s\n' "$(date -Iseconds 2>/dev/null || date)" > "$HUB/.orchestrator/memory-compiler.opted-out"
  ok "  Skipped session capture (re-run install.sh anytime to enable)"
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

if [[ -x "$HUB/bin/kb-bootstrap-manifest" ]]; then
  say "Bootstrapping install manifest…"
  KB_HUB="$HUB" "$HUB/bin/kb-bootstrap-manifest" --force --seed-path "$VEPOL_DIR" >/dev/null
  ok "install manifest written"
fi

# 8a. kb-doctor
if [[ -x "$HUB/bin/kb-doctor" ]]; then
  say "Running kb-doctor (system health check)…"
  set +e
  doctor_out="$(KB_HUB="$HUB" "$HUB/bin/kb-doctor" install-health --strict 2>&1)"
  RC=$?
  set -e
  # The report opens with the summary line and lists findings most severe first,
  # so a long one is cut at the bottom, never at the top. The log keeps all of it.
  if [[ -n "$doctor_out" ]]; then
    printf '%s\n' "$doctor_out" >> "$LOG"
    printf '%s\n' "$doctor_out" | awk -v max=40 -v cmd="$HUB/bin/kb-doctor install-health" '
      NR <= max { print }
      END { if (NR > max) printf "  … %d more line(s) not shown — see all of it: %s\n", NR - max, cmd }'
  fi
  if [[ "$RC" -eq 0 ]]; then
    ok "kb-doctor passed"
  else
    warn "kb-doctor reported issues (exit $RC) — review above"
  fi
else
  warn "kb-doctor not executable — check $HUB/bin/kb-doctor"
fi

# 8a-receipt. Install receipt — written by the installer (spine), safe even on a
# partial hub. The prompt-first agent reads this back to the user. (spec A6)
mkdir -p "$HUB/install/receipts" 2>/dev/null || true
RECEIPT="$HUB/install/receipts/$(date +%Y-%m-%d-%H%M%S).md"
if cat > "$RECEIPT" <<RECEOF 2>/dev/null
# Vepol install receipt

- version: $VEPOL_VERSION
- mode: $MODE
- when: $(date -Iseconds 2>/dev/null || date)
- hub: $HUB
- kb_doctor_exit: ${RC:-NA}
- needs_security_migration: ${NEEDS_SECURITY_MIGRATION:-0}
- opt_ins: launchd=$OPT_LAUNCHD telegram=$OPT_TELEGRAM memory_compiler=$OPT_MEMORY session_hooks=$OPT_HOOKS
- audio_backend: $AUDIO_RESULT
RECEOF
then
  ok "  install receipt: $RECEIPT"
fi

# 8b. Suggested next steps
cat <<NEXT

${C_INFO}━━━ Try these next ━━━${C_OFF}

  ${C_DIM}# Check the install (commands, hooks, scheduled tasks, tools):${C_OFF}
  $HUB/bin/kb-doctor install-health

  ${C_DIM}# Write your first task into the knowledge base:${C_OFF}
  $HUB/bin/kb-task "My first Vepol task"

  ${C_DIM}# Confirm retrieval works:${C_OFF}
  $HUB/bin/kb-search "first Vepol"

  ${C_DIM}# Capture your first idea (needs the Python packages from requirements.txt):${C_OFF}
  $HUB/bin/kb-idea capture "My first Vepol idea" --source chat

  ${C_DIM}# A sample brief from an invented hub: calls a model, sends nothing.${C_OFF}
  ${C_DIM}# Needs a signed-in Claude Code or Codex (see Manual steps below).${C_OFF}
  $HUB/bin/kb-demo brief

${C_INFO}━━━ Read next ━━━${C_OFF}

  ${C_DIM}# Canonical hub contract (how the knowledge base is organized):${C_OFF}
  $HUB/AGENTS.md

  ${C_DIM}# Claude Code adapter (loads the canonical contract):${C_OFF}
  $HUB/CLAUDE.md

NEXT

if [[ -f "$HUB/_template/GEMINI.md" ]]; then
  cat <<NEXT
  ${C_DIM}# Gemini CLI project-context template (if you use Gemini CLI):${C_OFF}
  $HUB/_template/GEMINI.md

NEXT
fi

cat <<NEXT
  ${C_DIM}# Global Claude Code conventions (your edits stay; managed block updates):${C_OFF}
  $HOME_DIR/.claude/CLAUDE.md

NEXT

if [[ -f "$HOME_DIR/.gemini/GEMINI.md" ]]; then
  cat <<NEXT
  ${C_DIM}# Global Antigravity / legacy Gemini CLI adapter (loads the canonical contract):${C_OFF}
  $HOME_DIR/.gemini/GEMINI.md

NEXT
fi

cat <<NEXT
  ${C_DIM}# Methodology pages (if shipped):${C_OFF}
  $VEPOL_DIR/docs/methodology/

${C_INFO}━━━ Manual steps remaining ━━━${C_OFF}

  1. Authenticate Claude Code (if not yet):
       claude auth login

  2. Optional — enable cross-agent review with Codex CLI:
       codex login                      # or place API key in ~/.codex/auth.json
     (install: $CODEX_INSTALL_HINT;
      $CODEX_LOOKUP_HINT)

  3. Optional — get the morning brief, retro and digests in Telegram:
       put TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID into
       $HUB/personal/.secrets
       Chat id: send your bot a message, then open
       https://api.telegram.org/bot<token>/getUpdates and read chat.id.
     $HOME_DIR/.claude/channels/telegram/.env is only for Claude Code's
     Telegram plugin (chatting with Claude) and must use a different bot.

  4. To start a wiki in your first project:
       cd <your-project>
       open Claude Code there (run: claude) and type /init-kb

${C_INFO}━━━ Stay in touch ━━━${C_OFF}

  Issues / questions:  https://github.com/nahornyi-ai-lab/vepol/issues
  Discussions:         https://github.com/nahornyi-ai-lab/vepol/discussions
  Sponsor:             https://github.com/sponsors/nahornyi-ai-lab

  Your feedback shapes Vepol: open an issue or a discussion.

NEXT

ok "Bootstrap complete — full log: $LOG"

if [[ "$AUDIO_FAILED" -eq 1 ]]; then
  warn "Local Qwen digest audio was requested but not installed — see the reason above."
  # Everything else is installed. --apply reports the requested-but-missing
  # part as a partial install so an agent notices; interactive installs end 0.
  [[ "$MODE" == "apply" ]] && exit 11
fi
exit 0
