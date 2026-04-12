# State Machine-Governed Context Injection

## Problem

The current context-injector has three limitations:

1. **Wasteful core re-injection**: Core context (~2K tokens in a typical project) is injected on every `UserPromptSubmit`, even though it was already injected at `SessionStart` and likely hasn't drifted from attention.
2. **No injection during autonomous work**: When Claude is in a multi-step tool loop (editing files, running tests, reasoning), no hooks fire to reinforce project invariants. Context drift is most dangerous during these autonomous chains.
3. **Conditional context is prompt-only**: Keyword-based conditional injection only triggers on `UserPromptSubmit`. If Claude autonomously decides to refactor mid-task, `refactoring.md` is never injected.

## Solution

Replace the keyword-matching context injection system with a **hierarchical state machine (HSM)** that governs Claude's workflow and injects context based on the current state. A lightweight **governor** process evaluates every tool call, enforces state transitions, and decides what context to inject.

## Architecture

Five components:

```
  Claude Code
      |
      | (PreToolUse / SessionStart / PreCompact hooks)
      v
  Governor Process  <-->  State Machine (python-statemachine)
      |                        |
      | writes                 | reads definition from
      v                        v
  Audit Trail              State Machine Definitions
  (.claude/audit/)         (Python classes)
      
  State File
  (.claude/state/<hash>.json)
```

---

## Component 1: Hierarchical State Machine Definition

State machines are defined as Python classes using `python-statemachine` (v3.0.0+, MIT license). They are composable: inner machines nest inside outer machines via `State.Compound`.

### State Properties

Each state specifies:
- **context_files**: list of context file paths to inject when this state is active (relative to `.claude/`)
- **allowed_tools**: optional list of tool patterns permitted in this state (for enforcement)

### Transition Properties

Each transition specifies:
- **softness** (float, 0.0-1.0): controls governor response when this transition is taken
  - 0.7-1.0: allow silently, inject target state's context
  - 0.3-0.7: allow, inject reminder context ("you're deviating from the expected flow")
  - 0.0-0.3: challenge, inject corrective context, require Claude to justify before proceeding
- **trigger**: what causes the transition (declaration, tool pattern, tool result)
- **guard**: optional condition that must be true for the transition to fire

### Example: TDD Cycle Inside Feature Development

```python
from statemachine import StateMachine, State

class TDDCycle(StateMachine):
    """Inner loop: Red -> Green -> Refactor"""
    
    red = State(initial=True)
    green = State()
    refactor = State()
    docs_detour = State()  # deviation state for documentation fixes
    
    # Happy path transitions (high softness)
    test_written = red.to(green)       # softness: 1.0
    test_passes = green.to(refactor)   # softness: 1.0
    refactor_done = refactor.to(red)   # softness: 1.0
    
    # Less expected transitions (lower softness)
    test_was_wrong = green.to(red)     # softness: 0.5
    skip_refactor = green.to(red)      # softness: 0.4
    
    # Deviation transitions (low softness)
    need_docs = red.to(docs_detour)           # softness: 0.2
    need_docs_g = green.to(docs_detour)       # softness: 0.2
    docs_done = docs_detour.to(red)           # softness: 1.0 (return from deviation)

    # Transition metadata
    SOFTNESS = {
        "test_written": 1.0,
        "test_passes": 1.0,
        "refactor_done": 1.0,
        "test_was_wrong": 0.5,
        "skip_refactor": 0.4,
        "need_docs": 0.2,
        "need_docs_g": 0.2,
        "docs_done": 1.0,
    }
    
    CONTEXT = {
        "red": ["conditional/testing-patterns.md"],
        "green": ["core/*"],
        "refactor": ["conditional/refactoring.md"],
    }


class FeatureDevelopment(StateMachine):
    """Outer loop: Plan -> Implement -> Review -> Commit"""
    
    planning = State(initial=True)
    implementing = State()  # contains TDDCycle as sub-machine
    reviewing = State()
    committing = State(final=True)
    
    begin_impl = planning.to(implementing)     # softness: 1.0
    impl_complete = implementing.to(reviewing)  # softness: 1.0
    review_passed = reviewing.to(committing)    # softness: 1.0
    review_failed = reviewing.to(implementing)  # softness: 0.8
    
    CONTEXT = {
        "planning": ["core/*", "conditional/design-principles.md"],
        "implementing": [],  # delegated to TDDCycle sub-machine
        "reviewing": ["core/*", "conditional/code-review.md"],
        "committing": ["core/*"],
    }
```

### Composability

