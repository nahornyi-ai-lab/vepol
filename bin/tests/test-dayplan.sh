#!/usr/bin/env bash
# Critical positive test for kb-dayplan (Plan my day).
#
# The behaviour that must hold: the owner's yes becomes exactly one calendar event per
# agreed block, a rerun writes nothing, a changed plan becomes one update and one delete,
# and any clash writes nothing. Runs against the fake calendar only (KB_CALENDAR_FAKE_DIR)
# in a temporary hub: it never touches the real calendar or the real hub.
#
# Usage:
#   bash bin/tests/test-dayplan.sh                    # tests the tree this script is in
#   KB_DAYPLAN_SRC_BIN=<bin dir> bash bin/tests/test-dayplan.sh

set -uo pipefail   # not -e: a failed assertion must not abort the harness

SRC_BIN="${KB_DAYPLAN_SRC_BIN:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DAYPLAN="${SRC_BIN}/kb-dayplan"

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "${TMP}"' EXIT

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

unset KB_CALENDAR_DISABLE
export TZ="Europe/Berlin"
HUB="${TMP}/hub"
FAKE="${TMP}/fake"
mkdir -p "${HUB}" "${FAKE}"
DATE="2026-10-14"
PLAN="${HUB}/personal/day-plans/${DATE}.json"
STORE="${FAKE}/dayplan-events.json"
CALLS="${FAKE}/dayplan-calls.jsonl"

if [[ ! -x "${DAYPLAN}" ]]; then
  echo "kb-dayplan not found or not executable: ${DAYPLAN}"
  exit 1
fi

dp() { KB_HUB="${HUB}" KB_CALENDAR_FAKE_DIR="${FAKE}" "${DAYPLAN}" "$@"; }

# plan_val <python expression over p>   -> value from the saved plan
plan_val() {
  python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "${PLAN}" "$1"
}
# store_val <python expression over ev> -> value from the fake calendar
store_val() {
  python3 -c 'import json,sys; ev=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "${STORE}" "$1"
}
# calls <op> -> how many write attempts of that kind the fake calendar saw
calls() {
  local n
  n=$(grep -c "\"op\": \"$1\"" "${CALLS}" 2>/dev/null)
  echo "${n:-0}"
}
check_eq() {  # check_eq <label> <got> <want>
  if [[ "$2" == "$3" ]]; then ok "$1 ($2)"; else fail "$1: got '$2', want '$3'"; fi
}

echo "== set -> confirm -> calendar creates exactly the agreed non-fixed blocks =="
dp set --date "${DATE}" --goal "Ship the release" --goal-source "tasks" \
  --outcome "Release notes written" --outcome "Regression run is green" \
  --block "09:00-10:30|Write release notes|work" \
  --block "14:00-15:00|Run regression|work" \
  --fixed "12:00-13:00|Lunch with the team" \
  --change "first proposal" >"${TMP}/o1" 2>&1
check_eq "set exits 0" "$?" "0"
check_eq "version after set" "$(plan_val 'p["version"]')" "1"
check_eq "status after set" "$(plan_val 'p["status"]')" "Draft"
check_eq "plan file mode" "$(python3 -c 'import os,sys; print(oct(os.stat(sys.argv[1]).st_mode & 0o777))' "${PLAN}")" "0o600"

dp confirm --date "${DATE}" --version 1 --said "yes, that is the plan" >"${TMP}/o2" 2>&1
check_eq "confirm exits 0" "$?" "0"
check_eq "status after confirm" "$(plan_val 'p["status"]')" "Confirmed"
check_eq "calendar untouched before the request" "$(calls create)" "0"

dp calendar --date "${DATE}" --version 1 --said "put it in the calendar" >"${TMP}/o3" 2>&1
check_eq "calendar exits 0" "$?" "0"
check_eq "status after calendar" "$(plan_val 'p["status"]')" "In calendar"
check_eq "events with a plan marker" "$(store_val 'len([e for e in ev if e["marker"].startswith("vepol-dayplan:2026-10-14:")])')" "2"
check_eq "create calls" "$(calls create)" "2"
check_eq "titles and times in the calendar" \
  "$(store_val 'sorted((e["title"], e["start"][11:], e["end"][11:]) for e in ev)')" \
  "[('Run regression', '14:00', '15:00'), ('Write release notes', '09:00', '10:30')]"
check_eq "event ids kept on the agreed blocks" \
  "$(plan_val 'all(b["event_id"] for b in p["blocks"] if not b["fixed"]) and all(b["event_id"] is None for b in p["blocks"] if b["fixed"])')" "True"

