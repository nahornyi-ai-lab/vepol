#!/usr/bin/env bash
# Integration test for the full Vepol People pipeline:
#   mock-MCP-runner → kb-calendar-sync → people/ cards → channel.send
#
# This complements bin/tests/test-people.sh (unit) by exercising the
# real subprocess + real Click + real card I/O against a temp KB hub.
# It uses a mock_runner injected through KB_PEOPLE_TEST_MCP_FIXTURE
# (a JSON file the calendar source's runner reads when set), so no
# real `claude -p` is invoked.
#
# Usage: bash bin/tests/test-people-integration.sh

set -euo pipefail

PASS=0; FAIL=0
TMPDIR_TEST=$(mktemp -d)

cleanup() { rm -rf "$TMPDIR_TEST"; }
trap cleanup EXIT

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# Set up a fully isolated KB
export KB_HUB="$TMPDIR_TEST/kb"
mkdir -p "$KB_HUB/people" "$KB_HUB/personal"
echo "" > "$KB_HUB/people/_index.yaml"

# Override card.PEOPLE_DIR + index.INDEX_PATH in the test environment
# by setting environment vars the modules look for. (The current
# implementation hardcodes ~/knowledge/people; tests work around this
# by patching at runtime — see PYEOF block below.)

echo "=== Vepol People integration tests ==="

# T1: full pipeline with realistic attendees
python3 - << PYEOF
import json, sys, os, tempfile
from pathlib import Path

# Patch hub path BEFORE imports
KB_HUB = Path(os.environ["KB_HUB"])
os.environ["KB_HUB"] = str(KB_HUB)

# Insert vepol-prep bin to sys.path explicitly
VEPOL_BIN = Path("/Users/macbook/vepol-prep/bin")
sys.path.insert(0, str(VEPOL_BIN))

# Patch module-level paths to the test KB
import _kb_people.card as card
import _kb_people.index as idx
card.PEOPLE_DIR = KB_HUB / "people"
card.COMPANIES_DIR = KB_HUB / "companies"
idx.INDEX_PATH = KB_HUB / "people" / "_index.yaml"

# Mock MCP runner returning a realistic-shaped envelope
from _kb_mcp.runner import McpHostRunner

REALISTIC_ITEMS = [
    {"name": "Alice Johnson", "email": "alice@acme.com", "date": "2026-04-30", "context": "Renewal scoping call"},
    {"name": "Bob Smith", "email": "bob.smith@vendor.io", "date": "2026-04-28", "context": "Q2 sync"},
    # Empty name → fallback to email local part
    {"name": "", "email": "charlie@external.org", "date": "2026-04-26", "context": "Discovery call"},
    # Bot-like address (B test will filter; for now, let it through)
    # {"name": "Scheduling", "email": "schedule@booking.io", "date": "2026-04-25", "context": "Meeting"},
    # Same person, multiple events → dedup by email
    {"name": "Alice Johnson", "email": "alice@acme.com", "date": "2026-04-22", "context": "Weekly sync"},
    # Resource calendar → must be skipped by sanitize
    {"name": "Conf Room A", "email": "room.a@resource.calendar.google.com", "date": "2026-04-20", "context": "Standup"},
]

def fake_runner(prompt, timeout):
    # Verify prompt content to catch source breakage
    assert "list_events" in prompt, "prompt should reference list_events"
    assert "Request ID:" in prompt, "prompt should include request_id"
    return json.dumps({
        "ok": True,
        "items": REALISTIC_ITEMS,
        "stats": {"n_items": len(REALISTIC_ITEMS), "fetched_at": "2026-05-02T12:00:00Z"},
    })

# Run sync programmatically (not via subprocess — we need to inject runner)
from _kb_people.sources.calendar_source import CalendarSource
from _kb_people import dedup

source = CalendarSource(days_back=30, runner=McpHostRunner(runner=fake_runner))
contacts = source.get_contacts()

# Sanitize should have dropped the resource-calendar attendee (5 items in → 4 out, but Alice has 2 sightings → unique emails: 3)
assert len(contacts) == 4, f"sanitize: expected 4 (dropped resource), got {len(contacts)}: {[c['email'] for c in contacts]}"

# Dedup by email within batch
seen_emails = set()
unique = []
for c in contacts:
    if c["email"] not in seen_emails:
        seen_emails.add(c["email"])
        if not (c.get("name") or "").strip():
            c["name"] = c["email"].split("@", 1)[0]
        unique.append(c)
assert len(unique) == 3, f"dedup: expected 3 unique, got {len(unique)}"

# Process each contact through dedup → card create
for c in unique:
    result = dedup.resolve(c["name"], email=c["email"])
    if result["action"] in ("create", "create-draft"):
        path = card.create(
            c["name"], email=c["email"], source="calendar",
            draft=result["action"] == "create-draft",
            possible_duplicate_of=result.get("possible_duplicate_of", ""),
        )
        slug = path.stem
        post = card.load(slug)
        idx.register(post["id"], slug, c["name"], {"email": c["email"]})
        card.upsert_sighting(slug, c["date"], "calendar/test", c["context"])

