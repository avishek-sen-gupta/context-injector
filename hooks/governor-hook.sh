#!/bin/sh
# governor-hook.sh — State Machine Governor PreToolUse hook.
# Pipes tool event JSON to the Python governor process.
# Outputs additionalContext based on governor response.
# Exit 0 always — errors are silent no-ops.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
GOVERNOR="$HOME/.claude/plugins/context-injector/governor/governor.py"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Governor not installed — fall back silently
[ -f "$GOVERNOR" ] || exit 0

# Read stdin (tool event JSON from Claude Code)
INPUT=$(cat)

# Set environment for governor
export CTX_STATE_DIR="/tmp/ctx-state"
export CTX_AUDIT_DIR="$PWD/.claude/audit"
export CTX_CONTEXT_DIR="$PWD/.claude"
export CTX_PROJECT_HASH="$(printf '%s' "$PWD" | md5)"

# Read machine config: file > env > default
MACHINE_FILE="$CTX_STATE_DIR/$CTX_PROJECT_HASH.machine"
if [ -f "$MACHINE_FILE" ]; then
  export CTX_MACHINE="$(cat "$MACHINE_FILE")"
else
  export CTX_MACHINE="${CTX_MACHINE:-machines.tdd_cycle.TDDCycle}"
fi

# Run governor
RESPONSE=$(printf '%s' "$INPUT" | python3 "$GOVERNOR" 2>/dev/null)

# If governor failed, exit silently
[ -z "$RESPONSE" ] && exit 0

# Extract action and message from response
ACTION=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('action',''))" 2>/dev/null)
MESSAGE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('message','') or '')" 2>/dev/null)
STATE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('current_state',''))" 2>/dev/null)

# Extract context files to inject
CONTEXT_FILES=$(printf '%s' "$RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for f in r.get('context_to_inject', []):
    print(f)
" 2>/dev/null)

# Output state indicator
echo "[governor: state=$STATE action=$ACTION]"
echo ""

# Output message if present (remind or challenge)
if [ -n "$MESSAGE" ]; then
    echo "<governor-message>"
    echo "$MESSAGE"
    echo "</governor-message>"
    echo ""
fi

# Inject context files
if [ -n "$CONTEXT_FILES" ]; then
    echo "$CONTEXT_FILES" | while read -r filepath; do
        [ -f "$filepath" ] && cat "$filepath"
    done
fi

exit 0
