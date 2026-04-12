# context-injector

A Claude Code plugin that auto-injects core + classified conditional context into every prompt when enabled. Toggled on/off with the `/ctx` command.

## How it works

- **`/ctx`** — toggles context injection on or off for the current project. State is stored in `/tmp/ctx-locks/<md5-of-project-path>` (ephemeral, no project pollution).
- When on, core context is also injected once at **session start** via the `SessionStart` hook.
- When on, every prompt receives:
  1. All files from `.claude/core/` (always)
  2. Matching files from `.claude/conditional/` based on keyword classification of the prompt

## Classification

| Keywords in prompt | Files injected from `.claude/conditional/` |
|---|---|
| implement, add, build, create, fix, feature, bug, write, emit, lower, migrate, introduce, wire, hook, support, handle, extend, port, close | design-principles, testing-patterns, refactoring, tools-skills |
| test, tdd, assert, coverage, xfail, failing, passes, red-green, fixture, integration test, unit test | testing-patterns |
| refactor, rename, extract, move, split, merge, simplify, clean, reorganize, restructure, consolidate, decompose, inline, deduplicate | design-principles, refactoring, tools-skills |
| review, pr, diff, check, feedback, critique, approve | code-review |
| verify, audit, scan, lint, sweep, validate, ensure, confirm, gate, black, lint-imports | testing-patterns, tools-skills |

## Requirements

- [Claude Code](https://claude.ai/code) with a project that has a `.claude/` directory
- `jq` (for the automated installer)
- `md5` (macOS built-in; on Linux use `md5sum` — see note below)

> **Linux note:** The hook and command use `md5` (macOS). On Linux, replace `md5` with `md5sum | cut -d' ' -f1` in both `hooks/user-prompt-submit.sh` and `commands/ctx.md`.

## Installation

### Automated (requires jq)

Run from the root of the project you want to wire:

```bash
git clone <repo-url> context-injector
cd /path/to/your/project
/path/to/context-injector/install.sh
```

The script:
- Copies the hook to `~/.claude/plugins/context-injector/hooks/`
- Copies the `/ctx` command to `~/.claude/commands/`
- Wires the `UserPromptSubmit` hook in `.claude/settings.json`
- Adds the required Bash permission entries
- Is idempotent — safe to run multiple times

### Manual

**1. Copy the hooks:**
```bash
mkdir -p ~/.claude/plugins/context-injector/hooks
cp hooks/user-prompt-submit.sh ~/.claude/plugins/context-injector/hooks/
cp hooks/pre-tool-use.sh ~/.claude/plugins/context-injector/hooks/
cp hooks/session-start.sh ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
chmod +x ~/.claude/plugins/context-injector/hooks/pre-tool-use.sh
chmod +x ~/.claude/plugins/context-injector/hooks/session-start.sh
```

**2. Copy the `/ctx` command:**
```bash
cp commands/ctx.md ~/.claude/commands/ctx.md
```

**3. Wire the hooks in your project's `.claude/settings.json`:**
```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "~/.claude/plugins/context-injector/hooks/session-start.sh"
      }
    ]
  }
],
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"
      }
    ]
  }
],
"PreToolUse": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "~/.claude/plugins/context-injector/hooks/pre-tool-use.sh"
      }
    ]
  }
]
```

**4. Add allow entries to `permissions.allow` in `.claude/settings.json`:**
```json
"Bash(mkdir:/tmp/ctx-locks)",
"Bash(touch:/tmp/ctx-locks/*)",
"Bash(rm:/tmp/ctx-locks/*)"
```

## v2: State Machine Governor

The governor mode replaces keyword-based classification with a state machine that tracks Claude's workflow phase, injects context based on current state, enforces transitions with configurable softness, and produces an audit trail.

### How it works

1. **SessionStart** initializes the state machine and injects DeclarePhase instructions
2. **PreToolUse** runs the governor on every tool call — it checks the tool against allowed-tools for the current state and detects phase declarations
3. **PreCompact** re-injects state context before conversation compaction so invariants survive compression
4. Claude announces transitions by running: `echo '{"declare_phase": "<phase>", "reason": "<why>"}'`
5. The governor validates the transition, applies a graduated response based on softness, injects context files for the new state, and writes an audit entry

### Graduated response

Each transition has a **softness** value (0.0–1.0) controlling how the governor responds:

| Softness | Action | Behavior |
|---|---|---|
| ≥ 0.7 | allow | Transition proceeds silently |
| 0.3–0.7 | remind | Transition proceeds with a deviation warning |
| < 0.3 | challenge | Transition proceeds but Claude is asked to justify |

### Built-in machines

**TDDCycle** (`machines.tdd_cycle.TDDCycle`) — the default:
- States: `red` → `green` → `refactor` (+ `docs_detour`)
- Enforces test-first development with tool restrictions per state (e.g., only test files editable in `red`)

**FeatureDevelopment** (`machines.feature_development.FeatureDevelopment`):
- States: `planning` → `implementing` → `reviewing` → `committing`
- Delegates `implementing` to a TDDCycle sub-machine

### Defining custom machines

Create a Python class extending `GovernedMachine`:

```python
from statemachine import State
from machines.base import GovernedMachine

class MyWorkflow(GovernedMachine):
    step_a = State(initial=True)
    step_b = State()

    advance = step_a.to(step_b)

    SOFTNESS = {"advance": 1.0}
    CONTEXT = {
        "step_a": ["core/*"],
        "step_b": ["conditional/review.md"],
    }
    ALLOWED_TOOLS = {
        "step_a": ["Edit", "Write"],
        "step_b": ["Read", "Grep"],
    }
```

Place it in `machines/` and set `CTX_MACHINE` to its dotted path (e.g., `machines.my_workflow.MyWorkflow`).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `CTX_MACHINE` | `machines.tdd_cycle.TDDCycle` | Dotted path to the state machine class |
| `CTX_STATE_DIR` | `/tmp/ctx-state` | Directory for persisted state files |
| `CTX_AUDIT_DIR` | `$PWD/.claude/audit` | Directory for JSONL audit logs |
| `CTX_CONTEXT_DIR` | `$PWD/.claude` | Base directory for context file resolution |
| `CTX_PROJECT_HASH` | md5 of `$PWD` | Unique identifier for the project |

### Audit trail

Each governor evaluation appends a JSON line to `$CTX_AUDIT_DIR/<session_id>.jsonl` with: timestamp, from/to state, trigger type, softness, action taken, tool name, and context files injected.

### Migration from v1

v1 hooks (keyword-based `UserPromptSubmit`, `PreToolUse`, `SessionStart`) are preserved. The governor adds three new hooks alongside them:
- `governor-hook.sh` (PreToolUse) — state machine evaluation
- `session-start-v2.sh` (SessionStart) — state machine initialization
- `pre-compact.sh` (PreCompact) — compaction survival

Both v1 and v2 hooks check the same lockfile (`/tmp/ctx-locks/<hash>`), so `/ctx on|off` controls both. To use v2, run `install.sh` — it installs all hooks and wires them into `.claude/settings.json`.

### Additional requirements for v2

- Python 3 with `python-statemachine>=3.0.0` (`pip3 install python-statemachine`)

## License

[MIT](LICENSE.md)

## Project convention

Each project provides its own context files:

```
.claude/
  core/                    ← always injected when ctx is on
    project-context.md
    workflow.md
    ...
  conditional/             ← injected based on keyword classification
    design-principles.md
    testing-patterns.md
    code-review.md
    refactoring.md
    tools-skills.md
```
