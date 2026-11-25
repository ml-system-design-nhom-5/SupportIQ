#!/usr/bin/env bash
# Renders every console UI mockup to a PNG next to this script. Needs Google Chrome on macOS.
set -euo pipefail
cd "$(dirname "$0")"

chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
profile="$(mktemp -d)"
screens=$(sed -n '/^const SCREENS = {/,/^};/p' mockup.js | grep -oE '^  "?[a-z-]+"?: ' | tr -d ' ":')

for screen in $screens; do
  "$chrome" --headless=new --hide-scrollbars --force-device-scale-factor=1.5 --window-size=1280,900 \
    --virtual-time-budget=6000 --user-data-dir="$profile" \
    --screenshot="$screen.png" "file://$PWD/mockup.html?screen=$screen" 2>/dev/null
done
