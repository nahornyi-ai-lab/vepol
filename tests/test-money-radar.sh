#!/usr/bin/env bash
# Tests for kb-money-radar (scheduled daily money-opportunity radar).
# Spec: project-local money-radar runtime spec 2026-06-20 (v6,
# approved: Codex + Claude approve-with-nits on sha256:9bc0a18e).
# Covers the load-bearing RED tests T1..T17 (rc contract, safety guard, idempotency,
# streak date-guard, matcher discrimination, roster fail-closed). Smoke/runtime
# acceptance (A13) is exercised live, not here.
#
# Usage: bash tests/test-money-radar.sh
set -uo pipefail

PASS=0; FAIL=0
SRC_BIN="${MONEY_RADAR_SRC_BIN:-$HOME/knowledge/bin}"
RUNNER="$SRC_BIN/kb-money-radar"
PY=python3
DATE=2026-06-20

ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

if [[ ! -f "$RUNNER" ]]; then echo "MISSING $RUNNER"; exit 1; fi

# --- canned payloads --------------------------------------------------------
# Two agents, same opportunity PARAPHRASED (share allegro/polish/board/game/
# collector after normalization) → corroboration=2.
CODEX_PAYLOAD='{"candidates":[{"title":"Flip vintage PL board games on Allegro before Christmas","band":"white","money_flow":"polish collectors pay for retro boardgames on allegro","who_earns":"resellers","why_now":"pre holiday demand","how_it_works":"buy low relist high","rough_numbers":"150-300 EUR per flip","proof_links":["https://allegro.pl/listing"],"risk":"sourcing","how_to_try":"list 5 sold-comp items on allegro today","interest":82,"money_real":78}]}'
CLAUDE_PAYLOAD='{"candidates":[{"title":"Pre-holiday resale of retro Polish boardgames via Allegro to collectors","band":"white","money_flow":"collectors buy vintage polish board games on allegro","who_earns":"local flippers","why_now":"holidays","how_it_works":"source and relist","rough_numbers":"180 EUR","proof_links":["https://allegro.pl/other"],"risk":"sourcing","how_to_try":"contact 3 sellers and relist","interest":78,"money_real":80}]}'

# --- shim factory -----------------------------------------------------------
mkhub() {
  local d; d=$(mktemp -d)
  mkdir -p "$d/hub/.orchestrator" "$d/hub/logs" "$d/hub/bin" "$d/hub/personal"
  mkdir -p "$d/proj/knowledge/sources" "$d/proj/knowledge/reports"
  : > "$d/proj/knowledge/escalations.md"
  echo "$d"
}

# generic agent shim: smoke→echo token; real→emit $PAYLOAD_FILE (+ to
# --output-last-message file if present); count invocations; rc from $RC_FILE
mkagent() { # path payload_file rc_file count_file
  cat > "$1" <<EOF
#!/usr/bin/env bash
echo "\$((\$(cat "$4" 2>/dev/null || echo 0)+1))" > "$4"
rc=\$(cat "$3" 2>/dev/null || echo 0)
out=""
prev=""
allargs="\$*"
for a in "\$@"; do
  if [ "\$prev" = "--output-last-message" ]; then out="\$a"; fi
  if [ "\$prev" = "--prompt-file" ] && [ -f "\$a" ]; then allargs="\$allargs \$(cat "\$a")"; fi
  prev="\$a"
done
case "\$allargs" in *"Reply with exactly"*) tok=\$(printf '%s' "\$allargs" | sed -n 's/.*exactly \([A-Z_]*\).*/\1/p' | head -1); echo "\$tok"; exit 0;; esac
payload=\$(cat "$2" 2>/dev/null)
[ -n "\$out" ] && printf '%s' "\$payload" > "\$out"
printf '%s' "\$payload"
exit \$rc
EOF
  chmod +x "$1"
}

mkchannel() { # path log_file rc_file  — one "SENT" line per delivery (countable)
  cat > "$1" <<EOF
#!/usr/bin/env bash
echo "SENT" >> "$2"
exit \$(cat "$3" 2>/dev/null || echo 0)
EOF
  chmod +x "$1"
}

mkcurl() { # path  (always reports 200)
  cat > "$1" <<'EOF'
#!/usr/bin/env bash
printf '200'
exit 0
EOF
  chmod +x "$1"
}

run_radar() { # hub_root extra_args...   (shims all 4 default agents)
  local d="$1"; shift
  KB_HUB="$d/hub" MONEY_RADAR_PROJECT="$d/proj" \
    KB_PROCESS_OUTPUTS="${OUTPUTS:-telegram,file}" \
    KB_PROCESS_BACKGROUND="${BG:-1}" \
    KB_CODEX_BIN="$d/hub/bin/codex-fake" \
    MONEY_RADAR_CLAUDE_BIN="$d/hub/bin/claude-fake" \
    MONEY_RADAR_GROK_BIN="$d/hub/bin/grok-fake" \
    MONEY_RADAR_ANTIGRAVITY_BIN="$d/hub/bin/agy-fake" \
    MONEY_RADAR_CHANNEL_BIN="$d/hub/bin/kb-channel-send" \
    MONEY_RADAR_CURL_BIN="$d/hub/bin/curl-fake" \
    "$PY" "$RUNNER" --text-only --date "$DATE" "$@"
}

setup() { # writes payloads & shims into hub; echoes hub root
  local d; d=$(mkhub)
  echo "$CODEX_PAYLOAD"  > "$d/codex_payload"
  echo "$CLAUDE_PAYLOAD" > "$d/claude_payload"
  # grok + antigravity default to empty (degraded) so behavior tests stay focused
  # on the codex/claude pair; tests that need them set their payloads.
  echo "" > "$d/grok_payload"; echo "" > "$d/agy_payload"
  for a in codex claude grok agy chan; do echo 0 > "$d/${a}_rc"; done
  for a in codex claude grok agy; do : > "$d/${a}_count"; done
  : > "$d/chan_log"
  mkagent "$d/hub/bin/codex-fake"  "$d/codex_payload"  "$d/codex_rc"  "$d/codex_count"
  mkagent "$d/hub/bin/claude-fake" "$d/claude_payload" "$d/claude_rc" "$d/claude_count"
  mkagent "$d/hub/bin/grok-fake"   "$d/grok_payload"   "$d/grok_rc"   "$d/grok_count"
  mkagent "$d/hub/bin/agy-fake"    "$d/agy_payload"    "$d/agy_rc"    "$d/agy_count"
  mkchannel "$d/hub/bin/kb-channel-send" "$d/chan_log" "$d/chan_rc"
  mkcurl "$d/hub/bin/curl-fake"
  echo "$d"
}

