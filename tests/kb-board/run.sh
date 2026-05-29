#!/usr/bin/env bash
# Dedicated RED/contract suite for the future multiline kb-board implementation.
# Intentionally not wired into tests/run-all.sh until the approved cutover phase.
set -euo pipefail

cd "$(dirname "$0")"
python3 contract.py "$@"
