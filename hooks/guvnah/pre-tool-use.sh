#!/usr/bin/env bash
# PreToolUse hook — evaluate tool call against governor phase.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 evaluate --session "$SESSION"
