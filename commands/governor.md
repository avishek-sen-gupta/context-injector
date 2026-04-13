Toggle the state machine governor on or off, or switch machines. Usage:

- `/governor tdd` — enable governor with pytest-driven TDD (the default)
- `/governor feature` — enable governor with Feature Development workflow
- `/governor machines.my_workflow.MyWorkflow` — enable with a custom machine
- `/governor off` — disable the governor

The argument is: $ARGUMENTS

Run this exact command:

```bash
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_DIR="/tmp/ctx-state"
GOVERNOR_DIR="/tmp/ctx-governor"
mkdir -p "$STATE_DIR" "$GOVERNOR_DIR"
LOCK="$GOVERNOR_DIR/$PROJECT_HASH"
ARG="$ARGUMENTS"

if [ "$ARG" = "off" ]; then
  rm -f "$LOCK"
  echo "[governor: off]"
else
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

  # Enable governor
  touch "$LOCK"

  echo "[governor: on — machine=$MACHINE]"
fi
```

Respond with exactly what the command prints. Do not explain. Do not ask for confirmation.