- State machines are Python classes, importable and composable
- An outer machine references an inner machine by instantiating it when entering a compound state
- The governor manages a stack of active machines (outer + inner)
- History states (via `python-statemachine`'s `HistoryState`) enable suspend/resume for deviations

### Deviations and the State Stack

When a deviation occurs (a low-softness transition), the current state is **suspended** (pushed onto a stack). The deviation runs in its own state or sub-machine. When it completes:

- **Normal return**: the stack pops and the original state resumes (history state restores position)
- **Abort (escape hatch)**: the deviation reveals the original plan was wrong; the suspended frame is discarded and the machine transitions to a new state at an appropriate level

The audit trail records both cases with full context.

---

## Component 2: The Governor

A lightweight process that runs on every `PreToolUse` hook invocation. Its job is narrow: classify what Claude is doing and enforce state transitions.

### Contract (Pluggable Backend)

The governor is defined as a **stdin/stdout JSON contract**. The hook script calls the governor process and reads its response.

**Input (stdin):**
```json
{
  "event": "pre_tool_use",
  "machine_state": {
    "outer": "feature-development.implementing",
    "inner": "tdd-cycle.red",
    "stack": []
  },
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/path/to/src/auth.py"
  },
  "declaration": null,
  "session_id": "abc123",
  "timestamp": "2026-04-12T12:34:56Z"
}
```

**Output (stdout):**
```json
{
  "current_state": "tdd-cycle.red",
  "transition": null,
  "softness": null,
  "action": "challenge",
  "context_to_inject": ["conditional/testing-patterns.md"],
  "message": "You are in the Red phase (writing a failing test). You are about to edit a source file (src/auth.py), not a test file. If you need to proceed, declare a phase transition first.",
  "audit_entry": {
    "from_state": "tdd-cycle.red",
    "to_state": null,
    "trigger": "tool_pattern_mismatch",
    "softness": null,
    "action_taken": "challenge",
    "tool_name": "Edit",
    "tool_target": "src/auth.py",
    "declaration": null,
    "stack_depth": 0,
    "user_prompt": false
  }
}
```

### Governor Responsibilities

The governor:
- Loads the persisted state from `.claude/state/<project-hash>.json`
- Loads the state machine definition (Python module)
- Evaluates the incoming event against the current state
- Determines if a transition should occur
- Applies graduated response based on softness
- Writes updated state back to the state file
- Emits audit entry and context injection instructions

The governor does NOT:
- Reason about code quality or architecture
- Make domain-specific decisions
- Understand file contents

It is a **classifier**: given the state graph, current position, and signals, it picks the edge (or enforces the current position).

### Default Implementation

The default governor is a Python script using `python-statemachine`:

```
~/.claude/plugins/context-injector/governor/governor.py
```

The pluggable contract means users can replace it with:
- A local LLM (via Ollama/llama.cpp) for smarter inference
- A pure heuristic engine (pattern matching, no LLM)
- A remote API call

### Graduated Response Bands

| Softness | Action | Governor Behavior |
|----------|--------|-------------------|
| 0.7-1.0 | allow | Transition silently, inject target state's context |
| 0.3-0.7 | remind | Allow transition, inject context + reminder message |
| 0.0-0.3 | challenge | Inject corrective context, require justification via DeclarePhase |

When no valid transition exists for the observed tool action, the governor holds the current state and may challenge or block depending on the state's `allowed_tools` configuration.

---

## Component 3: DeclarePhase Tool

A convention for Claude to explicitly announce state transitions, implemented as a **Bash echo command** that the `PreToolUse` hook intercepts.

Claude is instructed (via SessionStart context injection) to call a specific Bash command before transitioning:

```bash
Bash(echo '{"declare_phase": "green", "reason": "failing test for user auth confirmed"}')
```

The `PreToolUse` hook detects Bash calls matching the `echo '{"declare_phase"` pattern and routes them to the governor. This avoids requiring a custom MCP tool — it works entirely within the existing hook system.

### Behavior

1. Claude calls the DeclarePhase Bash command
2. The `PreToolUse` hook intercepts and recognizes the pattern
3. The governor validates the declaration against the state machine:
   - If the transition exists and softness is high: allow, transition, inject new context
   - If the transition exists but softness is low: allow with reminder/challenge
   - If the transition doesn't exist: block and inject corrective context
4. The audit trail records the declaration and outcome

### Injection of DeclarePhase Instructions

At `SessionStart`, the governor injects instructions telling Claude about the DeclarePhase convention (the Bash echo pattern) and the current state machine. This teaches Claude the expected workflow phases and when to declare transitions.

### Fallback: Tool Pattern Detection

When Claude forgets to declare (or doesn't know it should), the governor uses tool metadata as a secondary signal. For example:
- Claude is in `tdd-cycle.red` but calls `Edit` on a source file (not a test file) without declaring a transition
- The governor detects the mismatch and challenges

---

## Component 4: Audit Trail

Every governor evaluation produces an audit entry. These accumulate in session logs for analysis.

### Storage

- Location: `.claude/audit/` in the project directory
- Format: JSONL (one JSON object per line, per event)
- File naming: `<session-id>.jsonl`
- Gitignored by default (installer adds `.claude/audit/` to `.gitignore`)

### Audit Entry Schema

```json
{
  "timestamp": "2026-04-12T12:34:56Z",
  "session_id": "abc123",
  "machine": "tdd-cycle",
  "from_state": "red",
  "to_state": "green",
  "trigger": "declaration",
  "softness": 1.0,
  "action_taken": "allow",
  "tool_name": "Bash",
  "tool_input_summary": "pytest tests/test_auth.py",
  "declaration": "test confirmed failing",
  "stack_depth": 0,
  "user_prompt": false,
  "context_injected": ["conditional/testing-patterns.md"],
  "message": null
}
```

### Cross-Session Analysis

The structured audit data enables three categories of insight:

**1. Workflow Compliance**
- % of transitions at softness > 0.7 (happy path adherence)
- Frequency of challenges and blocks per state
- States where the governor intervenes most often

**2. State Machine Refinement**
- Transitions that consistently get aborted: candidates for removal
- Low-softness transitions that happen frequently: softness should be increased
- States where tool pattern mismatches are common: allowed_tools may need broadening

**3. Developer Behavior Patterns**
- Which user prompts trigger deviations from the state machine
- How often the developer overrides governor challenges
- Actual workflow shape vs. prescribed workflow
- Session duration per state (time-in-state analysis)

### Analysis Tooling

A CLI tool (future work) can aggregate JSONL files and produce reports:
```bash
ctx-audit summary                  # compliance metrics for recent sessions
ctx-audit refinement-signals       # suggested machine definition changes
ctx-audit developer-patterns       # behavioral analysis
```

---

## Component 5: Hook Integration

The governor integrates with Claude Code through these hooks:

### PreToolUse (Primary Hook)

Fires on every tool call. This is the governor's main evaluation point.

```json
{
  "hooks": [{
    "type": "command",
    "command": "~/.claude/plugins/context-injector/hooks/governor-hook.sh"
  }]
}
```

The hook script:
1. Checks if context injection is enabled (lockfile)
2. Reads tool metadata from stdin
3. Pipes it to the governor process
4. Reads governor response
5. Outputs `additionalContext` with injected context files and any governor messages

### SessionStart

Fires once at session start:
1. Initializes the state machine (creates state file if missing, sets initial state)
2. Injects initial state's context files
3. Injects DeclarePhase instructions and current state machine overview for Claude

### PreCompact

Fires before conversation compaction:
1. Always injects current state's context files (so they survive compression)
2. Injects a brief state summary ("You are in tdd-cycle.red, working on feature X")

### Relationship to Existing System

This design **replaces** the current keyword-matching system:
- `user-prompt-submit.sh` keyword classification is no longer needed; the state machine determines context
- `session-start.sh` is replaced by the new SessionStart hook that initializes the state machine
- `pre-tool-use.sh` (code-review-specific) is subsumed by the governor's per-tool-call evaluation
- The `/ctx` toggle and lockfile mechanism remain unchanged (on/off switch for the entire system)

---

## State Persistence

### State File

Location: `.claude/state/<project-hash>.json`

```json
{
  "outer_machine": "feature-development",
  "outer_state": "implementing",
  "inner_machine": "tdd-cycle",
  "inner_state": "red",
  "stack": [],
  "last_injected_state": "tdd-cycle.red",
  "last_injection_timestamp": "2026-04-12T12:34:56Z",
  "session_id": "abc123"
}
```

### Token Optimization

Context is only re-injected when the state actually changes. If the governor evaluates and determines "still in tdd-cycle.red, no transition," it checks `last_injected_state` and skips injection. This directly solves the original token waste problem.

---

## Project Layout (New Files)

```
context-injector/
  hooks/
    governor-hook.sh          # PreToolUse hook that calls the governor
    session-start-v2.sh       # SessionStart hook with state machine init
    pre-compact.sh            # PreCompact hook for compaction survival
  governor/
    governor.py               # Default governor implementation
    state_io.py               # State file read/write utilities
    audit.py                  # Audit trail writer
  machines/
    tdd_cycle.py              # Example: TDD inner loop machine
    feature_development.py    # Example: Feature development outer loop
  install.sh                  # Updated installer
```

---

## Dependencies

- Python 3.10+
- `python-statemachine` >= 3.0.0 (pip install)
- No other new dependencies (existing: md5, jq for installer)

---

## Verification Plan

1. **Unit tests**: Test state machine definitions (transitions, guards, softness lookup)
2. **Governor contract tests**: Feed known stdin JSON, assert expected stdout JSON
3. **Integration test**: Simulate a sequence of PreToolUse events through the hook and verify:
   - Correct state transitions
   - Correct context file injection
   - Audit trail entries written
   - Graduated response behavior at different softness levels
4. **End-to-end**: Enable the system in a real project, run a TDD session, verify:
   - State machine tracks phases correctly
   - Context files appear in Claude's responses
   - Deviations are caught and challenged
   - Audit log captures the full session
