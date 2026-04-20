# Evidence-Based Transition Mechanism

## Problem

The current governor architecture (v2 and v3) forces state transitions automatically when hooks detect events in tool output. The agent has no say — if pytest fails, the hook fires `pytest_fail` and the governor transitions. This removes agent agency: the agent can't choose to stay in a state, write more tests before moving on, or make nuanced workflow decisions.

## Solution

Invert the control model. The **agent** decides when to transition and provides evidence justifying the request. The **governor** validates the evidence against a contract and allows or denies. Evidence is captured from tool output into a tamper-proof locker that the agent cannot modify — it can only reference entries by key.

## Core Concepts

### Evidence Locker

A per-session key-value store of captured tool outputs.

- **Storage:** JSON file per session in the state directory (`{session_id}_evidence.json`)
- **Populated by:** PostToolUse hook, based on capture rules defined in the machine's node config
- **Immutable to the agent:** The agent receives keys via `additionalContext` but cannot write to or modify the locker
- **Key format:** `evt_` prefix + short hash (e.g., `evt_a3f9c1`)

Entry structure:
```json
{
  "evt_a3f9c1": {
    "type": "pytest_output",
    "tool_name": "Bash",
    "command": "pytest tests/test_auth.py",
    "output": "FAILED test_auth.py::test_login - AssertionError...",
    "exit_code": 1,
    "timestamp": "2026-04-21T00:15:00Z"
  }
}
```

### Capture Rules

Defined per node in the machine JSON. The PostToolUse hook checks the current node's capture rules and stores matching tool outputs.

```json
{
  "name": "writing_tests",
  "capture": [
    {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"}
  ]
}
```

`tool_pattern` uses the same `ToolName(arg_glob)` syntax as the existing exception patterns. The hook matches the tool name and command against the pattern using fnmatch.

### Edge Contracts

Each edge declares what evidence is required and which gate validates it. Edges are identified by `from` + `to` (no `trigger` field).

```json
{
  "from": "writing_tests",
  "to": "fixing_tests",
  "evidence_contract": {
    "required_type": "pytest_output",
    "gate": "pytest_fail_gate"
  }
}
```

