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

The governor is a guardrail system for Claude Code. It enforces workflow discipline by controlling **what the agent can do** at each phase and requiring **proof of work** before allowing phase transitions.

### The TDD cycle

The built-in TDD machine enforces red-green-refactor with four phases:

```mermaid
flowchart TD
    WT["<b>writing_tests</b><br/>BLOCKED: Write, Edit<br/>EXCEPT test files"]
    FT["<b>fixing_tests</b><br/>all tools allowed"]
    RF["<b>refactoring</b><br/>all tools allowed"]
    FL["<b>fixing_lint</b><br/>all tools allowed"]

    WT -- pytest_fail_gate --> FT
    FT -- "free, no evidence" --> WT
    FT -- pytest_pass_gate --> RF
    RF -- pytest_pass_gate --> WT
    RF -- pytest_fail_gate --> FT
    RF -- lint_fail_gate --> FL
    FL -- lint_pass_gate --> RF
```

Each arrow is a **transition** that requires evidence. The agent must actually run pytest or the linter, and the governor verifies the captured output before allowing the move.

**Full transition map:**

| From | To | Required evidence | Gate |
|---|---|---|---|
| `writing_tests` | `fixing_tests` | `pytest_output` | `pytest_fail_gate` |
| `fixing_tests` | `refactoring` | `pytest_output` | `pytest_pass_gate` |
| `fixing_tests` | `writing_tests` | *(none)* | *(free)* |
| `refactoring` | `writing_tests` | `pytest_output` | `pytest_pass_gate` |
| `refactoring` | `fixing_tests` | `pytest_output` | `pytest_fail_gate` |
| `refactoring` | `fixing_lint` | `lint_output` | `lint_fail_gate` |
| `fixing_lint` | `refactoring` | `lint_output` | `lint_pass_gate` |

### How tool blocking works

Think of the governor as a traffic cop sitting between Claude and its tools:

```mermaid
flowchart TD
    A["You: 'Add a login feature using TDD'"] --> B

    subgraph B["Governor: phase = writing_tests"]
        B1["✅ Write('test_login.py') — test file, allowed"]
        B2["🚫 Write('auth.py') — production file, BLOCKED"]
        B3["✅ Read('auth.py') — reading is always fine"]
        B4["✅ Bash('pytest') — captured as evidence"]
    end

    B --> C["Tests fail — evidence captured<br/>Agent requests transition<br/>Governor checks evidence"]
    C --> D

    subgraph D["Governor: phase = fixing_tests"]
        D1["✅ Write('auth.py') — now allowed"]
        D2["✅ Write('test_login.py') — still allowed"]
    end
```

### How transitions work

Unlike traditional state machines where transitions fire on events, the governor requires proof:

```mermaid
flowchart TD
    A["1. Agent does the work<br/>Bash('pytest tests/ -v')"] --> B["2. Governor captures output<br/>PostToolUse hook stores result<br/>as evidence (evt_abc123)"]
    B --> C["3. Agent requests transition<br/>/governor transition fixing_tests evt_abc123"]
    C --> D{"4. Governor validates<br/>Is evt_abc123 of type pytest_output?"}
    D -- Yes --> E["Transition allowed ✅"]
    D -- No --> F["Transition denied 🚫"]
```

Gates currently use **trust mode**: they verify the evidence key exists in the tamper-proof locker and its type matches what the transition requires (e.g., `pytest_output` for a pytest gate). Since the evidence locker can only be written to by the PostToolUse hook — not by the agent directly — this provides a chain of proof: the agent actually ran the tool, the output was captured, and the evidence type matches the transition contract.

### Commands

| Command | Effect |
|---|---|
| `/governor tdd` | Enable with the TDD state machine |
| `/governor off` | Disable |
| `/governor status` | Show current phase, blocked tools, and available transitions |
| `/governor transition <target> <evidence_key>` | Request transition to a target state with evidence |
| `/governor evidence` | List all captured evidence entries |

### Tool blocking

Each phase defines which tools are blocked, with glob exceptions:

| Phase | Blocked | Exceptions |
|---|---|---|
| `writing_tests` | `Write`, `Edit` | `Write(test_*)`, `Edit(test_*)` |
| `fixing_tests` | *(none)* | -- |
| `refactoring` | *(none)* | -- |
| `fixing_lint` | *(none)* | -- |

Non-destructive tools (`Read`, `Grep`, `Glob`, `Agent`, `Bash`, etc.) are never blocked.

### Evidence capture

Each phase defines **capture rules** — glob patterns that match tool calls and store their output:

```json
"capture": [
    {"tool_pattern": "Bash(*pytest*)", "evidence_type": "pytest_output"},
    {"tool_pattern": "Bash(*ruff*)", "evidence_type": "lint_output"}
]
```

When a tool call matches a pattern, the PostToolUse (or PostToolUseFailure) hook stores the output in a tamper-proof evidence locker with a unique key (e.g., `evt_abc123`). The agent is told the key and which transitions it unlocks.

Evidence entries include the tool name, command, full output, exit code, and timestamp. Both successful and failed tool calls are captured.

### Evidence contracts and gates

Each transition can require specific evidence, validated by a gate:

```json
{"from": "writing_tests", "to": "fixing_tests",
 "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"}}
```

Built-in gates (trust mode -- verify evidence type matches):

| Gate | Required evidence type |
|---|---|
| `pytest_pass_gate` | `pytest_output` |
| `pytest_fail_gate` | `pytest_output` |
| `lint_pass_gate` | `lint_output` |
| `lint_fail_gate` | `lint_output` |

Transitions with `"evidence_contract": null` are free (no proof required).

### Defining custom machines

Machines are JSON files in `machines/`. Each node defines tool blocking rules and capture patterns; each edge defines which evidence is needed to traverse it:

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

### Architecture

The governor uses five Claude Code hook events. Each hook is a shell script that computes a session ID from `MD5($PWD)`, checks a lock file, and delegates to `python3 -m governor_v4`:

| Hook | When it fires | What it does |
|---|---|---|
| `SessionStart` | Session opens | Restores governor state, injects phase context |
| `UserPromptSubmit` | User sends a message | Parses `/governor` commands |
| `PreToolUse` | Before any tool call | Checks tool against phase blocklist -- allow or deny |
| `PostToolUse` | After a tool succeeds | Matches capture rules, stores evidence in locker |
| `PostToolUseFailure` | After a tool fails | Same as PostToolUse but captures error output and exit code |

State is persisted to `/tmp/ctx-governor/<session_id>/` as JSON files: engine state (`<session_id>.json`), activation record (`active`), and evidence locker (`<session_id>_evidence.json`).

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
