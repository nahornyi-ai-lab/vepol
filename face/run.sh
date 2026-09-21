#!/usr/bin/env bash
# Vepol Face launcher. Loopback only.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$here/.venv/bin/python" -m vepol_face.server "$@"