echo "=== kb-money-radar tests ==="

# T1: both substantive, paraphrased same opportunity → corroboration=2, execute, delivered
D=$(setup)
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && ok "T1: rc=0" || bad "T1: rc=$rc"
[ -f "$REPORT" ] && ok "T1: report written" || bad "T1: no report"
[ -f "$DIGEST" ] && ok "T1: digest written" || bad "T1: no digest"
[ -f "$D/proj/knowledge/sources/money-radar/$DATE-context.md" ] && ok "T1: context pack" || bad "T1: no context"
[ -f "$D/proj/knowledge/sources/money-radar/$DATE-codex.md" ] && [ -f "$D/proj/knowledge/sources/money-radar/$DATE-claude.md" ] && ok "T1: per-agent notes" || bad "T1: missing agent notes"
grep -q "2 agents" "$REPORT" && ok "T1: corroboration=2 label (paraphrase merged)" || bad "T1: paraphrase did NOT merge to corroboration 2"
[ -s "$D/chan_log" ] && ok "T1: telegram delivered" || bad "T1: not delivered"
grep -qi "разведка\|intelligence\|decide" "$DIGEST" && ok "T1: 'you decide' intelligence framing" || bad "T1: no intelligence framing"
grep -qiE "white|grey|black|⚪|🟡|⚫" "$DIGEST" && ok "T1: band label present" || bad "T1: no band label"

# T2: only codex substantive, claude empty → still ships the one find
D=$(setup); echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && ok "T2: rc=0 (degrade to subset)" || bad "T2: rc=$rc"
grep -qi "Allegro" "$D/proj/knowledge/reports/money-radar/$DATE.md" && ok "T2: the one find is in the report" || bad "T2: find missing"
[ -s "$D/chan_log" ] && ok "T2: still delivered" || bad "T2: not delivered"

# T3: both empty, attempts<cap → rc!=0, no telegram
D=$(setup); echo "" > "$D/codex_payload"; echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && ok "T3: rc!=0 below cap" || bad "T3: rc=0 unexpected"
[ ! -s "$D/chan_log" ] && ok "T3: no delivery" || bad "T3: delivered on failure"

# T3b: both empty, attempts==cap → honest 'unavailable' rc=0
D=$(setup); echo "" > "$D/codex_payload"; echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; run_radar "$D" >/dev/null 2>&1; run_radar "$D" >/dev/null 2>&1; rc=$?
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && ok "T3b: rc=0 at cap (honest degraded-success)" || bad "T3b: rc=$rc at cap"
grep -qi "unavailable\|недоступны" "$DIGEST" && ok "T3b: 'agents unavailable' digest" || bad "T3b: wrong digest"

# T9: NO filtering — a bold black-band find (huge money, money_real 95, interest 90)
# PASSES and appears in the report; for black band the operational how_to_try steps
# are NOT shown (defanged) in the digest/report.
D=$(setup)
echo '{"candidates":[{"title":"Bold underground cash flow","band":"black","money_flow":"millions move through this scheme right now","who_earns":"organized operators per public reporting","why_now":"enforcement gap this quarter","how_it_works":"general dynamics only","rough_numbers":"7-figure monthly volume","proof_links":["https://news.example/report"],"risk":"illegal — awareness only","how_to_try":"SECRET-OPERATIONAL-STEPS-DO-NOT-SHOW","interest":90,"money_real":95}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && ok "T9: rc=0" || bad "T9: rc=$rc"
grep -qi "Bold underground cash flow" "$REPORT" && ok "T9: bold black find is NOT filtered (appears in report)" || bad "T9: bold find wrongly dropped"
grep -qiE "black|⚫" "$DIGEST" && ok "T9: black band tag present in digest" || bad "T9: no black band tag"
grep -q "SECRET-OPERATIONAL-STEPS-DO-NOT-SHOW" "$REPORT" && bad "T9: black how_to_try leaked into report" || ok "T9: black how_to_try defanged (not in report)"
grep -q "SECRET-OPERATIONAL-STEPS-DO-NOT-SHOW" "$DIGEST" && bad "T9: black how_to_try leaked into digest" || ok "T9: black how_to_try defanged (not in digest)"

# T9f: BLACK-band source safety (spec §3) ENFORCED in code — dangerous links stripped from
# all bands, and black keeps ONLY reputable reporting/gov/research. Candidate still ships.
D=$(setup)
echo '{"candidates":[{"title":"BlackSrc test","band":"black","money_flow":"f","who_earns":"w","why_now":"n","how_it_works":"x","rough_numbers":"big","proof_links":["https://www.fbi.gov/news/x","https://t.me/+abc123secret","http://darkmarket3xyz.onion/list","https://randomblog.example.xyz/post"],"risk":"crime","how_to_try":"","interest":60,"money_real":80}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && grep -qi "BlackSrc test" "$REPORT" && ok "T9f: black find with mixed links still ships" || bad "T9f: black find dropped (rc=$rc)"
grep -q "fbi.gov" "$REPORT" && ok "T9f: reputable black source (fbi.gov) kept" || bad "T9f: reputable source wrongly dropped"
grep -qE "t\.me|\.onion|randomblog" "$REPORT" && bad "T9f: dangerous/non-reputable black link leaked into report" || ok "T9f: dangerous + non-reputable black links stripped"
grep -qE "t\.me|\.onion|randomblog" "$DIGEST" && bad "T9f: dangerous black link leaked into digest" || ok "T9f: digest free of dangerous black links"

