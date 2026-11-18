#!/usr/bin/env bash
# Codex launcher contract: every production callsite goes through the shared
# resolver (bin/_kb_codex.py). Lookup order: KB_CODEX_BIN (authoritative when
# set), ~/.local/bin/codex, codex on PATH, /opt/homebrew/bin/codex,
# /usr/local/bin/codex; copies inside a macOS app bundle are never picked up
# from PATH or the fixed fallbacks. Claude follows the same idea
# (bin/_kb_claude_runner.py claude_bin) so launchd's short PATH still finds it.

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
    import _kb_codex
    from _kb_codex import CodexUnavailable, codex_bin
except Exception as exc:
    print(f"IMPORT_ERROR: {exc}")
    raise SystemExit(1)

home = pathlib.Path(os.environ["TEST_HOME"])
cwd = pathlib.Path(os.environ["TEST_CWD"])
expected = str((home / ".local/bin/codex").resolve())

def fake(path: pathlib.Path, mode: int = 0o755) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(mode)
    return path

def unavailable(**kwargs) -> bool:
    try:
        codex_bin(**kwargs)
    except CodexUnavailable:
        return True
    return False

# The fixed fallbacks point into this sandbox, so the host's own installs
# (if any) can never leak into the assertions below.
system = cwd / "system"
_kb_codex.SYSTEM_CANDIDATES = (str(system / "brew/codex"), str(system / "local/codex"))

on_path = fake(cwd / "pathbin/codex")
path_env = {"PATH": f"{cwd / 'pathbin'}"}

assert codex_bin(env={}, home=home, cwd=cwd) == expected
assert codex_bin(env={"PATH": ""}, home=home, cwd=cwd) == expected
# ~/.local/bin/codex comes before PATH.
assert codex_bin(env=path_env, home=home, cwd=cwd) == expected

override = cwd / "override-codex"
override.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
override.chmod(0o755)
assert codex_bin(env={"KB_CODEX_BIN": "./override-codex"}, home=home, cwd=cwd) == str(override.resolve())

override.chmod(0o644)
assert unavailable(env={"KB_CODEX_BIN": str(override)}, home=home, cwd=cwd), \
    "non-executable override accepted"
# An explicit override is authoritative: a broken one never falls through to
# ~/.local/bin, PATH or the fixed fallbacks (tests and owners rely on it).
assert unavailable(env={"KB_CODEX_BIN": str(cwd / "missing"), **path_env}, home=home, cwd=cwd), \
    "broken override fell through to another copy"

(home / ".local/bin/codex").unlink()
assert unavailable(env={}, home=home, cwd=cwd), "missing binary accepted with no PATH"

# Homebrew/npm style install found only on PATH.
assert codex_bin(env=path_env, home=home, cwd=cwd) == str(on_path.resolve())

# Non-executable and relative PATH entries are skipped.
fake(cwd / "noexec/codex", 0o644)
fake(cwd / "rel/codex")
assert codex_bin(env={"PATH": f"{cwd / 'noexec'}:rel:{cwd / 'pathbin'}"}, home=home, cwd=cwd) \
    == str(on_path.resolve())

# A copy inside a macOS app bundle is skipped, directly or through a symlink.
app_codex = fake(cwd / "Codex.app/Contents/Resources/codex")
link_dir = cwd / "linkbin"
link_dir.mkdir()
(link_dir / "codex").symlink_to(app_codex)
assert codex_bin(env={"PATH": f"{app_codex.parent}:{link_dir}:{cwd / 'pathbin'}"},
                 home=home, cwd=cwd) == str(on_path.resolve())
assert unavailable(env={"PATH": f"{app_codex.parent}:{link_dir}"}, home=home, cwd=cwd), \
    "app-bundle codex accepted"
# ...but an explicit override may still name it (the owner's choice).
assert codex_bin(env={"KB_CODEX_BIN": str(app_codex)}, home=home, cwd=cwd) == str(app_codex.resolve())

# Fixed fallbacks after PATH, in order.
local_codex = fake(system / "local/codex")
assert codex_bin(env={"PATH": ""}, home=home, cwd=cwd) == str(local_codex.resolve())
brew_codex = fake(system / "brew/codex")
assert codex_bin(env={"PATH": ""}, home=home, cwd=cwd) == str(brew_codex.resolve())
assert codex_bin(env=path_env, home=home, cwd=cwd) == str(on_path.resolve())

brew_codex.unlink(); local_codex.unlink(); on_path.unlink()
try:
    codex_bin(env=path_env, home=home, cwd=cwd)
except CodexUnavailable as exc:
    assert exc.path == (home / ".local/bin/codex").resolve(strict=False), exc.path
    assert str(exc).startswith("Codex executable unavailable: ") and "PATH" in str(exc), str(exc)
