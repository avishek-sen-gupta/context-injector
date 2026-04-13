#!/usr/bin/env bash
# bd-terminology-guard.sh — PreToolUse hook that blocks Beads issue write commands
# containing sensitive terminology from ~/.config/git/blocklist.txt.
#
# Receives Claude Code hook JSON on stdin:
#   {"tool_name": "Bash", "tool_input": {"command": "bd create ..."}}
#
# Outputs {"continue": false, "stopReason": "..."} to block, exits 0 silently to allow.

set -euo pipefail

BLOCKLIST="$HOME/.config/git/blocklist.txt"

# Read stdin
input="$(cat)"

# Extract the bash command being run
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // ""')"

# Only intercept bd write commands
if ! printf '%s' "$cmd" | grep -qE '^\s*bd\s+(create|new|update|edit|note|comment|dep\s+relate)\b'; then
    exit 0
fi

# Build combined grep pattern from blocklist (skip blank lines and comments)
pattern="$(grep -Ev '^\s*(#|$)' "$BLOCKLIST" | paste -sd '|' -)"

if [ -z "$pattern" ]; then
    exit 0
fi

# Extract all text content from the command:
# Strip the leading "bd <subcommand> [ID]" token, leaving flags and their values.
# We check the full argument string — conservative but safe.
text_to_check="$(printf '%s' "$cmd" | sed 's/^\s*bd\s\+[a-z ]*\s*//')"

if printf '%s' "$text_to_check" | grep -qE "$pattern"; then
    matched="$(printf '%s' "$text_to_check" | grep -oE "$pattern" | head -1)"
    printf '%s' "$(jq -n \
        --arg reason "Blocked: Beads command contains sensitive terminology matching pattern \"$matched\". Remove it before retrying." \
        '{"continue": false, "stopReason": $reason}')"
    exit 0
fi

exit 0
