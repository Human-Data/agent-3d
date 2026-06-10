#!/bin/bash
# Install the Claude Bridge addon programmatically (no UI needed), macOS paths.
# (Linux would use ~/.config/blender/<ver>/scripts/addons + a blender binary on PATH.)
# Copies the addon into every Blender version's addons dir, then enables it
# persistently — for the $BLENDER binary's version only — via a headless run.
set -euo pipefail
shopt -s nullglob
cd "$(dirname "$0")"

BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"

dirs=("$HOME/Library/Application Support/Blender"/*/)
if [ ${#dirs[@]} -eq 0 ]; then
  echo "no Blender version dirs found under ~/Library/Application Support/Blender (launch Blender once first)"
  exit 1
fi
for dir in "${dirs[@]}"; do
  mkdir -p "$dir/scripts/addons"
  cp blender_bridge.py "$dir/scripts/addons/"
  echo "installed -> ${dir}scripts/addons/blender_bridge.py"
done

if [ -x "$BLENDER" ]; then
  out=$("$BLENDER" --background --python-expr \
    'import bpy; bpy.ops.preferences.addon_enable(module="blender_bridge"); bpy.ops.wm.save_userpref(); print("BRIDGE_ENABLED_OK")' 2>&1) || true
  if echo "$out" | grep -q "BRIDGE_ENABLED_OK"; then
    echo "enabled + saved to userpref for $("$BLENDER" --version 2>/dev/null | head -1)"
    echo "(other versions got the file copy only; enable them the same way with their binary)"
    echo "note: an already-running Blender picks this up on next launch"
  else
    echo "enable failed:"; echo "$out" | tail -5; exit 1
  fi
else
  echo "Blender binary not found at $BLENDER (set BLENDER=/path/to/blender); addon copied but not enabled"
fi
