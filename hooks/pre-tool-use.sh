#!/bin/sh
# pre-tool-use.sh — Context Injector PreToolUse hook.
# Injects code-review + design-principles context when a code-review agent is invoked,
# but only when ctx mode is on (/tmp/ctx-locks/<md5-of-pwd> exists).
# Exit 0 always — miss just means no injection.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
COND_DIR="$PWD/.claude/conditional"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name" *: *"\([^"]*\)".*/\1/p' | head -1)
SUBAGENT=$(printf '%s' "$INPUT" | sed -n 's/.*"subagent_type" *: *"\([^"]*\)".*/\1/p' | head -1)

if [ "$TOOL" = "Agent" ] && printf '%s' "$SUBAGENT" | grep -qi "code-review"; then
  echo "[invariants injected: code-review design-principles (code-review agent activated)]"
  echo ""
  [ -f "$COND_DIR/code-review.md" ] && cat "$COND_DIR/code-review.md"
  [ -f "$COND_DIR/design-principles.md" ] && cat "$COND_DIR/design-principles.md"
fi

exit 0
