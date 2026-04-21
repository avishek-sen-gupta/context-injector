#!/usr/bin/env bash
# UserPromptSubmit hook — parse /governor commands.
set -euo pipefail

SESSION="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION" ] && exit 0

# Quick check: does stdin contain /governor? Read into var for reuse.
INPUT="$(cat)"
printf '%s' "$INPUT" | grep -q '/governor' || exit 0

printf '%s' "$INPUT" | exec python3 -m governor_v4 prompt --session "$SESSION"
