#!/usr/bin/env bash
# Tests for Vepol People module
# Usage: bash bin/tests/test-people.sh

set -euo pipefail

PASS=0; FAIL=0
TMPDIR_TEST=$(mktemp -d)

cleanup() { rm -rf "$TMPDIR_TEST"; }
trap cleanup EXIT

# Override KB paths for testing
export KB_PEOPLE_DIR="$TMPDIR_TEST/people"
export KB_INDEX_PATH="$TMPDIR_TEST/people/_index.yaml"
mkdir -p "$KB_PEOPLE_DIR"

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

echo "=== Vepol People tests ==="

# T1: kb-contact add creates valid frontmatter
python3 - << 'PYEOF'
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
os.environ["KB_PEOPLE_DIR"] = os.environ.get("KB_PEOPLE_DIR", "/tmp/test-people")
from _kb_people import card
Path(os.environ["KB_PEOPLE_DIR"]).mkdir(parents=True, exist_ok=True)
import _kb_people.card as c
c.PEOPLE_DIR = Path(os.environ["KB_PEOPLE_DIR"])
path = c.create("Test Person", email="test@example.com", first_met_context="unit test")
import frontmatter as fm
post = fm.load(str(path))
assert post["name"] == "Test Person", f"name mismatch: {post['name']}"
assert post["email"] == "test@example.com"
assert "id" in post.metadata
assert path.exists()
print("T1_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T1: add creates valid frontmatter" || fail "T1: add creates valid frontmatter"

# T2: duplicate email → upsert same file
python3 - << 'PYEOF'
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as c
import _kb_people.index as idx
c.PEOPLE_DIR = Path(os.environ["KB_PEOPLE_DIR"])
idx.INDEX_PATH = Path(os.environ["KB_INDEX_PATH"])
from _kb_people.dedup import resolve
# Create first
p1 = c.create("Alice B", email="alice@example.com", source="manual")
post1 = c.load(p1.stem)
uid1 = post1["id"]
idx.register(uid1, p1.stem, "Alice B", {"email": "alice@example.com"})
# Resolve same email
result = resolve("Alice B", email="alice@example.com")
assert result["action"] == "update", f"Expected update, got {result['action']}"
assert result["uid"] == uid1
print("T2_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T2: same email → update action" || fail "T2: same email → update action"

# T3: dedup email match returns same UUID
python3 - << 'PYEOF'
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
import _kb_people.index as idx
idx.INDEX_PATH = Path(os.environ["KB_INDEX_PATH"])
uid = "test-uuid-1234"
idx.register(uid, "bob-jones", "Bob Jones", {"email": "bob@stripe.com"})
found = idx.lookup_by_email("bob@stripe.com")
assert found == uid, f"Expected {uid}, got {found}"
found2 = idx.lookup_by_email("BOB@STRIPE.COM")  # case insensitive
assert found2 == uid
print("T3_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T3: email lookup returns correct UUID (case-insensitive)" || fail "T3: email lookup"

# T4: managed block upsert preserves MANUAL-NOTES
python3 - << 'PYEOF'
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as c
c.PEOPLE_DIR = Path(os.environ["KB_PEOPLE_DIR"])
path = c.create("Carol D", email="carol@example.com")
slug = path.stem
# Manually write a note
post = c.load(slug)
body = post.content
body = body.replace(
    "<!-- MANUAL-NOTES-END -->",
    "My private note here.\n<!-- MANUAL-NOTES-END -->"
)
post.content = body
c.save(post, path)
# Now upsert a sighting
c.upsert_sighting(slug, "2026-04-30", "calendar", "Test meeting")
post2 = c.load(slug)
assert "My private note here." in post2.content, "Manual note was erased!"
assert "Test meeting" in post2.content
print("T4_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T4: upsert_sighting preserves MANUAL-NOTES block" || fail "T4: MANUAL-NOTES preservation"

# T5: list_due returns only contacts within horizon
python3 - << 'PYEOF'
import sys, os
from pathlib import Path
from datetime import date, timedelta
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as c
c.PEOPLE_DIR = Path(os.environ["KB_PEOPLE_DIR"])
# Due in 3 days → should appear with horizon=7
c.create("Due Soon", email="due@example.com", next_touch_due=(date.today() + timedelta(days=3)).isoformat(), draft=False)
# Due in 30 days → should NOT appear
c.create("Not Due", email="notdue@example.com", next_touch_due=(date.today() + timedelta(days=30)).isoformat(), draft=False)
results = c.list_due(7)
names = [r["name"] for r in results]
assert "Due Soon" in names, f"'Due Soon' not in {names}"
assert "Not Due" not in names, f"'Not Due' appeared unexpectedly"
print("T5_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T5: list_due filters by horizon correctly" || fail "T5: list_due"

# T7: _index.yaml atomic write
python3 - << 'PYEOF'
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
import _kb_people.index as idx
idx.INDEX_PATH = Path(os.environ["KB_INDEX_PATH"])
idx.register("uid-atomic-test", "atomic-slug", "Atomic Test", {"email": "atomic@test.com"})
assert idx.INDEX_PATH.exists()
# Verify no .tmp file left
assert not Path(str(idx.INDEX_PATH) + ".tmp").exists(), ".tmp file left after write"
data = idx._load()
assert "uid-atomic-test" in data
print("T7_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T7: _index.yaml atomic write, no .tmp leftover" || fail "T7: atomic write"

# T8: slug collision → UUID-suffix, not overwrite
python3 - << 'PYEOF'
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
import _kb_people.card as c
c.PEOPLE_DIR = Path(os.environ["KB_PEOPLE_DIR"])
p1 = c.create("John Smith", email="john1@example.com")
p2 = c.create("John Smith", email="john2@example.com")
assert p1 != p2, "Slug collision: same path returned"
assert p1.exists() and p2.exists()
print("T8_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T8: slug collision → UUID-suffix slug" || fail "T8: slug collision"

# T9: MCP runner strict envelope parse (preamble/trailing/tool-error/empty)
python3 - << 'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
from _kb_mcp.runner import McpHostRunner, McpResponseError, McpToolError

def r1(p, t): return 'Sure!\n{"ok": true, "items": [], "stats": {"n_items": 0, "fetched_at": "X"}}'
try:
    McpHostRunner(runner=r1).call("test"); raise AssertionError("expected raise")
except McpResponseError: pass

def r2(p, t): return '{"ok": true, "items": [], "stats": {"n_items": 0, "fetched_at": "X"}}\n\nThanks.'
try:
    McpHostRunner(runner=r2).call("test"); raise AssertionError("expected raise")
except McpResponseError: pass

def r3(p, t): return '{"ok": false, "error": "auth_required", "detail": "ya"}'
try:
    McpHostRunner(runner=r3).call("test"); raise AssertionError("expected raise")
except McpToolError as e:
    assert e.error == "auth_required"

def r4(p, t): return ""
try:
    McpHostRunner(runner=r4).call("test"); raise AssertionError("expected raise")
except McpResponseError: pass

print("T9_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T9: MCP runner strict envelope parse" || fail "T9: MCP runner parse"

# T10: Calendar source sanitize — invalid email/date dropped, lowercase, length caps
python3 - << 'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "knowledge" / "bin"))
from _kb_mcp.runner import McpHostRunner
from _kb_people.sources.calendar_source import CalendarSource

def mock(p, t):
    long_n = "A" * 500
    long_c = "B" * 1000
    return ('{"ok": true, "items": ['
            '{"name": "Alice", "email": "alice@example.com", "date": "2026-04-30", "context": "Standup"},'
            '{"name": "Bob", "email": "BOB@example.COM", "date": "2026-04-30", "context": "Standup"},'
            '{"name": "NoEmail", "email": "", "date": "2026-04-29", "context": "skip"},'
            '{"name": "BadDate", "email": "bd@x.com", "date": "yesterday", "context": "skip"},'
            f'{{"name": "{long_n}", "email": "long@example.com", "date": "2026-05-01", "context": "{long_c}"}}'
            '], "stats": {"n_items": 5, "fetched_at": "X"}}')

src = CalendarSource(days_back=7, runner=McpHostRunner(runner=mock))
contacts = src.get_contacts()
assert len(contacts) == 3, f"expected 3, got {len(contacts)}"
emails = [c["email"] for c in contacts]
assert emails == ["alice@example.com", "bob@example.com", "long@example.com"], emails
assert len(contacts[2]["name"]) == 200 and len(contacts[2]["context"]) == 500
print("T10_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T10: Calendar source sanitize" || fail "T10: Calendar source"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
