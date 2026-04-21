#!/usr/bin/env bash
# PostToolUse hook — capture tool output as evidence.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 capture --session "$SESSION"