# T9g: a black find whose links are ALL unsafe → ships with NO links + a "withheld" note.
D=$(setup)
echo '{"candidates":[{"title":"AllUnsafe black","band":"black","money_flow":"f","who_earns":"w","why_now":"n","how_it_works":"x","rough_numbers":"big","proof_links":["https://t.me/+joinme","https://sketchysite.xyz/x"],"risk":"crime","how_to_try":"","interest":60,"money_real":80}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
grep -qiE "t\.me|sketchy" "$DIGEST" && bad "T9g: unsafe link leaked when all links unsafe" || ok "T9g: all-unsafe black links fully stripped"
grep -qi "withheld for safety" "$DIGEST" && ok "T9g: digest notes sources withheld for safety" || bad "T9g: missing withheld note"

# T9h: danger denylist applies to ALL bands — a .onion in a WHITE find is stripped, but a
# normal non-allowlisted site (white is not allowlist-restricted) is KEPT.
D=$(setup)
echo '{"candidates":[{"title":"White danger test","band":"white","money_flow":"real flow","who_earns":"sellers","why_now":"now","how_it_works":"resell","rough_numbers":"500 EUR","proof_links":["https://www.wallapop.com/item/123","http://evilmarket.onion/x"],"risk":"low","how_to_try":"list it","interest":70,"money_real":70}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
grep -q "wallapop.com" "$REPORT" && ok "T9h: white keeps a normal non-allowlisted source" || bad "T9h: white source wrongly dropped"
grep -q "\.onion" "$REPORT" && bad "T9h: .onion leaked in white find" || ok "T9h: danger denylist strips .onion on all bands"

# T9i: control/zero-width char smuggling is blocked (Codex re-review bypass 2026-06-21).
# `https://evil.onion<CTRL>.reuters.com` hid a live .onion host: the embedded char meant it
# didn't end in exactly ".onion" yet still matched the ".reuters.com" allowlist. Reject any
# link with control/ZWSP/tab/newline chars outright. Uses printf to embed real \n and \t.
D=$(setup)
NL=$(printf 'https://evil.onion\n.reuters.com/report')
TB=$(printf 'https://evil.onion\t.reuters.com/report')
python3 - "$D/codex_payload" "$NL" "$TB" <<'PY'
import json,sys
out,nl,tb=sys.argv[1],sys.argv[2],sys.argv[3]
zwsp="https://evil.onion​.reuters.com/report"
enq="https://evil.onion .reuters.com/report"   # U+2000 en-quad: NOT in any byte denylist
v6="https://[::1]/report"                            # bracketed IPv6 host
c={"title":"Smuggle test","band":"black","money_flow":"f","who_earns":"w","why_now":"n","how_it_works":"x","rough_numbers":"big","proof_links":[nl,tb,zwsp,enq,v6,"https://www.bka.de/report"],"risk":"crime","how_to_try":"","interest":60,"money_real":80}
open(out,"w").write(json.dumps({"candidates":[c]}))
PY
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && grep -qi "Smuggle test" "$REPORT" && ok "T9i: candidate still ships" || bad "T9i: dropped (rc=$rc)"
grep -q "onion" "$REPORT" || grep -q "onion" "$DIGEST" && bad "T9i: smuggled .onion host leaked" || ok "T9i: control/zero-width .onion smuggling blocked"
grep -q "bka.de" "$REPORT" && ok "T9i: bka.de (German law-enforcement) now kept" || bad "T9i: bka.de wrongly dropped"

# T9j: open-redirect / link-wrapper smuggling on an ALLOWLISTED host is dropped (Codex
# re-review round 3): first-hop host is reputable, but a dangerous host hides in the query
# string. Legit links with normal query strings must still survive.
D=$(setup)
python3 - "$D/codex_payload" <<'PY'
import json,sys
out=sys.argv[1]
bad=[
 "https://www.goo"+"gle.com/url?q=https://t."+"me/example_channel",
 "https://www.goo"+"gle.com/url?q=https://evil."+"onion/x",
 "https://l.face"+"book.com/l.php?u=https://disc"+"ord.gg/abc",
 "https://www.goo"+"gle.com/url?q=https%3A%2F%2Ft."+"me/channel",       # percent-encoded scheme
 "https://www.goo"+"gle.com/url?q=https%253A%252F%252Ft."+"me/x",       # double percent-encoded
 "https://www.goo"+"gle.com/url?q=https%2525253A%2525252F%2525252Ft."+"me/x",  # quad-encoded (Codex R4)
 "https://tor"+"2web.com/abcdef",                                       # Tor gateway
 "https://www.goo"+"gle.com/url?q=1.2.3.4/path",                        # scheme-less raw-IP dest (Codex R5)
 "https://www.goo"+"gle.com/url?q=https://1.2.3.4/path",               # raw-IP dest with scheme
]
good="https://www.reut"+"ers.com/world/article?utm_source=rss"
c={"title":"Redirect test","band":"black","money_flow":"f","who_earns":"w","why_now":"n","how_it_works":"x","rough_numbers":"big","proof_links":bad+[good],"risk":"crime","how_to_try":"","interest":60,"money_real":80}
open(out,"w").write(json.dumps({"candidates":[c]}))
PY
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && grep -qi "Redirect test" "$REPORT" && ok "T9j: candidate still ships" || bad "T9j: dropped (rc=$rc)"
grep -hqE "/url\?q=|l\.php\?u=|\.onion|disc.rd\.gg|2web\.com|1\.2\.3\.4" "$REPORT" "$DIGEST" && bad "T9j: open-redirect smuggled host leaked" || ok "T9j: open-redirect / wrapped danger dropped"
# black-band links are reduced to scheme://host/ (structural anti-smuggling), so the outlet
# domain must survive even though the path is intentionally stripped.
grep -q "reut.rs\|reuters\.com" "$REPORT" && ok "T9j: legit source outlet survives (reduced to domain for black)" || bad "T9j: legit source wrongly dropped"
grep -q "world/article" "$REPORT" && bad "T9j: black-band path NOT stripped (smuggling surface remains)" || ok "T9j: black-band link reduced to domain (path stripped)"

