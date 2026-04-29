#!/usr/bin/env bash
# fake-agent.sh — synthetic agent that emits various OUTCOME shapes for testing
# the executor's contract enforcement.
#
# Usage:
#   fake-agent.sh valid-single   → emits OUTCOME: closed: ok
#   fake-agent.sh valid-fail     → emits OUTCOME: failed: bad
#   fake-agent.sh missing        → no OUTCOME line
#   fake-agent.sh multiple       → 2 OUTCOME lines
#   fake-agent.sh trailing       → OUTCOME followed by extra non-empty line
#   fake-agent.sh raw-write      → durable raw-write to backlog.md
#   fake-agent.sh stderr-only    → OUTCOME on stderr (not stdout)
#   fake-agent.sh bad-enum       → OUTCOME with invalid enum
#
# Argument 2 (optional) is the backlog.md path for raw-write fixture.

set -e
mode="${1:-valid-single}"
backlog="${2:-}"

case "$mode" in
  valid-single)
    echo "did some work"
    echo "OUTCOME: closed: task complete"
    ;;
  valid-escalated)
    echo "OUTCOME: escalated: needed human review"
    ;;
  valid-failed)
    echo "OUTCOME: failed: rate-limited"
    ;;
  missing)
    echo "did some work"
    echo "but forgot to emit OUTCOME"
    ;;
  multiple)
    echo "OUTCOME: closed: first one"
    echo "OUTCOME: failed: second one"
    ;;
  trailing)
    echo "OUTCOME: closed: ok"
    echo "extra line after outcome"
    ;;
  raw-write)
    if [ -z "$backlog" ]; then
      echo "raw-write mode requires backlog path as arg 2" >&2
      exit 1
    fi
    # Append a forbidden raw line to backlog.md, bypassing kb-backlog.
    {
      cat "$backlog"
      echo "- [ ] raw-injected by misbehaving agent"
    } > "$backlog.tmp"
    mv "$backlog.tmp" "$backlog"
    echo "OUTCOME: closed: did the thing (with raw write)"
    ;;
  stderr-only)
    echo "did some work"
    echo "OUTCOME: closed: only-on-stderr" >&2
    ;;
  bad-enum)
    echo "OUTCOME: succeeded: not-a-valid-enum-value"
    ;;
  *)
    echo "unknown mode: $mode" >&2
    exit 1
    ;;
esac
