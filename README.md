# context-injector

A Claude Code plugin that auto-injects core + classified conditional context into every prompt when enabled. Toggled on/off with the `/ctx` command.

## How it works

- **`/ctx`** — toggles context injection on or off for the current project. State is stored in `/tmp/ctx-locks/<md5-of-project-path>` (ephemeral, no project pollution).
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

## Installation

**1. Copy the hook:**
```bash
mkdir -p ~/.claude/plugins/context-injector/hooks
cp hooks/user-prompt-submit.sh ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
```

**2. Copy the `/ctx` command:**
```bash
cp commands/ctx.md ~/.claude/commands/ctx.md
```

**3. Wire the hook in your project's `.claude/settings.json`:**
```json
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"
      }
    ]
  }
]
```

**4. Add allow entries for the toggle commands:**
```json
"Bash(mkdir:/tmp/ctx-locks)",
"Bash(touch:/tmp/ctx-locks/*)",
"Bash(rm:/tmp/ctx-locks/*)"
```

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