# T9k: black operational STEP-LIST in how_it_works (not just how_to_try) is defanged
# (Codex sweep 2026-06-21: steps shipped under "How it works"). Candidate still ships.
D=$(setup)
echo '{"candidates":[{"title":"Carding refund scheme","band":"black","money_flow":"stolen-card refunds laundered","who_earns":"carding crews","why_now":"holiday refund volume","how_it_works":"1. buy stolen cards at SECRETSHOP; 2. test BINs; 3. mule the refunds","rough_numbers":"5-figure monthly","proof_links":["https://www.bbc.com/news/x"],"risk":"serious crime","how_to_try":"","interest":70,"money_real":80}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
[ $rc -eq 0 ] && grep -qi "Carding refund scheme" "$REPORT" && ok "T9k: black find with smuggled steps still ships" || bad "T9k: dropped (rc=$rc)"
grep -hqE "test BINs|mule the refunds|SECRETSHOP|1\. buy" "$REPORT" "$DIGEST" && bad "T9k: black operational steps leaked into output" || ok "T9k: black step-list defanged (not in report/digest)"

# T9l: a band SYNONYM for illegal ("illegal") is treated as BLACK, not grey — so how_to_try
# is blanked and reputable-only source policy applies (Codex sweep 2026-06-21).
D=$(setup)
echo '{"candidates":[{"title":"Illegal-band test","band":"illegal","money_flow":"f","who_earns":"w","why_now":"n","how_it_works":"general dynamics","rough_numbers":"big","proof_links":["https://freshcards.example/list"],"risk":"crime","how_to_try":"buy cards from a vendor channel","interest":70,"money_real":80}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
grep -hqE "buy cards from a vendor channel" "$REPORT" "$DIGEST" && bad "T9l: illegal-synonym kept how_to_try (treated as grey)" || ok "T9l: illegal-synonym → black, how_to_try blanked"
grep -hq "freshcards.example" "$REPORT" "$DIGEST" && bad "T9l: illegal-synonym kept non-reputable source" || ok "T9l: illegal-synonym → black source policy applied"

# T9m: malformed field TYPES (number where string expected, non-str in proof_links) must
# not crash the run (Codex sweep 2026-06-21: LLM JSON will eventually do this).
D=$(setup)
echo '{"candidates":[{"title":"Typed-wrong offer","band":"white","money_flow":"real flow","who_earns":"sellers","why_now":"now","how_it_works":"resell","rough_numbers":1234,"proof_links":[123,"https://a.b"],"risk":"low","how_to_try":"list it","interest":70,"money_real":75}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qi "Typed-wrong offer" "$D/proj/knowledge/reports/money-radar/$DATE.md" && ok "T9m: malformed field types coerced, no crash, ships (rc=0)" || bad "T9m: malformed types crashed/dropped (rc=$rc)"

# T9d: malformed numeric field → COERCED, candidate still SHIPS (rc=0, title appears)
D=$(setup)
echo '{"candidates":[{"title":"Coerced-number offer","band":"white","money_flow":"real flow","who_earns":"sellers","why_now":"now","how_it_works":"buy relist","rough_numbers":"100 EUR","proof_links":["https://a.b"],"risk":"low","how_to_try":"list today","interest":"~50","money_real":70}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qi "Coerced-number offer" "$D/proj/knowledge/reports/money-radar/$DATE.md" && ok "T9d: string interest coerced, candidate still ships (rc=0)" || bad "T9d: malformed numeric handling wrong (rc=$rc)"

# T9e: an EMPTY field renders as NO line (not a dangling "Label:" with nothing after).
# live-smoke quality nit 2026-06-21: claude left how_it_works blank and the digest showed
# "How it works:" with an empty value. The find must still ship; only the field is omitted.
D=$(setup)
echo '{"candidates":[{"title":"Empty-howto offer","band":"white","money_flow":"real flow","who_earns":"sellers","why_now":"seasonal spike","how_it_works":"","rough_numbers":"100 EUR","proof_links":["https://a.b"],"risk":"low","how_to_try":"list today","interest":80,"money_real":75}]}' > "$D/codex_payload"
echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
[ $rc -eq 0 ] && grep -qi "Empty-howto offer" "$REPORT" && ok "T9e: candidate with empty field still ships (rc=0)" || bad "T9e: empty-field candidate dropped (rc=$rc)"
if grep -qE "(How it works|Как устроено): *$" "$DIGEST"; then bad "T9e: empty field rendered as a dangling label line"; else ok "T9e: empty field omitted, no dangling label"; fi
grep -qi "real flow" "$DIGEST" && ok "T9e: non-empty fields still rendered" || bad "T9e: non-empty field lost"

# T11b: cost cap — 9-agent override rejected
D=$(setup)
{ for i in $(seq 1 9); do echo "- id: a$i"; echo "  kind: stdout"; echo "  role: structured"; echo "  web: false"; echo "  bin: /bin/echo"; echo "  argv: [hi]"; echo "  smoke_token: OK"; done; } > "$D/hub/personal/money-radar-agents.yaml"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && ok "T11b: oversized roster rejected (rc!=0)" || bad "T11b: oversized roster accepted"
[ ! -s "$D/codex_count" ] && ok "T11b: no real agents launched on rejection" || bad "T11b: agents launched despite rejection"

