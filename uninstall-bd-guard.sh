#!/bin/sh
# uninstall-bd-guard.sh — Beads terminology guard uninstaller.
# Run from the root of the project you want to unwire.
# Requires: jq

set -e

PROJECT_DIR="$PWD"
SETTINGS="$PROJECT_DIR/.claude/settings.json"

# --- validate ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

# --- remove hook from settings.json ---
if [ -f "$SETTINGS" ]; then
  echo "Removing bd-terminology-guard hook from settings.json..."
  jq '.hooks.PreToolUse = [(.hooks.PreToolUse // [])[] | select(.hooks[0].command | contains("bd-terminology-guard") | not)]
     | if (.hooks.PreToolUse | length) == 0 then del(.hooks.PreToolUse) else . end
     | if (.hooks | length) == 0 then del(.hooks) else . end' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "No .claude/settings.json found, skipping hook removal."
fi

# --- remove hook file ---
if [ -f ~/.claude/plugins/context-injector/hooks/bd-terminology-guard.sh ]; then
  rm -f ~/.claude/plugins/context-injector/hooks/bd-terminology-guard.sh
  echo "Removed bd-terminology-guard.sh"
fi

echo ""
echo "Done. Beads terminology guard uninstalled for $PROJECT_DIR."
