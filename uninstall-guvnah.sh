#!/usr/bin/env bash
# uninstall-guvnah.sh — Remove guvnah hooks and machines from a project.
# Run from the root of the project you want to unwire.
# Requires: jq
set -euo pipefail

PROJECT_DIR="$PWD"
SETTINGS="$PROJECT_DIR/.claude/settings.json"
DEST="$PROJECT_DIR/.claude/hooks/guvnah"

# --- validate ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

# --- remove hooks from settings.json ---
if [ -f "$SETTINGS" ]; then
  for EVENT in SessionStart PreToolUse PostToolUse UserPromptSubmit; do
    echo "Removing $EVENT guvnah hook..."
    jq '.hooks.'"$EVENT"' = [(.hooks.'"$EVENT"' // [])[] | select(.hooks[0].command | contains("guvnah") | not)]
       | if (.hooks.'"$EVENT"' | length) == 0 then del(.hooks.'"$EVENT"') else . end' \
      "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  done

  # Clean up empty hooks object
  jq 'if (.hooks | length) == 0 then del(.hooks) else . end' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

  echo "Removing Bash permissions..."
  jq '.permissions.allow = [(.permissions.allow // [])[] | select(startswith("Bash(mkdir:/tmp/ctx-governor)") or startswith("Bash(touch:/tmp/ctx-governor") or startswith("Bash(rm:/tmp/ctx-governor") | not)]
     | if (.permissions.allow | length) == 0 then del(.permissions.allow) else . end
     | if (.permissions | length) == 0 then del(.permissions) else . end' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "No .claude/settings.json found, skipping hook removal."
fi

# --- remove hook files ---
if [ -d "$DEST" ]; then
  echo "Removing $DEST ..."
  rm -rf "$DEST"
else
  echo "Nothing to remove — $DEST does not exist."
fi

# --- remove state ---
STATE="/tmp/ctx-governor"
if [ -d "$STATE" ]; then
  echo "Removing state directory $STATE ..."
  rm -rf "$STATE"
fi

echo ""
echo "Done. Guvnah uninstalled for $PROJECT_DIR."
