#!/bin/sh
# session-start.sh — Context Injector SessionStart hook.
# Injects core context files once at session start when ctx mode is on.
# Lockfile lives in /tmp/ctx-locks/<md5-of-project-path> — no project pollution.
# Exit 0 always — missing dirs or no matches are silent no-ops.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# No core dir — nothing to do
[ -d "$CORE_DIR" ] || exit 0

echo "[ctx: core context injected at session start]"
echo ""

for f in "$CORE_DIR"/*.md; do
  [ -f "$f" ] && cat "$f"
done

exit 0
