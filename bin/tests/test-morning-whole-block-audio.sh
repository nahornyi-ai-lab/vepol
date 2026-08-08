#!/usr/bin/env bash
# R6c AC4-AC8/AC10 synthetic tests for literal whole-block morning composition.
# All Telegram/NotebookLM/Qwen/agent surfaces are local sentinels.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MORNING_FIDELITY_SRC_BIN:-$HOME/knowledge/bin}"
DIGEST="$SRC_BIN/kb-morning-digest"
DAY=2026-07-13

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

make_hub() {
  local name="$1" hub="$TMP/$1"
  mkdir -p "$hub"/{briefs,reports,.orchestrator,logs,personal,bin}
  echo "language: ru" > "$hub/personal/profile.yaml"
  : > "$hub/log.md"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$hub/bin/kb-idea"
  chmod +x "$hub/bin/kb-idea"
  echo "$hub"
}

write_selected_fixture() {
  local hub="$1"
  cat > "$hub/briefs/$DAY.md" <<'EOF'
---
date: 2026-07-13
delivery: telegram_ok
---

BRIEF-FIRST

BRIEF-MIDDLE

BRIEF-FINAL

## Retro (20:00)

RETRO-MUST-NOT-SPEAK
EOF
  cat > "$hub/.orchestrator/learning-arxiv-$DAY.json" <<'EOF'
{"date":"2026-07-13","status":"completed","no_new_papers":false,
 "selected_papers":[{"id":"paper-1"}],"error":null}
EOF
  cat > "$hub/reports/learning-arxiv-summary-$DAY.md" <<'EOF'
ARXIV-FIRST

**Что исследовали:** ARXIV-STUDIED

**Как исследовали:** ARXIV-METHOD

**Что выяснили:** ARXIV-FOUND

ARXIV-FINAL
EOF
  cat > "$hub/.orchestrator/money-radar-$DAY-digest.txt" <<'EOF'
MONEY-FIRST

MONEY-MIDDLE

MONEY-FINAL
EOF
}

echo "=== AC4/AC7: exact whole-block source and zero morning synth ==="
HUB=$(make_hub selected); write_selected_fixture "$HUB"
EXPECTED="$TMP/expected.txt"
python3 - "$HUB" "$EXPECTED" "$DAY" <<'PY'
import pathlib, sys
hub, out, day = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
brief = (hub / "briefs" / f"{day}.md").read_text()
body = brief.split("---\n", 2)[2]
body = body.split("\n## Retro (", 1)[0].strip("\r\n")
arxiv = (hub / "reports" / f"learning-arxiv-summary-{day}.md").read_text().strip("\r\n")
money = (hub / ".orchestrator" / f"money-radar-{day}-digest.txt").read_text().strip("\r\n")
out.write_text("\n\n".join((body, arxiv, money)) + "\n", encoding="utf-8")
PY
OUT=$(KB_HUB="$HUB" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
  KB_DIGEST_PROMPT_ONLY=1 "$DIGEST" --date "$DAY" 2>/dev/null); RC=$?
printf '%s\n' "$OUT" > "$TMP/actual.txt"
[[ "$RC" == "0" ]] && ok "AC4 assembly seam exits zero" || fail "AC4 seam rc=$RC"
cmp -s "$EXPECTED" "$TMP/actual.txt" && ok "AC4 exact brief/arXiv/Money assembly" \
  || fail "AC4 assembled source is not byte-exact"
for marker in BRIEF-FIRST BRIEF-MIDDLE BRIEF-FINAL ARXIV-FIRST ARXIV-STUDIED \
              ARXIV-METHOD ARXIV-FOUND ARXIV-FINAL MONEY-FIRST MONEY-MIDDLE MONEY-FINAL; do
  [[ "$OUT" == *"$marker"* ]] && ok "AC4 preserves $marker" || fail "AC4 missing $marker"
done
[[ "$OUT" != *"delivery: telegram_ok"* && "$OUT" != *"RETRO-MUST-NOT-SPEAK"* ]] \
  && ok "AC7 frontmatter and Retro tail excluded" || fail "AC7 metadata/tail leaked"
[[ "$OUT" != *"600–900"* && "$OUT" != *"ДАННЫЕ УТРЕННИХ ПРОЦЕССОВ"* ]] \
  && ok "AC4 no synth instruction in source" || fail "AC4 synth prompt remains"