echo "== rerun writes nothing =="
STORE_SUM=$(cksum <"${STORE}")
CALL_N=$(grep -c . "${CALLS}")
dp calendar --date "${DATE}" --version 1 --said "again" >"${TMP}/o4" 2>&1
check_eq "rerun exits 0" "$?" "0"
check_eq "fake calendar unchanged" "$(cksum <"${STORE}")" "${STORE_SUM}"
check_eq "no write calls on rerun" "$(grep -c . "${CALLS}")" "${CALL_N}"
check_eq "status still In calendar" "$(plan_val 'p["status"]')" "In calendar"

echo "== a changed plan becomes one update and one delete =="
dp set --date "${DATE}" --goal "Ship the release" --goal-source "tasks" \
  --outcome "Release notes written" \
  --block "09:30-11:00|Write release notes|work" \
  --fixed "12:00-13:00|Lunch with the team" \
  --change "moved the notes, dropped the regression run" >"${TMP}/o5" 2>&1
check_eq "set v2 exits 0" "$?" "0"
check_eq "set after a confirmation is a draft again" "$(plan_val 'p["status"]')" "Draft"
dp confirm --date "${DATE}" --version 2 --said "yes, this version" >"${TMP}/o6" 2>&1
check_eq "confirm v2 exits 0" "$?" "0"
dp calendar --date "${DATE}" --version 2 --said "update the calendar" >"${TMP}/o7" 2>&1
check_eq "calendar v2 exits 0" "$?" "0"
check_eq "update calls in total" "$(calls update)" "1"
check_eq "delete calls in total" "$(calls delete)" "1"
check_eq "create calls in total" "$(calls create)" "2"
check_eq "events left in the calendar" "$(store_val '[(e["title"], e["start"][11:], e["end"][11:]) for e in ev]')" \
  "[('Write release notes', '09:30', '11:00')]"
check_eq "status after the second calendar run" "$(plan_val 'p["status"]')" "In calendar"

echo "== a clash writes nothing =="
dp set --date "${DATE}" --goal "Ship the release" --goal-source "tasks" \
  --block "09:30-11:00|Write release notes|work" \
  --block "16:00-16:30|Review the notes|review" \
  --fixed "12:00-13:00|Lunch with the team" \
  --change "added a review" >"${TMP}/o8" 2>&1
python3 - "${STORE}" <<'PY'
import json, sys
path = sys.argv[1]
events = json.load(open(path))
events.append({"id": "foreign-1", "title": "Dentist", "start": "2026-10-14T16:15:00+02:00",
               "end": "2026-10-14T17:00:00+02:00", "busy": True, "all_day": False, "marker": ""})
json.dump(events, open(path, "w"))
PY
dp confirm --date "${DATE}" --version 3 --said "yes, with the review" >"${TMP}/o9" 2>&1
STORE_SUM=$(cksum <"${STORE}")
CALL_N=$(grep -c . "${CALLS}")
dp calendar --date "${DATE}" --version 3 --said "write it" >"${TMP}/o10" 2>&1
RC=$?
check_eq "clash exits 3" "${RC}" "3"
check_eq "status after the clash" "$(plan_val 'p["status"]')" "Conflict"
check_eq "fake calendar unchanged by the clash" "$(cksum <"${STORE}")" "${STORE_SUM}"
check_eq "no write calls on the clash" "$(grep -c . "${CALLS}")" "${CALL_N}"
if grep -q "Dentist" "${TMP}/o10"; then ok "output names the clashing event"; else fail "output does not name the clash: $(cat "${TMP}/o10")"; fi

echo "== show --json contract =="
dp show --date "${DATE}" --json >"${TMP}/show.json" 2>"${TMP}/show.err"
check_eq "show --json exits 0" "$?" "0"
SHOW=$(python3 - "${TMP}/show.json" <<'PY'
import json, os, sys
d = json.load(open(sys.argv[1]))
prompt = d.get("prompt", "")
good = (d.get("exists") is True and d.get("version") == 3 and d.get("status") == "Conflict"
        and d.get("schema") == "day-plan/v1" and os.path.isabs(prompt)
        and os.path.basename(prompt) == "day-plan-prompt.md" and os.path.isfile(prompt))
print("ok" if good else "bad: " + json.dumps({k: d.get(k) for k in ("exists", "version", "status", "schema", "prompt")}))
PY
)
check_eq "exists, version, status, schema, prompt file" "${SHOW}" "ok"
dp show --date "2026-10-15" --json >"${TMP}/none.json" 2>&1
check_eq "show --json without a plan exits 0" "$?" "0"
check_eq "show --json without a plan says exists false" \
  "$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["exists"], d["date"], "prompt" in d)' "${TMP}/none.json")" "False 2026-10-15 True"

echo
echo "dayplan: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" == "0" ]]
