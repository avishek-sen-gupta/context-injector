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
if [ -f "$CONFIG" ] && grep -q "id: terminology-guard" "$CONFIG" 2>/dev/null; then
  echo "terminology-guard already in .pre-commit-config.yaml, skipping."
else
  echo "Adding terminology-guard to .pre-commit-config.yaml..."
  if [ ! -f "$CONFIG" ]; then
    cat > "$CONFIG" <<'EOF'
repos:
  - repo: local
    hooks:
      - id: terminology-guard
        name: Terminology Guard
        entry: precommit-scripts/check-terminology
        language: script
        types: [text]
EOF
  else
    cat >> "$CONFIG" <<'EOF'

  - repo: local
    hooks:
      - id: terminology-guard
        name: Terminology Guard
        entry: precommit-scripts/check-terminology
        language: script
        types: [text]
EOF
  fi
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
