Toggle Context Injector mode on or off for the current project.

Run this exact command:

```bash
mkdir -p /tmp/ctx-locks; LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"; if [ -f "$LOCK" ]; then rm "$LOCK"; echo "[ctx: off]"; else touch "$LOCK"; echo "[ctx: on]"; fi
```

Respond with exactly what the command prints (`[ctx: on]` or `[ctx: off]`). Do not explain. Do not ask for confirmation.
