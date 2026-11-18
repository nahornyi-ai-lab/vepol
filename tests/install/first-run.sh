#!/usr/bin/env bash
# tests/install/first-run.sh — what a new user (and an existing setup) gets
# from install.sh: rendered hub files, logs/, registry.md, the real Claude
# Code import, Telegram guidance, LaunchAgent descriptions, non-fatal local
# Qwen failure, session-hook merge, roster rows, prerequisite reporting.
#
# Runs against throwaway HOMEs and a STAGED COPY of the seed, so the fakes it
# installs (kb-tts-install, kb-claude-hooks when the real one is absent,
# launchctl, git clone) never touch the repo, the real launchd or the network.

set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0; FAIL=0
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
p() { printf '  ✓ %s\n' "$1"; PASS=$((PASS+1)); }
f() { printf '  ✘ %s\n' "$1"; FAIL=$((FAIL+1)); }
check() { local label="$1"; shift; if "$@"; then p "$label"; else f "$label"; fi; }

# ── Staged seed ──────────────────────────────────────────────────────────
SEED="$WORK/seed"; mkdir -p "$SEED"
for item in install.sh uninstall.sh VERSION requirements.txt bin _template knowledge claude launchd security patches; do
  [[ -e "$REPO/$item" ]] && cp -R "$REPO/$item" "$SEED/"
done
INSTALL="$SEED/install.sh"

# Fake local Qwen installer: fails like a Mac without ffmpeg unless told to
# succeed (silently — an install that prints nothing must not trip set -e).
cat > "$SEED/bin/kb-tts-install" <<'SH'
#!/usr/bin/env bash
if [[ "${KB_FAKE_TTS_MODE:-failure}" == success ]]; then exit 0; fi
echo "Runtime home: fake"
echo "required command is missing: ffmpeg" >&2
exit 1
SH
chmod +x "$SEED/bin/kb-tts-install"

# kb-claude-hooks (shared contract 3) is owned by another unit. Use the real
# one when it ships; otherwise a fake with the same CLI. A sentinel file next
# to settings.json stands for "hooks present".
REAL_HOOKS=0
if [[ -x "$SEED/bin/kb-claude-hooks" ]]; then
  REAL_HOOKS=1
else
  cat > "$SEED/bin/kb-claude-hooks" <<'SH'
#!/usr/bin/env bash
mode="${1:-}"; shift || true
settings="$HOME/.claude/settings.json"
[[ "${1:-}" == "--settings" ]] && settings="$2"
echo "$mode $settings" >> "$HOME/kb-claude-hooks.calls"
case "$mode" in
  --check) [[ -f "$settings.fake-hooks" ]] && exit 0
           grep -q kb-session-start "$settings" && grep -q kb-session-end "$settings" \
             && grep -q kb-pre-compact "$settings" && exit 0
           echo "missing: SessionStart SessionEnd PreCompact"; exit 1 ;;
  --apply) cp "$settings" "$settings.bak-fake"; : > "$settings.fake-hooks"; exit 0 ;;
esac
exit 2
SH
  chmod +x "$SEED/bin/kb-claude-hooks"
fi

# ── Tool PATH: what install.sh needs, NO node and NO bun, fake launchctl ──
TOOLS="$WORK/tools"; mkdir -p "$TOOLS"
wrap() {  # wrap <name>: exec the real binary (keeps a venv python3 a venv python3)
  local real; real="$(command -v "$1" 2>/dev/null || true)"
  [[ -n "$real" ]] || return 1
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" > "$TOOLS/$1"; chmod +x "$TOOLS/$1"
}
shim() { printf '#!/bin/sh\necho "%s test shim"\n' "$1" > "$TOOLS/$1"; chmod +x "$TOOLS/$1"; }
for t in python3 bash git jq; do wrap "$t" || true; done
wrap rg || shim rg
# Never the real agent CLIs: a claude shim, and a codex that refuses to run.
shim claude
printf '#!/bin/sh\necho "codex is disabled in tests" >&2\nexit 97\n' > "$TOOLS/codex"; chmod +x "$TOOLS/codex"
export KB_CLAUDE_BIN="$TOOLS/claude" KB_CODEX_BIN="$TOOLS/codex"
cat > "$TOOLS/launchctl" <<'SH'
#!/bin/sh
echo "$*" >> "$HOME/launchctl.calls"
exit 0
SH
chmod +x "$TOOLS/launchctl"
TPATH="$TOOLS:/usr/bin:/bin:/usr/sbin:/sbin"

