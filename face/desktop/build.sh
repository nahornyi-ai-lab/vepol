#!/usr/bin/env bash
set -euo pipefail
desktop_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
exec /usr/bin/make -C "$desktop_dir" "$@"
