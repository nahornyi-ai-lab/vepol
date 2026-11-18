#!/usr/bin/env bash
# uninstall.sh — remove ONLY Vepol-managed files. Never touches user data.
#
# Removed (managed): bin/ symlinks into the seed, orchestrator-seed pointer,
#   ~/.claude/.vepol/, the VEPOL MANAGED include block in ~/.claude/CLAUDE.md,
#   installed Claude skills, the com.knowledge.* LaunchAgents made from this
#   repo's launchd/ templates (unloaded first; other com.knowledge.* are kept).
# NEVER removed (user data): your hub itself and everything in it that you own —
#   raw/, daily/, projects/, personal/, concepts/, sources/, *.md, security/,
#   install/receipts/. The hub directory is left in place.
# Left in place and listed at the end with how to remove them: Vepol's hooks
#   in ~/.claude/settings.json, ~/.claude/statusline-command.sh,
#   ~/claude-memory-compiler, the local Qwen voice in ~/.local/share/vepol-qwen-tts.
#
# Flags:
#   --dry-run   list what would be removed, change nothing
#   --yes       do not prompt for confirmation
#   --backup-user-data  tar the hub to ~/vepol-knowledge-backup-<ts>.tgz first
#
# Project: https://github.com/nahornyi-ai-lab/vepol

set -euo pipefail

VEPOL_DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${HOME}"
HUB="${VEPOL_HUB:-$HOME_DIR/knowledge}"

DRY=0; YES=0; BACKUP=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --yes|-y)  YES=1 ;;
    --backup-user-data) BACKUP=1 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'uninstall.sh: unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

if [[ -t 1 ]]; then C_I=$'\033[1;36m'; C_OK=$'\033[1;32m'; C_W=$'\033[1;33m'; C_O=$'\033[0m'
else C_I=''; C_OK=''; C_W=''; C_O=''; fi
say()  { printf '%s==>%s %s\n' "$C_I" "$C_O" "$1"; }
ok()   { printf '%s ✓%s  %s\n' "$C_OK" "$C_O" "$1"; }
warn() { printf '%s !%s  %s\n' "$C_W" "$C_O" "$1" >&2; }
act()  { # act <description> <command...> — honors --dry-run
  if [[ "$DRY" -eq 1 ]]; then printf '   would remove: %s\n' "$1"; else "${@:2}" 2>/dev/null && ok "removed: $1" || true; fi
}

say "Vepol uninstall — managed files only. Hub & user data are preserved."
echo "  hub:  $HUB   (NOT deleted)"
echo "  seed: $VEPOL_DIR"
[[ "$DRY" -eq 1 ]] && warn "dry-run: nothing will be changed"

if [[ "$DRY" -eq 0 && "$YES" -eq 0 && "${VEPOL_NONINTERACTIVE:-0}" != "1" ]]; then
  printf '%s ?%s  Remove Vepol-managed files now (your data stays)? [y/N] ' "$C_I" "$C_O"
  read -r a; [[ "$a" =~ ^[Yy]$ ]] || { warn "aborted"; exit 0; }
fi

# Optional backup of the whole hub (user data) before touching anything.
if [[ "$BACKUP" -eq 1 && -d "$HUB" ]]; then
  TB="$HOME_DIR/vepol-knowledge-backup-$(date +%Y-%m-%d-%H%M%S).tgz"
  if [[ "$DRY" -eq 1 ]]; then printf '   would back up hub to: %s\n' "$TB"
  else tar -czf "$TB" -C "$(dirname "$HUB")" "$(basename "$HUB")" && ok "hub backed up: $TB"; fi
fi

# 1. bin/ symlinks — drift-proof AND path-canonical managed-only rule. install
#    always creates $HUB/bin/<name> -> $VEPOL_DIR/bin/<name> (link name == target
#    basename, target in the seed bin). A link is "managed" iff: its name equals its
#    target's basename AND the target's directory, resolved to a physical path,
#    equals the seed bin's physical path. Resolving with `pwd -P` makes the check
#    immune to path aliasing (/tmp vs /private/tmp, a symlinked seed path, running
#    via $HUB/orchestrator-seed, trailing slashes) — string compares are not. This
#    catches every managed link now/future (incl. dangling ones whose target file
#    was removed) and never touches a user alias (name != target basename).
if [[ -d "$HUB/bin" ]]; then
  seed_bin_real="$(cd "$VEPOL_DIR/bin" 2>/dev/null && pwd -P || printf '%s' "$VEPOL_DIR/bin")"
  while IFS= read -r link; do
    name="$(basename "$link")"
    tgt="$(readlink "$link" 2>/dev/null || true)"
    [[ -n "$tgt" ]] || continue
    tdir="$(cd "$(dirname "$tgt")" 2>/dev/null && pwd -P || true)"
    if [[ "$name" == "$(basename "$tgt")" && -n "$tdir" && "$tdir" == "$seed_bin_real" ]]; then
      act "$link" rm -f "$link"
    elif [[ "$DRY" -eq 1 ]]; then
      printf '   keeping (not Vepol-managed): %s -> %s\n' "$link" "$tgt"
    fi
  done < <(find "$HUB/bin" -maxdepth 1 -type l 2>/dev/null)