Edges with `"evidence_contract": null` allow transition without evidence (agent's decision alone is sufficient).

### Gates

Gates are tied to edges, not states. A gate receives the evidence key(s) and a reference to the evidence locker. The gate fetches what it needs from the locker and applies its own validation logic.

```python
class PytestFailGate:
    def validate(self, evidence_keys: list[str], locker: EvidenceLocker) -> GateVerdict:
        # Gate fetches evidence from locker by key
        # Gate inspects the evidence and decides pass/fail
        # Gate owns all validation logic
```

The engine does not inspect evidence. It passes the key(s) and locker to the gate and returns the gate's verdict.

**Trust mode (initial implementation):** Gates check that the evidence key exists in the locker and the evidence type matches `required_type`. No deeper validation of output content. This is sufficient because the locker is tamper-proof — the agent can't fabricate entries.

**Verification mode (future):** Gates parse the actual tool output (e.g., check for `FAILED` in pytest output, check exit code). Added per-gate as needed.

### `want_to_transition()`

The engine's primary API for state transitions:

```python
def want_to_transition(self, target_state: str, evidence_key: str | None = None) -> dict:
```

Flow:
1. Find edge from `current_state` to `target_state` (error if no edge exists)
2. If edge has an evidence contract:
   a. Retrieve evidence from locker by key (error if key missing)
   b. Check evidence type matches `required_type` (deny if mismatch)
   c. Pass evidence key(s) and locker reference to the gate
   d. If gate returns FAIL, deny transition with gate's message
3. If edge has no evidence contract, allow transition
4. Transition to target state, persist, return result

### `/transition` Slash Command

Agent or human invokes: `/transition <target_state> <evidence_key>`

Examples:
- `/transition fixing_tests evt_a3f9c1`
- `/transition writing_tests` (no evidence needed for this edge)

Parsed by a `UserPromptSubmit` hook that calls `want_to_transition()` on the engine and returns the result.

## Hook Changes

### PostToolUse Hook (revised)

Old behavior: detect event from tool output, force transition.

New behavior:
1. Get current node's capture rules from the engine
2. Match tool name + argument against capture rule patterns
3. If match: store tool output in evidence locker, inject key to agent via `additionalContext`
4. No transition. No event detection. No pass/fail determination.

The hook injects a message like:
> Evidence captured: `evt_a3f9c1` (pytest_output)

### UserPromptSubmit Hook (new)

Parses `/transition` commands from agent or human input. Calls `want_to_transition()`. Returns result to the conversation:
- Success: "Transitioned from writing_tests to fixing_tests"
- Denied: "Transition denied: [gate message]"
- Error: "No edge from writing_tests to refactoring"

## Machine Definition Format

```json
{
  "name": "tdd",
  "description": "Test-Driven Development cycle (Red-Green-Refactor)",
  "nodes": [
    {
      "name": "writing_tests",
      "initial": true,
      "blocked_tools": ["Write", "Edit"],
      "allowed_exceptions": ["Write(test_*)", "Edit(test_*)"],
      "capture": [
        {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"}
      ]
    },
    {
      "name": "fixing_tests",
      "blocked_tools": [],
      "capture": [
        {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"},
        {"tool_pattern": "Bash(ruff*)", "evidence_type": "lint_output"}
      ]
    },
    {
      "name": "refactoring",
      "blocked_tools": [],
      "capture": [
        {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"},
        {"tool_pattern": "Bash(ruff*)", "evidence_type": "lint_output"}
      ]
    },
    {
      "name": "fixing_lint",
      "blocked_tools": [],
      "capture": [
        {"tool_pattern": "Bash(ruff*)", "evidence_type": "lint_output"}
      ]
    }
  ],
  "edges": [
    {"from": "writing_tests", "to": "fixing_tests", "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"}},
    {"from": "fixing_tests", "to": "refactoring", "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_pass_gate"}},
    {"from": "fixing_tests", "to": "writing_tests", "evidence_contract": null},
    {"from": "refactoring", "to": "writing_tests", "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_pass_gate"}},
    {"from": "refactoring", "to": "fixing_tests", "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"}},
    {"from": "refactoring", "to": "fixing_lint", "evidence_contract": {"required_type": "lint_output", "gate": "lint_fail_gate"}},
    {"from": "fixing_lint", "to": "refactoring", "evidence_contract": {"required_type": "lint_output", "gate": "lint_pass_gate"}}
  ]
}
```

## What Gets Removed

The entire `governor_v3/` package is deleted. It was built around auto-advance, trigger-based transitions, and on_exit/on_enter gates — all of which are replaced by the evidence-based model. Specific v3 concepts that do not carry over:

- `trigger` field on edges (replaced by `from`/`to` + evidence contract)
- `auto_transition` on nodes (no transient states)
- `on_exit` / `on_enter` gate configuration (gates live on edges)
- `GateConfig` as a top-level machine concept
- Event detection logic in PostToolUse hook (replaced by evidence capture)
- `_auto_advance()`, `_run_exit_gates()`, `_run_enter_gates()` engine methods

Tool blocking (`evaluate()`, `check_tool_allowed()`, fnmatch exceptions) is reimplemented in the new package — the logic is simple and worth keeping.

## New Package Structure

Built from scratch as `governor_v4/` (replaces `governor_v3/`):

- `governor_v4/__init__.py` — package exports
- `governor_v4/config.py` — dataclasses: NodeConfig (with capture rules), EdgeConfig (with evidence_contract), MachineConfig
- `governor_v4/locker.py` — EvidenceLocker class (store, retrieve, key generation)
- `governor_v4/engine.py` — GovernorV4: want_to_transition(), evaluate() (tool blocking, reused from v3)
- `governor_v4/gates.py` — gate base class + evidence gate implementations (PytestFailGate, PytestPassGate, LintFailGate, LintPassGate)
- `governor_v4/loader.py` — JSON machine loader with validation
- `machines/tdd_v4.json` — TDD machine definition

## Testing Strategy

- Unit tests for EvidenceLocker (store, retrieve, key generation, missing key)
- Unit tests for each gate (trust mode validation)
- Unit tests for engine (want_to_transition flow, edge lookup, contract validation, denial)
- Unit tests for loader (JSON parsing, validation)
- Integration tests for full TDD cycle (capture → store → transition → gate)
- Tool blocking tests (reused logic from v3)
