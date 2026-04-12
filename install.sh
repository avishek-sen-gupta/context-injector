#!/bin/sh
# install.sh — Context Injector plugin installer.
# Run from the root of the project you want to wire (it must have a .claude/ directory).
# Requires: jq

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$PWD"
SETTINGS="$PROJECT_DIR/.claude/settings.json"
GOVERNOR_DIR="$HOME/.claude/plugins/context-injector/governor"
MACHINES_DIR="$HOME/.claude/plugins/context-injector/machines"

# --- validate ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

if ! python3 -c "import statemachine" 2>/dev/null; then
  echo "Warning: python-statemachine not found. Install with: pip3 install python-statemachine>=3.0.0" >&2
fi

if [ ! -d "$PROJECT_DIR/.claude" ]; then
  echo "Error: no .claude/ directory found in $PROJECT_DIR. Run from a Claude Code project root." >&2
  exit 1
fi

# --- install global files ---
echo "Installing hooks..."
mkdir -p ~/.claude/plugins/context-injector/hooks
cp "$PLUGIN_DIR/hooks/user-prompt-submit.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/pre-tool-use.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/session-start.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/governor-hook.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/session-start-v2.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/pre-compact.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/post-tool-use.sh" ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
chmod +x ~/.claude/plugins/context-injector/hooks/pre-tool-use.sh
chmod +x ~/.claude/plugins/context-injector/hooks/session-start.sh
chmod +x ~/.claude/plugins/context-injector/hooks/governor-hook.sh
chmod +x ~/.claude/plugins/context-injector/hooks/session-start-v2.sh
chmod +x ~/.claude/plugins/context-injector/hooks/pre-compact.sh
chmod +x ~/.claude/plugins/context-injector/hooks/post-tool-use.sh

echo "Installing commands..."
cp "$PLUGIN_DIR/commands/ctx.md" ~/.claude/commands/ctx.md
cp "$PLUGIN_DIR/commands/governor.md" ~/.claude/commands/governor.md

echo "Installing governor..."
mkdir -p "$GOVERNOR_DIR"
cp "$PLUGIN_DIR/governor/__init__.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/__main__.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/state_io.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/audit.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/governor.py" "$GOVERNOR_DIR/"

echo "Installing machine definitions..."
mkdir -p "$MACHINES_DIR"
cp "$PLUGIN_DIR/machines/__init__.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/base.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/tdd_cycle.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/tdd_v2.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/feature_development.py" "$MACHINES_DIR/"

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

# --- wire SessionStart hook (v2 governor, upgrades v1) ---
HAS_V2_SESSION=$(jq '[.hooks.SessionStart[]?.hooks[]?.command // ""] | any(contains("session-start-v2"))' "$SETTINGS")
if [ "$HAS_V2_SESSION" = "false" ]; then
  echo "Wiring SessionStart hook (v2)..."
  # Remove v1 session-start hook if present
  jq '.hooks.SessionStart = [(.hooks.SessionStart // [])[] | select(.hooks[0].command | contains("session-start-v2") or (contains("context-injector") | not))]' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  # Add v2 hook
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/session-start-v2.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.SessionStart = ((.hooks.SessionStart // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "SessionStart v2 hook already wired, skipping."
fi

# --- wire PreToolUse hook (v2 governor, upgrades v1) ---
HAS_GOVERNOR=$(jq '[.hooks.PreToolUse[]?.hooks[]?.command // ""] | any(contains("governor-hook"))' "$SETTINGS")
if [ "$HAS_GOVERNOR" = "false" ]; then
  echo "Wiring PreToolUse hook (governor)..."
  # Remove v1 pre-tool-use hook if present
  jq '.hooks.PreToolUse = [(.hooks.PreToolUse // [])[] | select(.hooks[0].command | contains("governor-hook") or (contains("context-injector") | not))]' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  # Add governor hook
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/governor-hook.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "PreToolUse governor hook already wired, skipping."
fi

# --- wire PostToolUse hook (idempotent) ---
HAS_POST_TOOL=$(jq '[.hooks.PostToolUse[]?.hooks[]?.command // ""] | any(contains("context-injector"))' "$SETTINGS")
if [ "$HAS_POST_TOOL" = "false" ]; then
  echo "Wiring PostToolUse hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/post-tool-use.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.PostToolUse = ((.hooks.PostToolUse // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "PostToolUse hook already wired, skipping."
fi

# --- wire PreCompact hook (idempotent) ---
ALREADY_WIRED=$(jq '[.hooks.PreCompact[]?.hooks[]?.command // ""] | any(contains("context-injector"))' "$SETTINGS")
if [ "$ALREADY_WIRED" = "false" ]; then
  echo "Wiring PreCompact hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/pre-compact.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.PreCompact = ((.hooks.PreCompact // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "PreCompact hook already wired, skipping."
fi

# --- add audit/state dirs to .gitignore ---
GITIGNORE="$PROJECT_DIR/.gitignore"
if [ -f "$GITIGNORE" ]; then
  grep -q '.claude/audit/' "$GITIGNORE" || echo '.claude/audit/' >> "$GITIGNORE"
  grep -q '.claude/state/' "$GITIGNORE" || echo '.claude/state/' >> "$GITIGNORE"
fi

# --- add Bash permissions (idempotent via unique) ---
echo "Adding Bash permissions..."
jq '.permissions.allow = ((.permissions.allow // []) + ["Bash(mkdir:/tmp/ctx-locks)", "Bash(touch:/tmp/ctx-locks/*)", "Bash(rm:/tmp/ctx-locks/)"] | unique)' \
  "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

echo ""
echo "Done. Context Injector installed for $PROJECT_DIR."
echo "Use /ctx to toggle context injection on/off."
