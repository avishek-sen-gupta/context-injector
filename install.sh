#!/bin/sh
# install.sh — Context Injector plugin installer.
# Run from the root of the project you want to wire (it must have a .claude/ directory).
# Requires: jq

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$PWD"
SETTINGS="$PROJECT_DIR/.claude/settings.json"

# --- validate ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

if [ ! -d "$PROJECT_DIR/.claude" ]; then
  echo "Error: no .claude/ directory found in $PROJECT_DIR. Run from a Claude Code project root." >&2
  exit 1
fi

# --- install global files ---
echo "Installing hook..."
mkdir -p ~/.claude/plugins/context-injector/hooks
cp "$PLUGIN_DIR/hooks/user-prompt-submit.sh" ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh

echo "Installing /ctx command..."
cp "$PLUGIN_DIR/commands/ctx.md" ~/.claude/commands/ctx.md

# --- create settings.json if missing ---
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# --- wire UserPromptSubmit hook (idempotent) ---
ALREADY_WIRED=$(jq '[.hooks.UserPromptSubmit[]?.hooks[]?.command // ""] | any(contains("context-injector"))' "$SETTINGS")
if [ "$ALREADY_WIRED" = "false" ]; then
  echo "Wiring UserPromptSubmit hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.UserPromptSubmit = ((.hooks.UserPromptSubmit // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "UserPromptSubmit hook already wired, skipping."
fi

# --- add Bash permissions (idempotent via unique) ---
echo "Adding Bash permissions..."
jq '.permissions.allow = ((.permissions.allow // []) + ["Bash(mkdir:/tmp/ctx-locks)", "Bash(touch:/tmp/ctx-locks/*)", "Bash(rm:/tmp/ctx-locks/)"] | unique)' \
  "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

echo ""
echo "Done. Context Injector installed for $PROJECT_DIR."
echo "Use /ctx to toggle context injection on/off."
