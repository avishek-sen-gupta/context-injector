#!/usr/bin/env bash
# UserPromptSubmit hook — parse /governor commands.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

# Quick check: does stdin contain a governor command?
# Matches both raw "/governor" and expanded "Governor workflow enforcer has been invoked with:"
INPUT="$(cat)"
printf '%s' "$INPUT" | grep -qE '/governor|Governor workflow enforcer has been invoked with:' || exit 0

printf '%s' "$INPUT" | exec python3 -m governor_v4 prompt --session "$SESSION"
