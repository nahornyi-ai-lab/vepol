#!/usr/bin/env bash
# Canonical Codex launcher contract: one standalone path, one diagnostic/test
# override, and no production dependence on PATH or desktop app bundles.

set -uo pipefail
PASS=0; FAIL=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SRC_BIN="${KB_CODEX_SRC_BIN:-$(cd "$(dirname "$0")/.." && pwd)}"
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

mkdir -p "$TMP/home/.local/bin" "$TMP/cwd"
FAKE="$TMP/home/.local/bin/codex"
printf '#!/bin/sh\nexit 0\n' >"$FAKE"
chmod +x "$FAKE"

SRC_BIN="$SRC_BIN" TEST_HOME="$TMP/home" TEST_CWD="$TMP/cwd" python3 - <<'PY'
import os
import pathlib
import sys

sys.path.insert(0, os.environ["SRC_BIN"])
try:
    from _kb_codex import CodexUnavailable, codex_bin
except Exception as exc:
    print(f"IMPORT_ERROR: {exc}")
    raise SystemExit(1)

home = pathlib.Path(os.environ["TEST_HOME"])
cwd = pathlib.Path(os.environ["TEST_CWD"])
expected = str((home / ".local/bin/codex").resolve())

assert codex_bin(env={}, home=home, cwd=cwd) == expected
assert codex_bin(env={"PATH": ""}, home=home, cwd=cwd) == expected

override = cwd / "override-codex"
override.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
override.chmod(0o755)
assert codex_bin(env={"KB_CODEX_BIN": "./override-codex"}, home=home, cwd=cwd) == str(override.resolve())

override.chmod(0o644)
try:
    codex_bin(env={"KB_CODEX_BIN": str(override)}, home=home, cwd=cwd)
except CodexUnavailable:
    pass
else:
    raise AssertionError("non-executable override accepted")

(home / ".local/bin/codex").unlink()
try:
    codex_bin(env={}, home=home, cwd=cwd)
except CodexUnavailable:
    pass
else:
    raise AssertionError("missing canonical binary accepted")
PY
[[ $? -eq 0 ]] && ok "resolver uses only canonical standalone path or validated override" \
  || fail "canonical resolver contract failed"

SRC_BIN="$SRC_BIN" python3 - <<'PY'
import os
import pathlib
import re
import sys

root = pathlib.Path(os.environ["SRC_BIN"])
targets = [
    "kb-orchestrator-run",
    "_kb_mail/host.py",
    "_kb_multibot/spawner.py",
    "kb-morning-digest",
    "kb-learning-arxiv",
    "kb-money-radar",
    "kb-contact",
    "kb-agent-review",
]
forbidden = [
    r"shutil\.which\([\"']codex[\"']",
    r"/Applications/(?:Codex|ChatGPT)\.app/.+codex",
    r"/(?:opt/homebrew|usr/local)/bin/codex",
    r"KB_CONTACT_CODEX_BIN",
    r"KB_LEARNING_ARXIV_TRANSLATE_BIN",
]
errors = []
seen = 0
for rel in targets:
    path = root / rel
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    launcher = any(marker in text for marker in (
        "codex exec", "CODEX_BIN", "_codex_path", "_synth_codex",
        "def run_codex", '"id": "codex"',
    ))
    if not launcher:
        continue
    seen += 1
    if "_kb_codex" not in text or "codex_bin" not in text:
        errors.append(f"{rel}: does not use shared resolver")
    for pattern in forbidden:
        if re.search(pattern, text):
            errors.append(f"{rel}: forbidden launcher pattern {pattern}")
if seen < 5:
    errors.append(f"expected at least 5 released callsites, found {seen}")
if errors:
    print("\n".join(errors))
    raise SystemExit(1)
PY
[[ $? -eq 0 ]] && ok "all production callsites use shared resolver; no fallback zoo" \
  || fail "production callsite static guard failed"

SRC_ROOT="$(cd "$SRC_BIN/.." && pwd)" SRC_BIN="$SRC_BIN" python3 - <<'PY'
import os
import pathlib
import re

