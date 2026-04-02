Toggle Context Injector mode on or off for the current project. Accepts an optional argument: `on` to explicitly enable, `off` to explicitly disable, or no argument to toggle.

The argument is: $ARGUMENTS

Run this exact command:

```bash
mkdir -p /tmp/ctx-locks
LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
ARG="$ARGUMENTS"

if [ "$ARG" = "on" ]; then
  touch "$LOCK"; echo "[ctx: on]"
elif [ "$ARG" = "off" ]; then
  rm -f "$LOCK"; echo "[ctx: off]"
elif [ -f "$LOCK" ]; then
  rm "$LOCK"; echo "[ctx: off]"
else
  touch "$LOCK"; echo "[ctx: on]"
fi
```

Respond with exactly what the command prints (`[ctx: on]` or `[ctx: off]`). Do not explain. Do not ask for confirmation.
