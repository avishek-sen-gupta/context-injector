#!/bin/sh
# post-tool-use.sh — PostToolUse hook for pytest result detection.
# Fires governor trigger_transition with pytest_fail or pytest_pass
# based on the tool result after Bash(pytest*) commands.
# Exit 0 always (PostToolUse cannot block).

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
PLUGIN_DIR="$HOME/.claude/plugins/context-injector"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Governor not installed — fall back silently
[ -f "$PLUGIN_DIR/governor/governor.py" ] || exit 0

# Read stdin (tool event JSON from Claude Code)
INPUT=$(cat)

# Only care about Bash tool
TOOL_NAME=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)
[ "$TOOL_NAME" = "Bash" ] || exit 0

# Only care about pytest commands
COMMAND=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
case "$COMMAND" in
    pytest*|python*pytest*|python3*-m*pytest*) ;;
    *) exit 0 ;;
esac

# Extract tool response to determine pass/fail
# PostToolUse events include tool_response — structure varies by tool.
# Try multiple known field names; fall back to stringifying the whole response.
TOOL_RESPONSE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
event = json.load(sys.stdin)
resp = event.get('tool_response', '')
if isinstance(resp, dict):
    # Try known field names for Bash output
    parts = []
    for key in ('stdout', 'stderr', 'output', 'content', 'result', 'text'):
        v = resp.get(key, '')
        if v:
            parts.append(str(v))
    if parts:
        print('\n'.join(parts))
    else:
        # Fallback: stringify the whole dict so grep can match
        print(json.dumps(resp))
elif isinstance(resp, str):
    print(resp)
else:
    print(str(resp))
" 2>/dev/null)

# Determine pytest result from output
# pytest exit code 0 = all passed, non-zero = failures
# Look for pytest summary patterns
if printf '%s' "$TOOL_RESPONSE" | grep -qE '(FAILED|ERROR|failed|error.*occurred)'; then
    EVENT="pytest_fail"
elif printf '%s' "$TOOL_RESPONSE" | grep -qE '(passed|no tests ran)'; then
    EVENT="pytest_pass"
else
    # Can't determine result — skip
    exit 0
fi

# Set environment for governor
export CTX_STATE_DIR="/tmp/ctx-state"
export CTX_AUDIT_DIR="$PWD/.claude/audit"
export CTX_CONTEXT_DIR="$PWD/.claude"
export CTX_PROJECT_HASH="$(printf '%s' "$PWD" | md5)"

# Read machine config
MACHINE_FILE="$CTX_STATE_DIR/$CTX_PROJECT_HASH.machine"
if [ -f "$MACHINE_FILE" ]; then
    export CTX_MACHINE="$(cat "$MACHINE_FILE")"
else
    export CTX_MACHINE="${CTX_MACHINE:-machines.tdd_v2.TDDv2}"
fi

# Fire the transition
RESPONSE=$(printf '%s' "$INPUT" | PYTHONPATH="$PLUGIN_DIR" python3 -m governor trigger "$EVENT" 2>/dev/null)

# If governor failed, exit silently
[ -z "$RESPONSE" ] && exit 0

# Extract state and context
STATE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('current_state',''))" 2>/dev/null)
TRANSITION=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('transition','') or '')" 2>/dev/null)

# Extract context files to inject
CONTEXT_FILES=$(printf '%s' "$RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for f in r.get('context_to_inject', []):
    print(f)
" 2>/dev/null)

# Output transition info as additional context
echo "[governor: $EVENT → state=$STATE]"
if [ -n "$TRANSITION" ]; then
    echo "Transition: $TRANSITION"
fi
echo ""

# Inject context files
if [ -n "$CONTEXT_FILES" ]; then
    echo "$CONTEXT_FILES" | while read -r filepath; do
        [ -f "$filepath" ] && cat "$filepath"
    done
fi

exit 0
