#!/usr/bin/env bash
# SessionStart hook — set BASH_ENV so every Bash tool call sources bash-strict.sh.
# This runs unconditionally (not gated on governor).
# Uses CLAUDE_ENV_FILE to inject env vars into the session.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$HOOK_DIR/bash-strict.sh"

if [ ! -f "$ENV_FILE" ]; then
  exit 0
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export BASH_ENV=\"$ENV_FILE\"" >> "$CLAUDE_ENV_FILE"
fi

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "pipefail enabled for all Bash operations via BASH_ENV"
  }
}
JSON
