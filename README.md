# context-injector

A Claude Code plugin that governs agent behavior during development workflows. It enforces discipline — blocking tools that shouldn't be used, advancing state based on real signals (like test results), injecting the right context at the right time, and producing an audit trail of every decision.

Two modes, from lightweight to full enforcement:

1. **Governor** (`/governor`) — a state machine that enforces workflow phases, blocks disallowed tools, transitions automatically on pytest results, and injects state-specific context
2. **Context Injection** (`/ctx`) — keyword-based context injection without enforcement, for projects that want guidance without guardrails

Both modes are independent and can run simultaneously.

## Governor

The governor wraps Claude Code in a state machine. Every tool call is evaluated against the current workflow phase. Tools that violate the phase are blocked or challenged. Transitions happen automatically based on real signals — not declarations.

### Commands

| Command | Effect |
|---|---|
| `/governor tdd` | Enable with the TDD state machine |
| `/governor feature` | Enable with Feature Development machine |
| `/governor off` | Disable |
| `/governor status` | Show current machine and state (JSON) |

### How it works

1. **SessionStart** (`session-start.sh`) — initializes the state machine, injects core context and workflow instructions
2. **PreToolUse** (`governor-hook.sh`) — evaluates every tool call against the current state's rules; blocks disallowed tools; scans the conversation transcript for unprocessed pytest results
3. **PostToolUse** (`post-tool-use.sh`) — detects pytest pass/fail from Bash tool output and fires state transitions
4. **PreCompact** (`pre-compact.sh`) — re-injects state context and workflow instructions before conversation compaction so invariants survive compression

### Tool blocking

The governor uses a **blocklist** approach — tools not listed are allowed. Each state defines which tools are blocked, with `!` prefix exceptions:

| State | Blocked | Exceptions |
|---|---|---|
| `writing_tests` | `Write`, `Edit` | `!Write(test_*)`, `!Edit(test_*)` |
| `red` | `Write`, `Edit` | — |
| `fixing_tests` | *(none)* | — |
| `green` | `Write`, `Edit` | — |

Non-destructive tools (`Read`, `Grep`, `Glob`, `Agent`, `Bash`, etc.) are always allowed.

### Graduated response

When a tool violates the current state's rules, the governor doesn't always hard-block. It applies a **graduated response** based on the transition's softness value (0.0–1.0):

| Softness | Action | Behavior |
|---|---|---|
| >= 0.7 | allow | Proceeds silently |
| 0.3–0.7 | remind | Proceeds with a deviation warning |
| < 0.3 | challenge | Proceeds but Claude is asked to justify |

This means the governor can be strict where it matters (e.g., no production code during test-writing) and lenient where rigid enforcement would slow things down.

### Transition guards (gates)

Gates are transition guards — they run when a transition is about to fire, after preconditions pass but before the transition executes. Each gate inspects the work done during the current state and returns a verdict:

| Verdict | Behavior |
|---|---|
| `PASS` | Transition proceeds |
| `FAIL` | Blocked per gate softness (graduated response) |
| `REVIEW` | Injects a review prompt — agent must self-review, then retry |

**Built-in gates:**

