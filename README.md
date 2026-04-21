# context-injector

[![CI](https://github.com/avishek-sen-gupta/context-injector/actions/workflows/ci.yml/badge.svg)](https://github.com/avishek-sen-gupta/context-injector/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)

A collection of Claude Code hooks and tools for enforcing discipline during agentic development workflows.

**Tools:**

- **Pipefail Guard** — a PreToolUse hook that prepends `set -o pipefail;` to every Bash command, ensuring that exit codes of all Bash invocations are surfaced correctly (even when they are tailed, etc.)
- **Governor** (`/governor`) — an evidence-based state machine that enforces workflow phases, blocks disallowed tools, captures tool output as evidence, and validates transitions via gates
- **Context Injection** (`/ctx`) — keyword-based context injection that adds relevant guidance files to every prompt based on what you're working on
- **[Python FP Lint](https://github.com/avishek-sen-gupta/python-fp-lint)** (`/lint`) — a functional-programming linter for Python that detects mutation, reassignment, and impurity patterns using ast-grep, Ruff, and beniget backends
- **Beads Terminology Guard** — a PreToolUse hook that blocks Beads issue-tracker commands containing sensitive terminology
- **Git Terminology Guard** — a git pre-commit hook that prevents forbidden terms from entering source history
- **History Scanner** (`scan-history`) — scans full git history (file contents + commit messages) for forbidden terms and prints a formatted report

All tools are independent and can be installed/enabled simultaneously.

## Governor

The governor wraps Claude Code in an evidence-based state machine. Every tool call is evaluated against the current workflow phase. Tools that violate the phase are blocked. The agent decides when to transition and provides evidence — the governor validates that evidence via gates before allowing the transition.

### Commands

| Command | Effect |
|---|---|
| `/governor tdd` | Enable with the TDD state machine |
| `/governor off` | Disable |
| `/governor status` | Show current phase, blocked tools, and available transitions |
| `/governor transition <target> [evidence_key]` | Request transition to a target state with evidence |
| `/governor evidence` | List all captured evidence entries |

### How it works

The governor uses four Claude Code hook events. Each hook is a thin shell script that computes a session ID from `MD5($PWD)`, checks a lock file, and delegates to `python3 -m governor_v4`.

```
                         Claude Code
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                     │
  SessionStart        UserPromptSubmit        Tool Call
        │                    │               ┌─────┴─────┐
        ▼                    ▼               ▼           ▼
  session-start.sh   user-prompt-submit.sh  pre-tool-use.sh  post-tool-use.sh
        │                    │               │           │
        ▼                    ▼               ▼           ▼
   governor_v4          governor_v4      governor_v4  governor_v4
     cmd_init            cmd_prompt      cmd_evaluate cmd_capture
        │                    │               │           │
        ▼                    ▼               ▼           ▼
  Load engine,       Parse /governor     Check tool   Match capture
  inject phase       commands, toggle    against      rules, store
  context            activation          blocklist    evidence
        │                    │               │           │
        ▼                    ▼               ▼           ▼
  additionalContext   additionalContext   allow/deny  additionalContext
  (phase + rules)    (status message)    decision    (evidence key)
```

#### Dataflow per hook

**1. SessionStart** — restores governor state on session open

```
Claude Code starts session
  → session-start.sh
    → MD5($PWD) → session_id
    → check /tmp/ctx-governor/<session>/active exists, else exit 0
    → python3 -m governor_v4 init --session <session_id>
      → load engine from /tmp/ctx-governor/<session>/<session>.json
      → read current phase + blocked tools from machine config
      → stdout: {"hookSpecificOutput": {"hookEventName": "SessionStart",
          "additionalContext": "Governor active: phase=writing_tests. Write, Edit blocked..."}}
  → Claude sees phase context in conversation
```

**2. UserPromptSubmit** — parses `/governor` commands

```
User types "/governor tdd"
  → user-prompt-submit.sh
    → grep stdin for "/governor" or expanded command prefix, else exit 0
    → python3 -m governor_v4 prompt --session <session_id> < stdin
      → extract command from prompt (raw "/governor tdd" or expanded form)
      → /governor <machine>: load JSON, create lock file + state, return activation message
      → /governor off: remove lock file + state dir
      → /governor status: load engine, describe phase + blocked tools + transitions
      → /governor transition <target> [key]: validate edge + evidence + gate, transition or deny
      → /governor evidence: list all entries in evidence locker
      → stdout: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
          "additionalContext": "Governor activated: machine=tdd, phase=writing_tests..."}}
  → Claude sees command result in conversation
```

**3. PreToolUse** — evaluates every tool call against current phase

```
Claude wants to call Write("main.py")
  → pre-tool-use.sh
    → check lock file exists, else exit 0
    → python3 -m governor_v4 evaluate --session <session_id> < stdin
      → stdin: {"tool_name": "Write", "tool_input": {"file_path": "main.py"}}
      → load engine, get current node's blocked_tools + allowed_exceptions
      → check_tool_allowed("Write", "main.py", blocked=["Write","Edit"],
          exceptions=["Write(test_*)","Edit(test_*)"])
      → "main.py" doesn't match "test_*" → BLOCKED
      → stdout: {"decision": "block", "reason": "...",
          "hookSpecificOutput": {"hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Write is blocked in writing_tests"}}
  → Claude Code blocks the tool call, shows reason to agent

Claude wants to call Write("test_auth.py")
  → same flow, but "test_auth.py" matches "test_*" → ALLOWED
  → no stdout (exit 0) → Claude Code allows the tool call
```

**4. PostToolUse** — captures tool output as evidence

```
Claude runs Bash("python3 -m pytest tests/ -v") and it completes
  → post-tool-use.sh
    → check lock file exists, else exit 0
    → python3 -m governor_v4 capture --session <session_id> < stdin
      → stdin: {"tool_name": "Bash", "tool_input": {"command": "python3 -m pytest ..."},
          "tool_response": {"stdout": "FAILED 2 passed, 1 failed", "stderr": ""}}
      → load engine, get current node's capture rules
      → match_capture_rule("Bash", "python3 -m pytest ...", "Bash(*pytest*)")
        → fnmatch "python3 -m pytest ..." against "*pytest*" → MATCH
      → store in evidence locker: {type: "pytest_output", tool_name: "Bash",
          command: "...", output: "...", exit_code: 1}
      → stdout: {"hookSpecificOutput": {"hookEventName": "PostToolUse",
          "additionalContext": "Evidence captured: evt_abc123 (type=pytest_output).
            Use '/governor transition <target> evt_abc123' to request a state transition."}}
  → Claude sees evidence key, can use it for transition
```

#### State persistence

All state lives under `/tmp/ctx-governor/<session_id>/`:

```
/tmp/ctx-governor/
  d41d8cd9.../              ← MD5 of project directory
    active                  ← lock file (contains {"machine": "/path/to/tdd.json"})
    d41d8cd9....json        ← engine state (contains {"current_phase": "writing_tests"})
    d41d8cd9..._evidence.json  ← evidence locker (TinyDB)
```

Each hook invocation loads the engine from these files, performs its action, and saves updated state. The lock file doubles as the activation check — all hooks exit immediately if it doesn't exist.

### Evidence-based transitions

Unlike traditional state machines where transitions fire automatically on events, the governor requires the agent to:

1. **Do the work** — run pytest, run linters, etc.
2. **Evidence is captured** — the PostToolUse hook stores matching tool output in an evidence locker
3. **Request a transition** — `/governor transition <target> <evidence_key>`
4. **Gate validates** — the edge's evidence contract specifies a gate that inspects the evidence and decides pass/fail

This means transitions are grounded in real tool output, not declarations.

### Tool blocking

The governor uses a **blocklist** approach — tools not listed are allowed. Each state defines which tools are blocked, with exceptions using `ToolName(glob_pattern)` syntax:

| State | Blocked | Exceptions |
|---|---|---|
| `writing_tests` | `Write`, `Edit` | `Write(test_*)`, `Edit(test_*)` |
| `fixing_tests` | *(none)* | — |
| `refactoring` | *(none)* | — |
| `fixing_lint` | *(none)* | — |

Non-destructive tools (`Read`, `Grep`, `Glob`, `Agent`, `Bash`, etc.) are always allowed.

### Evidence capture

Each node defines **capture rules** that match tool output and store it in the evidence locker:

```json
"capture": [
    {"tool_pattern": "Bash(*pytest*)", "evidence_type": "pytest_output"},
    {"tool_pattern": "Bash(*ruff*)", "evidence_type": "lint_output"}
]
```

When a tool call matches a capture rule, the PostToolUse hook stores the output with a unique key (e.g., `evt_abc123`) and injects a message telling the agent how to use it for a transition.

### Evidence contracts and gates

Each edge can define an **evidence contract** — what type of evidence is required and which gate validates it:

```json
{"from": "writing_tests", "to": "fixing_tests",
 "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"}}
```

Built-in gates:

| Gate | What it checks |
|---|---|
| `pytest_pass_gate` | Evidence contains pytest output with all tests passing (exit code 0) |
| `pytest_fail_gate` | Evidence contains pytest output with test failures (exit code non-zero) |
| `lint_pass_gate` | Evidence contains linter output with no violations (exit code 0) |
| `lint_fail_gate` | Evidence contains linter output with violations (exit code non-zero) |

Edges without an evidence contract allow free transitions (no evidence required).

### TDD cycle

The default TDD machine enforces a red-green-refactor loop:

```
writing_tests → (pytest fails) → fixing_tests
      ↑                              ↓
      ├── (pytest pass) ←── refactoring ← (pytest passes)
      │                          ↓
      └──────────────── fixing_lint ← (lint fails)
                            ↓
                     (lint passes) → refactoring
```

- **writing_tests** (start): Write failing tests. Only `test_*` files can be created/edited. Captures pytest output.
- **fixing_tests**: Write production code to make tests pass. All files editable. Captures pytest and lint output.
- **refactoring**: Clean up code with passing tests. All files editable. Captures pytest and lint output.
- **fixing_lint**: Fix lint violations. Captures lint output.

### Defining custom machines

Machines are JSON files placed in `machines/` and deployed to `~/.claude/plugins/guvnah/machines/`:

```json
{
    "name": "my-workflow",
    "description": "Custom workflow",
    "nodes": [
        {
            "name": "step_a",
            "initial": true,
            "blocked_tools": ["Write", "Edit"],
            "allowed_exceptions": ["Write(test_*)"],
            "capture": [
                {"tool_pattern": "Bash(*pytest*)", "evidence_type": "pytest_output"}
            ]
        },
        {"name": "step_b"}
    ],
    "edges": [
        {
            "from": "step_a", "to": "step_b",
            "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"}
        },
        {
            "from": "step_b", "to": "step_a",
            "evidence_contract": null
        }
    ]
}
```

### State persistence

Governor state is persisted to `/tmp/ctx-governor/<session_id>/` as JSON files. The evidence locker stores captured tool output alongside the state. State survives across hook invocations within a session.

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

## Using all three modes

All three modes use **separate lock files / hooks** and can be enabled independently:

| Tool | Command | Hook events |
|---|---|---|
| Context Injection | `/ctx on\|off` | `UserPromptSubmit` |
| Governor | `/governor tdd\|off\|status` | `SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit` |
| Pipefail Guard | `install-guvnah.sh` | `PreToolUse` (matcher: Bash) |
| Beads Terminology Guard | `install-bd-guard.sh` / `uninstall-bd-guard.sh` | `PreToolUse` |
| Git Terminology Guard | `install-terminology-guard.sh` / `uninstall-terminology-guard.sh` | git pre-commit hook |

When multiple modes are active they don't conflict — each operates on its own hook events and lock files.

## Requirements

- [Claude Code](https://claude.ai/code) with a project that has a `.claude/` directory
- Python 3.10+ (governor only — no external runtime dependencies)
- `jq` (for the automated installers)

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management during development.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (runtime + dev) into .venv/
uv sync --dev

# Run tests
uv run pytest tests/ -v
```

The development environment (`.venv/` managed by uv) is independent of the hook deployment. Contributors use `uv sync --dev` for local testing; end users run `hooks/guvnah/install.sh` to deploy.

## Installation

### Governor

```bash
cd /path/to/your/project
/path/to/context-injector/install-guvnah.sh
```

Installs:
- Governor hooks (`session-start.sh`, `pre-tool-use.sh`, `post-tool-use.sh`, `user-prompt-submit.sh`) → `.claude/hooks/guvnah/`
- Machine definitions (`tdd.json`, etc.) → `.claude/hooks/guvnah/machines/`
- Wires all four hook events in `.claude/settings.json`
- Adds `/tmp/ctx-governor` Bash permissions

Uninstall: `/path/to/context-injector/uninstall-guvnah.sh`

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

### Beads Terminology Guard

```bash
cd /path/to/your/project
/path/to/context-injector/install-bd-guard.sh
```

Installs:
- `bd-terminology-guard.sh` hook → `~/.claude/plugins/context-injector/hooks/`
- Wires `PreToolUse` hook in `.claude/settings.json`

Blocklist: `~/.config/git/blocklist.txt` (one term per line)

Uninstall: `/path/to/context-injector/uninstall-bd-guard.sh`

### Git Terminology Guard

Prevents forbidden terms from entering git history via a pre-commit hook. Uses the same blocklist as the Beads guard.

```bash
cd /path/to/your/project
/path/to/context-injector/install-terminology-guard.sh
```

Installs:
- `check-terminology`, `scan-history`, `lib-terminology.sh` → `~/.claude/plugins/context-injector/gates/terminology/`
- Wires `check-terminology` into `.git/hooks/pre-commit` of the current project (idempotent)

**Blocklist:** `~/.config/git/blocklist.txt` — one regex pattern per line (comments with `#` ignored)  
**Excludelist:** `~/.config/git/blocklist-exclude.txt` — glob patterns for files to skip (optional)

**Scanning history:**
```bash
~/.claude/plugins/context-injector/gates/terminology/scan-history
```

Scans the full git history (file contents + commit messages) for forbidden terms and prints a formatted report.

Uninstall: `/path/to/context-injector/uninstall-terminology-guard.sh`

### All three

You can install all three independently — they use separate lock files and hooks and don't conflict.

All scripts are idempotent — safe to run multiple times.

### Manual

#### Governor

**1. Copy hooks** (with PYTHONPATH pointing to context-injector repo):
```bash
REPO=/path/to/context-injector
mkdir -p .claude/hooks/guvnah
for f in session-start.sh pre-tool-use.sh post-tool-use.sh user-prompt-submit.sh; do
  { echo '#!/usr/bin/env bash'
    echo "GUVNAH_ROOT=\"$REPO\""
    echo 'export PYTHONPATH="$GUVNAH_ROOT${PYTHONPATH:+:$PYTHONPATH}"'
    echo 'export GUVNAH_MACHINES="$(cd "$(dirname "$0")" && pwd)/machines"'
    tail -n +2 "$REPO/hooks/guvnah/$f"
  } > ".claude/hooks/guvnah/$f"
  chmod +x ".claude/hooks/guvnah/$f"
done
```

**2. Copy machines:**
```bash
mkdir -p .claude/hooks/guvnah/machines
cp "$REPO"/machines/*.json .claude/hooks/guvnah/machines/
```

**3. Wire in `.claude/settings.json`:**
```json
"hooks": {
  "SessionStart": [
    {"hooks": [{"type": "command", "command": ".claude/hooks/guvnah/session-start.sh"}]}
  ],
  "PreToolUse": [
    {"hooks": [{"type": "command", "command": ".claude/hooks/guvnah/pre-tool-use.sh"}]}
  ],
  "PostToolUse": [
    {"hooks": [{"type": "command", "command": ".claude/hooks/guvnah/post-tool-use.sh"}]}
  ],
  "UserPromptSubmit": [
    {"hooks": [{"type": "command", "command": ".claude/hooks/guvnah/user-prompt-submit.sh"}]}
  ]
}
```

**4. Add permissions:**
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

#### Beads Terminology Guard

**1. Copy the hook:**
```bash
mkdir -p ~/.claude/plugins/context-injector/hooks
cp hooks/bd-terminology-guard.sh ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/bd-terminology-guard.sh
```

**2. Wire in `.claude/settings.json`:**
```json
"hooks": {
  "PreToolUse": [
    {"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/bd-terminology-guard.sh"}]}
  ]
}
```

**3. Create blocklist:**
```bash
mkdir -p ~/.config/git
echo "sensitive-term" >> ~/.config/git/blocklist.txt
```

## License

[MIT](LICENSE.md)
