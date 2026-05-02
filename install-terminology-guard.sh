#!/bin/sh
# install-terminology-guard.sh — Terminology Guard installer.
# Run from the root of the git project you want to protect.
# Copies scripts to precommit-scripts/ and wires .pre-commit-config.yaml.
# scan-history is also installed to precommit-scripts/ for manual use.

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$PWD"
SCRIPTS_DIR="$PROJECT_DIR/precommit-scripts"

# --- validate ---
if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Error: not a git repository. Run from the root of a git project." >&2
  exit 1
fi

# --- install scripts ---
echo "Installing terminology guard scripts to precommit-scripts/..."
mkdir -p "$SCRIPTS_DIR"
cp "$PLUGIN_DIR/hooks/terminology/lib-terminology.sh" "$SCRIPTS_DIR/"
cp "$PLUGIN_DIR/hooks/terminology/check-terminology"  "$SCRIPTS_DIR/"
cp "$PLUGIN_DIR/hooks/terminology/scan-history"       "$SCRIPTS_DIR/"
chmod +x "$SCRIPTS_DIR/check-terminology" "$SCRIPTS_DIR/scan-history"

# --- wire .pre-commit-config.yaml (idempotent) ---
CONFIG="$PROJECT_DIR/.pre-commit-config.yaml"
HOOK_ENTRY="      - id: terminology-guard
        name: Terminology Guard
        entry: precommit-scripts/check-terminology
        language: script
        types: [text]"

if [ -f "$CONFIG" ] && grep -q "id: terminology-guard" "$CONFIG" 2>/dev/null; then
  echo "terminology-guard already in .pre-commit-config.yaml, skipping."
elif [ ! -f "$CONFIG" ]; then
  echo "Creating .pre-commit-config.yaml with terminology-guard..."
  cat > "$CONFIG" <<EOF
repos:
  - repo: local
    hooks:
$HOOK_ENTRY
EOF
elif grep -q "repo: local" "$CONFIG" 2>/dev/null; then
  echo "Adding terminology-guard to existing repo: local block..."
  # Append the hook entry after the last line of the repo: local block.
  # Strategy: find the line number of "repo: local", then find the last
  # non-blank line before the next "- repo:" or EOF, and insert after it.
  python3 -c "
import re, sys

with open('$CONFIG') as f:
    lines = f.readlines()

# Find the 'repo: local' line
local_idx = None
for i, line in enumerate(lines):
    if re.search(r'repo:\s*local', line):
        local_idx = i
        break

if local_idx is None:
    sys.exit(1)

# Find the end of this repo block: next '- repo:' at same indent or EOF
insert_at = len(lines)
for i in range(local_idx + 1, len(lines)):
    if re.match(r'\s*- repo:', lines[i]):
        # Back up past any blank lines
        insert_at = i
        while insert_at > local_idx and lines[insert_at - 1].strip() == '':
            insert_at -= 1
        break

hook = '''
      - id: terminology-guard
        name: Terminology Guard
        entry: precommit-scripts/check-terminology
        language: script
        types: [text]
'''
lines.insert(insert_at, hook)

with open('$CONFIG', 'w') as f:
    f.writelines(lines)
"
else
  echo "Adding terminology-guard as new repo: local block..."
  cat >> "$CONFIG" <<EOF

  - repo: local
    hooks:
$HOOK_ENTRY
EOF
fi

# --- blocklist reminder ---
BLOCKLIST="$HOME/.config/git/blocklist.txt"
if [ ! -f "$BLOCKLIST" ]; then
  echo ""
  echo "Note: no blocklist found at $BLOCKLIST"
  echo "Create it with one regex pattern per line, e.g.:"
  echo "  mkdir -p ~/.config/git && echo 'my-secret-term' > ~/.config/git/blocklist.txt"
fi

echo ""
echo "Done. Terminology guard installed for $PROJECT_DIR."
echo ""
echo "  Pre-commit gate : precommit-scripts/check-terminology (via .pre-commit-config.yaml)"
echo "  History scanner : precommit-scripts/scan-history  (run from any git repo)"
echo "  Blocklist       : $BLOCKLIST"
echo "  Excludelist     : $HOME/.config/git/blocklist-exclude.txt  (optional)"
