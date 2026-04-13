#!/bin/sh
# pre-compact.sh — State Machine Governor PreCompact hook.
# Injects core context, state-specific context, and workflow instructions
# before conversation compaction so invariants survive compression.
# Exit 0 always.

LOCK="/tmp/ctx-governor/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"
STATE_DIR="/tmp/ctx-state"
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_FILE="$STATE_DIR/$PROJECT_HASH.json"
PLUGIN_DIR="$HOME/.claude/plugins/context-injector"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Read active machine config
MACHINE_FILE="$STATE_DIR/$PROJECT_HASH.machine"
if [ -f "$MACHINE_FILE" ]; then
  ACTIVE_MACHINE="$(cat "$MACHINE_FILE")"
else
  ACTIVE_MACHINE="machines.tdd.TDD"
fi

# Read current state
if [ -f "$STATE_FILE" ]; then
    INNER_STATE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('inner_state','unknown'))" 2>/dev/null)
    MACHINE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('inner_machine','unknown'))" 2>/dev/null)
else
    INNER_STATE="unknown"
    MACHINE="unknown"
fi

echo "[ctx: pre-compaction context injection — state=$MACHINE.$INNER_STATE]"
echo ""

# Always inject core context before compaction
if [ -d "$CORE_DIR" ]; then
    for f in "$CORE_DIR"/*.md; do
        [ -f "$f" ] && cat "$f"
    done
    echo ""
fi

# Inject state-specific context files
if [ -f "$PLUGIN_DIR/governor/governor.py" ]; then
    CONTEXT_FILES=$(CTX_STATE_DIR="$STATE_DIR" \
        CTX_CONTEXT_DIR="$PWD/.claude" \
        CTX_PROJECT_HASH="$PROJECT_HASH" \
        CTX_MACHINE="$ACTIVE_MACHINE" \
        PYTHONPATH="$PLUGIN_DIR" \
        python3 -m governor context 2>/dev/null)
    if [ -n "$CONTEXT_FILES" ]; then
        echo "$CONTEXT_FILES" | while read -r filepath; do
            [ -f "$filepath" ] && cat "$filepath"
        done
        echo ""
    fi
fi

# Inject machine-specific workflow instructions
if [ -f "$PLUGIN_DIR/governor/governor.py" ]; then
    INSTRUCTIONS=$(printf '{"session_id":"compact"}' | \
        CTX_MACHINE="$ACTIVE_MACHINE" \
        CTX_STATE_DIR="$STATE_DIR" \
        CTX_AUDIT_DIR="$PWD/.claude/audit" \
        CTX_CONTEXT_DIR="$PWD/.claude" \
        CTX_PROJECT_HASH="$PROJECT_HASH" \
        PYTHONPATH="$PLUGIN_DIR" \
        python3 -m governor session-instructions 2>/dev/null)
    if [ -n "$INSTRUCTIONS" ]; then
        echo "$INSTRUCTIONS"
        echo ""
    fi
fi

# Inject state summary
echo "## Current Governor State"
echo "You are in state: $MACHINE.$INNER_STATE"
echo "The conversation is being compacted. Your workflow state is preserved."
echo ""

exit 0
