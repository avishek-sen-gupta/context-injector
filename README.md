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
- Copies hooks to `~/.claude/plugins/context-injector/hooks/`
- Copies the governor and machine definitions to `~/.claude/plugins/context-injector/`
- Copies `/ctx` and `/governor` commands to `~/.claude/commands/`
- Wires all hooks (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`) in `.claude/settings.json`
- Adds the required Bash permission entries
- Is idempotent — safe to run multiple times

### Manual

**1. Copy the hooks:**
```bash
mkdir -p ~/.claude/plugins/context-injector/hooks
for f in user-prompt-submit.sh governor-hook.sh session-start-v2.sh post-tool-use.sh pre-compact.sh; do
  cp "hooks/$f" ~/.claude/plugins/context-injector/hooks/
  chmod +x ~/.claude/plugins/context-injector/hooks/"$f"
done
```

**2. Copy the governor and machines:**
```bash
mkdir -p ~/.claude/plugins/context-injector/{governor,machines}
cp governor/*.py ~/.claude/plugins/context-injector/governor/
cp machines/*.py ~/.claude/plugins/context-injector/machines/
```

**3. Copy commands:**
```bash
cp commands/ctx.md ~/.claude/commands/ctx.md
cp commands/governor.md ~/.claude/commands/governor.md
```

**4. Wire the hooks in your project's `.claude/settings.json`:**
```json
"hooks": {
  "SessionStart": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/session-start-v2.sh"}]}
  ],
  "UserPromptSubmit": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"}]}
  ],
  "PreToolUse": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/governor-hook.sh"}]}
  ],
  "PostToolUse": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/post-tool-use.sh"}]}
  ],
  "PreCompact": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/pre-compact.sh"}]}
  ]
}
```

**5. Add allow entries to `permissions.allow` in `.claude/settings.json`:**
```json
"Bash(mkdir:/tmp/ctx-locks)",
"Bash(touch:/tmp/ctx-locks/*)",
"Bash(rm:/tmp/ctx-locks/*)"
```

### Uninstall

Run from the root of the project you want to unwire:

```bash
/path/to/context-injector/uninstall.sh
```

This removes all hooks from `.claude/settings.json`, deletes the plugin directory, commands, and state files.

## v2: State Machine Governor (TDD)

The governor replaces keyword-based classification with an enforced TDD state machine. It tracks Claude's workflow phase, blocks disallowed tools, automatically transitions based on pytest results, injects context per state, and produces an audit trail.

### How it works

1. **SessionStart** (`session-start-v2.sh`) initializes the state machine and injects TDD workflow instructions
2. **PreToolUse** (`governor-hook.sh`) runs the governor on every tool call — checks the tool against blocked-tools for the current state, and scans the conversation transcript for unprocessed pytest results
3. **PostToolUse** (`post-tool-use.sh`) detects pytest pass/fail from Bash tool output and fires state transitions
4. **PreCompact** (`pre-compact.sh`) re-injects state context before conversation compaction so invariants survive compression

Transitions are **automatic** — driven by pytest results, not manual declarations.

### TDD cycle

```
writing_tests → (pytest fails) → red → (auto) → fixing_tests
                                                       ↓
writing_tests ← (auto) ← green ← (pytest passes) ←───┘
```

- **writing_tests** (start): Write failing tests. Only `test_*` files can be created/edited.
- **red**: Transient — auto-advances to `fixing_tests`.
- **fixing_tests**: Write production code to make tests pass. All files editable.
- **green**: Transient — auto-advances back to `writing_tests`.

### Pytest detection

The governor detects pytest results through two mechanisms:

1. **PostToolUse hook**: Fires after successful Bash commands (`exit 0`). Parses the tool output for pytest summary patterns (`FAILED`, `passed`, etc.) and triggers the appropriate state transition.
2. **Transcript scanning** (PreToolUse fallback): PostToolUse hooks do **not** fire for non-zero Bash exit codes, so pytest failures (`exit 1`) and collection errors (`exit 2`) are invisible to PostToolUse. As a fallback, the governor scans the Claude Code conversation transcript (JSONL) on every PreToolUse call, looking for unprocessed pytest results. A marker file prevents re-processing the same result.

### Tool blocking

The governor uses a **blocklist** approach. Tools not listed are allowed. Each state defines which tools are blocked, with `!` prefix exceptions:

| State | Blocked | Exceptions |
|---|---|---|
| `writing_tests` | `Write`, `Edit` | `!Write(test_*)`, `!Edit(test_*)` |
| `red` | `Write`, `Edit` | — |
| `fixing_tests` | *(none)* | — |
| `green` | `Write`, `Edit` | — |

Non-destructive tools (`Read`, `Grep`, `Glob`, `Agent`, `Bash`, etc.) are always allowed in all states.

### Graduated response

When a blocked tool is used, the governor applies a graduated response based on the transition's **softness** value (0.0–1.0):

| Softness | Action | Behavior |
|---|---|---|
| >= 0.7 | allow | Proceeds silently |
| 0.3–0.7 | remind | Proceeds with a deviation warning |
| < 0.3 | challenge | Proceeds but Claude is asked to justify |

### Built-in machines

**TDD** (`machines.tdd.TDD`) — the default:
- States: `writing_tests` → `red` → `fixing_tests` → `green` → `writing_tests`
- Pytest-driven transitions with auto-advancing transient states
- Blocklist-based tool restrictions

**TDDCycle** (`machines.tdd_cycle.TDDCycle`) — legacy:
- States: `red` → `green` → `refactor` (+ `docs_detour`)
- Declaration-based transitions, allowlist-based tool restrictions

**FeatureDevelopment** (`machines.feature_development.FeatureDevelopment`):
- States: `planning` → `implementing` → `reviewing` → `committing`

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
    BLOCKED_TOOLS = {
        "step_a": ["Write", "Edit"],
        "step_b": [],
    }
    # Optional: auto-advance transient states
    AUTO_TRANSITIONS = {
        "step_b": "some_event",
    }
    # Optional: require tools to have been used before a transition
    PRECONDITIONS = {
        "advance": ["Bash(pytest*)"],
    }
```

Place it in `machines/` and set `CTX_MACHINE` to its dotted path (e.g., `machines.my_workflow.MyWorkflow`).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `CTX_MACHINE` | `machines.tdd.TDD` | Dotted path to the state machine class |
| `CTX_STATE_DIR` | `/tmp/ctx-state` | Directory for persisted state files |
| `CTX_AUDIT_DIR` | `$PWD/.claude/audit` | Directory for JSONL audit logs |
| `CTX_CONTEXT_DIR` | `$PWD/.claude` | Base directory for context file resolution |
| `CTX_PROJECT_HASH` | md5 of `$PWD` | Unique identifier for the project |

### Audit trail

Each governor evaluation appends a JSON line to `$CTX_AUDIT_DIR/<session_id>.jsonl` with: timestamp, from/to state, trigger type, softness, action taken, tool name, and context files injected.

### Migration from v1

v1 hooks (keyword-based `UserPromptSubmit`, `PreToolUse`, `SessionStart`) are preserved. The governor adds new hooks alongside them:
- `governor-hook.sh` (PreToolUse) — state machine evaluation + transcript scanning
- `session-start-v2.sh` (SessionStart) — state machine initialization
- `post-tool-use.sh` (PostToolUse) — pytest result detection
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
