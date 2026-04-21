# context-injector

[![CI](https://github.com/avishek-sen-gupta/context-injector/actions/workflows/ci.yml/badge.svg)](https://github.com/avishek-sen-gupta/context-injector/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)

A Claude Code plugin that governs agent behavior during development workflows. It enforces discipline — blocking tools that shouldn't be used, requiring evidence before state transitions, and producing an audit trail of every decision.

Three modes, from lightweight to full enforcement:

1. **Governor** (`/governor`) — an evidence-based state machine that enforces workflow phases, blocks disallowed tools, captures tool output as evidence, and validates transitions via gates
2. **Context Injection** (`/ctx`) — keyword-based context injection without enforcement, for projects that want guidance without guardrails
3. **Beads Terminology Guard** — a PreToolUse hook that blocks Beads issue-tracker commands containing sensitive terminology

Plus a standalone **Git Terminology Guard** — a pre-commit hook that prevents forbidden terms from entering source history, plus a history scanner for auditing past commits.

All modes are independent and can be installed/enabled simultaneously.

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

1. **SessionStart** (`session-start.sh`) — restores governor state if a session is active
2. **PreToolUse** (`pre-tool-use.sh`) — evaluates every tool call against the current phase's rules; blocks disallowed tools
3. **PostToolUse** (`post-tool-use.sh`) — captures tool output as evidence when it matches a node's capture rules
4. **UserPromptSubmit** (`user-prompt-submit.sh`) — parses `/governor` commands from user prompts

All hooks are thin shell scripts that check `CLAUDE_SESSION_ID` and a lock file (`/tmp/ctx-governor/<session>/active`) before delegating to `python3 -m governor_v4`.

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

| Mode | Command | Hook events |
|---|---|---|
| Context Injection | `/ctx on\|off` | `UserPromptSubmit` |
| Governor | `/governor tdd\|off\|status` | `SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit` |
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