fi

# 2. orchestrator-seed pointer (only if it's a symlink we made).
[[ -L "$HUB/orchestrator-seed" ]] && act "$HUB/orchestrator-seed" rm -f "$HUB/orchestrator-seed"

# 3. ~/.claude/.vepol/ managed dir.
[[ -d "$HOME_DIR/.claude/.vepol" ]] && act "$HOME_DIR/.claude/.vepol" rm -rf "$HOME_DIR/.claude/.vepol"

# 4. Strip the VEPOL MANAGED include block from ~/.claude/CLAUDE.md — remove ONLY
#    a block the installer writes, not arbitrary text between a stray BEGIN and
#    END that a user may have typed. Recognised: a "<!-- BEGIN VEPOL MANAGED ... -->"
#    line, then one to three lines that each reference the managed file — the
#    legacy "<!-- @include ~/.claude/.vepol/CLAUDE.managed.md -->" comment or a
#    Claude Code import line "@<path>/.vepol/CLAUDE.managed.md" — then
#    "<!-- END VEPOL MANAGED -->". Anything else inside the markers keeps the block.
CM="$HOME_DIR/.claude/CLAUDE.md"
if [[ -f "$CM" ]] && grep -qF "BEGIN VEPOL MANAGED" "$CM"; then
  if [[ "$DRY" -eq 1 ]]; then printf '   would strip the exact VEPOL MANAGED block from: %s\n' "$CM"
  else
    strip_rc=0
    python3 - "$CM" <<'PY' || strip_rc=$?
import re, sys
p = sys.argv[1]
BEGIN = re.compile(r"^<!-- BEGIN VEPOL MANAGED\b.*-->$")
END = "<!-- END VEPOL MANAGED -->"
INNER = (
    re.compile(r"^<!-- @include ~/\.claude/\.vepol/CLAUDE\.managed\.md -->$"),  # legacy
    re.compile(r"^@\S*\.vepol/CLAUDE\.managed\.md$"),                         # @import
)
lines = open(p, encoding="utf-8").read().split("\n")

def block_end(k):
    """Index of the END line if a recognised block starts at k, else None."""
    if not BEGIN.match(lines[k].strip()):
        return None
    j = k + 1
    while j < len(lines) and j <= k + 3 and any(r.match(lines[j].strip()) for r in INNER):
        j += 1
    if j > k + 1 and j < len(lines) and lines[j].strip() == END:
        return j
    return None

out = []; k = 0; n = len(lines); removed = False
while k < n:
    end = None if removed else block_end(k)
    if end is not None:
        k = end + 1
        while k < n and lines[k].strip() == "":  # drop trailing blank lines
            k += 1
        removed = True
        continue
    out.append(lines[k]); k += 1
if not removed:
    sys.exit(3)
open(p, "w", encoding="utf-8").write("\n".join(out))
PY
    if [[ "$strip_rc" -eq 0 ]]; then
      ok "stripped VEPOL MANAGED block from $CM (your content kept)"
    elif [[ "$strip_rc" -eq 3 ]]; then
      warn "$CM has a VEPOL MANAGED marker but not a block uninstall.sh wrote — left unchanged; remove it by hand"
    else
      warn "could not edit $CM (python3 exit $strip_rc) — remove the VEPOL MANAGED block by hand"
    fi
  fi
fi

