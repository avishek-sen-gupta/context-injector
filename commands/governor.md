Toggle the state machine governor on or off, switch machines, or check status. Usage:

- `/governor tdd` — enable governor with pytest-driven TDD (the default)
- `/governor feature` — enable governor with Feature Development workflow
- `/governor machines.my_workflow.MyWorkflow` — enable with a custom machine
- `/governor off` — disable the governor
- `/governor status` — show current governor state (machine and phase)

The argument is: $ARGUMENTS

Run this exact command:

```bash
~/.claude/plugins/context-injector/bin/governor $ARGUMENTS
```

Respond with exactly what the command prints. Do not explain. Do not ask for confirmation.
