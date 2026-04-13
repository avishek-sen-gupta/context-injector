Toggle the state machine governor on or off, switch machines, run lint, query audit, or check status. Usage:

- `/governor tdd` — enable governor with pytest-driven TDD (the default)
- `/governor feature` — enable governor with Feature Development workflow
- `/governor machines.my_workflow.MyWorkflow` — enable with a custom machine
- `/governor off` — disable the governor
- `/governor status` — show current governor state (machine and phase)
- `/governor trigger <event>` — fire a named transition (e.g. `add_tests` to go back to writing tests from fixing_tests)
- `/governor lint <pattern> [pattern ...]` — run ast-grep lint rules on files matching patterns (e.g. `*.py`, `src/**/*.py`)
- `/governor audit` — query audit trail (supports `--type`, `--gate`, `--verdict`, `--session`, `--since`, `--limit`)

The argument is: $ARGUMENTS

Run this exact command:

```bash
~/.claude/plugins/context-injector/bin/governor $ARGUMENTS
```

Respond with exactly what the command prints. Do not explain. Do not ask for confirmation.
