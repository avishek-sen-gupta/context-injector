#!/usr/bin/env bash
# SessionStart hook — enable pipefail for every Bash tool call.
# Works with both bash (BASH_ENV) and zsh (ZDOTDIR/.zshenv).
# Uses CLAUDE_ENV_FILE to inject env vars into the session.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
STRICT_FILE="$HOOK_DIR/bash-strict.sh"

if [ ! -f "$STRICT_FILE" ]; then
  exit 0
fi

# --- set up zsh support ---
ZDOTDIR_CUSTOM="$HOOK_DIR/.zdotdir"
mkdir -p "$ZDOTDIR_CUSTOM"
cat > "$ZDOTDIR_CUSTOM/.zshenv" <<ZEOF
# Chain-load original .zshenv
if [ -n "\${ORIGINAL_ZDOTDIR:-}" ] && [ -f "\$ORIGINAL_ZDOTDIR/.zshenv" ]; then
  source "\$ORIGINAL_ZDOTDIR/.zshenv"
elif [ -f "\$HOME/.zshenv" ]; then
  source "\$HOME/.zshenv"
fi
source "$STRICT_FILE"
ZEOF

# --- inject env vars ---
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export BASH_ENV=\"$STRICT_FILE\"" >> "$CLAUDE_ENV_FILE"
  echo "export ORIGINAL_ZDOTDIR=\"${ZDOTDIR:-$HOME}\"" >> "$CLAUDE_ENV_FILE"
  echo "export ZDOTDIR=\"$ZDOTDIR_CUSTOM\"" >> "$CLAUDE_ENV_FILE"
fi

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "pipefail enabled for all Bash operations via BASH_ENV (bash) and ZDOTDIR (zsh)"
  }
}
JSON
