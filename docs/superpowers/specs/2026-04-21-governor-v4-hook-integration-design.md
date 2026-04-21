# Governor v4 Hook Integration Design

## Goal

Wire the governor_v4 evidence-based state transition engine into Claude Code's hook system so it can enforce workflow phases, capture tool output as evidence, and process `/governor` commands during live sessions.

## Decisions

- **Plugin directory:** `~/.claude/plugins/guvnah/`
- **Command surface:** `/governor` with subcommands (not `/transition`)
- **Hook invocation:** Shell scripts calling `python3 -m governor_v4 <subcommand>`
- **v1 coexistence:** v1 keyword classification (`context-injector/hooks/user-prompt-submit.sh`) remains untouched; v4 hooks are separate entries in settings.json
- **State directory:** `/tmp/ctx-governor/<session_hash>/`
- **Scope:** Four hooks (SessionStart, PreToolUse, PostToolUse, UserPromptSubmit). No PreCompact.

## Command Surface

All commands parsed by the UserPromptSubmit hook:

| Command | Action |
|---------|--------|
| `/governor <machine>` | Activate governor with named machine (e.g., `tdd`) |
| `/governor off` | Deactivate governor, clear state |
| `/governor status` | Show current phase + available transitions |
| `/governor transition <target> [evidence_key]` | Request state transition with optional evidence |
| `/governor evidence` | List stored evidence keys with type/tool/timestamp |

## Architecture

### Plugin Layout

```
~/.claude/plugins/guvnah/
├── hooks/
│   ├── session-start.sh
│   ├── pre-tool-use.sh
│   ├── post-tool-use.sh
│   └── user-prompt-submit.sh
└── machines/
    └── tdd.json
```

### New Python Files (in governor_v4 package)

- `__main__.py` — CLI dispatcher: parses subcommand, lazy-imports the relevant handler
- `cli.py` — shared setup: load machine JSON, init/restore engine from state dir, lock file management

### Approach: Monolithic CLI with Lazy Dispatch

Single entry point `python3 -m governor_v4 <subcommand>`. The `__main__.py` parses the subcommand and only imports the handler needed. Shared setup (load machine config, restore engine state) lives in `cli.py`. Shell scripts are one-liners.

## Hook Contracts

### SessionStart (`session-start.sh`)

- Reads `$CLAUDE_SESSION_ID`
- Checks if lock file exists at `/tmp/ctx-governor/<hash>/active`
- If active: `python3 -m governor_v4 init --restore` — restores engine from state, injects current phase info via `additionalContext`
- If not active: exits 0 (no-op)

### PreToolUse (`pre-tool-use.sh`)

- Reads tool name and input from stdin (`$CLAUDE_TOOL_NAME`, tool input JSON)
- If governor not active (no lock file): exits 0 (pass-through)
- If active: `python3 -m governor_v4 evaluate` — reads tool info from stdin, calls `engine.evaluate()`, outputs `{"decision": "block", "reason": "..."}` or empty (allow)

### PostToolUse (`post-tool-use.sh`)

- Reads tool name, input, and output from stdin
- If governor not active: exits 0
- If active: `python3 -m governor_v4 capture` — matches capture rules from machine config, stores in evidence locker, injects evidence key via `additionalContext`

### UserPromptSubmit (`user-prompt-submit.sh`)

- Reads user prompt from stdin
- Scans for `/governor` prefix
- If no `/governor` command: exits 0 (no-op)
- If found: `python3 -m governor_v4 prompt` — routes to subcommand handler:
  - `start <machine>` — creates lock file, loads machine JSON, inits engine, saves state
  - `off` — removes lock file + state files
  - `status` — returns current phase + available transitions via `additionalContext`
  - `transition <target> [evidence_key]` — calls `want_to_transition()`, returns result
  - `evidence` — lists locker contents via `additionalContext`

## State & Lifecycle

### Activation

1. User types `/governor tdd`
2. UserPromptSubmit hook parses it, calls `python3 -m governor_v4 prompt`
3. Python loads `~/.claude/plugins/guvnah/machines/tdd.json`, inits engine at initial state
4. Saves state to `/tmp/ctx-governor/<session_hash>/state.json`
5. Creates lock file `/tmp/ctx-governor/<session_hash>/active`
6. Returns `additionalContext` with phase info + tool restrictions

### Per-Tool-Call (active)

1. PreToolUse fires → shell checks lock file → calls `evaluate` → blocks or allows
2. Tool executes
3. PostToolUse fires → shell checks lock file → calls `capture` → if tool matches capture rule, stores evidence, injects key via `additionalContext`

### Transition

1. User/LLM types `/governor transition green evt_a1b2c3`
2. UserPromptSubmit parses → calls `want_to_transition()`
3. Engine validates evidence via gates → transitions or denies
4. Saves updated state → returns result via `additionalContext`

### Deactivation

1. `/governor off` → removes lock file + state files
2. All hooks see no lock file → no-op

### Session Restore

1. New session starts → SessionStart checks for lock file
2. If found → restores engine from state file → injects current phase context

The lock file is the single "is governor active?" check. Shell scripts skip Python invocation entirely when no lock file exists.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Missing evidence key on transition | Denial via `additionalContext`: "no evidence provided" or "key not found in locker" |
| Gate validation failure | Denial with gate failure message. State unchanged. LLM stays in current phase. |
| Invalid machine name | Error via `additionalContext`: "machine not found." Lists available machines. |
| Stale lock file (orphaned session) | `/governor off` always cleans up. `/governor <machine>` on existing lock resets fresh. |
| Python import failure | Shell hook exits 0 (fail-open). Does not break user's session. |

## Out of Scope

- PreCompact hook (deferred)
- v1 keyword classification changes (stays untouched)
- New machine definitions (reuse existing `tdd_v4.json`)
- Gate escalation policies (future phase)
