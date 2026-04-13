#!/bin/sh
# session-start.sh — State Machine Governor SessionStart hook.
# Initializes state machine, injects initial context and TDD workflow instructions.
# Exit 0 always.

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$HOOK_DIR/lib/hash.sh"

LOCK="/tmp/ctx-governor/$(project_hash "$PWD")"
CORE_DIR="$PWD/.claude/core"
STATE_DIR="/tmp/ctx-state"
PROJECT_HASH="$(project_hash "$PWD")"
STATE_FILE="$STATE_DIR/$PROJECT_HASH.json"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Initialize state directory
mkdir -p "$STATE_DIR"
mkdir -p "$PWD/.claude/audit"

# Read active machine config
MACHINE_FILE="$STATE_DIR/$PROJECT_HASH.machine"
if [ -f "$MACHINE_FILE" ]; then
  ACTIVE_MACHINE="$(cat "$MACHINE_FILE")"
else
  ACTIVE_MACHINE="machines.tdd.TDD"
fi

# Reset state file for new session (fresh start)
rm -f "$STATE_FILE"

echo "[ctx: governor mode — machine=$ACTIVE_MACHINE — initialized]"
echo ""

# Inject core context
if [ -d "$CORE_DIR" ]; then
    for f in "$CORE_DIR"/*.md; do
        [ -f "$f" ] && cat "$f"
    done
    echo ""
fi

# Inject machine-specific workflow instructions via governor
PLUGIN_DIR="$HOME/.claude/plugins/context-injector"
if [ -f "$PLUGIN_DIR/governor/governor.py" ]; then
    INSTRUCTIONS=$(printf '{"session_id":"init"}' | \
        CTX_MACHINE="$ACTIVE_MACHINE" \
        CTX_STATE_DIR="$STATE_DIR" \
        CTX_AUDIT_DIR="$PWD/.claude/audit" \
        CTX_CONTEXT_DIR="$PWD/.claude" \
        CTX_PROJECT_HASH="$PROJECT_HASH" \
        PYTHONPATH="$PLUGIN_DIR" \
        python3 -m governor session-instructions 2>/dev/null)
    if [ -n "$INSTRUCTIONS" ]; then
        echo "$INSTRUCTIONS"
    fi
fi

exit 0
