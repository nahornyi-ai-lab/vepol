#!/usr/bin/env python3
"""Critical positive test for kb-child-rollup (spec checks 1-5).

Run: python3 ~/knowledge/bin/test_child_rollup.py
Every check builds a fresh temp hub and runs the script as a subprocess with
KB_HUB and --hub pointing at it; the live hub is never touched.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parents[2] / "bin"
SCRIPT = BIN / "kb-child-rollup"
BEGIN = "<!-- kb-child-rollup:begin -->"
END = "<!-- kb-child-rollup:end -->"

passed = failed = 0
TEMPS = []


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")


PARENT_STATE = """# P — state

## Current Snapshot

Parent prose that must stay untouched.

## Next Actions

- parent task
"""

CHILD_STATE = """# {slug} — state

> Permanent contract: present-tense, overwrite-only.

## Current Snapshot

{slug} snapshot first line.
{slug} snapshot second line, still the same paragraph.

## Next Actions

- something

## Last Updated

{date}
"""

CHILD_LOG = """# {slug} log

## [2026-09-01] init | {slug} | "first"

body

## [2026-09-02] update | {slug} | "second"

## [2026-09-03] decision | {slug} | "third"
"""


def make_hub(with_b_state=True):
    hub = Path(tempfile.mkdtemp(prefix="child-rollup-test-"))
    TEMPS.append(hub)
    (hub / "personal").mkdir()
    (hub / "personal" / "profile.yaml").write_text("language: ru\n", encoding="utf-8")
    for slug in ("p", "a", "b"):
        (hub / slug / "knowledge").mkdir(parents=True)
    (hub / "hierarchy.yaml").write_text(
        "version: 1\n"
        "root: hub\n"
        "nodes:\n"
        "  hub:\n"
        "    kind: root\n"
        "    parent: null\n"
        f"    knowledge_path: {hub}\n"
        "    children: [p]\n"
        "  p:\n"
        "    kind: project\n"
        "    parent: hub\n"
        f"    knowledge_path: {hub}/p/knowledge\n"
        "    children: [a, b]\n"
        "  a:\n"
        "    kind: project\n"
        "    parent: p\n"
        f"    knowledge_path: {hub}/a/knowledge\n"
        "    children: []\n"
        "  b:\n"
        "    kind: project\n"
        "    parent: p\n"
        f"    knowledge_path: {hub}/b/knowledge\n"
        "    children: []\n",
        encoding="utf-8")
    (hub / "p" / "knowledge" / "state.md").write_text(PARENT_STATE, encoding="utf-8")
    (hub / "p" / "knowledge" / "log.md").write_text("# p log\n", encoding="utf-8")
    for slug, date in (("a", "2026-09-10"), ("b", "2026-09-11")):
        k = hub / slug / "knowledge"
        if slug != "b" or with_b_state:
            (k / "state.md").write_text(CHILD_STATE.format(slug=slug, date=date), encoding="utf-8")
        (k / "log.md").write_text(CHILD_LOG.format(slug=slug), encoding="utf-8")
    return hub


def run(hub):
    env = dict(os.environ)
    env["KB_HUB"] = str(hub)
    env.pop("KB_LANG", None)
    return subprocess.run([sys.executable, str(SCRIPT), "--hub", str(hub)],
                          env=env, capture_output=True, text=True)


def block_of(text):
    return text[text.index(BEGIN) + len(BEGIN):text.index(END)]


def sections(block):
    out, cur = {}, None
    for ln in block.split("\n"):
        if ln.startswith("### "):
            cur = ln[4:].split(" ", 1)[0]
            out[cur] = []
        if cur is not None:
            out[cur].append(ln)
    return out


def outcome(hub):
    files = sorted((hub / ".orchestrator").glob("child-rollup-*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else {}


def citations_ok(hub, slug, sec):
    """Every `state.md:<n>` / `log.md:<n>` points at the real line."""
    k = hub / slug / "knowledge"
    slines = (k / "state.md").read_text(encoding="utf-8").split("\n")
    llines = (k / "log.md").read_text(encoding="utf-8").split("\n")
    ok, n_cites = True, 0
    for ln in sec:
        m = re.search(r"\(источник: state\.md:(\d+)\)$", ln)
        if m:
            n_cites += 1
            ok &= ln.startswith(slines[int(m.group(1)) - 1].strip())
        m = re.match(r"^- (.*) \(log\.md:(\d+)\)$", ln)
        if m:
            n_cites += 1
            ok &= llines[int(m.group(2)) - 1] == "## " + m.group(1)
    return ok and n_cites > 0


# --- Check 1: first run inserts the section with verbatim, cited content ---
print("check 1: first run inserts the block")
hub = make_hub()
r = run(hub)
check("1 exit 0", r.returncode == 0)
st = (hub / "p" / "knowledge" / "state.md").read_text(encoding="utf-8")
heads = [m.start() for m in re.finditer(r"^## ", st, re.M)]
sec_pos = st.find("## Из дочерних проектов")
check("1 section after first ## and before the next", heads[0] < sec_pos == heads[1])
check("1 markers once", st.count(BEGIN) == 1 and st.count(END) == 1 and st.index(BEGIN) < st.index(END))
check("1 parent prose untouched", st.startswith(PARENT_STATE.split("## Next Actions")[0])
      and st.endswith("## Next Actions\n\n- parent task\n"))
secs = sections(block_of(st))
a_sec = secs.get("a", [])
check("1 a snapshot verbatim",
      "a snapshot first line. a snapshot second line, still the same paragraph. (источник: state.md:7)" in a_sec)
check("1 three headlines", sum(1 for ln in a_sec if ln.startswith("- [")) == 3)
check("1 a citations point at real lines", citations_ok(hub, "a", a_sec))
check("1 b citations point at real lines", citations_ok(hub, "b", secs.get("b", [])))
check("1 outcome updated", outcome(hub).get("p", {}).get("result") == "updated")

# --- Check 2: second run with no child change writes nothing ---
print("check 2: rerun is a no-op")
hub = make_hub()
run(hub)
sp, lp = hub / "p" / "knowledge" / "state.md", hub / "p" / "knowledge" / "log.md"
s1, l1 = sp.read_bytes(), lp.read_bytes()
r = run(hub)
check("2 exit 0", r.returncode == 0)
check("2 state.md byte-identical", sp.read_bytes() == s1)
check("2 log.md unchanged", lp.read_bytes() == l1)
check("2 result unchanged", outcome(hub).get("p", {}).get("result") == "unchanged")

# --- Check 3: one new child headline moves the block and logs one line ---
print("check 3: a new child headline is rolled up")
hub = make_hub()
run(hub)
sp, lp = hub / "p" / "knowledge" / "state.md", hub / "p" / "knowledge" / "log.md"
log_before = lp.read_text(encoding="utf-8")
with open(hub / "a" / "knowledge" / "log.md", "a", encoding="utf-8") as f:
    f.write('\n## [2026-09-20] update | a | "fourth"\n')
r = run(hub)
check("3 exit 0", r.returncode == 0)
st = sp.read_text(encoding="utf-8")
a_sec = sections(block_of(st)).get("a", [])
first_head = next((ln for ln in a_sec if ln.startswith("- [")), "")
check("3 new headline first", first_head.startswith('- [2026-09-20] update | a | "fourth"'))
check("3 child log date moved", a_sec and "log 2026-09-20)" in a_sec[0])
check("3 intro date moved", "по состоянию на 2026-09-20._" in st)
check("3 a citations still real", citations_ok(hub, "a", a_sec))
new_lines = lp.read_text(encoding="utf-8")[len(log_before):].strip().split("\n")
rollups = [ln for ln in new_lines if "rollup" in ln]
check("3 exactly one rollup line", len(rollups) == 1 and len([ln for ln in new_lines if ln.strip()]) == 1)
check("3 rollup names a only", rollups and " a (2026-09-20)" in rollups[0] and " b (" not in rollups[0])

# --- Check 4: corrupted markers leave the file untouched and fail loudly ---
print("check 4: corrupted markers")
hub = make_hub()
sp = hub / "p" / "knowledge" / "state.md"
sp.write_text(PARENT_STATE.replace("## Next Actions", BEGIN + "\n\n## Next Actions"), encoding="utf-8")
before = sp.read_bytes()
r = run(hub)
check("4 exit 1", r.returncode == 1)
check("4 file byte-identical", sp.read_bytes() == before)
check("4 stderr names markers-corrupted", "markers-corrupted" in r.stderr)
check("4 outcome says markers-corrupted", outcome(hub).get("p", {}).get("result") == "failed:markers-corrupted")

# --- Check 5: a child without state.md is shown as unavailable ---
print("check 5: unavailable child")
hub = make_hub(with_b_state=False)
r = run(hub)
check("5 exit 0", r.returncode == 0)
st = (hub / "p" / "knowledge" / "state.md").read_text(encoding="utf-8")
check("5 unavailable line", f"### b — вика недоступна ({hub}/b/knowledge)" in block_of(st))
check("5 a still rolled up", "### a — " in block_of(st))

for t in TEMPS:
    shutil.rmtree(t, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
