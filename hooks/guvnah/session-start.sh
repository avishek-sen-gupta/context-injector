#!/usr/bin/env bash
# SessionStart hook — restore governor state if active.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 init --session "$SESSION"
