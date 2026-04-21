#!/usr/bin/env bash
# install-guvnah.sh — Deploy guvnah hooks and machines to a project.
# Run from the root of the project you want to wire (it must have a .claude/ directory).
# Requires: jq
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$PWD"
SETTINGS="$PROJECT_DIR/.claude/settings.json"
DEST="$PROJECT_DIR/.claude/hooks/guvnah"

# --- validate ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

if [ ! -d "$PROJECT_DIR/.claude" ]; then
  echo "Error: no .claude/ directory found in $PROJECT_DIR. Run from a Claude Code project root." >&2
  exit 1
fi

echo "Installing guvnah to $DEST ..."

# --- install hooks (prepend PYTHONPATH and GUVNAH_MACHINES) ---
mkdir -p "$DEST"
for f in session-start.sh pre-tool-use.sh post-tool-use.sh post-tool-use-failure.sh user-prompt-submit.sh; do
    {
        echo '#!/usr/bin/env bash'
        echo "GUVNAH_ROOT=\"$REPO_ROOT\""
        echo 'export PYTHONPATH="$GUVNAH_ROOT${PYTHONPATH:+:$PYTHONPATH}"'
        echo 'export GUVNAH_MACHINES="$(cd "$(dirname "$0")" && pwd)/machines"'
        # Append everything after the shebang from the source
        tail -n +2 "$REPO_ROOT/hooks/guvnah/$f"
    } > "$DEST/$f"
    chmod +x "$DEST/$f"
done

# --- install pipefail guard (no PYTHONPATH needed) ---
cp "$REPO_ROOT/hooks/guvnah/pipefail-guard.sh" "$DEST/pipefail-guard.sh"
chmod +x "$DEST/pipefail-guard.sh"

# --- install machines ---
mkdir -p "$DEST/machines"
for f in "$REPO_ROOT"/machines/*.json; do
    [ -f "$f" ] && cp "$f" "$DEST/machines/$(basename "$f" | sed 's/_v4//')"
done

# --- create settings.json if missing ---
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# --- wire hooks (idempotent) ---
for pair in \
  "SessionStart:.claude/hooks/guvnah/session-start.sh" \
  "PreToolUse:.claude/hooks/guvnah/pre-tool-use.sh" \
  "PostToolUse:.claude/hooks/guvnah/post-tool-use.sh" \
  "PostToolUseFailure:.claude/hooks/guvnah/post-tool-use-failure.sh" \
  "UserPromptSubmit:.claude/hooks/guvnah/user-prompt-submit.sh"; do

  EVENT="${pair%%:*}"
  CMD="${pair#*:}"

  ALREADY=$(jq --arg cmd "$CMD" \
    '[.hooks.'"$EVENT"'[]?.hooks[]?.command // ""] | any(contains($cmd))' "$SETTINGS")
  if [ "$ALREADY" = "false" ]; then
    echo "Wiring $EVENT hook..."
    ENTRY='{"hooks": [{"type": "command", "command": "'"$CMD"'"}]}'
    jq --argjson entry "$ENTRY" \
      '.hooks.'"$EVENT"' = ((.hooks.'"$EVENT"' // []) + [$entry])' \
      "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  else
    echo "$EVENT hook already wired, skipping."
  fi
done

# --- wire pipefail guard (PreToolUse with Bash matcher, idempotent) ---
PIPEFAIL_CMD=".claude/hooks/guvnah/pipefail-guard.sh"
ALREADY=$(jq --arg cmd "$PIPEFAIL_CMD" \
  '[.hooks.PreToolUse[]?.hooks[]?.command // ""] | any(contains($cmd))' "$SETTINGS")
if [ "$ALREADY" = "false" ]; then
  echo "Wiring pipefail guard..."
  ENTRY='{"matcher": "Bash", "hooks": [{"type": "command", "command": "'"$PIPEFAIL_CMD"'"}]}'
  jq --argjson entry "$ENTRY" \
    '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "Pipefail guard already wired, skipping."
fi

# --- install guvnah-ctl CLI wrapper (with PYTHONPATH/GUVNAH_MACHINES baked in) ---
echo "Installing guvnah-ctl CLI wrapper..."
{
    echo '#!/usr/bin/env bash'
    echo "GUVNAH_ROOT=\"$REPO_ROOT\""
    echo 'export PYTHONPATH="$GUVNAH_ROOT${PYTHONPATH:+:$PYTHONPATH}"'
    echo 'export GUVNAH_MACHINES="$(cd "$(dirname "$0")" && pwd)/machines"'
    # Append everything after the shebang from the source
    tail -n +2 "$REPO_ROOT/bin/guvnah-ctl"
} > "$DEST/ctl"
chmod +x "$DEST/ctl"

# --- install /governor command ---
echo "Installing /governor command..."
mkdir -p "$PROJECT_DIR/.claude/commands"
cp "$REPO_ROOT/commands/governor.md" "$PROJECT_DIR/.claude/commands/governor.md"

# --- add Bash permissions (idempotent) ---
echo "Adding Bash permissions..."
jq '.permissions.allow = ((.permissions.allow // []) + ["Bash(.claude/hooks/guvnah/ctl*)", "Bash(mkdir:/tmp/ctx-governor)", "Bash(touch:/tmp/ctx-governor/*)", "Bash(rm:/tmp/ctx-governor/*)"] | unique)' \
  "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

echo ""
echo "Done. Guvnah installed for $PROJECT_DIR."
echo "Use /governor tdd to start the TDD workflow."
