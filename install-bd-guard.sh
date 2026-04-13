#!/bin/sh
# install-bd-guard.sh — Beads terminology guard installer.
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

# --- install hook ---
echo "Installing bd-terminology-guard hook..."
mkdir -p ~/.claude/plugins/context-injector/hooks
cp "$PLUGIN_DIR/hooks/bd-terminology-guard.sh" ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/bd-terminology-guard.sh

# --- create settings.json if missing ---
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# --- wire PreToolUse hook (idempotent) ---
HAS_BD_GUARD=$(jq '[.hooks.PreToolUse[]?.hooks[]?.command // ""] | any(contains("bd-terminology-guard"))' "$SETTINGS")
if [ "$HAS_BD_GUARD" = "false" ]; then
  echo "Wiring bd-terminology-guard PreToolUse hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/bd-terminology-guard.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "bd-terminology-guard hook already wired, skipping."
fi

echo ""
echo "Done. Beads terminology guard installed for $PROJECT_DIR."
echo "Blocklist: ~/.config/git/blocklist.txt"
