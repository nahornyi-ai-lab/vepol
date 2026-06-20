#!/usr/bin/env bash
# uninstall.sh — remove ONLY Vepol-managed files. Never touches user data.
#
# Removed (managed): bin/ symlinks into the seed, orchestrator-seed pointer,
#   ~/.claude/.vepol/, the VEPOL MANAGED include block in ~/.claude/CLAUDE.md,
#   installed Claude skills, com.knowledge.* LaunchAgents.
# NEVER removed (user data): your hub itself and everything in it that you own —
#   raw/, daily/, projects/, personal/, concepts/, sources/, *.md, security/,
#   install/receipts/. The hub directory is left in place.
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
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
#    the exact 3-line block the installer writes, not arbitrary text between a
#    stray BEGIN and END that a user may have typed.
CM="$HOME_DIR/.claude/CLAUDE.md"
INCLUDE_BEGIN="<!-- BEGIN VEPOL MANAGED — do not edit. Source: ~/.claude/.vepol/CLAUDE.managed.md -->"
INCLUDE_INNER="<!-- @include ~/.claude/.vepol/CLAUDE.managed.md -->"
INCLUDE_END="<!-- END VEPOL MANAGED -->"
if [[ -f "$CM" ]] && grep -qF "BEGIN VEPOL MANAGED" "$CM"; then
  if [[ "$DRY" -eq 1 ]]; then printf '   would strip the exact VEPOL MANAGED block from: %s\n' "$CM"
  else
    python3 - "$CM" "$INCLUDE_BEGIN" "$INCLUDE_INNER" "$INCLUDE_END" <<'PY'
import sys
p, b, i, e = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
lines = open(p, encoding="utf-8").read().split("\n")
out = []; k = 0; n = len(lines); removed = False
while k < n:
    if (not removed and lines[k].strip() == b.strip()
            and k + 2 < n and lines[k+1].strip() == i.strip()
            and lines[k+2].strip() == e.strip()):
        k += 3
        while k < n and lines[k].strip() == "":  # drop trailing blank lines
            k += 1
        removed = True
        continue
    out.append(lines[k]); k += 1
open(p, "w", encoding="utf-8").write("\n".join(out))
PY
    ok "stripped VEPOL MANAGED block from $CM (your content kept)"
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

# 6. LaunchAgents.
LA="$HOME_DIR/Library/LaunchAgents"
for name in com.knowledge.tick com.knowledge.planner com.knowledge.orchestrator-cycle; do
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
if [[ -d "$HUB" ]]; then
  sz="$(du -sh "$HUB" 2>/dev/null | cut -f1 || echo '?')"
  echo "  Your knowledge hub is preserved at $HUB ($sz). Delete it manually if you really want it gone."
fi