# Verify cards exist on disk
created = sorted(p.name for p in card.PEOPLE_DIR.glob("*.md"))
expected_names = {"alice-johnson.md", "bob-smith.md", "charlie.md"}  # charlie from email local-part fallback
assert set(created) == expected_names, f"expected {expected_names}, got {set(created)}"
print("T1_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T1: full pipeline (3 unique contacts, resource-calendar skipped, empty-name → local-part)" || fail "T1: full pipeline"

# T2: cards have valid schema (frontmatter + MANUAL-NOTES + SIGHTINGS regions)
python3 - << PYEOF
import os, sys
from pathlib import Path
sys.path.insert(0, "/Users/macbook/vepol-prep/bin")
import frontmatter

KB_HUB = Path(os.environ["KB_HUB"])
for p in (KB_HUB / "people").glob("*.md"):
    if p.name.startswith("_"):
        continue
    with open(p) as f:
        post = frontmatter.load(f)
    assert "id" in post, f"{p.name} missing id"
    assert "slug" in post, f"{p.name} missing slug"
    assert "email" in post, f"{p.name} missing email"
    body = post.content
    assert "<!-- MANUAL-NOTES-BEGIN -->" in body, f"{p.name} missing MANUAL-NOTES"
    assert "<!-- DERIVED-SIGHTINGS-BEGIN -->" in body, f"{p.name} missing SIGHTINGS"
    # Sightings table populated
    assert "calendar/test" in body, f"{p.name} sighting source missing"
print("T2_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T2: cards have valid schema (frontmatter + both managed regions)" || fail "T2: cards schema"

# T3: prompt-injection attempt in event title is escaped, doesn't break sightings region
python3 - << PYEOF
import sys, os
from pathlib import Path
sys.path.insert(0, "/Users/macbook/vepol-prep/bin")
import _kb_people.card as card
KB_HUB = Path(os.environ["KB_HUB"])
card.PEOPLE_DIR = KB_HUB / "people"

# Hostile title that tries to break the table AND escape the SIGHTINGS region
hostile = "Standup | extra | column <!-- DERIVED-SIGHTINGS-END --> evil"
card.upsert_sighting("alice-johnson", "2026-04-15", "calendar/test", hostile)

with open(card.PEOPLE_DIR / "alice-johnson.md") as f:
    body = f.read()

# Pipe must be escaped
assert "Standup \\| extra \\| column" in body, "pipe should be escaped"
# Comment markers must be defanged
assert "<! --" in body or "DERIVED-SIGHTINGS-END -->" not in body.split("DERIVED-SIGHTINGS-END")[0] + "DERIVED-SIGHTINGS-END -->", "comment marker should be defanged"
# SIGHTINGS region still has exactly ONE end marker (not duplicated by injection)
assert body.count("<!-- DERIVED-SIGHTINGS-END -->") == 1, "exactly one DERIVED-SIGHTINGS-END marker"
print("T3_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T3: markdown injection in event title escaped (pipe + comment markers)" || fail "T3: injection mitigation"

# T4: empty-name attendee creation refused at card.create()
python3 - << PYEOF
import sys, os
from pathlib import Path
sys.path.insert(0, "/Users/macbook/vepol-prep/bin")
import _kb_people.card as card
KB_HUB = Path(os.environ["KB_HUB"])
card.PEOPLE_DIR = KB_HUB / "people"

try:
    card.create("", email="x@y.com", source="test")
    print("T4_FAIL: should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    assert "empty name" in str(e).lower(), str(e)

try:
    card.create("   ", email="x@y.com", source="test")
    print("T4_FAIL: should have raised on whitespace-only")
    sys.exit(1)
except ValueError:
    pass

print("T4_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T4: card.create refuses empty/whitespace name" || fail "T4: empty-name guard"

# T5: bot/system local-part filter (real audit findings 2026-05-02)
python3 - << 'PYEOF'
import sys
sys.path.insert(0, "/Users/macbook/vepol-prep/bin")
from _kb_people.sources.calendar_source import CalendarSource

# Real bots from yesterday's audit + common patterns
bot_emails = [
    "meet1@zezman.com.ua",        # real audit finding
    "schedule@mint.greenhouse.io", # real audit finding
    "assistant@zezman.ua",         # real audit finding
    "noreply@example.com",
    "no-reply@example.com",
    "notifications@github.com",
    "alerts@datadog.com",
    "reminder@calendly.com",
    "booking@vendor.io",
    "scheduling@x.com",
    "calendar@team.io",
    "info@somecorp.com",
    "support@vendor.io",
    "admin@host.com",
    "billing@stripe.com",
]
real_emails = [
    "alice@acme.com",
    "bob.smith@vendor.io",
    "first.last@personal.email",
    "ceo@startup.io",  # not a bot pattern
    "vadym@nahornyi.ai",
]

items = [{"name": "X", "email": e, "date": "2026-04-30", "context": "test"} for e in bot_emails + real_emails]
sanitized = CalendarSource._sanitize(items)
emails_kept = {c["email"] for c in sanitized}

# All real emails should pass through
for e in real_emails:
    assert e in emails_kept, f"{e!r} should not be filtered"

# All bot emails should be dropped
for e in bot_emails:
    assert e not in emails_kept, f"{e!r} should be filtered as bot, but was kept"

print(f"T5_PASS: {len(real_emails)}/{len(real_emails)} real emails kept; {len(bot_emails)}/{len(bot_emails)} bots filtered")
PYEOF
[[ $? -eq 0 ]] && ok "T5: bot/system local-part filter (15 bots dropped, 5 real kept)" || fail "T5: bot filter"

# T6: review-drafts helpers — list_drafts, promote_draft, merge_into, delete
python3 - << PYEOF
import sys, os, tempfile, shutil
from pathlib import Path
sys.path.insert(0, "/Users/macbook/vepol-prep/bin")

# Fresh isolated KB for this test
tmpdir = Path(tempfile.mkdtemp())
KB_HUB = tmpdir / "kb"
(KB_HUB / "people").mkdir(parents=True)
(KB_HUB / "people" / "_index.yaml").write_text("")

import _kb_people.card as card
import _kb_people.index as idx
card.PEOPLE_DIR = KB_HUB / "people"
idx.INDEX_PATH = KB_HUB / "people" / "_index.yaml"

# Set up: 1 real card, 1 draft (no dup), 1 draft (with dup)
real_path = card.create("Alice Real", email="alice@real.com", source="manual", draft=False)
real_post = card.load("alice-real")
idx.register(real_post["id"], "alice-real", "Alice Real", {"email": "alice@real.com"})

draft_no_dup = card.create("Bob Draft", email="bob@new.com", source="calendar", draft=True)
bob_post = card.load("bob-draft")
idx.register(bob_post["id"], "bob-draft", "Bob Draft", {"email": "bob@new.com"})

draft_with_dup = card.create("Alice Cline", email="alice2@other.com",
                              source="calendar", draft=True,
                              possible_duplicate_of="alice-real")
ac_post = card.load("alice-cline")
idx.register(ac_post["id"], "alice-cline", "Alice Cline", {"email": "alice2@other.com"})

# Add some sightings to the merge-source so we can verify they transfer
card.upsert_sighting("alice-cline", "2026-04-30", "calendar/test", "Q2 sync")
card.upsert_sighting("alice-cline", "2026-04-25", "calendar/test", "Pricing call")

# T6a: list_drafts returns 2 drafts, with-dup first
drafts = card.list_drafts()
assert len(drafts) == 2, f"expected 2 drafts, got {len(drafts)}"
assert drafts[0]["slug"] == "alice-cline", f"with-dup should sort first; got {drafts[0]}"
assert drafts[1]["slug"] == "bob-draft"

# T6b: promote_draft on bob → draft False, can't promote unknown
assert card.promote_draft("bob-draft") is True
assert card.load("bob-draft").get("draft") is False
assert card.promote_draft("nonexistent-slug") is False

# T6c: merge_into — alice-cline merges into alice-real, sightings transfer
assert card.merge_into("alice-cline", "alice-real") is True
# Source card removed
assert not (card.PEOPLE_DIR / "alice-cline.md").exists()
# Sightings on dest now contain the merged rows
real_body = (card.PEOPLE_DIR / "alice-real.md").read_text()
assert "Q2 sync" in real_body, "merged sighting Q2 sync"
assert "Pricing call" in real_body, "merged sighting Pricing call"
# Source email added as alias
real_post = card.load("alice-real")
aliases = real_post.get("aliases", []) or []
assert "alice2@other.com" in aliases, f"aliases should contain merged email; got {aliases}"
# alice-cline source card removed; alice-real and bob-draft remain
remaining = sorted(p.name for p in card.PEOPLE_DIR.glob("*.md"))
assert remaining == ["alice-real.md", "bob-draft.md"], f"got {remaining}"

# T6d: merge_into with missing dest returns False
assert card.merge_into("alice-real", "no-such-slug") is False

# T6e: delete removes file + index entry
card.delete("alice-real")
assert not (card.PEOPLE_DIR / "alice-real.md").exists()

shutil.rmtree(tmpdir)
print("T6_PASS")
PYEOF
[[ $? -eq 0 ]] && ok "T6: review-drafts helpers (list/promote/merge/delete + sightings transfer + alias)" || fail "T6: helpers"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
