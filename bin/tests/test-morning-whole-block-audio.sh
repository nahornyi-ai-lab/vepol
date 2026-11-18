#!/usr/bin/env bash
# R6c AC4-AC8/AC10 synthetic tests for literal whole-block morning composition.
# All Telegram/NotebookLM/Qwen/agent surfaces are local sentinels.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_MORNING_FIDELITY_SRC_BIN:-$HOME/knowledge/bin}"
DIGEST="$SRC_BIN/kb-morning-digest"
DAY=2026-07-13

# Hermetic agent CLIs: a failing claude/codex comes first on PATH and is the
# default KB_CLAUDE_BIN/KB_CODEX_BIN, so nothing here can reach a real agent.
mkdir -p "$TMP/stub-bin"
for agent in claude codex; do
  printf '#!/bin/sh\necho "%s is disabled in tests" >&2\nexit 97\n' "$agent" >"$TMP/stub-bin/$agent"
  chmod +x "$TMP/stub-bin/$agent"
done
export PATH="$TMP/stub-bin:$PATH" KB_CLAUDE_BIN="$TMP/stub-bin/claude" KB_CODEX_BIN="$TMP/stub-bin/codex"

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
  # Russian field labels on purpose: the hub profile is ru, so this mirrors the
  # report kb-learning-arxiv writes for a Russian-speaking user.
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
[[ "$OUT" != *"600–900"* && "$OUT" != *"MORNING PROCESS DATA"* ]] \
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
# ru hub: the report keeps the Russian strings ru users already get.
REPORT="$HUB/reports/morning-digest-$DAY.md"
grep -qx "# Утренний дайджест Vepol — $DAY (понедельник)" "$REPORT" \
  && grep -qx '## Источники (для проверки, не для озвучки)' "$REPORT" \
  && grep -q '^- Утренний бриф (finalized) — ' "$REPORT" \
  && ok "ru report keeps the Russian title, sources heading and sources list" \
  || fail "ru report title/sources heading/sources list changed"

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
# The Russian phrases are kb-learning-arxiv's ru no-new literals (this hub is ru).
[[ "$NO_OUT" == *"NO-NEW-BRIEF"* && "$NO_OUT" == *"NO-NEW-MONEY"* \
   && "$NO_OUT" != *"PRIOR-ARXIV"* && "$NO_OUT" != *"Сегодня новых статей"* \
   && "$NO_OUT" != *"Новых статей arXiv"* && "$NO_OUT" != *"no new arXiv papers"* ]] \
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

echo "=== Language: Russian-only narration rules apply to a ru profile only ==="
for lang in en es ru; do
  KB_HUB="$HUB" KB_VEPOL_DEV="$TMP/no-project" KB_LANG="$lang" \
  python3 - "$DIGEST" "$lang" <<'PY' \
    && ok "synth prompt narration rules match the $lang profile" \
    || fail "synth prompt narration rules wrong for the $lang profile"
import importlib.machinery, importlib.util, re, sys
loader = importlib.machinery.SourceFileLoader("digest_lang", sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
lang = sys.argv[2]
morning, evening = mod.SYNTH_INSTRUCTION, mod.EVENING_SYNTH_INSTRUCTION
name = {"en": "English", "es": "Spanish", "ru": "Russian"}[lang]
# Instructions are English for everyone and keep the user-language directive.
assert "Hard rules:" in morning and "Hard rules:" in evening
assert f"in the user's language, {name}" in morning
assert f"Only {name}." in evening
cyrillic = re.compile(r"[\u0400-\u04FF]")
if lang == "ru":
    # The owner's Russian TTS rules and Russian heading samples stay intact.
    assert "Write the finished text only in Russian." in morning
    assert "Latin letters" in morning and "in Cyrillic" in morning
    assert "«искусственный интеллект», not «ИИ»" in morning
    assert "## Утро: коротко о главном" in morning
    assert "## Что закрыто сегодня" in evening
else:
    # A non-ru profile must never be told to write Russian (the old bug).
    assert f"Write the finished text only in {name}." in morning
    assert "only in Russian" not in morning and "Cyrillic" not in morning
    assert "Latin letters" not in morning
    assert not cyrillic.search(morning) and not cyrillic.search(evening)
    assert "## What I suggest doing today" in morning
PY
done

echo "=== Speech drops the arXiv report's machine lines; the report keeps them ==="
for lang in ru en; do
  MH=$(make_hub "machine-$lang"); write_selected_fixture "$MH"
  echo "language: $lang" > "$MH/personal/profile.yaml"
  if [[ "$lang" == ru ]]; then
    A=Авторы; C=Категория; SC=Скоры; SO=Источники; O=Оригинал
  else
    A=Authors; C=Category; SC=Scores; SO=Sources; O="Original title"
  fi
  # Same shape as kb-learning-arxiv's render_report for this language.
  cat > "$MH/reports/learning-arxiv-summary-$DAY.md" <<EOF
# arXiv learning — $DAY

## 1. ARXIV-TITLE

- $O: ARXIV-ORIGINAL-TITLE
- $A: Alice Researcher, Bob Scholar
- arXiv: https://arxiv.org/abs/2607.00001
- $C: cs.AI · 2026-07-12
- $SC: \`{"topic_relevance": 2, "abstract_signal": 3, "final": 41}\`

**Studied:** ARXIV-STUDIED

$SO: [[arxiv-learning-snapshot-$DAY]], [[arxiv-learning-translation-codex-$DAY]]
EOF
  # A wiki-link line in the BRIEF is ordinary prose and must still be spoken.
  printf '%s\n' '---' "date: $DAY" '---' '' 'BRIEF-FIRST' '' "$SO: [[brief-note]]" '' 'BRIEF-FINAL' \
    > "$MH/briefs/$DAY.md"
  KB_HUB="$MH" KB_VEPOL_DEV="$TMP/no-project" "$DIGEST" --date "$DAY" --no-push >/dev/null 2>&1
  MRC=$?
  SPOKEN=$(cat "$MH/reports/morning-digest-$DAY.txt" 2>/dev/null)
  WRITTEN=$(cat "$MH/reports/morning-digest-$DAY.md" 2>/dev/null)
  [[ "$MRC" == "0" && "$SPOKEN" == *"ARXIV-STUDIED"* && "$SPOKEN" == *"ARXIV-ORIGINAL-TITLE"* \
     && "$SPOKEN" != *"topic_relevance"* && "$SPOKEN" != *"arxiv-learning-snapshot"* \
     && "$SPOKEN" != *"Alice Researcher"* && "$SPOKEN" != *"cs.AI"* \
     && "$SPOKEN" != *"$SC:"* && "$SPOKEN" != *"arXiv:"* ]] \
    && ok "[$lang] speech has no scores/sources/authors/category/link lines" \
    || fail "[$lang] machine lines reached the speech (rc=$MRC): $SPOKEN"
  [[ "$SPOKEN" == *"$SO: brief note"* && "$SPOKEN" == *"BRIEF-FINAL"* ]] \
    && ok "[$lang] the brief's own lines are untouched" || fail "[$lang] brief lines were stripped"
  [[ "$WRITTEN" == *'"topic_relevance": 2'* && "$WRITTEN" == *"[[arxiv-learning-snapshot-$DAY]]"* \
     && "$WRITTEN" == *"$A: Alice Researcher"* && "$WRITTEN" == *"$C: cs.AI"* ]] \
    && ok "[$lang] the written report keeps every line" || fail "[$lang] the written report lost lines"
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
