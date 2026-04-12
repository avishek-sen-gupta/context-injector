#!/bin/sh
# session-start-v2.sh — State Machine Governor SessionStart hook.
# Initializes state machine, injects initial context and DeclarePhase instructions.
# Exit 0 always.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"
STATE_DIR="/tmp/ctx-state"
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_FILE="$STATE_DIR/$PROJECT_HASH.json"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Initialize state directory
mkdir -p "$STATE_DIR"
mkdir -p "$PWD/.claude/audit"

# Reset state file for new session (fresh start)
rm -f "$STATE_FILE"

echo "[ctx: governor mode — state machine initialized]"
echo ""

# Inject core context
if [ -d "$CORE_DIR" ]; then
    for f in "$CORE_DIR"/*.md; do
        [ -f "$f" ] && cat "$f"
    done
    echo ""
fi

# Inject DeclarePhase instructions
cat << 'DECLARE_PHASE_EOF'
## State Machine Governance

You are operating under a state machine governor. The governor tracks your current
workflow phase and injects relevant context automatically.

### Declaring Phase Transitions

When you move to a new phase of work, announce it by running:

```bash
echo '{"declare_phase": "<phase_name>", "reason": "<why you are transitioning>"}'
```

The governor will validate your transition. If it's unexpected, you'll receive
guidance about the expected workflow.

### Current Workflow: TDD Cycle

The default workflow follows Red → Green → Refactor:

- **red**: Write a failing test. Declare `green` when the test is written and confirmed failing.
- **green**: Write minimal code to make the test pass. Declare `refactor` when tests pass.
- **refactor**: Improve the code without changing behavior. Declare `red` when ready for the next test.

### Important

- The governor runs on every tool call — you don't need to do anything special
- If you need to deviate (e.g., fix documentation), declare the deviation phase
- The governor will challenge low-confidence transitions but won't hard-block you
DECLARE_PHASE_EOF

exit 0
