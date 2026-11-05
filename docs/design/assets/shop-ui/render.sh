#!/usr/bin/env bash
# Renders every shop UI mockup to a PNG next to this script. Needs Google Chrome on macOS.
# Screens whose name ends in "-mobile" are rendered inside a 360 px frame; the others at 1280 px.
set -euo pipefail
cd "$(dirname "$0")"

chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
profile="$(mktemp -d)"
screens=$(sed -n '/^const SCREENS = {/,/^};/p' mockup.js | grep -oE '^  "?[a-z-]+"?: ' | tr -d ' ":')

for screen in $screens; do
  if [[ "$screen" == *-mobile ]]; then size="500,1290"; scale=2; else size="1280,1100"; scale=1.5; fi
  "$chrome" --headless=new --hide-scrollbars --force-device-scale-factor="$scale" --window-size="$size" \
    --virtual-time-budget=6000 --user-data-dir="$profile" \
    --screenshot="$screen.png" "file://$PWD/mockup.html?screen=$screen" 2>/dev/null
done