run_install() {  # run_install <home> [env...] -- [install args...]; stdout+stderr → $home.out
  local home="$1"; shift
  local -a envs=()
  while [[ $# -gt 0 && "$1" != "--" ]]; do envs+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  mkdir -p "$home"
  env -u VEPOL_HUB -u KB_HUB -u KB_LANG -u VEPOL_MERGE_HOOKS -u VEPOL_ENABLE_LAUNCHD \
      -u VEPOL_ENABLE_TELEGRAM -u VEPOL_ENABLE_MEMORY_COMPILER \
      HOME="$home" PATH="$TPATH" LANG=en_US.UTF-8 VEPOL_NONINTERACTIVE=1 ${envs[@]+"${envs[@]}"} \
      "$INSTALL" "$@" > "$home.out" 2>&1
}
pyjson() { python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if ($1) else 1)"; }

echo "first-run install tests (seed=$SEED, real kb-claude-hooks=$REAL_HOOKS)"

# ── A. Fresh install, no node/bun on PATH ───────────────────────────────
A="$WORK/a"
check "test PATH really has no node and no bun" \
  bash -c "PATH='$TPATH'; ! command -v node >/dev/null && ! command -v bun >/dev/null"
run_install "$A"; rc=$?
H="$A/knowledge"
check "fresh install without node/bun → exit 0 (node/bun are optional)" [ "$rc" -eq 0 ]
check "optional tools named with what they enable (bun → Telegram plugin)" \
  grep -q "bun — Claude Code's Telegram plugin" "$A.out"
check "logs/ created for the LaunchAgents" [ -d "$H/logs" ]
left="$(grep -l '{{' "$H"/*.md 2>/dev/null)"
check "hub *.md have no {{placeholders}} left (${left:-none})" [ -z "$left" ]
check "index.md rendered for the hub" grep -qx '# Hub — wiki index' "$H/index.md"
check "log.md milestone names install.sh, with a real date" \
  grep -qE '^## \[[0-9]{4}-[0-9]{2}-[0-9]{2}\] milestone \| Hub created by `install.sh`$' "$H/log.md"
check "registry.md created (English form)" grep -qx '## personal / other' "$H/registry.md"
check "registry.md has the kb-rebuild-registry column header" \
  grep -qx '| slug | status | path | description |' "$H/registry.md"
check "registry.md: English headings say what each category is, no <placeholder>" \
  bash -c "grep -qx '## lab — research and experiments' '$H/registry.md' && grep -qx '## order — client work' '$H/registry.md' \
    && grep -qx '## pet — side projects' '$H/registry.md' && grep -qx '## job — employment' '$H/registry.md' \
    && ! grep -q '^## .*<' '$H/registry.md' && grep -q '^Each category groups projects of one kind' '$H/registry.md'"
dj="$(HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-doctor" --format json 2>/dev/null)"
check "kb-doctor accepts the fresh registry (no P0/P1, registry-no-projects info)" \
  pyjson '[x for x in (d.get("findings") if isinstance(d, dict) else d) if x["severity"] in ("P0","P1")] == [] and any(x["id"].startswith("registry-no-projects") for x in (d.get("findings") if isinstance(d, dict) else d))' <<< "$dj"
HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-rebuild-registry" bootstrap > "$WORK/boot.out" 2>&1; brc=$?
check "kb-rebuild-registry bootstrap on the fresh hub → exit 0 (no FileNotFoundError)" [ "$brc" -eq 0 ]
printf '| demo-proj | no-wiki | `~/demo-proj` | Demo project |\n' >> "$H/registry.md"
cp "$H/migration-2026-04-25.yaml" "$WORK/mig.first"
HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-rebuild-registry" bootstrap > "$WORK/boot2.out" 2>&1; brc=$?
check "bootstrap refuses to overwrite an existing migration table without --force" \
  bash -c "[ $brc -eq 2 ] && grep -q -- '--force' '$WORK/boot2.out' && cmp -s '$WORK/mig.first' '$H/migration-2026-04-25.yaml'"
HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-rebuild-registry" bootstrap --force > "$WORK/boot3.out" 2>&1
check "a row added under '## personal / other' is parsed by bootstrap --force" \
  bash -c "grep -q 'slug: demo-proj' '$H/migration-2026-04-25.yaml' && grep -A8 'slug: demo-proj' '$H/migration-2026-04-25.yaml' | grep -q 'category: personal'"
check "bootstrap --force keeps the old table as a .bak copy" \
  bash -c "cmp -s '$WORK/mig.first' \"\$(ls '$H'/migration-2026-04-25.yaml.bak-* | head -1)\""
# new-wiki on the installed hub: a client project with a description, and one
# added the way Desktop «Add project…» does it (folder and slug, no description;
# the project README then has `description: \"\"`). apply used to crash on it.
mkdir -p "$A/code/client-app" "$A/code/plain-app"
HOME="$A" PATH="$TPATH" "$H/bin/new-wiki" "$A/code/client-app" client-app order "Client app" > "$WORK/nw1.out" 2>&1
HOME="$A" PATH="$TPATH" "$H/bin/new-wiki" "$A/code/plain-app" plain-app > "$WORK/nw2.out" 2>&1
check "new-wiki puts an order project under '## order — client work'" \
  bash -c "sed -n '/^## order — client work/,/^## job/p' '$H/registry.md' | grep -q '^| client-app | seeded |'"
# A project with its own AGENTS.md (run twice): the text stays, one Vepol block.
mkdir -p "$A/code/own-rules"; printf '# Mine\nkeep me\n' > "$A/code/own-rules/AGENTS.md"
HOME="$A" PATH="$TPATH" "$H/bin/new-wiki" "$A/code/own-rules" own-rules > "$WORK/nw3.out" 2>&1
HOME="$A" PATH="$TPATH" "$H/bin/new-wiki" "$A/code/own-rules" own-rules > "$WORK/nw4.out" 2>&1
own_agents_ok() {
  local f="$A/code/own-rules/AGENTS.md"
  [[ "$(head -2 "$f")" == $'# Mine\nkeep me' ]] && [[ "$(grep -c 'BEGIN VEPOL' "$f")" == 1 ]] \
    && grep -Fq '`~/knowledge/bin/kb-session-start --print --cwd "$PWD"`' "$f" \
    && grep -q 'Vepol block appended' "$WORK/nw3.out" && grep -q "already loads Vepol's startup context" "$WORK/nw4.out"
}
check "existing AGENTS.md keeps its text and gets the Vepol startup block once" own_agents_ok
HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-rebuild-registry" bootstrap --force > "$WORK/boot4.out" 2>&1
HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-rebuild-registry" apply > "$WORK/apply.out" 2>&1; arc=$?
HOME="$A" KB_HUB="$H" PATH="$TPATH" "$H/bin/kb-rebuild-registry" check > "$WORK/check.out" 2>&1; crc=$?
check "new-wiki without a description → bootstrap → apply → check clean" \
  bash -c "[ $arc -eq 0 ] && [ $crc -eq 0 ] && ! grep -q Traceback '$WORK/apply.out' \
    && grep -A8 'slug: client-app' '$H/migration-2026-04-25.yaml' | grep -q 'category: order' \
    && grep -qx 'description: \"\"' '$A/code/plain-app/knowledge/README.md'"
check "no empty ~/.gemini created" [ ! -e "$A/.gemini" ]
cm_block="$(sed -n '1,3p' "$A/.claude/CLAUDE.md")"
check "~/.claude/CLAUDE.md block is a real @import between the markers" \
  [ "$cm_block" == "<!-- BEGIN VEPOL MANAGED — do not edit. Source: ~/.claude/.vepol/CLAUDE.managed.md -->
@~/.claude/.vepol/CLAUDE.managed.md
<!-- END VEPOL MANAGED -->" ]
check ".secrets explains the chat id and is honest about empty values" \
  bash -c "grep -q 'getUpdates' '$H/personal/.secrets' && grep -q 'NOT delivered' '$H/personal/.secrets' && ! grep -q 'Empty values are safe' '$H/personal/.secrets'"
check "Telegram text points the brief at personal/.secrets and warns about a second bot" \
  bash -c "grep -q 'put TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .*personal/.secrets' '$A.out' && grep -q 'DIFFERENT bot' '$A.out'"
check "next steps: interactive /init-kb, no 'claude -p', no Gemini CLI step" \
  bash -c "grep -q 'type /init-kb' '$A.out' && ! grep -q 'claude -p' '$A.out' && ! grep -q 'with Gemini CLI' '$A.out'"
check "LaunchAgent descriptions match what the agents do" \
  bash -c "grep -q 'tick (every 15 min)' '$A.out' && grep -q 'planner (daily at 00:05)' '$A.out' && grep -q 'orchestrator-cycle (07:30 and 20:45, experimental)' '$A.out' && ! grep -q 'sunrise/sunset' '$A.out' && ! grep -q 'brief + retro' '$A.out'"
# (non-interactive answers "no" to the new-install audio question → NotebookLM)
check "receipt records the audio route" grep -q '^- audio_backend: notebooklm$' "$H"/install/receipts/*.md

# Re-run: existing hub files are never touched.
sums_before="$(cd "$H" && md5 -q index.md log.md state.md backlog.md escalations.md incidents.md strategies.md registry.md 2>/dev/null || true)"
run_install "$A"; rc=$?
sums_after="$(cd "$H" && md5 -q index.md log.md state.md backlog.md escalations.md incidents.md strategies.md registry.md 2>/dev/null || true)"
check "re-run → exit 0 and hub files byte-identical" bash -c "[ $rc -eq 0 ] && [ '$sums_before' == '$sums_after' ]"
check "re-run: unchanged AGENTS.md / CLAUDE.md reported up to date, no 'not overwritten' warning" \
  bash -c "grep -q 'knowledge/AGENTS.md up to date' '$A.out' && grep -q 'knowledge/CLAUDE.md up to date' '$A.out' \
    && ! grep -q 'not overwritten' '$A.out'"
check "final 'Try these next' points at kb-doctor install-health and kb-demo brief, not a plain kb-brief" \
  bash -c "sed -n '/Try these next/,/Read next/p' '$A.out' > '$WORK/try.txt' \
    && grep -q 'bin/kb-doctor install-health\$' '$WORK/try.txt' && grep -q 'bin/kb-demo brief\$' '$WORK/try.txt' \
    && ! grep -q 'bin/kb-brief\$' '$WORK/try.txt' && grep -q 'signed-in Claude Code or Codex' '$WORK/try.txt'"

# ── A2. Missing Python package → a pip hint that works under PEP 668 ─────
# A python3 that reports jellyfish as missing to the installer's import probe
# only (everything else runs normally).
NODEPS="$WORK/nodeps"; mkdir -p "$NODEPS"
cat > "$NODEPS/python3" <<SH
#!/bin/sh
if [ "\$1" = "-c" ] && [ "\$2" = "import jellyfish" ]; then exit 1; fi
exec "$TOOLS/python3" "\$@"
SH
chmod +x "$NODEPS/python3"
A2="$WORK/a2"; mkdir -p "$A2"
env -u VEPOL_HUB -u KB_HUB -u KB_LANG HOME="$A2" PATH="$NODEPS:$TPATH" LANG=en_US.UTF-8 VEPOL_NONINTERACTIVE=1 \
  "$INSTALL" --apply > "$A2.out" 2>&1; rc=$?
check "missing Python package → detect-only hint: pip --user, then --break-system-packages" \
  bash -c "[ $rc -eq 0 ] && grep -q 'Python deps missing for .*: jellyfish' '$A2.out' \
    && grep -q 'python3 -m pip install --user -r ' '$A2.out' \
    && grep -q 'python3 -m pip install --break-system-packages -r ' '$A2.out' && ! grep -q 'pip3 install' '$A2.out'"
check "fresh --apply receipt records the NotebookLM route it created" \
  grep -q '^- audio_backend: notebooklm$' "$A2"/knowledge/install/receipts/*.md

# ── B. Russian profile → Russian registry headings ───────────────────────
B="$WORK/b"
run_install "$B" LANG=ru_RU.UTF-8; rc=$?
check "ru install → exit 0" [ "$rc" -eq 0 ]
check "ru registry.md uses the ru headings/columns" \
  bash -c "grep -qx '## personal / прочее' '$B/knowledge/registry.md' && grep -qx '| slug | статус | путь | описание |' '$B/knowledge/registry.md'"
printf '| ru-proj | no-wiki | `~/ru-proj` | Проект |\n' >> "$B/knowledge/registry.md"
HOME="$B" KB_HUB="$B/knowledge" PATH="$TPATH" "$B/knowledge/bin/kb-rebuild-registry" bootstrap >/dev/null 2>&1; brc=$?
check "ru registry row parsed by bootstrap" \
  bash -c "[ $brc -eq 0 ] && grep -A8 'slug: ru-proj' '$B/knowledge/migration-2026-04-25.yaml' | grep -q 'category: personal'"

# ── C. Pre-existing hub files stay untouched ─────────────────────────────
C="$WORK/c"; mkdir -p "$C/knowledge"
printf 'MY INDEX\n' > "$C/knowledge/index.md"; printf 'MY REGISTRY\n' > "$C/knowledge/registry.md"
run_install "$C"
check "existing index.md / registry.md never overwritten" \
  bash -c "[ \"\$(cat '$C/knowledge/index.md')\" == 'MY INDEX' ] && [ \"\$(cat '$C/knowledge/registry.md')\" == 'MY REGISTRY' ]"

# ── D. Agent roster: append only missing agents ──────────────────────────
D="$WORK/d"; mkdir -p "$D/knowledge/.orchestrator"
REG="$D/knowledge/.orchestrator/cli-tools.tsv"
printf '# my registry\nclaude | which-any | claude | MY CLAUDE ROW\ncodex  | path-any  | /custom/codex | MY CODEX ROW\n# grok | path-any | grok | disabled by me\nmytool | which-any | mytool | my tool' > "$REG"
orig="$(cat "$REG")"
run_install "$D"; rc=$?
expected="$(awk -F'|' '$0 !~ /^[ \t]*(#|$)/ && $0 ~ /\|/ { n=$1; gsub(/[ \t]/, "", n); print n }' "$SEED/bin/cli-tools.tsv" \
  | grep -vxE 'claude|codex|grok|mytool' | sort | tr '\n' ' ')"
got="$(awk -F'|' 'NR > 5 && $0 ~ /\|/ { n=$1; gsub(/[ \t]/, "", n); print n }' "$REG" | sort | tr '\n' ' ')"
check "existing roster rows kept byte-identical (incl. no trailing newline)" \
  bash -c "[ \"\$(head -5 '$REG')\" == \"\$1\" ]" _ "$orig"
check "missing agents appended once ($got)" [ -n "$expected" -a "$got" == "$expected" ]
check "commented-out agent (grok) not re-added" bash -c "! grep -qE '^grok[[:space:]]*\|' '$REG'"
printf '\nMy own hub rule.\n' >> "$D/knowledge/AGENTS.md"; cp "$D/knowledge/AGENTS.md" "$WORK/d-agents"
before="$(md5 -q "$REG")"; run_install "$D"
check "roster merge is idempotent" [ "$before" == "$(md5 -q "$REG")" ]
check "re-run: an edited hub AGENTS.md is kept and named as different; CLAUDE.md up to date" \
  bash -c "cmp -s '$D/knowledge/AGENTS.md' '$WORK/d-agents' && grep -q 'knowledge/AGENTS.md differs from this version' '$D.out' \
    && grep -q 'diff $D/knowledge/AGENTS.md -' '$D.out' && grep -q 'knowledge/CLAUDE.md up to date' '$D.out'"
D2="$WORK/d2"; mkdir -p "$D2/knowledge/.orchestrator"; : > "$D2/knowledge/.orchestrator/cli-tools.tsv"
run_install "$D2"
all="$(awk -F'|' '$0 !~ /^[ \t]*(#|$)/ && $0 ~ /\|/ { n=$1; gsub(/[ \t]/, "", n); print n }' "$SEED/bin/cli-tools.tsv" | sort | tr '\n' ' ')"
got2="$(awk -F'|' '$0 ~ /\|/ { n=$1; gsub(/[ \t]/, "", n); print n }' "$D2/knowledge/.orchestrator/cli-tools.tsv" | sort | tr '\n' ' ')"
check "an empty existing roster gets every agent ($got2)" [ -n "$all" -a "$got2" == "$all" ]

# ── E. Local Qwen failure is non-fatal ───────────────────────────────────
E="$WORK/e"
run_install "$E" -- --apply
run_install "$E" -- --apply --audio-backend notebooklm
cp "$E/knowledge/personal/processes.yaml" "$WORK/e.before"
run_install "$E" -- --apply --audio-backend local_qwen; rc=$?
check "--apply --audio-backend local_qwen with failing kb-tts-install → exit 11 (partial)" [ "$rc" -eq 11 ]
check "failure reason printed and install continued to the end" \
  bash -c "grep -q 'required command is missing: ffmpeg' '$E.out' && grep -q 'Bootstrap complete' '$E.out'"
check "digest route byte-identical after the failure" cmp -s "$E/knowledge/personal/processes.yaml" "$WORK/e.before"
check "receipt says local_qwen-failed" bash -c "grep -h '^- audio_backend:' '$E'/knowledge/install/receipts/*.md | grep -q 'local_qwen-failed'"

E2="$WORK/e2"; mkdir -p "$E2"
# Interactive answers: scheduled tasks n, Telegram plugin n, local Qwen y, memory compiler n.
printf 'n\nn\ny\nn\n' | env -u VEPOL_NONINTERACTIVE -u VEPOL_HUB -u KB_HUB -u KB_LANG \
  HOME="$E2" PATH="$TPATH" LANG=en_US.UTF-8 "$INSTALL" > "$E2.out" 2>&1; rc=$?
check "interactive: Qwen yes + failing install → exit 0, ~/.claude and skills installed" \
  bash -c "[ $rc -eq 0 ] && [ -f '$E2/.claude/CLAUDE.md' ] && [ -f '$E2/.claude/skills/init-kb/SKILL.md' ]"
check "interactive: NotebookLM route kept" \
  [ "$(grep -c '^  outputs: \[file, notebooklm_audio\]$' "$E2/knowledge/personal/processes.yaml")" -eq 2 ]
first_q="$(grep -n 'Use local Qwen' "$E2.out" | head -1 | cut -d: -f1)"
step1="$(grep -n 'Step 1 ·' "$E2.out" | head -1 | cut -d: -f1)"
check "Qwen question is asked after the prerequisite check, not first" \
  [ -n "$first_q" -a -n "$step1" -a "${first_q:-0}" -gt "${step1:-0}" ]

E3="$WORK/e3"; mkdir -p "$E3"
printf 'n\nn\ny\nn\n' | env -u VEPOL_NONINTERACTIVE -u VEPOL_HUB -u KB_HUB -u KB_LANG KB_FAKE_TTS_MODE=success \
  HOME="$E3" PATH="$TPATH" LANG=en_US.UTF-8 "$INSTALL" > "$E3.out" 2>&1; rc=$?
check "interactive: Qwen yes + successful install → Telegram audio route" \
  bash -c "[ $rc -eq 0 ] && [ \$(grep -c '^  outputs: \[file, telegram_audio\]$' '$E3/knowledge/personal/processes.yaml') -eq 2 ]"

# ── F. Session hooks for an existing settings.json ───────────────────────
hooks_ok() { HOME="$1" PATH="$TPATH" "$1/knowledge/bin/kb-claude-hooks" --check --settings "$1/.claude/settings.json" >/dev/null 2>&1; }
F1="$WORK/f1"; mkdir -p "$F1/.claude"; printf '{\n  "theme": "dark"\n}\n' > "$F1/.claude/settings.json"
cp "$F1/.claude/settings.json" "$WORK/f1.before"
run_install "$F1" -- --apply; rc=$?
check "--apply without VEPOL_MERGE_HOOKS: settings.json untouched, command printed" \
  bash -c "[ $rc -eq 0 ] && cmp -s '$F1/.claude/settings.json' '$WORK/f1.before' && grep -q 'kb-claude-hooks --apply' '$F1.out'"
check "... and hooks still missing" bash -c "! HOME='$F1' PATH='$TPATH' '$F1/knowledge/bin/kb-claude-hooks' --check --settings '$F1/.claude/settings.json' >/dev/null 2>&1"
run_install "$F1" VEPOL_MERGE_HOOKS=1 -- --apply; rc=$?
check "--apply with VEPOL_MERGE_HOOKS=1 → hooks present, other keys kept, backup written" \
  bash -c "[ $rc -eq 0 ] && HOME='$F1' PATH='$TPATH' '$F1/knowledge/bin/kb-claude-hooks' --check --settings '$F1/.claude/settings.json' >/dev/null 2>&1 \
    && python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))[\"theme\"] == \"dark\"' '$F1/.claude/settings.json' \
    && [ \$(ls -A '$F1/.claude' | grep -c '^settings\.json.') -ge 1 ]"
F2="$WORK/f2"; mkdir -p "$F2/.claude"; printf '{"theme": "dark"}\n' > "$F2/.claude/settings.json"
# Interactive answers: add hooks y, scheduled n, Telegram plugin n, local Qwen n, memory compiler n.
printf 'y\nn\nn\nn\nn\n' | env -u VEPOL_NONINTERACTIVE -u VEPOL_HUB -u KB_HUB -u KB_LANG \
  HOME="$F2" PATH="$TPATH" LANG=en_US.UTF-8 "$INSTALL" > "$F2.out" 2>&1; rc=$?
check "interactive: asks 'Add Vepol's session hooks…' and applies on yes" \
  bash -c "[ $rc -eq 0 ] && grep -q \"Add Vepol's session hooks to your existing settings.json? A backup is kept.\" '$F2.out'"
check "... hooks present after the yes" hooks_ok "$F2"
check "fresh settings.json from the template → no hooks step" bash -c "! grep -q 'Step 3c' '$A.out'"

# ── G. Scheduled tasks accepted (fake launchctl) ─────────────────────────
G="$WORK/g"
run_install "$G" VEPOL_ENABLE_LAUNCHD=1 -- --apply; rc=$?
check "VEPOL_ENABLE_LAUNCHD=1 → exit 0, 4 plists rendered, 4 bootstrap calls (fake launchctl)" \
  bash -c "[ $rc -eq 0 ] && [ \$(ls '$G/Library/LaunchAgents'/com.knowledge.*.plist | wc -l) -eq 4 ] && [ \$(grep -c '^bootstrap gui/' '$G/launchctl.calls') -eq 4 ]"
check "every plist log folder exists" \
  bash -c "for d in \$(grep -ho '<string>[^<]*/logs/' '$G/Library/LaunchAgents'/*.plist | sed 's/<string>//' | sort -u); do [ -d \"\$d\" ] || exit 1; done"
check "receipt: launchd=on" grep -q 'opt_ins: launchd=on' "$G"/knowledge/install/receipts/*.md

# ── H. Probe / capabilities report what --apply enforces ─────────────────
caps="$(PATH="$TPATH" "$INSTALL" --capabilities --json 2>/dev/null)"
check "--capabilities: node/bun optional with a reason, VEPOL_MERGE_HOOKS listed" \
  pyjson '"node" in d["optional_tools"] and "bun" in d["optional_tools"] and "node" not in d["required_tools"] and "bun" not in d["required_tools"] and "VEPOL_MERGE_HOOKS" in d["opt_in_env"] and d["min_versions"]["python3"] == "3.10"' <<< "$caps"
PH="$WORK/ph"; mkdir -p "$PH"
probe="$(HOME="$PH" PATH="$TPATH" "$INSTALL" --probe --json 2>/dev/null)"; prc=$?
check "--probe without node/bun: not required-missing, listed as optional, no version problem" \
  bash -c "[ $prc -eq 0 ] && python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert \"node\" not in d[\"prereqs_missing_required\"] and \"node\" in d[\"prereqs_missing_optional\"] and \"bun\" in d[\"prereqs_missing_optional\"] and d[\"prereqs_version_problems\"] == []' \"\$1\"" _ "$probe"
if [[ -x /usr/bin/python3 ]] && /usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info < (3, 10) else 1)' 2>/dev/null; then
  OLD="$WORK/oldpy"; mkdir -p "$OLD"; ln -s /usr/bin/python3 "$OLD/python3"
  probe="$(HOME="$PH" PATH="$OLD:$TPATH" "$INSTALL" --probe --json 2>/dev/null)"; prc=$?
  check "--probe with stock python3 < 3.10 → exit 10 + python-3.10+ in prereqs_version_problems" \
    bash -c "[ $prc -eq 10 ] && python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert \"python-3.10+\" in d[\"prereqs_version_problems\"] and d[\"prereq_versions\"][\"python3\"].startswith(\"3.\")' \"\$1\"" _ "$probe"
else
  p "--probe old-python case skipped (no /usr/bin/python3 < 3.10 here)"
fi
if [[ ! -x /opt/homebrew/bin/bash && ! -x /usr/local/bin/bash ]]; then
  OLDB="$WORK/oldbash"; mkdir -p "$OLDB"; ln -s /bin/bash "$OLDB/bash"
  probe="$(HOME="$PH" PATH="$OLDB:$TPATH" "$INSTALL" --probe --json 2>/dev/null)"; prc=$?
  check "--probe with only bash 3.2 → exit 10 + bash-5+" \
    bash -c "[ $prc -eq 10 ] && printf '%s' \"\$1\" | grep -q 'bash-5+'" _ "$probe"
else
  p "--probe bash-3.2 case skipped (a Homebrew bash 5 is installed here)"
fi

# ── I. Session-capture clone is pinned (fake git clone, no network) ──────
I="$WORK/i"; GT="$WORK/gittools"; mkdir -p "$GT"
REALGIT="$(command -v git)"
cat > "$GT/git" <<SH
#!/bin/sh
echo "\$*" >> "\$HOME/git.calls"
if [ "\$1" = clone ]; then for last; do :; done; exec "$REALGIT" init --quiet "\$last"; fi
exec "$REALGIT" "\$@"
SH
chmod +x "$GT/git"
mkdir -p "$I"
env -u VEPOL_HUB -u KB_HUB -u KB_LANG HOME="$I" PATH="$GT:$TPATH" LANG=en_US.UTF-8 VEPOL_NONINTERACTIVE=1 \
  VEPOL_ENABLE_MEMORY_COMPILER=1 "$INSTALL" --apply > "$I.out" 2>&1; rc=$?
check "memory-compiler clone is checked out at the tested commit 54eddd7" \
  bash -c "[ $rc -eq 0 ] && grep -q 'checkout --quiet 54eddd709e83d3be244e9c56c9fc3a6cf375d534' '$I/git.calls'"

echo "  ---"
echo "  PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
