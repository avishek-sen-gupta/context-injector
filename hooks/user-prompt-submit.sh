#!/bin/sh
# user-prompt-submit.sh — Context Injector plugin hook.
# Called by UserPromptSubmit. When ctx mode is on, injects core context +
# classified conditional invariants into the conversation.
# Lockfile lives in /tmp/ctx-locks/<md5-of-project-path> — no project pollution.
# Exit 0 always — missing dirs or no matches are silent no-ops.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"
COND_DIR="$PWD/.claude/conditional"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Extract prompt from JSON stdin (no jq dependency)
PROMPT=$(sed -n 's/.*"prompt" *: *"\(.*\)"/\1/p' | head -1)

# Lowercase for keyword matching
LOWER=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# --- classify ---
DESIGN=0
TESTING=0
REVIEW=0
REFACTORING=0
SKILLS=0

if printf '%s' "$LOWER" | grep -qiEw \
  'implement|add|build|create|fix|feature|bug|write|emit|lower|migrate|introduce|wire|hook|support|handle|extend|port|close'; then
  DESIGN=1; TESTING=1; REFACTORING=1; SKILLS=1
fi

if printf '%s' "$LOWER" | grep -qiEw \
  'test|tdd|assert|coverage|xfail|failing|passes|red-green|fixture'; then
  TESTING=1
fi
if printf '%s' "$LOWER" | grep -qi 'integration test\|unit test'; then
  TESTING=1
fi

if printf '%s' "$LOWER" | grep -qiEw \
  'refactor|rename|extract|move|split|merge|simplify|clean|reorganize|restructure|consolidate|decompose|inline|deduplicate'; then
  DESIGN=1; REFACTORING=1; SKILLS=1
fi

if printf '%s' "$LOWER" | grep -qiEw \
  'review|pr|diff|check|feedback|critique|approve'; then
  REVIEW=1
fi

if printf '%s' "$LOWER" | grep -qiEw \
  'verify|audit|scan|lint|sweep|validate|ensure|confirm|gate|black|lint-imports'; then
  TESTING=1; SKILLS=1
fi

# --- build injection summary ---
INJECTED="core"
[ "$DESIGN" = 1 ] && INJECTED="${INJECTED} design-principles"
[ "$TESTING" = 1 ] && INJECTED="${INJECTED} testing-patterns"
[ "$REVIEW" = 1 ] && INJECTED="${INJECTED} code-review"
[ "$REFACTORING" = 1 ] && INJECTED="${INJECTED} refactoring"
[ "$SKILLS" = 1 ] && INJECTED="${INJECTED} tools-skills"

echo "[invariants injected: ${INJECTED}]"
echo ""

# --- inject core (always when mode is on) ---
if [ -d "$CORE_DIR" ]; then
  for f in "$CORE_DIR"/*.md; do
    [ -f "$f" ] && cat "$f"
  done
fi

# --- inject matching conditional files ---
[ "$DESIGN" = 1 ] && [ -f "$COND_DIR/design-principles.md" ] && cat "$COND_DIR/design-principles.md"
[ "$TESTING" = 1 ] && [ -f "$COND_DIR/testing-patterns.md" ] && cat "$COND_DIR/testing-patterns.md"
[ "$REVIEW" = 1 ] && [ -f "$COND_DIR/code-review.md" ] && cat "$COND_DIR/code-review.md"
[ "$REFACTORING" = 1 ] && [ -f "$COND_DIR/refactoring.md" ] && cat "$COND_DIR/refactoring.md"
[ "$SKILLS" = 1 ] && [ -f "$COND_DIR/tools-skills.md" ] && cat "$COND_DIR/tools-skills.md"

exit 0