# T11c: social/web adapters now RUN in background (owner directive 2026-06-21:
# all agents have internet; the old social-rejection gate is removed). A social
# override agent with a working shim runs and contributes.
D=$(setup)
cp "$D/hub/bin/codex-fake" "$D/hub/bin/sniffer-fake"
echo "$CODEX_PAYLOAD" > "$D/sniffer_payload"; echo 0 > "$D/sniffer_rc"; : > "$D/sniffer_count"
mkagent "$D/hub/bin/sniffer-fake" "$D/sniffer_payload" "$D/sniffer_rc" "$D/sniffer_count"
cat > "$D/hub/personal/money-radar-agents.yaml" <<YML
- id: sniffer
  kind: stdout
  role: social
  web: true
  bin: $D/hub/bin/sniffer-fake
  argv: ["{prompt}"]
  smoke_token: CODEX_OK
YML
BG=1 KB_HUB="$D/hub" MONEY_RADAR_PROJECT="$D/proj" KB_PROCESS_OUTPUTS="telegram,file" KB_PROCESS_BACKGROUND=1 \
  MONEY_RADAR_CHANNEL_BIN="$D/hub/bin/kb-channel-send" MONEY_RADAR_CURL_BIN="$D/hub/bin/curl-fake" \
  "$PY" "$RUNNER" --text-only --date "$DATE" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ -f "$D/proj/knowledge/sources/money-radar/$DATE-sniffer.md" ] && ok "T11c: social/web adapter RUNS in background (gate removed)" || bad "T11c: social adapter blocked (rc=$rc)"

# T11d: fail-closed on malformed adapter (missing web)
D=$(setup)
cat > "$D/hub/personal/money-radar-agents.yaml" <<'YML'
- id: bad
  kind: stdout
  role: structured
  bin: /bin/echo
  argv: [hi]
  smoke_token: OK
YML
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && ok "T11d: fail-closed on malformed adapter" || bad "T11d: malformed adapter accepted"

# T16: all 4 default agents are web-enabled (owner directive 2026-06-21)
ROSTER=$($PY -c "
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('mr','$RUNNER').load_module()
r=m.default_roster()
print(','.join(a['id'] for a in r))
print('webcount', sum(1 for a in r if a.get('web')))
")
echo "$ROSTER" | head -1 | grep -q "codex" && echo "$ROSTER" | grep -q "grok" && echo "$ROSTER" | grep -q "antigravity" && ok "T16a: default roster has codex+claude+grok+antigravity" || bad "T16a: default roster missing agents ($ROSTER)"
echo "$ROSTER" | grep -q "webcount 4" && ok "T16b: all 4 default agents web-enabled" || bad "T16b: not all agents web-enabled ($ROSTER)"
grep -q "WebSearch,WebFetch" "$RUNNER" && ok "T16c: claude has WebSearch/WebFetch tools" || bad "T16c: claude web tools missing"
grep -q "network_access=true" "$RUNNER" && ok "T16d: codex has network access" || bad "T16d: codex network missing"

# T16e: codex strips the inherited chrome-devtools/browser MCP (which hangs under the
# sandbox → 420s empty-output kill, diag 2026-06-21) and runs low reasoning. All three
# flags must be present or the hang/loop can silently return.
CODEX_ARGV=$(python3 -c "
import importlib.util,sys
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('mr','$RUNNER').load_module()
cx=[a for a in m.default_roster() if a['id']=='codex'][0]
print(' '.join(cx['argv']))
")
echo "$CODEX_ARGV" | grep -q "mcp_servers={}" && echo "$CODEX_ARGV" | grep -q "plugins={}" && ok "T16e: codex disables browser MCP (mcp_servers={} + plugins={})" || bad "T16e: codex browser-MCP not disabled ($CODEX_ARGV)"
echo "$CODEX_ARGV" | grep -q "model_reasoning_effort=low" && ok "T16e: codex uses low reasoning (tight searches)" || bad "T16e: codex reasoning not capped"

# T18: owner-language output — the digest content must come back in the owner's language,
# not English (owner 2026-06-22 "радар пришёл на английском"). The agent prompt carries a
# LANGUAGE directive for non-en owners; the digest labels/band tags localize; en is unchanged.
python3 -c "
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('mr','$RUNNER').load_module()
m.owner_lang=lambda: 'ru'
assert 'Russian' in m._lang_directive(), 'no ru directive'
lab=m.labels()
assert lab['bands']['black']=='⚫ чёрная', lab['bands']
assert lab['conf_vals']['medium']=='средняя'
blk=m._find_block(1,{'candidate':{'title':'X','band':'black','money_flow':'y','proof_links':[]},'corroboration':2,'rank_score':80.0}, lab)
assert 'ранг' in blk and 'чёрная' in blk and 'агентов' in blk, blk
m.owner_lang=lambda: 'en'
assert m._lang_directive()=='', 'en must add no directive'
assert m._find_block(1,{'candidate':{'title':'X','band':'white','proof_links':[]},'corroboration':1,'rank_score':50.0}, m.labels()).count('rank')==1
print('ok')
" >/dev/null 2>&1 && ok "T18: owner-language directive + localized ru digest (en unchanged)" || bad "T18: owner-language output broken"

# T19: chrome (digest labels) must be language-agnostic across the SAME set the content
# directive supports — not a ru/en-only hardcode (owner 2026-06-22 "vepol работает на языке
# пользователя, а не хардкодит язык"). Every LANG_NAMES code has a complete localized label
# set; en is the universal fallback; a non-ru/en owner gets localized chrome, not English.
python3 -c "
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('mr','$RUNNER').load_module()
# invariant: chrome covers exactly the languages the content directive covers
assert set(m.L) == set(m.LANG_NAMES), ('chrome/content lang drift', set(m.LANG_NAMES)^set(m.L))
req=set(m.L['en'])
for code in m.LANG_NAMES:
    lab=m.L[code]
    assert set(lab)==req, (code,'key mismatch',req^set(lab))
    assert set(lab['bands'])=={'white','grey','black'}, (code,'bands')
    assert set(lab['conf_vals'])=={'high','medium','low'}, (code,'conf_vals')
    for k,v in lab.items():
        if isinstance(v,str): assert v.strip(), (code,k,'empty label')
        elif isinstance(v,dict):
            for sk,sv in v.items(): assert sv.strip(), (code,k,sk,'empty')
# a non-ru/en owner: chrome localizes (Spanish sample), no English label leaks
m.owner_lang=lambda:'es'
lab=m.labels()
assert lab is m.L['es'], 'es did not select es chrome'
assert lab['bands']['black']=='⚫ negra' and lab['rank']=='rango', lab['bands']
blk=m._find_block(1,{'candidate':{'title':'X','band':'black','money_flow':'y','proof_links':[]},'corroboration':2,'rank_score':80.0}, lab)
assert 'negra' in blk and 'rango' in blk, blk
assert 'Money flow' not in blk and 'Why now' not in blk, ('English chrome leaked',blk)
# BOUNDARY (the property that actually matters, not just table-equality): an UNSUPPORTED
# profile language must degrade CONTENT and CHROME to English together — never content-in-X
# under English labels (Codex stop-review 2026-06-22). 'xx' is in neither table.
assert 'xx' not in m.LANG_NAMES and 'xx' not in m.L, 'xx must be unsupported for this test'
m.owner_lang=lambda:'xx'
assert m._lang_directive()=='', 'unsupported lang must NOT emit a content directive'
assert m.labels() is m.L['en'], 'unsupported lang chrome must fall back to en'
print('ok')
" >/dev/null 2>&1 && ok "T19: chrome+content language sets agree; unsupported degrades to en in lockstep" || bad "T19: chrome/content language sets misaligned"

# T6: telegram delivery failure → rc!=0
D=$(setup); echo 1 > "$D/chan_rc"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && ok "T6: delivery failure → rc!=0" || bad "T6: delivery failure swallowed"

# T8: idempotent rerun reuses substantive cache (0 extra agent calls)
D=$(setup)
run_radar "$D" >/dev/null 2>&1
c1=$(cat "$D/codex_count" | wc -l | tr -d ' '); [ -s "$D/codex_count" ] && c1=$(tail -1 "$D/codex_count")
run_radar "$D" >/dev/null 2>&1
c2=$(tail -1 "$D/codex_count")
[ "$c1" = "$c2" ] && ok "T8: rerun reused cache (codex invocations $c1==$c2)" || bad "T8: codex re-invoked ($c1 -> $c2)"

# T8c: --force re-invokes agents
D=$(setup)
run_radar "$D" >/dev/null 2>&1; c1=$(tail -1 "$D/codex_count")
run_radar "$D" --force >/dev/null 2>&1; c2=$(tail -1 "$D/codex_count")
[ "$c2" -gt "$c1" ] && ok "T8c: --force re-invoked agents ($c1 -> $c2)" || bad "T8c: --force did not rerun"

# T10: stray write INTO THE RADAR'S PRIVATE DIR → guard fails the run
D=$(setup)
# claude shim drops a stray file into the radar's own output dir, outside the allowlist
cat > "$D/hub/bin/claude-fake" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do case "\$a" in *"Reply with exactly"*) echo CLAUDE_OK; exit 0;; esac; done
echo "stray" > "$D/proj/knowledge/sources/money-radar/STRAY-OUT-OF-BAND.md"
cat "$D/claude_payload"
EOF
chmod +x "$D/hub/bin/claude-fake"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && ok "T10: stray file in radar's private dir fails the run (rc=$rc)" || bad "T10: guard missed out-of-band write"

# T10c: the guard GATES delivery — when it trips, the digest must NOT have shipped to
# Telegram (Codex sweep 2026-06-21: guard ran AFTER deliver, so a leak warned post-ship).
D=$(setup)
cat > "$D/hub/bin/claude-fake" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do case "\$a" in *"Reply with exactly"*) echo CLAUDE_OK; exit 0;; esac; done
echo "stray" > "$D/proj/knowledge/sources/money-radar/STRAY-OUT-OF-BAND.md"
cat "$D/claude_payload"
EOF
chmod +x "$D/hub/bin/claude-fake"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && [ ! -s "$D/chan_log" ] && ok "T10c: guard trip blocks Telegram delivery (nothing shipped)" || bad "T10c: digest delivered despite guard trip (rc=$rc, chan_log=$(wc -l < "$D/chan_log"))"

