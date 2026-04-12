#!/bin/sh
# uninstall.sh — Context Injector plugin uninstaller.
# Run from the root of the project you want to unwire.
# Requires: jq

set -e

PROJECT_DIR="$PWD"
SETTINGS="$PROJECT_DIR/.claude/settings.json"
PLUGIN_DIR="$HOME/.claude/plugins/context-injector"

# --- validate ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

# --- remove hooks from settings.json ---
if [ -f "$SETTINGS" ]; then
  echo "Removing hooks from settings.json..."
  for hook_type in SessionStart UserPromptSubmit PreToolUse PostToolUse PreCompact; do
    jq --arg ht "$hook_type" \
      '.hooks[$ht] = [(.hooks[$ht] // [])[] | select(.hooks[0].command | contains("context-injector") | not)]
       | if (.hooks[$ht] | length) == 0 then del(.hooks[$ht]) else . end' \
      "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  done
  # Remove empty hooks object
  jq 'if (.hooks | length) == 0 then del(.hooks) else . end' \
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
rm -f "$LOCK"

# --- remove plugin directory ---
if [ -d "$PLUGIN_DIR" ]; then
  echo "Removing plugin directory ($PLUGIN_DIR)..."
  rm -rf "$PLUGIN_DIR"
else
  echo "Plugin directory not found, skipping."
fi

# --- remove commands ---
for cmd in ctx.md governor.md; do
  if [ -f "$HOME/.claude/commands/$cmd" ]; then
    echo "Removing command: $cmd"
    rm -f "$HOME/.claude/commands/$cmd"
  fi
done

# --- remove state files ---
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
rm -f "/tmp/ctx-state/$PROJECT_HASH.json"
rm -f "/tmp/ctx-state/$PROJECT_HASH.machine"
rm -f "/tmp/ctx-state/$PROJECT_HASH.last_pytest_line"

echo ""
echo "Done. Context Injector uninstalled for $PROJECT_DIR."
