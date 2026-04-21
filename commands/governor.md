Control the Governor workflow enforcer. Accepts: a machine name (e.g. `tdd`) to activate, `off` to deactivate, `status` to check current state, `transition <target> [evidence_key]` to change phase, or `evidence` to list captured evidence.

The argument is: $ARGUMENTS

Run this exact command:

```bash
.claude/hooks/guvnah/governor $ARGUMENTS
```

Respond with exactly what the command prints. Do not explain. Do not ask for confirmation.
