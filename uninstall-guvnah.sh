#!/usr/bin/env bash
# Remove guvnah hooks, machines, and state from the system.
set -euo pipefail

DEST="$HOME/.claude/plugins/guvnah"
STATE="/tmp/ctx-governor"

if [ -d "$DEST" ]; then
    echo "Removing $DEST ..."
    rm -rf "$DEST"
else
    echo "Nothing to remove — $DEST does not exist."
fi

if [ -d "$STATE" ]; then
    echo "Removing state directory $STATE ..."
    rm -rf "$STATE"
fi

echo "Done. Remember to remove the guvnah hook entries from your .claude/settings.json."
