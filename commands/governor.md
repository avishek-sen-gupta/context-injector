Switch the governor's active state machine. Usage: `/governor <machine>` where `<machine>` is one of:

- `tdd` — Pytest-driven TDD (WritingTests/Red/FixingTests/Green) — the default
- `feature` — Feature Development (Plan/Implement/Review/Commit)
- A fully qualified dotted path like `machines.my_workflow.MyWorkflow`

The argument is: $ARGUMENTS

Run this exact command:

```bash
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_DIR="/tmp/ctx-state"
mkdir -p "$STATE_DIR"
ARG="$ARGUMENTS"

# Resolve shorthand names
case "$ARG" in
  tdd)     MACHINE="machines.tdd.TDD" ;;
  feature) MACHINE="machines.feature_development.FeatureDevelopment" ;;
  *)       MACHINE="$ARG" ;;
esac

# Write machine config
printf '%s' "$MACHINE" > "$STATE_DIR/$PROJECT_HASH.machine"

# Reset state file so the new machine starts fresh
rm -f "$STATE_DIR/$PROJECT_HASH.json"

echo "[governor: switched to $MACHINE]"
```

Respond with exactly what the command prints. Do not explain. Do not ask for confirmation.