cat > "$TMP/fake-codex" <<EOF
#!/usr/bin/env bash
echo called >> "$TMP/synth-called"
out=""
while [[ \$# -gt 0 ]]; do
  [[ "\$1" == "-o" ]] && { out="\$2"; shift 2; continue; }
  shift
done
[[ -n "\$out" ]] && printf '%0300d\n' 0 > "\$out"
exit 0
EOF
chmod +x "$TMP/fake-codex"
rm -f "$TMP/synth-called"
KB_HUB="$HUB" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
  KB_CODEX_BIN="$TMP/fake-codex" KB_MORNING_SYNTH_AGENTS=codex \
  "$DIGEST" --date "$DAY" --no-push >/dev/null 2>&1
RC=$?
[[ "$RC" == "0" && ! -e "$TMP/synth-called" ]] \
  && ok "AC4 file-only route makes zero synth-agent calls" \
  || fail "AC4 file-only route called morning synth or rc=$RC"
SPEECH="$HUB/reports/morning-digest-$DAY.txt"
[[ -s "$SPEECH" ]] && grep -q 'BRIEF-FINAL' "$SPEECH" && grep -q 'ARXIV-FINAL' "$SPEECH" \
  && grep -q 'MONEY-FINAL' "$SPEECH" \
  && ok "AC4 frozen speech keeps every block final marker" \
  || fail "AC4 frozen speech missing/rewritten"

echo "=== AC5/AC6: no-new and mismatch never select stale research ==="
NO=$(make_hub nonew)
cat > "$NO/briefs/$DAY.md" <<'EOF'
---
date: 2026-07-13
---

NO-NEW-BRIEF
EOF
cat > "$NO/.orchestrator/learning-arxiv-$DAY.json" <<'EOF'
{"status":"completed","no_new_papers":true,"selected_papers":[]}
EOF
echo 'PRIOR-ARXIV-MUST-NOT-SPEAK' > "$NO/reports/learning-arxiv-summary-2026-07-11.md"
echo 'NO-NEW-MONEY' > "$NO/.orchestrator/money-radar-$DAY-digest.txt"
NO_OUT=$(KB_HUB="$NO" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
  KB_DIGEST_PROMPT_ONLY=1 "$DIGEST" --date "$DAY" 2>/dev/null)
[[ "$NO_OUT" == *"NO-NEW-BRIEF"* && "$NO_OUT" == *"NO-NEW-MONEY"* \
   && "$NO_OUT" != *"PRIOR-ARXIV"* && "$NO_OUT" != *"Сегодня новых статей"* \
   && "$NO_OUT" != *"Новых статей arXiv"* ]] \
  && ok "AC5 no-new skips arXiv audio and stale report" \
  || fail "AC5 no-new/stale behavior wrong"

cat > "$NO/.orchestrator/learning-arxiv-$DAY.json" <<'EOF'
{"status":"completed","no_new_papers":true,"selected_papers":[{"id":"bad"}]}
EOF
echo 'MISMATCH-REPORT-MUST-NOT-SPEAK' > "$NO/reports/learning-arxiv-summary-$DAY.md"
MIS=$(KB_HUB="$NO" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
  KB_DIGEST_PROMPT_ONLY=1 "$DIGEST" --date "$DAY" 2>/dev/null)
[[ "$MIS" != *"MISMATCH-REPORT"* && "$MIS" == *"NO-NEW-BRIEF"* ]] \
  && ok "AC6 contradictory research state skips only arXiv" \
  || fail "AC6 mismatch selected report"

echo "=== AC7: malformed evening-tail lookalikes fail before source ==="
for heading in '## Retro' '## Retro:' '## Retro – broken' '## Reflection' \
               '## Reflection:' '## Reflection — broken'; do
  BAD=$(make_hub "bad-$RANDOM")
  cat > "$BAD/briefs/$DAY.md" <<EOF
---
date: $DAY
---

MORNING-OK

$heading

MALFORMED-TAIL-MUST-NOT-SPEAK
EOF
  set +e
  BAD_OUT=$(KB_HUB="$BAD" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
    KB_DIGEST_PROMPT_ONLY=1 "$DIGEST" --date "$DAY" 2>/dev/null)
  BRC=$?
  # No `set -e` restore: the script's baseline is `set -uo pipefail` (line 5);
  # re-enabling errexit here silently aborted everything after AC7.
  [[ "$BRC" != "0" && "$BAD_OUT" != *"MALFORMED-TAIL"* ]] \
    && ok "AC7 malformed '$heading' fails closed" \
    || fail "AC7 malformed '$heading' leaked or rc=$BRC"
done

echo "=== AC8: v3 exactly three inputs and legacy completion is terminal ==="
KB_HUB="$HUB" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
python3 - "$DIGEST" <<'PY' && ok "AC8 morning-input/v3 canonical three records" \
  || fail "AC8 snapshot schema/records/hash"
import hashlib, importlib.machinery, importlib.util, json, sys
loader = importlib.machinery.SourceFileLoader("digest_mod", sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
snap = mod.capture_morning_input("2026-07-13")["upstream_snapshot"]
assert snap["schema"] == "morning-input/v3"
assert [x["name"] for x in snap["inputs"]] == ["brief", "learning", "money_radar"]
assert len(snap["inputs"]) == 3 and mod.snapshot_valid(snap)
canon = json.dumps(snap["inputs"], ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode()
assert snap["semantic_sha256"] == hashlib.sha256(canon).hexdigest()
PY

for schema in morning-input/v1 morning-input/v2; do
  TERM=$(make_hub "terminal-${schema##*/}"); write_selected_fixture "$TERM"
  KB_HUB="$TERM" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
  python3 - "$DIGEST" "$schema" <<'PY'
import importlib.machinery, importlib.util, sys
loader = importlib.machinery.SourceFileLoader("digest_term", sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
m = mod.fresh_manifest("2026-07-13", "morning")
m.update({"status":"completed", "retry_disposition":"terminal",
          "telegram":{"message_id":999}, "updated_at":"2026-07-13T07:00:00+02:00",
          "upstream_snapshot":{"schema":sys.argv[2], "inputs":[],
                               "semantic_sha256":"0"*64}})
mod.save_manifest(mod.manifest_path("2026-07-13", "morning"), m)
PY
  rm -f "$TMP/synth-called" "$TMP/external-called"
  printf '#!/usr/bin/env bash\necho tts >> "%s"\nexit 91\n' "$TMP/external-called" \
    > "$TERM/bin/kb-tts-render"
  printf '#!/usr/bin/env bash\necho tg >> "%s"\nexit 91\n' "$TMP/external-called" \
    > "$TERM/bin/kb-channel-send-audio"
  chmod +x "$TERM/bin/kb-tts-render" "$TERM/bin/kb-channel-send-audio"
  # Manual mode (no KB_PROCESS_* background env): with --date in argv the
  # background allowlist would demote the run to file-only and both terminal
  # assertions below would pass vacuously. Manual mode takes the canonical
  # delivery branch, where a completed manifest short-circuits — the exact
  # "terminal" property under test.
  KB_HUB="$TERM" KB_VEPOL_DEV="$TMP/no-project" KB_LANG=ru \
    KB_CODEX_BIN="$TMP/fake-codex" KB_MORNING_SYNTH_AGENTS=codex \
    "$DIGEST" --date "$DAY" >/dev/null 2>&1
  TRC=$?
  [[ "$TRC" == "0" && ! -e "$TMP/synth-called" && ! -e "$TMP/external-called" ]] \
    && ok "AC8 completed $schema local delivery is terminal" \
    || fail "AC8 completed $schema recaptured or called external rc=$TRC"
done

echo "=== AC5/AC9: learning literals and current public documentation ==="
grep -q 'Сегодня новых статей arXiv нет\.' "$SRC_BIN/kb-learning-arxiv" \
  && grep -q 'There are no new arXiv papers today\.' "$SRC_BIN/kb-learning-arxiv" \
  && ok "AC5 exact RU/EN learning no-new literals" \
  || fail "AC5 learning no-new literals are stale/missing"
# Seed-safe: no dev-path default. Dev exercises this AC9 doc-check by exporting
# VEPOL_PREP_DIR; unset → the `[[ -d "$PREP" ]]` guard below skips it cleanly.
PREP="${VEPOL_PREP_DIR:-}"
if [[ -d "$PREP" ]]; then
  # Current-behavior docs only: shipped release notes and historical CHANGELOG
  # sections are immutable; supersession lives in current docs, not in history.
  # The mutable [Unreleased] CHANGELOG section IS current-behavior surface.
  awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f' \
    "$PREP/CHANGELOG.md" > "$TMP/changelog-unreleased" 2>/dev/null || true
  if rg -n 'keeps its existing morning synthesis|Digest text generation is unchanged|Text generation is unchanged|digest synthesis uses your configured CLI agents' \
      "$PREP/README.md" "$PREP/docs/getting-started.md" "$TMP/changelog-unreleased" \
      >"$TMP/stale-docs" 2>/dev/null; then
    fail "AC9 public docs still present old morning synthesis as current"
  else
    ok "AC9 public current-behavior docs supersede old synthesis contract"
  fi
  rg -q 'whole|whole-block|finalized blocks|without.*synth|no morning synthesis' \
      "$PREP/README.md" "$PREP/CHANGELOG.md" "$PREP/docs/getting-started.md" \
      && ok "AC9 public docs describe whole finalized blocks" \
      || fail "AC9 public docs do not describe new whole-block behavior"
fi

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
