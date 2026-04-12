#!/bin/sh
# session-start-v2.sh — State Machine Governor SessionStart hook.
# Initializes state machine, injects initial context and TDD workflow instructions.
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

# Read active machine config
MACHINE_FILE="$STATE_DIR/$PROJECT_HASH.machine"
if [ -f "$MACHINE_FILE" ]; then
  ACTIVE_MACHINE="$(cat "$MACHINE_FILE")"
else
  ACTIVE_MACHINE="machines.tdd_v2.TDDv2"
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

# Inject TDD workflow instructions
cat << 'TDD_INSTRUCTIONS_EOF'
## TDD Governor — Enforced Workflow

You are operating under an enforced TDD governor. The governor tracks your workflow
phase and **blocks** tool calls that don't match the current phase.

### How It Works

Phase transitions are **automatic** — driven by pytest results, not manual declarations.

**States:**
- **writing_tests** (start): Write failing tests. Only test files can be created/edited.
- **red**: Transient — auto-advances to fixing_tests after pytest fails.
- **fixing_tests**: Write production code to make tests pass. All files editable.
- **green**: Transient — auto-advances to writing_tests after pytest passes.

**Cycle:** writing_tests → (pytest fails) → fixing_tests → (pytest passes) → writing_tests

### Rules

1. **Start by writing a test.** You can only create/edit `test_*` files in writing_tests.
2. **Run pytest** to see your test fail. This transitions you to fixing_tests.
3. **Write minimal code** to make the test pass in fixing_tests.
4. **Run pytest** again. When tests pass, you return to writing_tests.
5. **Production code is blocked** in writing_tests — the governor will reject Write/Edit on non-test files.

### Important

- The governor **blocks** disallowed tools (not just warns)
- You do NOT need to declare phase transitions — pytest results drive them automatically
- If blocked, check which state you're in and follow the TDD cycle
TDD_INSTRUCTIONS_EOF

exit 0
