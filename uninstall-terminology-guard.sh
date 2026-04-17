#!/bin/sh
# uninstall-terminology-guard.sh — Terminology Guard uninstaller.
# Run from the root of the git project you want to unwire.

set -e

PROJECT_DIR="$PWD"
INSTALL_DIR="$HOME/.claude/plugins/context-injector/gates/terminology"
PRE_COMMIT_HOOK="$PROJECT_DIR/.git/hooks/pre-commit"

# --- validate ---
if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Error: not a git repository. Run from the root of a git project." >&2
  exit 1
fi

# --- remove from pre-commit hook ---
if [ -f "$PRE_COMMIT_HOOK" ]; then
  if grep -q "check-terminology" "$PRE_COMMIT_HOOK" 2>/dev/null; then
    echo "Removing terminology guard from pre-commit hook..."
    # Remove the guard line and its comment, and any blank line immediately before them
    sed -i.bak '/^[[:space:]]*# terminology guard$/d; /check-terminology/d' "$PRE_COMMIT_HOOK"
    rm -f "$PRE_COMMIT_HOOK.bak"

    # If the hook is now empty (only shebang or blank), remove it
    if [ "$(grep -v '^\s*$' "$PRE_COMMIT_HOOK" | grep -v '^#!' | wc -l | tr -d ' ')" = "0" ]; then
      rm -f "$PRE_COMMIT_HOOK"
      echo "Pre-commit hook was empty after removal — deleted."
    fi
  else
    echo "Terminology guard not found in pre-commit hook, skipping."
  fi
else
  echo "No pre-commit hook found, skipping."
fi

# --- remove installed scripts ---
if [ -d "$INSTALL_DIR" ]; then
  echo "Removing installed scripts from $INSTALL_DIR..."
  rm -f "$INSTALL_DIR/check-terminology" "$INSTALL_DIR/scan-history" "$INSTALL_DIR/lib-terminology.sh"
  rmdir "$INSTALL_DIR" 2>/dev/null || true
  rmdir "$HOME/.claude/plugins/context-injector/gates" 2>/dev/null || true
else
  echo "No installed scripts found at $INSTALL_DIR, skipping."
fi

echo ""
echo "Done. Terminology guard uninstalled for $PROJECT_DIR."