root = pathlib.Path(os.environ["SRC_ROOT"])
offer = (root / "bin/kb-cli-offer").read_text(encoding="utf-8")
registry_path = root / "bin/cli-tools.tsv"
if not registry_path.is_file():
    registry_path = root / ".orchestrator/cli-tools.tsv"
registry = registry_path.read_text(encoding="utf-8")
doctor = (root / "bin/kb-doctor").read_text(encoding="utf-8")
setup_path = root / "claude/skills/orchestrator-setup/SKILL.md"
if not setup_path.is_file():
    setup_path = pathlib.Path.home() / ".claude/skills/orchestrator-setup/SKILL.md"
setup = setup_path.read_text(encoding="utf-8")

assert "https://chatgpt.com/codex/install.sh" in offer
assert "npm install -g @openai/codex" not in offer
codex_rows = [line for line in registry.splitlines() if line.strip().startswith("codex")]
assert len(codex_rows) == 1, codex_rows
assert "path-any" in codex_rows[0] and "$HOME/.local/bin/codex" in codex_rows[0]
assert ":codex" not in codex_rows[0]
assert "from _kb_codex import" in doctor and "shutil.which(\"codex\"" not in doctor
assert "https://chatgpt.com/codex/install.sh" in setup
assert "npm install -g @openai/codex" not in setup
PY
[[ $? -eq 0 ]] && ok "installer, roster, doctor and setup use the canonical standalone contract" \
  || fail "install/diagnostic surfaces still advertise fallback or npm/PATH Codex"

# Executable boundary checks: a missing Codex degrades one lane, doctor reports
# the canonical failure, and the managed inventory keeps the shared import.
SRC_BIN="$SRC_BIN" TEST_TMP="$TMP" KB_CODEX_BIN="$TMP/missing-codex" python3 - <<'PY'
import importlib.machinery
import importlib.util
import os
import pathlib
import sys

src = pathlib.Path(os.environ["SRC_BIN"])
sys.path.insert(0, str(src))

def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

money = load("codex_path_money", src / "kb-money-radar")
roster = money.load_roster(True)
ids = [row["id"] for row in roster]
assert "codex" in ids and "claude" in ids, ids
codex_lane = next(row for row in roster if row["id"] == "codex")
assert codex_lane["available"] is False
assert money.smoke_agent(codex_lane) is False

from _kb_mail.errors import MailUnavailable
from _kb_mail.host import CodexHostRunner
try:
    CodexHostRunner().call("x", timeout_s=1)
except MailUnavailable as exc:
    assert "unavailable" in str(exc).lower(), str(exc)
else:
    raise AssertionError("mail accepted missing Codex")

spawner_path = src / "_kb_multibot/spawner.py"
if spawner_path.is_file():
    import _kb_multibot.spawner as spawner
    assert spawner._codex_path() is None

morning_path = src / "kb-morning-digest"
if morning_path.is_file():
    morning = load("codex_path_morning", morning_path)
    assert morning._synth_codex("x", 1) is None

learning_path = src / "kb-learning-arxiv"
if learning_path.is_file():
    learning = load("codex_path_learning", learning_path)
    learning.atomic_write = lambda *args, **kwargs: None
    message, rc, detail = learning.run_codex("2026-07-11", [])
    assert message == "" and rc == -1 and "unavailable" in detail.lower()

contact_path = src / "kb-contact"
if contact_path.is_file():
    contact = load("codex_path_contact", contact_path)
    if hasattr(contact, "_run_codex_search"):
        assert contact._run_codex_search("Example Person", {"company": "example"}) is None

review_path = src / "kb-agent-review"
if review_path.is_file():
    review = load("codex_path_review", review_path)
    ok_result, output, note = review.run_planner("codex", src.parent, "x", 1)
    assert ok_result is False and output == "" and "unavailable" in note.lower()

doctor = load("codex_path_doctor", src / "kb-doctor")
findings = doctor._ih_check_codex_currency()
assert any(f.id.startswith("install-health:codex-missing") and f.severity == "P1"
           for f in findings), [(f.id, f.severity) for f in findings]

