#!/usr/bin/env bash
set -euo pipefail
desktop_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
/usr/bin/make -C "$desktop_dir" "$@"

# Stamp the built app with the repo's VERSION, so the About box always matches
# the release, then re-sign: Info.plist is sealed by the signature.
version_file="$desktop_dir/../../VERSION"
app="$desktop_dir/build/VepolDesktop.app"
plist="$app/Contents/Info.plist"
if [[ -f "$version_file" && -f "$plist" ]]; then
  version="$(tr -d '[:space:]' < "$version_file")"
  if [[ -n "$version" ]]; then
    /usr/bin/plutil -replace CFBundleShortVersionString -string "$version" "$plist"
    /usr/bin/plutil -replace CFBundleVersion -string "$version" "$plist"
    /usr/bin/plutil -lint "$plist"
    /usr/bin/codesign --force --sign - "$app"
    /usr/bin/codesign --verify --strict "$app"
    printf 'Stamped version %s\n' "$version"
  fi
fi
