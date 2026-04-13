#!/bin/sh
# install-governor.sh — State Machine Governor (v2) installer.
# Run from the root of the project you want to wire (it must have a .claude/ directory).
# Requires: jq, python3 with python-statemachine>=3.0.0

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

if ! python3 -c "import tinydb" 2>/dev/null; then
  echo "Warning: tinydb not found. Install with: pip3 install tinydb>=4.0.0" >&2
fi

if [ ! -d "$PROJECT_DIR/.claude" ]; then
  echo "Error: no .claude/ directory found in $PROJECT_DIR. Run from a Claude Code project root." >&2
  exit 1
fi

# --- install hooks ---
echo "Installing governor hooks..."
mkdir -p ~/.claude/plugins/context-injector/hooks/lib
cp "$PLUGIN_DIR/hooks/lib/hash.sh" ~/.claude/plugins/context-injector/hooks/lib/
for hook in governor-hook.sh session-start.sh post-tool-use.sh pre-compact.sh; do
  cp "$PLUGIN_DIR/hooks/$hook" ~/.claude/plugins/context-injector/hooks/
  chmod +x ~/.claude/plugins/context-injector/hooks/"$hook"
done

# --- install CLI ---
echo "Installing governor CLI..."
mkdir -p ~/.claude/plugins/context-injector/bin
cp "$PLUGIN_DIR/bin/governor" ~/.claude/plugins/context-injector/bin/
chmod +x ~/.claude/plugins/context-injector/bin/governor

# --- install command ---
echo "Installing /governor command..."
mkdir -p ~/.claude/commands
cp "$PLUGIN_DIR/commands/governor.md" ~/.claude/commands/governor.md

# --- install governor ---
echo "Installing governor..."
mkdir -p "$GOVERNOR_DIR"
cp "$PLUGIN_DIR/governor/__init__.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/__main__.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/state_io.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/audit.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/governor.py" "$GOVERNOR_DIR/"

# --- install machines ---
echo "Installing machine definitions..."
mkdir -p "$MACHINES_DIR"
cp "$PLUGIN_DIR/machines/__init__.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/base.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/tdd_cycle.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/tdd.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/feature_development.py" "$MACHINES_DIR/"

# --- install gates ---
echo "Installing gates..."
GATES_DIR="$HOME/.claude/plugins/context-injector/gates"
mkdir -p "$GATES_DIR"
cp "$PLUGIN_DIR/gates/__init__.py" "$GATES_DIR/"
cp "$PLUGIN_DIR/gates/base.py" "$GATES_DIR/"
cp "$PLUGIN_DIR/gates/test_quality.py" "$GATES_DIR/"
cp "$PLUGIN_DIR/gates/lint.py" "$GATES_DIR/"

# --- install lint rules ---
echo "Installing lint rules..."
LINT_DIR="$HOME/.claude/plugins/context-injector/scripts/lint/rules"
mkdir -p "$LINT_DIR"
cp "$PLUGIN_DIR/scripts/lint/sgconfig.yml" "$HOME/.claude/plugins/context-injector/scripts/lint/"
cp "$PLUGIN_DIR/scripts/lint/rules/"*.yml "$LINT_DIR/"

# --- write plugin config ---
echo "Writing plugin config..."
CONFIG_FILE="$HOME/.claude/plugins/context-injector/config.json"
LINT_RULES_PATH="$HOME/.claude/plugins/context-injector/scripts/lint"
printf '{"lint_rules_dir": "%s"}\n' "$LINT_RULES_PATH" > "$CONFIG_FILE"

# --- create settings.json if missing ---
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# --- wire SessionStart hook (idempotent) ---
HAS_SESSION=$(jq '[.hooks.SessionStart[]?.hooks[]?.command // ""] | any(contains("session-start"))' "$SETTINGS")
if [ "$HAS_SESSION" = "false" ]; then
  echo "Wiring SessionStart hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/session-start.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.SessionStart = ((.hooks.SessionStart // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "SessionStart hook already wired, skipping."
fi

# --- wire PreToolUse hook (idempotent) ---
HAS_PRETOOL=$(jq '[.hooks.PreToolUse[]?.hooks[]?.command // ""] | any(contains("governor-hook"))' "$SETTINGS")
if [ "$HAS_PRETOOL" = "false" ]; then
  echo "Wiring PreToolUse hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/governor-hook.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "PreToolUse hook already wired, skipping."
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
HAS_COMPACT=$(jq '[.hooks.PreCompact[]?.hooks[]?.command // ""] | any(contains("context-injector"))' "$SETTINGS")
if [ "$HAS_COMPACT" = "false" ]; then
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

# --- add Bash permissions (idempotent) ---
echo "Adding Bash permissions..."
jq '.permissions.allow = ((.permissions.allow // []) + ["Bash(mkdir:/tmp/ctx-governor)", "Bash(touch:/tmp/ctx-governor/*)", "Bash(rm:/tmp/ctx-governor/)"] | unique)' \
  "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

echo ""
echo "Done. State Machine Governor installed for $PROJECT_DIR."
echo "Use /governor tdd to enable the TDD governor."
