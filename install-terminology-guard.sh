#!/bin/sh
# install-terminology-guard.sh — Terminology Guard installer.
# Run from the root of the git project you want to protect.
# Wires check-terminology into .git/hooks/pre-commit (idempotent).
# scan-history is installed globally and callable from any repo.

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$PWD"
INSTALL_DIR="$HOME/.claude/plugins/context-injector/gates/terminology"
PRE_COMMIT_HOOK="$PROJECT_DIR/.git/hooks/pre-commit"
HOOK_CALL="$INSTALL_DIR/check-terminology"

# --- validate ---
if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Error: not a git repository. Run from the root of a git project." >&2
  exit 1
fi

# --- install scripts ---
echo "Installing terminology guard scripts..."
mkdir -p "$INSTALL_DIR"
cp "$PLUGIN_DIR/gates/terminology/lib-terminology.sh" "$INSTALL_DIR/"
cp "$PLUGIN_DIR/gates/terminology/check-terminology"  "$INSTALL_DIR/"
cp "$PLUGIN_DIR/gates/terminology/scan-history"       "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/check-terminology" "$INSTALL_DIR/scan-history"

# --- wire pre-commit hook (idempotent) ---
if [ -f "$PRE_COMMIT_HOOK" ]; then
  if grep -q "check-terminology" "$PRE_COMMIT_HOOK" 2>/dev/null; then
    echo "pre-commit hook already wired, skipping."
  else
    echo "Adding terminology guard to existing pre-commit hook..."
    echo "" >> "$PRE_COMMIT_HOOK"
    echo "# terminology guard" >> "$PRE_COMMIT_HOOK"
    echo "$HOOK_CALL" >> "$PRE_COMMIT_HOOK"
    chmod +x "$PRE_COMMIT_HOOK"
  fi
else
  echo "Creating pre-commit hook..."
  cat > "$PRE_COMMIT_HOOK" <<EOF
#!/bin/sh
# terminology guard
$HOOK_CALL
EOF
  chmod +x "$PRE_COMMIT_HOOK"
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
echo "  Pre-commit gate : $HOOK_CALL"
echo "  History scanner : $INSTALL_DIR/scan-history  (run from any git repo)"
echo "  Blocklist       : $BLOCKLIST"
echo "  Excludelist     : $HOME/.config/git/blocklist-exclude.txt  (optional)"