bad_version = pathlib.Path(os.environ["TEST_TMP"]) / "bad-version-codex"
bad_version.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
bad_version.chmod(0o755)
os.environ["KB_CODEX_BIN"] = str(bad_version)
version_findings = doctor._ih_check_codex_currency()
assert any(f.id.startswith("install-health:codex-version-failed") and f.severity == "P1"
           for f in version_findings), [(f.id, f.severity) for f in version_findings]

broken_alt = pathlib.Path(os.environ["TEST_TMP"]) / "broken-alt-codex"
broken_alt.symlink_to(pathlib.Path(os.environ["TEST_TMP"]) / "missing-target")
os.environ["KB_CODEX_BIN"] = str(pathlib.Path(os.environ["TEST_TMP"]) / "missing-codex")
os.environ["KB_DOCTOR_CODEX_ALT_PATHS"] = str(broken_alt)
drift_findings = doctor._ih_check_codex_currency()
assert any(f.id.startswith("install-health:codex-launcher-drift") and f.severity == "P2"
           for f in drift_findings), [(f.id, f.severity) for f in drift_findings]

bad_exec = pathlib.Path(os.environ["TEST_TMP"]) / "bad-exec-codex"
bad_exec.write_text("not a binary\n", encoding="utf-8")
bad_exec.chmod(0o755)
os.environ["KB_CODEX_BIN"] = str(bad_exec)
os_error_findings = doctor._ih_check_codex_currency()
assert any(f.id.startswith("install-health:codex-version-failed") for f in os_error_findings)
assert any(f.id.startswith("install-health:codex-launcher-drift") for f in os_error_findings)
os.environ.pop("KB_DOCTOR_CODEX_ALT_PATHS", None)

manifest = load("codex_path_manifest", src / "kb-bootstrap-manifest")
root = src.parent
items = manifest._build_inventory(root, pathlib.Path(os.environ["TEST_TMP"]) / "home")
assert any(item["source_path"].endswith("bin/_kb_codex.py")
           for item in items), [item["source_path"] for item in items]
for rel in (pathlib.Path("bin"), pathlib.Path("knowledge/bin")):
    layout = pathlib.Path(os.environ["TEST_TMP"]) / ("layout-" + str(rel).replace("/", "-"))
    module = layout / rel / "_kb_codex.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("# fixture\n", encoding="utf-8")
    rows = [item for item in manifest._build_inventory(layout, layout / "home")
            if item["artifact_id"] == "_kb_codex.py"]
    assert len(rows) == 1 and rows[0]["source_path"].endswith("bin/_kb_codex.py"), rows
PY
[[ $? -eq 0 ]] && ok "missing Codex degrades one lane and remains doctor/manifest-visible" \
  || fail "missing-Codex boundary or managed inventory failed"

# Broker must type the unavailable Codex attempt and continue to Claude without
# a traceback. The fake is intentionally found only through the test PATH.
cat > "$TMP/claude" <<'SH'
#!/bin/sh
echo CLAUDE_FALLBACK_OK
SH
chmod +x "$TMP/claude"
BROKER_OUT=$(PATH="$TMP:$PATH" KB_CODEX_BIN="$TMP/missing-codex" \
  KB_ORCHESTRATOR_BACKENDS="codex,claude" \
  KB_ORCHESTRATOR_STATE_DIR="$TMP/state" KB_ORCHESTRATOR_LOG_FILE="$TMP/broker.log" \
  "$SRC_BIN/kb-orchestrator-run" --backend auto --cwd "$TMP/cwd" \
  --timeout 10 "reply with the marker" 2>"$TMP/broker.err")
broker_rc=$?
[[ $broker_rc -eq 0 && "$BROKER_OUT" == *CLAUDE_FALLBACK_OK* \
   && "$(cat "$TMP/broker.err")" != *Traceback* ]] \
  && ok "broker falls through missing Codex to Claude without traceback" \
  || fail "broker missing-Codex fallback failed (rc=$broker_rc)"

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
