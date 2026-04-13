#!/bin/sh
# uninstall.sh — Context Injector v1 (keyword classification) uninstaller.
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
  echo "Removing UserPromptSubmit hook from settings.json..."
  jq '.hooks.UserPromptSubmit = [(.hooks.UserPromptSubmit // [])[] | select(.hooks[0].command | contains("user-prompt-submit") | not)]
     | if (.hooks.UserPromptSubmit | length) == 0 then del(.hooks.UserPromptSubmit) else . end
     | if (.hooks | length) == 0 then del(.hooks) else . end' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

  echo "Removing Bash permissions..."
  jq '.permissions.allow = [(.permissions.allow // [])[] | select(startswith("Bash(mkdir:/tmp/ctx-locks)") or startswith("Bash(touch:/tmp/ctx-locks") or startswith("Bash(rm:/tmp/ctx-locks") | not)]
     | if (.permissions.allow | length) == 0 then del(.permissions.allow) else . end
     | if (.permissions | length) == 0 then del(.permissions) else . end' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "No .claude/settings.json found, skipping hook removal."
fi

# --- remove lock file ---
LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
rm -f "$LOCK" && echo "Removed ctx lock file."

# --- remove v1 hook file ---
if [ -f ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh ]; then
  rm -f ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
  echo "Removed user-prompt-submit.sh hook."
fi

# --- remove ctx CLI ---
if [ -f ~/.claude/plugins/context-injector/bin/ctx ]; then
  rm -f ~/.claude/plugins/context-injector/bin/ctx
  echo "Removed ctx CLI."
fi

# --- remove command ---
if [ -f ~/.claude/commands/ctx.md ]; then
  rm -f ~/.claude/commands/ctx.md
  echo "Removed /ctx command."
fi

# --- clean up plugin dir if empty ---
rmdir ~/.claude/plugins/context-injector/hooks 2>/dev/null || true
rmdir ~/.claude/plugins/context-injector 2>/dev/null || true

echo ""
echo "Done. Context Injector v1 uninstalled for $PROJECT_DIR."