# T10b: concurrent write into the SHARED sources/ (unrelated dev work) does NOT trip the
# guard. This is the 2026-06-21 false-positive fix: the guard watches only the radar's
# private dirs, so other sessions writing to the shared sources/ no longer false-fail us.
D=$(setup)
cat > "$D/hub/bin/claude-fake" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do case "\$a" in *"Reply with exactly"*) echo CLAUDE_OK; exit 0;; esac; done
echo "unrelated review note" > "$D/proj/knowledge/sources/some-other-dev-review.md"
cat "$D/claude_payload"
EOF
chmod +x "$D/hub/bin/claude-fake"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && ok "T10b: concurrent write to shared sources/ does NOT false-fail the run (rc=$rc)" || bad "T10b: guard false-positived on shared-dir churn (rc=$rc)"

# T4: downstream fault (delivery fail) AT the attempt cap must still rc!=0 (cap never swallows)
D=$(setup); echo "" > "$D/codex_payload"; echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; run_radar "$D" >/dev/null 2>&1   # 2 attempts, still below cap
echo 1 > "$D/chan_rc"                                            # now make delivery fail
# restore substantive payloads so the 3rd attempt reaches delivery
echo "$CODEX_PAYLOAD" > "$D/codex_payload"; echo "$CLAUDE_PAYLOAD" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; rc=$?
[ $rc -ne 0 ] && ok "T4: downstream fault at/після cap still rc!=0" || bad "T4: cap swallowed a downstream fault (rc=0)"