else:
    raise AssertionError("missing codex accepted")
PY
[[ $? -eq 0 ]] && ok "resolver order: override, ~/.local/bin, PATH, Homebrew/npm; app bundles skipped" \
  || fail "codex resolver contract failed"

# Claude lookup: KB_CLAUDE_BIN (if executable), PATH, ~/.local/bin, Homebrew/npm.
SRC_BIN="$SRC_BIN" TEST_TMP="$TMP" python3 - <<'PY'
import os
import pathlib
import sys

sys.path.insert(0, os.environ["SRC_BIN"])
import _kb_claude_runner as runner

tmp = pathlib.Path(os.environ["TEST_TMP"]) / "claude-lookup"
home = tmp / "home"
runner.CLAUDE_SYSTEM_CANDIDATES = (str(tmp / "system/brew/claude"), str(tmp / "system/local/claude"))

def fake(path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path

launchd = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
assert runner.claude_bin(env=launchd) == "claude", "nothing installed -> bare name (launch fails as before)"
brew = fake(tmp / "system/brew/claude")
assert runner.claude_bin(env=launchd) == str(brew)
native = fake(home / ".local/bin/claude")
assert runner.claude_bin(env=launchd) == str(native), "~/.local/bin wins over the fixed fallbacks"
on_path = fake(tmp / "pathbin/claude")
assert runner.claude_bin(env={**launchd, "PATH": f"{on_path.parent}:/usr/bin:/bin"}) == str(on_path), \
    "PATH wins over ~/.local/bin"
pinned = fake(tmp / "pinned/claude")
assert runner.claude_bin(env={**launchd, "KB_CLAUDE_BIN": str(pinned)}) == str(pinned), \
    "an executable KB_CLAUDE_BIN wins"
assert runner.claude_bin(env={**launchd, "KB_CLAUDE_BIN": "/nowhere/claude"}) == str(native), \
    "a KB_CLAUDE_BIN that is not executable falls through to the lookup"
PY
[[ $? -eq 0 ]] && ok "claude lookup: override, PATH, ~/.local/bin, Homebrew/npm" \
  || fail "claude lookup order failed"

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
def row(name):
    rows = [line for line in registry.splitlines() if line.split("|")[0].strip() == name]
    assert len(rows) == 1, rows
    fields = [f.strip() for f in rows[0].split("|")]
    return fields[1], fields[2].split(":")
kind, cands = row("codex")
assert kind == "path-any", kind
assert cands == ["$HOME/.local/bin/codex", "codex", "/opt/homebrew/bin/codex", "/usr/local/bin/codex"], cands
kind, cands = row("claude")
assert cands == ["claude", "$HOME/.local/bin/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"], cands
assert ".app/" not in registry
offer_codex = [l for l in offer.splitlines() if l.strip().startswith('"codex|')]
assert len(offer_codex) == 1 and "/opt/homebrew/bin/codex" in offer_codex[0], offer_codex
assert any(l.strip().startswith('"hermes|') for l in offer.splitlines()), "kb-cli-offer lists hermes"
assert "from _kb_codex import" in doctor and "shutil.which(\"codex\"" not in doctor
assert "https://chatgpt.com/codex/install.sh" in setup
assert "npm install -g @openai/codex" not in setup
PY
[[ $? -eq 0 ]] && ok "installer, roster, doctor and setup use the shared lookup contract" \
  || fail "install/diagnostic surfaces disagree with the lookup contract"

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
# a traceback. The fake is intentionally found only through the test PATH; an
# inherited KB_CLAUDE_BIN would win over PATH, so it is dropped here.
cat > "$TMP/claude" <<'SH'
#!/bin/sh
echo CLAUDE_FALLBACK_OK
SH
chmod +x "$TMP/claude"
BROKER_OUT=$(env -u KB_CLAUDE_BIN PATH="$TMP:$PATH" KB_CODEX_BIN="$TMP/missing-codex" \
  KB_ORCHESTRATOR_BACKENDS="codex,claude" \
  KB_ORCHESTRATOR_STATE_DIR="$TMP/state" KB_ORCHESTRATOR_LOG_FILE="$TMP/broker.log" \
  "$SRC_BIN/kb-orchestrator-run" --backend auto --cwd "$TMP/cwd" \
  --timeout 10 "reply with the marker" 2>"$TMP/broker.err")
broker_rc=$?
[[ $broker_rc -eq 0 && "$BROKER_OUT" == *CLAUDE_FALLBACK_OK* \
   && "$(cat "$TMP/broker.err")" != *Traceback* ]] \
  && ok "broker falls through missing Codex to Claude without traceback" \
  || fail "broker missing-Codex fallback failed (rc=$broker_rc)"

# Scheduled jobs run under launchd, whose PATH has no ~/.local/bin. A Claude
# that the native installer put there must still be found, by the broker and
# by kb-claude-run, and no model is pinned unless CLAUDE_MODEL is set. env -i
# keeps the caller's KB_CLAUDE_BIN/CLAUDE_MODEL out; no real agent is reachable.
PY3="$(command -v python3)"
LHOME="$TMP/launchd-home"; mkdir -p "$LHOME/.local/bin"
cat > "$LHOME/.local/bin/claude" <<SH
#!/bin/sh
printf '%s\n' "\$*" >> "$TMP/claude-argv.log"
echo NATIVE_CLAUDE_OK
SH
chmod +x "$LHOME/.local/bin/claude"
launchd_broker() {  # launchd_broker <state-name> [VAR=value ...]
  local name="$1"; shift
  env -i HOME="$LHOME" PATH="/usr/bin:/bin" "$@" \
    KB_ORCHESTRATOR_STATE_DIR="$TMP/$name" KB_ORCHESTRATOR_LOG_FILE="$TMP/$name.log" \
    KB_CLAUDE_RUN_ROOT="$TMP/launchd-runs" \
    "$PY3" "$SRC_BIN/kb-orchestrator-run" --backend auto --cwd "$TMP/cwd" \
    --timeout 10 "reply with the marker" 2>"$TMP/$name.err"
}
OUT=$(launchd_broker ld1 KB_CODEX_BIN="$TMP/missing-codex" KB_ORCHESTRATOR_BACKENDS="codex,claude"); rc=$?
[[ $rc -eq 0 && "$OUT" == *NATIVE_CLAUDE_OK* ]] \
  && ok "broker finds Claude in ~/.local/bin with launchd's PATH" \
  || fail "broker missed ~/.local/bin/claude under a launchd PATH (rc=$rc, err=$(tail -c 200 "$TMP/ld1.err"))"
[[ -s "$TMP/claude-argv.log" && "$(cat "$TMP/claude-argv.log")" != *--model* ]] \
  && ok "broker passes no --model when CLAUDE_MODEL is unset" \
  || fail "broker pinned a Claude model: $(cat "$TMP/claude-argv.log" 2>/dev/null)"
: > "$TMP/claude-argv.log"
OUT=$(launchd_broker ld2 KB_CODEX_BIN="$TMP/missing-codex" KB_ORCHESTRATOR_BACKENDS="claude" \
  CLAUDE_MODEL="claude-test-model"); rc=$?
[[ $rc -eq 0 && "$(cat "$TMP/claude-argv.log")" == *"--model claude-test-model"* ]] \
  && ok "CLAUDE_MODEL still selects the Claude model" \
  || fail "CLAUDE_MODEL was not passed (rc=$rc): $(cat "$TMP/claude-argv.log" 2>/dev/null)"
OUT=$(env -i HOME="$LHOME" PATH="/usr/bin:/bin" KB_CLAUDE_RUN_ROOT="$TMP/launchd-runs" \
  "$PY3" "$SRC_BIN/kb-claude-run" --cwd "$TMP/cwd" -- claude -p hi 2>"$TMP/ld3.err"); rc=$?
[[ $rc -eq 0 && "$OUT" == *NATIVE_CLAUDE_OK* ]] \
  && ok "kb-claude-run -- claude finds ~/.local/bin/claude with launchd's PATH" \
  || fail "kb-claude-run missed ~/.local/bin/claude (rc=$rc, err=$(tail -c 200 "$TMP/ld3.err"))"

# A Homebrew/npm Codex that is only on PATH is used by the broker.
mkdir -p "$TMP/brewbin"
cat > "$TMP/brewbin/codex" <<'SH'
#!/bin/sh
out=""; prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
[ -n "$out" ] && printf 'PATH_CODEX_OK\n' > "$out"
exit 0
SH
chmod +x "$TMP/brewbin/codex"
OUT=$(env -i HOME="$LHOME" PATH="$TMP/brewbin:/usr/bin:/bin" KB_ORCHESTRATOR_BACKENDS="codex" \
  KB_ORCHESTRATOR_STATE_DIR="$TMP/ld4" KB_ORCHESTRATOR_LOG_FILE="$TMP/ld4.log" \
  "$PY3" "$SRC_BIN/kb-orchestrator-run" --backend auto --cwd "$TMP/cwd" \
  --timeout 10 "reply with the marker" 2>"$TMP/ld4.err"); rc=$?
[[ $rc -eq 0 && "$OUT" == *PATH_CODEX_OK* ]] \
  && ok "broker uses a Codex found only on PATH" \
  || fail "broker ignored the PATH Codex (rc=$rc, err=$(tail -c 200 "$TMP/ld4.err"))"

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == "0" ]]
