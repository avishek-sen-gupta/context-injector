#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash) — prepend `set -o pipefail;` to every command.
set -euo pipefail

INPUT="$(cat)"
TOOL_NAME="$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))")"

[ "$TOOL_NAME" = "Bash" ] || exit 0

COMMAND="$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))")"

# Skip if already has pipefail
case "$COMMAND" in
  *"set -o pipefail"*) exit 0 ;;
esac

cat <<JSON
{
  "decision": "approve",
  "tool_input": {
    "command": "set -o pipefail; $COMMAND"
  }
}
JSON