# 5. Installed Claude skills — remove ONLY skills carrying Vepol's ownership marker
#    (.vepol-managed). A user's own same-named SKILL.md (no marker) is left alone.
#    We remove only SKILL.md + the marker, then rmdir if the dir is now empty, so
#    any sidecar files a user added are preserved.
if [[ -d "$VEPOL_DIR/claude/skills" ]]; then
  for sd in "$VEPOL_DIR"/claude/skills/*; do
    [[ -d "$sd" ]] || continue
    name="$(basename "$sd")"
    target="$HOME_DIR/.claude/skills/$name"
    [[ -f "$target/.vepol-managed" ]] || { [[ "$DRY" -eq 1 && -e "$target" ]] && printf '   keeping (not Vepol-owned): %s\n' "$target"; continue; }
    act "$target/SKILL.md" rm -f "$target/SKILL.md"
    [[ "$DRY" -eq 0 ]] && rm -f "$target/.vepol-managed"
    [[ "$DRY" -eq 0 ]] && rmdir "$target" 2>/dev/null && ok "removed empty skill dir: $target" || true
  done
fi

# 6. LaunchAgents — every agent made from a launchd/ template in this repo.
#    install.sh loads tick, planner, orchestrator-cycle and people-review-bot;
#    channel-telegram and multibot-supervisor are rendered from the same
#    templates by hand (see docs/multibot-runbook.md). All of them run scripts
#    from $HUB/bin, and the KeepAlive ones would keep restarting against the
#    links removed above, so each is unloaded before its plist is deleted.
LA="$HOME_DIR/Library/LaunchAgents"
for name in com.knowledge.tick com.knowledge.planner com.knowledge.orchestrator-cycle \
            com.knowledge.people-review-bot com.knowledge.channel-telegram \
            com.knowledge.multibot-supervisor; do
  plist="$LA/$name.plist"
  [[ -f "$plist" ]] || continue
  if [[ "$DRY" -eq 1 ]]; then printf '   would unload+remove: %s\n' "$plist"
  else
    launchctl bootout "gui/$(id -u)/$name" 2>/dev/null || launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist" && ok "removed LaunchAgent: $name"
  fi
done

echo
if [[ "$DRY" -eq 1 ]]; then
  say "dry-run complete — nothing changed."
else
  ok "Vepol-managed files removed."
fi

# 7. What stays on purpose: these may carry the user's own settings or large
#    downloads, so uninstall only names them and says how to remove each one.
echo
if [[ "$DRY" -eq 1 ]]; then say "Would be left in place (remove by hand if you want them gone):"
else say "Left in place on purpose (remove by hand if you want them gone):"; fi
kept=0
SJ="$HOME_DIR/.claude/settings.json"
if [[ -f "$SJ" ]] && grep -qE 'knowledge/bin/kb-(session-start|session-end|pre-compact)' "$SJ"; then
  echo "  - $SJ: Vepol's Claude Code hooks, which run ~/knowledge/bin scripts this uninstall removes."
  echo "    Copy the file first, then delete the entries under hooks.SessionStart, hooks.SessionEnd"
  echo "    and hooks.PreCompact whose command runs ~/knowledge/bin/kb-session-start, kb-session-end"
  echo "    or kb-pre-compact (they were added by install.sh or kb-claude-hooks)."
  kept=1
fi
if [[ -f "$SJ" ]] && grep -qF '.claude/statusline-command.sh' "$SJ"; then
  echo "  - $SJ: the \"statusLine\" key that runs ~/.claude/statusline-command.sh; delete it"
  echo "    before removing that script."
  kept=1
fi
if [[ -f "$HOME_DIR/.claude/statusline-command.sh" ]]; then
  echo "  - $HOME_DIR/.claude/statusline-command.sh (status line script):"
  echo "    rm \"$HOME_DIR/.claude/statusline-command.sh\""
  kept=1
fi
if [[ -d "$HOME_DIR/claude-memory-compiler" ]]; then
  echo "  - $HOME_DIR/claude-memory-compiler (session capture tool):"
  echo "    rm -rf \"$HOME_DIR/claude-memory-compiler\""
  kept=1
fi
QWEN_DIR="${KB_TTS_HOME:-$HOME_DIR/.local/share/vepol-qwen-tts}"
if [[ -d "$QWEN_DIR" ]]; then
  echo "  - $QWEN_DIR (local Qwen voice: Python env and model files):"
  echo "    rm -rf \"$QWEN_DIR\""
  kept=1
fi
if [[ -d "$HOME_DIR/.claude/channels/telegram" ]]; then
  echo "  - $HOME_DIR/.claude/channels/telegram/ (Telegram channel scaffold; holds your bot token"
  echo "    if you added one, and Claude Code's Telegram plugin uses the same folder)"
  kept=1
fi
[[ "$kept" -eq 1 ]] || echo "  (nothing)"

if [[ -d "$HUB" ]]; then
  echo
  sz="$(du -sh "$HUB" 2>/dev/null | cut -f1 || echo '?')"
  echo "  Your knowledge hub is preserved at $HUB ($sz). Delete it manually if you really want it gone."
fi
