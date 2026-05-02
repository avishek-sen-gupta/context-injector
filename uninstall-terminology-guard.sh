#!/bin/sh
# uninstall-terminology-guard.sh — Terminology Guard uninstaller.
# Run from the root of the git project you want to unwire.

set -e

PROJECT_DIR="$PWD"
SCRIPTS_DIR="$PROJECT_DIR/precommit-scripts"
CONFIG="$PROJECT_DIR/.pre-commit-config.yaml"

# --- validate ---
if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Error: not a git repository. Run from the root of a git project." >&2
  exit 1
fi

# --- remove from .pre-commit-config.yaml ---
if [ -f "$CONFIG" ]; then
  if grep -q "id: terminology-guard" "$CONFIG" 2>/dev/null; then
    echo "Removing terminology-guard from .pre-commit-config.yaml..."
    # Remove the terminology-guard hook block (local repo entry)
    sed -i.bak '/- repo: local/,/types: \[text\]/{
      /terminology-guard/,/types: \[text\]/d
      /- repo: local/{
        N
        /hooks:/{
          N
          /^[[:space:]]*$/d
        }
      }
    }' "$CONFIG"
    # Clean up empty local repo entries left behind
    sed -i.bak '/- repo: local/{N;/hooks:$/d;}' "$CONFIG"
    rm -f "$CONFIG.bak"

    # If the config is now effectively empty, remove it
    if ! grep -q "id:" "$CONFIG" 2>/dev/null; then
      rm -f "$CONFIG"
      echo ".pre-commit-config.yaml was empty after removal — deleted."
    fi
  else
    echo "Terminology guard not found in .pre-commit-config.yaml, skipping."
  fi
else
  echo "No .pre-commit-config.yaml found, skipping."
fi

# --- remove installed scripts ---
if [ -d "$SCRIPTS_DIR" ]; then
  echo "Removing terminology guard scripts from precommit-scripts/..."
  rm -f "$SCRIPTS_DIR/check-terminology" "$SCRIPTS_DIR/scan-history" "$SCRIPTS_DIR/lib-terminology.sh"
  rmdir "$SCRIPTS_DIR" 2>/dev/null || true
else
  echo "No precommit-scripts/ directory found, skipping."
fi

# --- clean up legacy install location if present ---
LEGACY_DIR="$HOME/.claude/plugins/context-injector/gates/terminology"
if [ -d "$LEGACY_DIR" ]; then
  echo "Removing legacy install at $LEGACY_DIR..."
  rm -f "$LEGACY_DIR/check-terminology" "$LEGACY_DIR/scan-history" "$LEGACY_DIR/lib-terminology.sh"
  rmdir "$LEGACY_DIR" 2>/dev/null || true
  rmdir "$HOME/.claude/plugins/context-injector/gates" 2>/dev/null || true
fi

echo ""
echo "Done. Terminology guard uninstalled for $PROJECT_DIR."
