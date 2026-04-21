#!/usr/bin/env bash
# Deploy guvnah hooks and machines to ~/.claude/plugins/guvnah/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEST="$HOME/.claude/plugins/guvnah"

echo "Installing guvnah to $DEST ..."

# Hooks
mkdir -p "$DEST/hooks"
for f in session-start.sh pre-tool-use.sh post-tool-use.sh user-prompt-submit.sh; do
    cp "$SCRIPT_DIR/$f" "$DEST/hooks/$f"
    chmod +x "$DEST/hooks/$f"
done

# Machines
mkdir -p "$DEST/machines"
for f in "$REPO_ROOT"/machines/*.json; do
    [ -f "$f" ] && cp "$f" "$DEST/machines/$(basename "$f" | sed 's/_v4//')"
done

echo "Done. Add hook entries to your project's .claude/settings.json:"
echo ""
echo '  "SessionStart": [{"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/session-start.sh"}]}],'
echo '  "PreToolUse":   [..., {"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/pre-tool-use.sh"}]}],'
echo '  "PostToolUse":  [{"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/post-tool-use.sh"}]}],'
echo '  "UserPromptSubmit": [..., {"hooks": [{"type": "command", "command": "~/.claude/plugins/guvnah/hooks/user-prompt-submit.sh"}]}]'
