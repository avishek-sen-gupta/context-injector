#!/bin/sh
# uninstall-governor.sh — State Machine Governor (v2) uninstaller.
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

# --- remove hooks from settings.json ---
if [ -f "$SETTINGS" ]; then
  echo "Removing governor hooks from settings.json..."
  for hook_type in SessionStart PreToolUse PostToolUse PreCompact; do
    jq --arg ht "$hook_type" \
      '.hooks[$ht] = [(.hooks[$ht] // [])[] | select(.hooks[0].command | contains("context-injector") | not)]
       | if (.hooks[$ht] | length) == 0 then del(.hooks[$ht]) else . end' \
      "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  done
  # Remove empty hooks object
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

# --- remove governor lock file ---
GOV_LOCK="/tmp/ctx-governor/$(printf '%s' "$PWD" | md5)"
rm -f "$GOV_LOCK" && echo "Removed governor lock file."

# --- remove governor hook files ---
echo "Removing governor hook files..."
for hook in governor-hook.sh session-start.sh post-tool-use.sh pre-compact.sh; do
  if [ -f ~/.claude/plugins/context-injector/hooks/"$hook" ]; then
    rm -f ~/.claude/plugins/context-injector/hooks/"$hook"
    echo "  Removed $hook"
  fi
done

# --- remove governor and machine code ---
if [ -d ~/.claude/plugins/context-injector/governor ]; then
  rm -rf ~/.claude/plugins/context-injector/governor
  echo "Removed governor Python code."
fi
if [ -d ~/.claude/plugins/context-injector/machines ]; then
  rm -rf ~/.claude/plugins/context-injector/machines
  echo "Removed machine definitions."
fi

# --- remove command ---
if [ -f ~/.claude/commands/governor.md ]; then
  rm -f ~/.claude/commands/governor.md
  echo "Removed /governor command."
fi

# --- remove state files ---
echo "Removing state files..."
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
rm -f "/tmp/ctx-state/$PROJECT_HASH.json"
rm -f "/tmp/ctx-state/$PROJECT_HASH.machine"
rm -f "/tmp/ctx-state/$PROJECT_HASH.last_pytest_line"

# --- clean up plugin dir if empty ---
rmdir ~/.claude/plugins/context-injector/hooks 2>/dev/null || true
rmdir ~/.claude/plugins/context-injector 2>/dev/null || true

echo ""
echo "Done. State Machine Governor uninstalled for $PROJECT_DIR."
