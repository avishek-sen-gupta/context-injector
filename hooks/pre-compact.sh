#!/bin/sh
# pre-compact.sh — State Machine Governor PreCompact hook.
# Injects current state context before conversation compaction so invariants
# survive compression. Exit 0 always.

LOCK="/tmp/ctx-governor/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"
STATE_DIR="/tmp/ctx-state"
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_FILE="$STATE_DIR/$PROJECT_HASH.json"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

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

# Inject state summary
echo "## Current Governor State"
echo "You are in state: $MACHINE.$INNER_STATE"
echo "The conversation is being compacted. Your workflow state is preserved."
echo ""

exit 0
