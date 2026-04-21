#!/usr/bin/env bash
# SessionStart hook — set BASH_ENV so every Bash tool call sources bash-strict.sh.
# This runs unconditionally (not gated on governor).
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$HOOK_DIR/bash-strict.sh"

if [ ! -f "$ENV_FILE" ]; then
  exit 0
fi

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "pipefail enabled for all Bash operations via BASH_ENV"
  },
  "environment": {
    "BASH_ENV": "$ENV_FILE"
  }
}
JSON