# T-key: two clearly DIFFERENT opportunities do NOT merge (no "2 agents" label).
# Distinct title+why_now tokens → below the merge threshold → stay separate.
D=$(setup)
echo "finds: 2" > "$D/hub/personal/money-radar.yaml"
echo '{"candidates":[{"title":"Sell handmade ceramic mugs at tourist markets","band":"white","money_flow":"tourists pay cash for local ceramics","who_earns":"craft stall vendors","why_now":"autumn tourist crowds peak","how_it_works":"make and sell at stalls","rough_numbers":"90 EUR per day","proof_links":["https://a.example"],"risk":"weather","how_to_try":"book a stall","interest":70,"money_real":72}]}' > "$D/codex_payload"
echo '{"candidates":[{"title":"Resell imported mechanical keyboards to gamers","band":"white","money_flow":"esports buyers pay premiums for keyboards","who_earns":"import flippers","why_now":"competitive season hype spikes","how_it_works":"import and relist","rough_numbers":"120 EUR per unit","proof_links":["https://b.example"],"risk":"customs","how_to_try":"order samples","interest":68,"money_real":74}]}' > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
# two distinct candidates → neither corroborated → no "2 agents" merge label
if grep -q "2 agents" "$REPORT"; then bad "T-key: distinct candidates falsely merged"; else ok "T-key: distinct candidates did NOT merge"; fi
grep -qi "ceramic mugs" "$REPORT" && grep -qi "mechanical keyboards" "$REPORT" && ok "T-key: both candidates present" || bad "T-key: candidate lost"

# T-rank: higher money_real+interest ranks first in the digest (finds: 2 → both show)
D=$(setup)
echo "finds: 2" > "$D/hub/personal/money-radar.yaml"
echo '{"candidates":[{"title":"LOWSCORE offer","band":"white","money_flow":"modest flow","who_earns":"a few sellers","why_now":"minor seasonal bump","how_it_works":"resell basics","rough_numbers":"50 EUR","proof_links":["https://a.example"],"risk":"low","how_to_try":"list one item","interest":40,"money_real":45}]}' > "$D/codex_payload"
echo '{"candidates":[{"title":"HIGHSCORE bonanza","band":"white","money_flow":"large confirmed flow","who_earns":"many active operators","why_now":"huge live demand surge","how_it_works":"scale fast","rough_numbers":"5000 EUR","proof_links":["https://b.example"],"risk":"low","how_to_try":"jump in now","interest":95,"money_real":92}]}' > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
hi=$(grep -n "HIGHSCORE" "$DIGEST" | head -1 | cut -d: -f1)
lo=$(grep -n "LOWSCORE" "$DIGEST" | head -1 | cut -d: -f1)
[ -n "$hi" ] && [ -n "$lo" ] && [ "$hi" -lt "$lo" ] && ok "T-rank: higher money_real+interest ranked first" || bad "T-rank: ranking order wrong (hi=$hi lo=$lo)"

# T-div1: band diversity (owner 2026-06-21) — a high-money BLACK awareness item must not
# bury a strong WHITE opportunity. Default (1/day) auto-promotes the cross-lane find to #2.
D=$(setup)   # no finds override → default 1
echo '{"candidates":[{"title":"BLACK awareness pig butchering","band":"black","money_flow":"scam flow","who_earns":"syndicates","why_now":"AI deepfakes surge","how_it_works":"fake dashboards","rough_numbers":"billions/yr","proof_links":["https://fbi.gov"],"risk":"serious crime","how_to_try":"","interest":66,"money_real":90}]}' > "$D/codex_payload"
echo '{"candidates":[{"title":"WHITE missed-call recovery service","band":"white","money_flow":"SMBs pay for recovered leads","who_earns":"solo operators","why_now":"AI makes it cheap now","how_it_works":"AI answers missed calls","rough_numbers":"3000 EUR/mo","proof_links":["https://a.b"],"risk":"low","how_to_try":"build MVP","interest":76,"money_real":80}]}' > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
grep -qi "BLACK awareness" "$DIGEST" && grep -qi "WHITE missed-call" "$DIGEST" && ok "T-div1: black awareness + strong white BOTH shown (band diversity)" || bad "T-div1: cross-lane opportunity buried under awareness item"

# T-div2: a WEAK cross-lane find is NOT promoted — default stays 1 ("если интересные").
D=$(setup)
echo '{"candidates":[{"title":"BLACK strong awareness","band":"black","money_flow":"flow","who_earns":"crews","why_now":"now","how_it_works":"x","rough_numbers":"big","proof_links":["https://fbi.gov"],"risk":"crime","how_to_try":"","interest":66,"money_real":90}]}' > "$D/codex_payload"
echo '{"candidates":[{"title":"WHITE weak idea","band":"white","money_flow":"tiny flow","who_earns":"few","why_now":"meh","how_it_works":"x","rough_numbers":"20 EUR","proof_links":["https://a.b"],"risk":"low","how_to_try":"try","interest":30,"money_real":30}]}' > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
grep -qi "WHITE weak idea" "$DIGEST" && bad "T-div2: weak cross-lane find wrongly promoted to digest" || ok "T-div2: weak cross-lane find NOT promoted (default stays 1)"
grep -qi "BLACK strong awareness" "$DIGEST" && ok "T-div2: top find still shown" || bad "T-div2: top find missing"

# T-div3: a BLACK and a WHITE candidate with heavily overlapping tokens must NOT collapse
# into one merged find (Codex stop-review 2026-06-21: clustering keyed a dead `lane` field
# → cross-band merge). Different bands → never merge → both shown (band diversity), each
# corroboration=1 (no "2 agents" label).
D=$(setup)
echo '{"candidates":[{"title":"Counterfeit designer sneaker flipping ring","band":"black","money_flow":"fakes move fast","who_earns":"counterfeit crews","why_now":"hype sneaker drops this autumn","how_it_works":"x","rough_numbers":"big","proof_links":["https://www.bbc.com/news/x"],"risk":"illegal","how_to_try":"","interest":80,"money_real":85}]}' > "$D/codex_payload"
echo '{"candidates":[{"title":"Authentic designer sneaker flipping on resale apps","band":"white","money_flow":"resale buyers pay premiums","who_earns":"legit flippers","why_now":"hype sneaker drops this autumn","how_it_works":"buy retail relist","rough_numbers":"120 EUR","proof_links":["https://a.b"],"risk":"low","how_to_try":"cop and relist","interest":82,"money_real":80}]}' > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
REPORT="$D/proj/knowledge/reports/money-radar/$DATE.md"
DIGEST="$D/proj/knowledge/reports/money-radar/$DATE-digest.txt"
grep -q "2 agents" "$REPORT" && bad "T-div3: black+white collapsed into a merged find" || ok "T-div3: cross-band candidates did NOT merge"
grep -qi "Counterfeit designer sneaker" "$DIGEST" && grep -qi "Authentic designer sneaker" "$DIGEST" && ok "T-div3: both black + white finds shown (band diversity intact)" || bad "T-div3: a find was collapsed/lost"