- **TestQualityGate** — runs on `pytest_fail` in the TDD machine. Uses AST analysis to detect structurally invalid tests (no assertions, `assert True`, `pytest.skip`) and weak patterns (none-only, membership-only, type-only checks).
- **LintGate** — runs on `pytest_pass` in the TDD machine. Executes [ast-grep](https://ast-grep.github.io/) rules from `scripts/lint/rules/` against recently touched Python files. Blocks the transition if any violations are found. Gracefully passes if `ast-grep` (`sg`) is not installed.

Machines register gates via `GUARDS` and `GATE_SOFTNESS`:

```python
GUARDS = {
    "pytest_fail": [TestQualityGate],
    "pytest_pass": [LintGate],
}
GATE_SOFTNESS = {
    "test_quality": 0.1,   # Strict — override per project
    "lint": 0.1,
}
```

**Audit queries:**

```bash
governor audit --gate test_quality --verdict fail
governor audit --type gate_eval --limit 20
governor audit --all
```

### TDD cycle

The default machine enforces a strict red-green TDD loop:

```
writing_tests → (pytest fails) → red → (auto) → fixing_tests
                                                       ↓
writing_tests ← (auto) ← green ← (pytest passes) ←───┘
```

- **writing_tests** (start): Write failing tests. Only `test_*` files can be created/edited.
- **red**: Transient — auto-advances to `fixing_tests`.
- **fixing_tests**: Write production code to make tests pass. All files editable.
- **green**: Transient — auto-advances back to `writing_tests`.

Transitions are **automatic** — driven by pytest results, not manual declarations.

### Pytest detection

The governor detects pytest results through two mechanisms:

1. **PostToolUse hook**: Fires after successful Bash commands (`exit 0`). Parses tool output for pytest summary patterns (`FAILED`, `passed`, etc.) and triggers state transitions.
2. **Transcript scanning** (PreToolUse fallback): PostToolUse hooks don't fire for non-zero Bash exit codes, so pytest failures (`exit 1`) and collection errors (`exit 2`) are invisible to PostToolUse. The governor scans the Claude Code conversation transcript (JSONL) on every PreToolUse call, looking for unprocessed pytest results. A marker file prevents re-processing.

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

### Audit trail

Each governor evaluation is stored in a TinyDB document database at `$CTX_AUDIT_DIR/<session_id>.audit.json`. Documents include: timestamp, from/to state, trigger type, softness, action taken, tool name, and gate evaluation results.

Query the audit trail via `governor audit` — see Transition guards section above.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `CTX_MACHINE` | `machines.tdd.TDD` | Dotted path to the state machine class |
| `CTX_STATE_DIR` | `/tmp/ctx-state` | Directory for persisted state files |
| `CTX_AUDIT_DIR` | `$PWD/.claude/audit` | Directory for JSONL audit logs |
| `CTX_CONTEXT_DIR` | `$PWD/.claude` | Base directory for context file resolution |
| `CTX_PROJECT_HASH` | md5 of `$PWD` | Unique identifier for the project |


LintGate reads its rules path from `~/.claude/plugins/context-injector/config.json` (written by the installer). Project-local `scripts/lint/` takes priority if present.

## Context Injection (lightweight mode)

For projects that want context guidance without workflow enforcement. No state machine, no tool blocking — just keyword-matched file injection on every prompt.

### Commands

- **`/ctx`** — toggle on/off (state stored in `/tmp/ctx-locks/<hash>`)

### How it works

When on, every prompt receives:
1. All files from `.claude/core/` (always)
2. Matching files from `.claude/conditional/` based on keyword classification

### Keyword classification

| Keywords in prompt | Files injected from `.claude/conditional/` |
|---|---|
| implement, add, build, create, fix, feature, bug, write, emit, lower, migrate, introduce, wire, hook, support, handle, extend, port, close | design-principles, testing-patterns, refactoring, tools-skills |
| test, tdd, assert, coverage, xfail, failing, passes, red-green, fixture, integration test, unit test | testing-patterns |
| refactor, rename, extract, move, split, merge, simplify, clean, reorganize, restructure, consolidate, decompose, inline, deduplicate | design-principles, refactoring, tools-skills |
| review, pr, diff, check, feedback, critique, approve | code-review |
| verify, audit, scan, lint, sweep, validate, ensure, confirm, gate, black, lint-imports | testing-patterns, tools-skills |

### Project convention

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

## Using both modes

v1 and v2 use **separate lock files** and can be enabled independently:

| Mode | Command | Lock file |
|---|---|---|
| Context Injection | `/ctx on\|off` | `/tmp/ctx-locks/<hash>` |
| Governor | `/governor tdd\|off\|status` | `/tmp/ctx-governor/<hash>` |

When both are active, context injection adds keyword-matched files via `UserPromptSubmit`, while the governor enforces workflow state via `PreToolUse`, `PostToolUse`, `SessionStart`, and `PreCompact`.

## Requirements

- [Claude Code](https://claude.ai/code) with a project that has a `.claude/` directory
- `jq` (for the automated installers)
- Python 3 with `python-statemachine>=3.0.0` and `tinydb>=4.0.0` (governor only)
- [ast-grep](https://ast-grep.github.io/) (`sg`) — optional, for LintGate; gate passes silently if not installed

## Installation

### Governor

```bash
cd /path/to/your/project
/path/to/context-injector/install-governor.sh
```

Installs:
- Governor hooks (`governor-hook.sh`, `session-start.sh`, `post-tool-use.sh`, `pre-compact.sh`) → `~/.claude/plugins/context-injector/hooks/`
- Governor Python code and machine definitions → `~/.claude/plugins/context-injector/`
- `/governor` command → `~/.claude/commands/`
- Wires `SessionStart`, `PreToolUse`, `PostToolUse`, `PreCompact` hooks in `.claude/settings.json`
- Adds `/tmp/ctx-governor` Bash permissions

Uninstall: `/path/to/context-injector/uninstall-governor.sh`

### Context Injection

```bash
cd /path/to/your/project
/path/to/context-injector/install-ctx.sh
```

Installs:
- `user-prompt-submit.sh` hook → `~/.claude/plugins/context-injector/hooks/`
- `/ctx` command → `~/.claude/commands/`
- Wires `UserPromptSubmit` hook in `.claude/settings.json`
- Adds `/tmp/ctx-locks` Bash permissions

Uninstall: `/path/to/context-injector/uninstall-ctx.sh`

### Both

You can install both independently — they use separate lock files and don't conflict.

All scripts are idempotent — safe to run multiple times.

### Manual

#### Governor

**1. Copy hooks:**
```bash
mkdir -p ~/.claude/plugins/context-injector/hooks/lib
cp hooks/lib/hash.sh ~/.claude/plugins/context-injector/hooks/lib/
for f in governor-hook.sh session-start.sh post-tool-use.sh pre-compact.sh; do
  cp "hooks/$f" ~/.claude/plugins/context-injector/hooks/
  chmod +x ~/.claude/plugins/context-injector/hooks/"$f"
done
```

**2. Copy governor and machines:**
```bash
mkdir -p ~/.claude/plugins/context-injector/{governor,machines}
cp governor/*.py ~/.claude/plugins/context-injector/governor/
cp machines/*.py ~/.claude/plugins/context-injector/machines/
```

**3. Copy command:**
```bash
cp commands/governor.md ~/.claude/commands/governor.md
```

**4. Wire in `.claude/settings.json`:**
```json
"hooks": {
  "SessionStart": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/session-start.sh"}]}
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

**5. Add permissions:**
```json
"Bash(mkdir:/tmp/ctx-governor)",
"Bash(touch:/tmp/ctx-governor/*)",
"Bash(rm:/tmp/ctx-governor/*)"
```

#### Context Injection

**1. Copy the hook:**
```bash
mkdir -p ~/.claude/plugins/context-injector/hooks/lib
cp hooks/lib/hash.sh ~/.claude/plugins/context-injector/hooks/lib/
cp hooks/user-prompt-submit.sh ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
```

**2. Copy command:**
```bash
cp commands/ctx.md ~/.claude/commands/ctx.md
```

**3. Wire in `.claude/settings.json`:**
```json
"hooks": {
  "UserPromptSubmit": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"}]}
  ]
}
```

**4. Add permissions:**
```json
"Bash(mkdir:/tmp/ctx-locks)",
"Bash(touch:/tmp/ctx-locks/*)",
"Bash(rm:/tmp/ctx-locks/*)"
```

## License

[MIT](LICENSE.md)
