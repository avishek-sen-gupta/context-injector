#!/bin/sh
# post-tool-use.sh — PostToolUse hook for governor state transitions.
# Handles two event sources:
#   1. Bash(pytest*) results → fires pytest_pass / pytest_fail
#   2. Edit/Write while in fixing_lint → runs lint, fires lint_pass / lint_fail
# Exit 0 always (PostToolUse cannot block).

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$HOOK_DIR/lib/hash.sh"

LOCK="/tmp/ctx-governor/$(project_hash "$PWD")"
PLUGIN_DIR="$HOME/.claude/plugins/context-injector"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Governor not installed — fall back silently
[ -f "$PLUGIN_DIR/governor/governor.py" ] || exit 0

# Read stdin (tool event JSON from Claude Code)
INPUT=$(cat)

TOOL_NAME=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)

# Set environment for governor (needed by both paths)
export CTX_STATE_DIR="/tmp/ctx-state"
export CTX_AUDIT_DIR="$PWD/.claude/audit"
export CTX_CONTEXT_DIR="$PWD/.claude"
export CTX_PROJECT_HASH="$(project_hash "$PWD")"

MACHINE_FILE="$CTX_STATE_DIR/$CTX_PROJECT_HASH.machine"
if [ -f "$MACHINE_FILE" ]; then
    export CTX_MACHINE="$(cat "$MACHINE_FILE")"
else
    export CTX_MACHINE="${CTX_MACHINE:-machines.tdd.TDD}"
fi

# --- Determine EVENT from tool results ---

EVENT=""
LINT_MESSAGE=""

# Path 1: Bash(pytest*) → detect pass/fail from output
if [ "$TOOL_NAME" = "Bash" ]; then
    COMMAND=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
    case "$COMMAND" in
        pytest*|python*pytest*|python3*-m*pytest*)
            TOOL_RESPONSE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
event = json.load(sys.stdin)
resp = event.get('tool_response', '')
if isinstance(resp, dict):
    parts = []
    for key in ('stdout', 'stderr', 'output', 'content', 'result', 'text'):
        v = resp.get(key, '')
        if v:
            parts.append(str(v))
    if parts:
        print('\n'.join(parts))
    else:
        print(json.dumps(resp))
elif isinstance(resp, str):
    print(resp)
else:
    print(str(resp))
" 2>/dev/null)

            if printf '%s' "$TOOL_RESPONSE" | grep -qE '(FAILED|ERROR|failed|error.*occurred)'; then
                EVENT="pytest_fail"
            elif printf '%s' "$TOOL_RESPONSE" | grep -qE '(passed|no tests ran)'; then
                EVENT="pytest_pass"
            fi
            ;;
    esac
fi

# Path 2: Edit/Write in fixing_lint → run lint on edited file
if [ -z "$EVENT" ] && { [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; }; then
    STATE_FILE="$CTX_STATE_DIR/$CTX_PROJECT_HASH.json"
    CURRENT_STATE=$(python3 -c "
import sys, json
with open('$STATE_FILE') as f:
    print(json.load(f).get('inner_state', ''))
" 2>/dev/null)

    if [ "$CURRENT_STATE" = "fixing_lint" ]; then
        FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)
        if [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
            LINT_OUTPUT=$(PYTHONPATH="$PLUGIN_DIR" python3 -m governor lint "$FILE_PATH" 2>&1)
            LINT_EXIT=$?
            if [ $LINT_EXIT -eq 0 ]; then
                EVENT="lint_pass"
            else
                EVENT="lint_fail"
                LINT_MESSAGE="$LINT_OUTPUT"
            fi
        fi
    fi
fi

# No event determined — nothing to do
[ -z "$EVENT" ] && exit 0

# --- Fire transition and output results ---

RESPONSE=$(printf '%s' "$INPUT" | PYTHONPATH="$PLUGIN_DIR" python3 -m governor trigger "$EVENT" 2>/dev/null)

# If governor failed, exit silently
[ -z "$RESPONSE" ] && exit 0

# Extract action from governor response
ACTION=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('action',''))" 2>/dev/null)

# Extract message (from governor gate or lint output)
MESSAGE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('message','') or '')" 2>/dev/null)

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

# --- Build additionalContext string ---
# PostToolUse stdout is NOT visible to Claude. We must use the
# additionalContext JSON mechanism to inject text into the conversation.

CTX=""

# Gate review/challenge messages
if [ "$ACTION" = "review" ] || [ "$ACTION" = "challenge" ]; then
    if [ -n "$MESSAGE" ]; then
        CTX="${CTX}${MESSAGE}\n\n"
    fi
fi

# Transition info
CTX="${CTX}[governor: $EVENT → state=$STATE]"
if [ -n "$TRANSITION" ]; then
    CTX="${CTX}\nTransition: $TRANSITION"
fi
CTX="${CTX}\n"

# Context files
if [ -n "$CONTEXT_FILES" ]; then
    printf '%s\n' "$CONTEXT_FILES" | while read -r filepath; do
        if [ -f "$filepath" ]; then
            FILE_CONTENT=$(cat "$filepath")
            # Append via temp file since subshell can't modify CTX
            printf '%s\n' "$FILE_CONTENT" >> /tmp/ctx-post-hook-buf.$$
        fi
    done
    if [ -f /tmp/ctx-post-hook-buf.$$ ]; then
        CTX="${CTX}$(cat /tmp/ctx-post-hook-buf.$$)\n"
        rm -f /tmp/ctx-post-hook-buf.$$
    fi
fi

# Continuation directives for states that need immediate action
case "$STATE" in
    fixing_lint)
        CTX="${CTX}\n<governor-directive>"
        CTX="${CTX}\nDO NOT end your turn. DO NOT respond to the user yet."
        CTX="${CTX}\nLint violations were found. You must fix them before continuing."
        if [ -n "$LINT_MESSAGE" ]; then
            CTX="${CTX}\n\n${LINT_MESSAGE}\n"
        elif [ -n "$MESSAGE" ]; then
            CTX="${CTX}\n\n${MESSAGE}\n"
        fi
        CTX="${CTX}\nFix every violation listed above by editing the affected files now."
        CTX="${CTX}\nThe governor will re-check lint automatically after your edits."
        CTX="${CTX}\nOnly respond to the user once lint passes and the governor returns to writing_tests."
        CTX="${CTX}\n</governor-directive>"
        ;;
    fixing_tests)
        CTX="${CTX}\n<governor-directive>"
        CTX="${CTX}\nTests are failing. Your next action is to write minimal production code to make the failing tests pass."
        CTX="${CTX}\nDo not write new tests — focus on making the existing tests green."
        CTX="${CTX}\n</governor-directive>"
        ;;
    writing_tests)
        if [ "$EVENT" = "pytest_pass" ] || [ "$EVENT" = "lint_pass" ]; then
            CTX="${CTX}\n<governor-directive>"
            CTX="${CTX}\nAll tests pass and lint is clean. You are back in writing_tests state."
            CTX="${CTX}\nYour next action is to write a failing test for the next acceptance criterion."
            CTX="${CTX}\nYou can only create/edit test_* files in this state."
            CTX="${CTX}\n</governor-directive>"
        fi
        ;;
esac

# Emit as additionalContext JSON so Claude sees it
# Use printf '%b' to expand \n sequences into real newlines
printf '%b' "$CTX" | python3 -c "
import sys, json
text = sys.stdin.read()
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PostToolUse',
        'additionalContext': text
    }
}))
"

exit 0