# T11: positive override roster (alpha/beta, no codex/claude names) runs end-to-end
D=$(setup)
cp "$D/hub/bin/codex-fake" "$D/hub/bin/alpha-fake"; cp "$D/hub/bin/claude-fake" "$D/hub/bin/beta-fake"
cat > "$D/hub/personal/money-radar-agents.yaml" <<'YML'
- id: alpha
  kind: stdout
  role: structured
  web: false
  bin: PLACEHOLDER_ALPHA
  argv: ["{prompt}"]
  smoke_token: ALPHA_OK
- id: beta
  kind: stdout
  role: execution
  web: false
  bin: PLACEHOLDER_BETA
  argv: ["{prompt}"]
  smoke_token: BETA_OK
YML
sed -i '' "s#PLACEHOLDER_ALPHA#$D/hub/bin/alpha-fake#; s#PLACEHOLDER_BETA#$D/hub/bin/beta-fake#" "$D/hub/personal/money-radar-agents.yaml"
# alpha/beta shims must answer their own smoke tokens (mkagent extracts the token from the prompt)
MONEY_RADAR_ALPHA_BIN="$D/hub/bin/alpha-fake" MONEY_RADAR_BETA_BIN="$D/hub/bin/beta-fake" \
KB_HUB="$D/hub" MONEY_RADAR_PROJECT="$D/proj" KB_PROCESS_OUTPUTS="telegram,file" KB_PROCESS_BACKGROUND=1 \
MONEY_RADAR_CHANNEL_BIN="$D/hub/bin/kb-channel-send" MONEY_RADAR_CURL_BIN="$D/hub/bin/curl-fake" \
  "$PY" "$RUNNER" --text-only --date "$DATE" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && ok "T11: arbitrary client roster (alpha/beta) runs" || bad "T11: client roster failed (rc=$rc)"
[ -f "$D/proj/knowledge/sources/money-radar/$DATE-alpha.md" ] && ok "T11: alpha agent note written" || bad "T11: no alpha note"

# T6b: a delivered run, rerun, must NOT resend (send shim called exactly once) AND the
# rerun must return rc=0 — NOT crash before sending (Codex stop-review 2026-06-22: cached
# agent entries lacked "id" → re-run KeyError('id'); send-count alone hid it).
D=$(setup)
run_radar "$D" >/dev/null 2>&1; rc1=$?
n1=$(wc -l < "$D/chan_log" | tr -d ' ')
run_radar "$D" >/dev/null 2>&1; rc2=$?
run_radar "$D" >/dev/null 2>&1; rc3=$?
n2=$(wc -l < "$D/chan_log" | tr -d ' ')
[ "$n1" = "1" ] && [ "$n2" = "1" ] && ok "T6b: idempotent delivery (sent once across reruns)" || bad "T6b: resend happened ($n1 -> $n2)"
[ "$rc1" = "0" ] && [ "$rc2" = "0" ] && [ "$rc3" = "0" ] && ok "T6b: reruns return rc=0 (no crash before sending)" || bad "T6b: rerun failed (rc1=$rc1 rc2=$rc2 rc3=$rc3)"

# T6c: a run that fails at DELIVERY (status!=completed, but agents already captured) must,
# on the next run, REUSE the cached substantive captures without crashing and then deliver
# (exercises the cached-result reconstruction; the idempotency short-circuit does NOT apply
# because the prior run never reached completed/delivered).
D=$(setup); echo 1 > "$D/chan_rc"          # first run: delivery fails
run_radar "$D" >/dev/null 2>&1; rcf=$?
echo 0 > "$D/chan_rc"                        # delivery now works
run_radar "$D" >/dev/null 2>&1; rcok=$?
[ "$rcf" != "0" ] && [ "$rcok" = "0" ] && [ -s "$D/chan_log" ] && ok "T6c: rerun reuses cached captures, no crash, delivers (rc=0)" || bad "T6c: cache-reuse rerun broke (rcf=$rcf rcok=$rcok)"

# T17: streak per-day — two same-day failures raise streak by at most 1; later success resets
D=$(setup); echo "" > "$D/codex_payload"; echo "" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1; run_radar "$D" >/dev/null 2>&1   # 2 failing invocations same day
s=$($PY -c "import json;print(json.load(open('$D/hub/.orchestrator/money-radar-streak.json'))['streak'])" 2>/dev/null)
[ "$s" = "1" ] && ok "T17: two same-day failures → streak==1 (date-guarded)" || bad "T17: streak over-counted ($s)"
# now a healthy run same day must reset to 0
echo "$CODEX_PAYLOAD" > "$D/codex_payload"; echo "$CLAUDE_PAYLOAD" > "$D/claude_payload"
run_radar "$D" >/dev/null 2>&1
s2=$($PY -c "import json;print(json.load(open('$D/hub/.orchestrator/money-radar-streak.json'))['streak'])" 2>/dev/null)
[ "$s2" = "0" ] && ok "T17: later healthy run resets streak to 0" || bad "T17: streak not reset ($s2)"

# T13: runner imports no urllib
grep -q "import urllib" "$RUNNER" && bad "T13: runner imports urllib" || ok "T13: no urllib in runner"
# T14: no NotebookLM in background
grep -qi "notebooklm" "$RUNNER" && bad "T14: NotebookLM referenced in runner" || ok "T14: no NotebookLM"

echo
echo "=== kb-money-radar: $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ]
