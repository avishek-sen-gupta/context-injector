# State Machine-Governed Context Injection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace keyword-matching context injection with a hierarchical state machine that governs Claude's workflow, injects context based on current state, and produces an audit trail.

**Architecture:** A Python governor process (using `python-statemachine`) evaluates every tool call via Claude Code's `PreToolUse` hook. It loads persisted state, determines transitions based on tool metadata and DeclarePhase declarations, applies graduated response (allow/remind/challenge) based on transition softness, injects the right context files, and writes audit entries.

**Tech Stack:** Python 3.10+, python-statemachine >= 3.0.0, pytest, POSIX shell (hooks)

**Spec:** `docs/superpowers/specs/2026-04-12-state-machine-governed-context-injection-design.md`

---

## File Structure

```
context-injector/
  governor/                       # NEW — Python package
    __init__.py                   # Package init
    state_io.py                   # State file read/write utilities
    audit.py                      # Audit trail writer (JSONL)
    governor.py                   # Main governor logic (stdin/stdout contract)
  machines/                       # NEW — Example state machine definitions
    __init__.py                   # Package init
    base.py                       # GovernedMachine base class (SOFTNESS, CONTEXT, ALLOWED_TOOLS)
    tdd_cycle.py                  # TDD inner loop: Red → Green → Refactor
    feature_development.py        # Outer loop: Plan → Implement → Review → Commit
  hooks/
    governor-hook.sh              # NEW — PreToolUse hook calling governor.py
    session-start-v2.sh           # NEW — SessionStart hook with state machine init
    pre-compact.sh                # NEW — PreCompact hook for compaction survival
    user-prompt-submit.sh         # EXISTING — kept for backward compat (v1 mode)
    session-start.sh              # EXISTING — kept for backward compat (v1 mode)
    pre-tool-use.sh               # EXISTING — kept for backward compat (v1 mode)
  tests/                          # NEW — pytest test suite
    __init__.py
    conftest.py                   # Shared fixtures
    test_state_io.py              # State I/O tests
    test_audit.py                 # Audit writer tests
    test_base_machine.py          # GovernedMachine base class tests
    test_tdd_cycle.py             # TDD cycle machine tests
    test_governor.py              # Governor logic tests
    test_hooks_integration.py     # Shell hook integration tests
  install.sh                      # MODIFY — add v2 hook wiring
  pyproject.toml                  # NEW — Python project config + pytest
```

---

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `governor/__init__.py`
- Create: `machines/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Install python-statemachine**

Run: `pip3 install "python-statemachine>=3.0.0"`
Expected: Successfully installed python-statemachine-3.x.x

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "context-injector"
version = "2.0.0"
requires-python = ">=3.10"
dependencies = [
    "python-statemachine>=3.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create package init files**

Create `governor/__init__.py`:
```python
"""Governor process for state machine-governed context injection."""
```

Create `machines/__init__.py`:
```python
"""State machine definitions for workflow governance."""
```

Create `tests/__init__.py` (empty file):
```python
```

- [ ] **Step 4: Create test fixtures**

Create `tests/conftest.py`:
```python
import json
import os
import tempfile

import pytest


@pytest.fixture
def tmp_state_dir():
    """Temporary directory for state files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_audit_dir():
    """Temporary directory for audit JSONL files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_context_dir():
    """Temporary .claude directory with sample context files."""
    with tempfile.TemporaryDirectory() as d:
        core_dir = os.path.join(d, "core")
        cond_dir = os.path.join(d, "conditional")
        os.makedirs(core_dir)
        os.makedirs(cond_dir)

        with open(os.path.join(core_dir, "project-context.md"), "w") as f:
            f.write("# Project Context\nThis is a test project.\n")

        with open(os.path.join(cond_dir, "testing-patterns.md"), "w") as f:
            f.write("# Testing Patterns\nAlways write tests first.\n")

        with open(os.path.join(cond_dir, "refactoring.md"), "w") as f:
            f.write("# Refactoring\nKeep changes small.\n")

        with open(os.path.join(cond_dir, "code-review.md"), "w") as f:
            f.write("# Code Review\nCheck for correctness.\n")

        with open(os.path.join(cond_dir, "design-principles.md"), "w") as f:
            f.write("# Design Principles\nSingle responsibility.\n")

        yield d


@pytest.fixture
def sample_pre_tool_use_event():
    """A sample PreToolUse event as the hook would receive it."""
    return {
        "event": "pre_tool_use",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/project/tests/test_auth.py",
        },
        "session_id": "test-session-001",
        "timestamp": "2026-04-12T12:00:00Z",
    }


@pytest.fixture
def sample_declare_phase_event():
    """A DeclarePhase event (Bash echo intercepted by hook)."""
    return {
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {
            "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
        },
        "session_id": "test-session-001",
        "timestamp": "2026-04-12T12:01:00Z",
    }
```

- [ ] **Step 5: Verify setup**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/ -v`
Expected: `no tests ran` (0 collected, no errors)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml governor/ machines/ tests/
git commit -m "chore: scaffold project structure for state machine governor"
```

---

### Task 2: State I/O Module

**Files:**
- Create: `governor/state_io.py`
- Create: `tests/test_state_io.py`

- [ ] **Step 1: Write failing tests for state I/O**

Create `tests/test_state_io.py`:
```python
import json
import os

from governor.state_io import load_state, save_state, default_state


def test_default_state_has_required_fields():
    state = default_state(session_id="s1")
    assert state["outer_machine"] is None
    assert state["outer_state"] is None
    assert state["inner_machine"] is None
    assert state["inner_state"] is None
    assert state["stack"] == []
    assert state["last_injected_state"] is None
    assert state["last_injection_timestamp"] is None
    assert state["session_id"] == "s1"


def test_save_and_load_roundtrip(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "test-project.json")
    state = default_state(session_id="s1")
    state["inner_machine"] = "tdd-cycle"
    state["inner_state"] = "red"

    save_state(state_file, state)
    loaded = load_state(state_file)

    assert loaded["inner_machine"] == "tdd-cycle"
    assert loaded["inner_state"] == "red"
    assert loaded["session_id"] == "s1"


def test_load_returns_default_when_missing(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "nonexistent.json")
    loaded = load_state(state_file, session_id="s2")
    assert loaded["session_id"] == "s2"
    assert loaded["inner_state"] is None


def test_save_creates_parent_directories(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "nested", "deep", "state.json")
    state = default_state(session_id="s3")
    save_state(state_file, state)
    assert os.path.exists(state_file)


def test_save_overwrites_existing(tmp_state_dir):
    state_file = os.path.join(tmp_state_dir, "overwrite.json")
    save_state(state_file, default_state(session_id="s1"))
    save_state(state_file, default_state(session_id="s2"))
    loaded = load_state(state_file)
    assert loaded["session_id"] == "s2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_state_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'governor.state_io'`

- [ ] **Step 3: Implement state_io.py**

Create `governor/state_io.py`:
```python
"""Read and write governor state files.

State files are JSON documents stored at .claude/state/<project-hash>.json.
They track which state machine is active, the current state, the deviation
stack, and when context was last injected.
"""

import json
import os


def default_state(session_id: str = "") -> dict:
    """Return a blank state dict with all required fields."""
    return {
        "outer_machine": None,
        "outer_state": None,
        "inner_machine": None,
        "inner_state": None,
        "stack": [],
        "last_injected_state": None,
        "last_injection_timestamp": None,
        "session_id": session_id,
    }


def load_state(path: str, session_id: str = "") -> dict:
    """Load state from *path*. Return default_state if file is missing."""
    if not os.path.exists(path):
        return default_state(session_id=session_id)
    with open(path, "r") as f:
        return json.load(f)


def save_state(path: str, state: dict) -> None:
    """Write *state* to *path*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_state_io.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add governor/state_io.py tests/test_state_io.py
git commit -m "feat: add state I/O module for governor state persistence"
```

---

### Task 3: Audit Trail Module

**Files:**
- Create: `governor/audit.py`
- Create: `tests/test_audit.py`

- [ ] **Step 1: Write failing tests for audit writer**

Create `tests/test_audit.py`:
```python
import json
import os

from governor.audit import write_audit_entry, read_audit_log


def test_write_creates_file_and_appends(tmp_audit_dir):
    log_file = os.path.join(tmp_audit_dir, "session-1.jsonl")

    entry1 = {
        "timestamp": "2026-04-12T12:00:00Z",
        "session_id": "session-1",
        "machine": "tdd-cycle",
        "from_state": "red",
        "to_state": "green",
        "trigger": "declaration",
        "softness": 1.0,
        "action_taken": "allow",
        "tool_name": "Bash",
        "tool_input_summary": "pytest tests/",
        "declaration": "test failing",
        "stack_depth": 0,
        "user_prompt": False,
        "context_injected": ["conditional/testing-patterns.md"],
        "message": None,
    }
    entry2 = {**entry1, "from_state": "green", "to_state": "refactor"}

    write_audit_entry(log_file, entry1)
    write_audit_entry(log_file, entry2)

    entries = read_audit_log(log_file)
    assert len(entries) == 2
    assert entries[0]["from_state"] == "red"
    assert entries[1]["from_state"] == "green"


def test_write_creates_parent_directories(tmp_audit_dir):
    log_file = os.path.join(tmp_audit_dir, "nested", "session-2.jsonl")
    entry = {"timestamp": "2026-04-12T12:00:00Z", "session_id": "session-2"}
    write_audit_entry(log_file, entry)
    assert os.path.exists(log_file)


def test_read_returns_empty_for_missing_file(tmp_audit_dir):
    log_file = os.path.join(tmp_audit_dir, "nonexistent.jsonl")
    entries = read_audit_log(log_file)
    assert entries == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'governor.audit'`

- [ ] **Step 3: Implement audit.py**

Create `governor/audit.py`:
```python
"""Audit trail writer for governor evaluations.

Writes one JSON object per line (JSONL) to .claude/audit/<session-id>.jsonl.
"""

import json
import os


def write_audit_entry(path: str, entry: dict) -> None:
    """Append *entry* as a single JSON line to *path*."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit_log(path: str) -> list[dict]:
    """Read all entries from a JSONL audit log. Return [] if file missing."""
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_audit.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add governor/audit.py tests/test_audit.py
git commit -m "feat: add JSONL audit trail writer"
```

---

### Task 4: GovernedMachine Base Class

**Files:**
- Create: `machines/base.py`
- Create: `tests/test_base_machine.py`

- [ ] **Step 1: Write failing tests for base class**

Create `tests/test_base_machine.py`:
```python
from statemachine import State

from machines.base import GovernedMachine


class SimpleMachine(GovernedMachine):
    """Minimal machine for testing the base class."""

    alpha = State(initial=True)
    beta = State()

    go = alpha.to(beta)
    back = beta.to(alpha)

    SOFTNESS = {"go": 1.0, "back": 0.3}
    CONTEXT = {
        "alpha": ["core/*"],
        "beta": ["conditional/testing-patterns.md"],
    }
    ALLOWED_TOOLS = {
        "alpha": ["*"],
        "beta": ["Edit(test_*)", "Bash(pytest*)"],
    }


def test_get_softness_returns_value():
    sm = SimpleMachine()
    assert sm.get_softness("go") == 1.0
    assert sm.get_softness("back") == 0.3


def test_get_softness_defaults_to_one():
    sm = SimpleMachine()
    assert sm.get_softness("nonexistent") == 1.0


def test_get_context_for_state():
    sm = SimpleMachine()
    assert sm.get_context("alpha") == ["core/*"]
    assert sm.get_context("beta") == ["conditional/testing-patterns.md"]


def test_get_context_returns_empty_for_unknown():
    sm = SimpleMachine()
    assert sm.get_context("unknown") == []


def test_get_allowed_tools():
    sm = SimpleMachine()
    assert sm.get_allowed_tools("beta") == ["Edit(test_*)", "Bash(pytest*)"]


def test_get_allowed_tools_returns_none_when_unconstrained():
    sm = SimpleMachine()
    # alpha has ["*"] which means everything is allowed
    assert sm.get_allowed_tools("alpha") == ["*"]


def test_get_allowed_tools_returns_none_for_unknown():
    sm = SimpleMachine()
    assert sm.get_allowed_tools("unknown") is None


def test_current_state_name():
    sm = SimpleMachine()
    assert sm.current_state_name == "alpha"
    sm.go()
    assert sm.current_state_name == "beta"


def test_available_transition_names():
    sm = SimpleMachine()
    names = sm.available_transition_names
    assert "go" in names
    assert "back" not in names  # can't go back from alpha
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_base_machine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'machines.base'`

- [ ] **Step 3: Implement base.py**

Create `machines/base.py`:
```python
"""Base class for state machines governed by the context-injector governor.

Subclasses define SOFTNESS, CONTEXT, and ALLOWED_TOOLS as class-level dicts.
The governor uses these to decide what action to take and which context to inject.
"""

from statemachine import StateMachine


class GovernedMachine(StateMachine):
    """Base class adding softness, context, and allowed-tools metadata."""

    SOFTNESS: dict[str, float] = {}
    CONTEXT: dict[str, list[str]] = {}
    ALLOWED_TOOLS: dict[str, list[str]] = {}

    def get_softness(self, transition_name: str) -> float:
        """Return the softness value for a transition. Defaults to 1.0."""
        return self.SOFTNESS.get(transition_name, 1.0)

    def get_context(self, state_name: str) -> list[str]:
        """Return context file patterns for a state. Defaults to []."""
        return self.CONTEXT.get(state_name, [])

    def get_allowed_tools(self, state_name: str) -> list[str] | None:
        """Return allowed tool patterns for a state. None if unconstrained."""
        return self.ALLOWED_TOOLS.get(state_name)

    @property
    def current_state_name(self) -> str:
        """Return the name of the current state."""
        return self.current_state.id

    @property
    def available_transition_names(self) -> list[str]:
        """Return names of transitions available from the current state."""
        return [t.event for t in self.current_state.transitions if t.source == self.current_state]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_base_machine.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add machines/base.py tests/test_base_machine.py
git commit -m "feat: add GovernedMachine base class with softness/context/allowed_tools"
```

---

### Task 5: TDD Cycle State Machine

**Files:**
- Create: `machines/tdd_cycle.py`
- Create: `tests/test_tdd_cycle.py`

- [ ] **Step 1: Write failing tests for TDD cycle**

Create `tests/test_tdd_cycle.py`:
```python
import pytest
from statemachine.exceptions import TransitionNotAllowed

from machines.tdd_cycle import TDDCycle


def test_initial_state_is_red():
    sm = TDDCycle()
    assert sm.current_state_name == "red"


def test_happy_path_red_green_refactor():
    sm = TDDCycle()
    sm.test_written()
    assert sm.current_state_name == "green"
    sm.test_passes()
    assert sm.current_state_name == "refactor"
    sm.refactor_done()
    assert sm.current_state_name == "red"


def test_softness_happy_path_is_high():
    sm = TDDCycle()
    assert sm.get_softness("test_written") == 1.0
    assert sm.get_softness("test_passes") == 1.0
    assert sm.get_softness("refactor_done") == 1.0


def test_test_was_wrong_goes_back_to_red():
    sm = TDDCycle()
    sm.test_written()
    assert sm.current_state_name == "green"
    sm.test_was_wrong()
    assert sm.current_state_name == "red"


def test_test_was_wrong_softness_is_medium():
    sm = TDDCycle()
    assert sm.get_softness("test_was_wrong") == 0.5


def test_docs_detour_from_red():
    sm = TDDCycle()
    sm.need_docs()
    assert sm.current_state_name == "docs_detour"
    assert sm.get_softness("need_docs") == 0.2


def test_docs_detour_returns_to_red():
    sm = TDDCycle()
    sm.need_docs()
    sm.docs_done()
    assert sm.current_state_name == "red"


def test_cannot_refactor_from_red():
    sm = TDDCycle()
    with pytest.raises(TransitionNotAllowed):
        sm.refactor_done()


def test_context_for_states():
    sm = TDDCycle()
    assert sm.get_context("red") == ["conditional/testing-patterns.md"]
    assert sm.get_context("refactor") == ["conditional/refactoring.md"]


def test_allowed_tools_for_red():
    sm = TDDCycle()
    allowed = sm.get_allowed_tools("red")
    assert allowed is not None
    assert "Edit(test_*)" in allowed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_tdd_cycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'machines.tdd_cycle'`

- [ ] **Step 3: Implement tdd_cycle.py**

Create `machines/tdd_cycle.py`:
```python
"""TDD Cycle state machine: Red → Green → Refactor.

The inner loop of test-driven development. Each state specifies which context
files to inject and which tools are expected.
"""

from statemachine import State

from machines.base import GovernedMachine


class TDDCycle(GovernedMachine):
    """Red → Green → Refactor cycle with deviation support."""

    red = State(initial=True)
    green = State()
    refactor = State()
    docs_detour = State()

    # Happy path
    test_written = red.to(green)
    test_passes = green.to(refactor)
    refactor_done = refactor.to(red)

    # Less expected
    test_was_wrong = green.to(red)
    skip_refactor = green.to(red)

    # Deviations
    need_docs = red.to(docs_detour)
    need_docs_g = green.to(docs_detour)
    docs_done = docs_detour.to(red)

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
        "docs_detour": ["core/*"],
    }

    ALLOWED_TOOLS = {
        "red": ["Edit(test_*)", "Write(test_*)", "Bash(pytest*)"],
        "green": ["Edit", "Write", "Bash(pytest*)"],
        "refactor": ["Edit", "Write", "Bash(pytest*)"],
        "docs_detour": ["Edit(*.md)", "Write(*.md)"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_tdd_cycle.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add machines/tdd_cycle.py tests/test_tdd_cycle.py
git commit -m "feat: add TDD cycle state machine (Red/Green/Refactor)"
```

---

### Task 6: Feature Development State Machine

**Files:**
- Create: `machines/feature_development.py`
- Create: `tests/test_feature_development.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_feature_development.py`:
```python
import pytest
from statemachine.exceptions import TransitionNotAllowed

from machines.feature_development import FeatureDevelopment


def test_initial_state_is_planning():
    sm = FeatureDevelopment()
    assert sm.current_state_name == "planning"


def test_happy_path_plan_to_commit():
    sm = FeatureDevelopment()
    sm.begin_impl()
    assert sm.current_state_name == "implementing"
    sm.impl_complete()
    assert sm.current_state_name == "reviewing"
    sm.review_passed()
    assert sm.current_state_name == "committing"


def test_review_fail_returns_to_implementing():
    sm = FeatureDevelopment()
    sm.begin_impl()
    sm.impl_complete()
    sm.review_failed()
    assert sm.current_state_name == "implementing"


def test_review_failed_softness():
    sm = FeatureDevelopment()
    assert sm.get_softness("review_failed") == 0.8


def test_context_for_planning():
    sm = FeatureDevelopment()
    ctx = sm.get_context("planning")
    assert "core/*" in ctx
    assert "conditional/design-principles.md" in ctx


def test_context_for_reviewing():
    sm = FeatureDevelopment()
    ctx = sm.get_context("reviewing")
    assert "conditional/code-review.md" in ctx


def test_cannot_review_from_planning():
    sm = FeatureDevelopment()
    with pytest.raises(TransitionNotAllowed):
        sm.review_passed()


def test_sub_machine_reference():
    sm = FeatureDevelopment()
    assert sm.SUB_MACHINES.get("implementing") == "machines.tdd_cycle.TDDCycle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_feature_development.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement feature_development.py**

Create `machines/feature_development.py`:
```python
"""Feature Development state machine: Plan → Implement → Review → Commit.

The outer workflow loop. The 'implementing' state delegates to a TDD cycle
sub-machine managed by the governor.
"""

from statemachine import State

from machines.base import GovernedMachine


class FeatureDevelopment(GovernedMachine):
    """Outer feature development loop."""

    planning = State(initial=True)
    implementing = State()
    reviewing = State()
    committing = State(final=True)

    begin_impl = planning.to(implementing)
    impl_complete = implementing.to(reviewing)
    review_passed = reviewing.to(committing)
    review_failed = reviewing.to(implementing)

    SOFTNESS = {
        "begin_impl": 1.0,
        "impl_complete": 1.0,
        "review_passed": 1.0,
        "review_failed": 0.8,
    }

    CONTEXT = {
        "planning": ["core/*", "conditional/design-principles.md"],
        "implementing": [],
        "reviewing": ["core/*", "conditional/code-review.md"],
        "committing": ["core/*"],
    }

    # Maps state names to dotted-path sub-machine classes.
    # The governor instantiates these when entering the state.
    SUB_MACHINES = {
        "implementing": "machines.tdd_cycle.TDDCycle",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_feature_development.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add machines/feature_development.py tests/test_feature_development.py
git commit -m "feat: add Feature Development outer loop state machine"
```

---

### Task 7: Governor Core Logic

This is the central component. The governor reads a JSON event from stdin, evaluates it against the active state machine, and writes a JSON response to stdout.

**Files:**
- Create: `governor/governor.py`
- Create: `tests/test_governor.py`

- [ ] **Step 1: Write failing tests for governor — basic evaluation**

Create `tests/test_governor.py`:
```python
import json
import os

import pytest

from governor.governor import Governor
from machines.tdd_cycle import TDDCycle


@pytest.fixture
def governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=TDDCycle(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


class TestBasicEvaluation:
    def test_evaluate_returns_current_state(self, governor):
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["current_state"] == "red"
        assert result["action"] in ("allow", "remind", "challenge", "block")

    def test_no_transition_when_tool_matches_state(self, governor):
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["transition"] is None
        assert result["action"] == "allow"

    def test_challenge_when_tool_mismatches_state(self, governor):
        # In red state, editing a source file (not test) should challenge
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/src/auth.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert result["message"] is not None


class TestDeclarePhase:
    def test_declaration_triggers_transition(self, governor):
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["transition"] == "red -> green"
        assert result["action"] == "allow"
        assert result["current_state"] == "green"

    def test_invalid_declaration_is_challenged(self, governor):
        # Can't go to refactor from red
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "refactor", "reason": "skip ahead"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert result["transition"] is None


class TestGraduatedResponse:
    def test_high_softness_allows_silently(self, governor):
        # test_written is softness 1.0
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "allow"
        assert result["message"] is None

    def test_low_softness_challenges(self, governor):
        # need_docs is softness 0.2
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "docs_detour", "reason": "docs are wrong"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert result["message"] is not None


class TestContextInjection:
    def test_context_included_on_state_change(self, governor):
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert len(result["context_to_inject"]) > 0

    def test_context_skipped_when_state_unchanged(self, governor):
        # First call injects context
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        # Second call with same state skips injection
        result = governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_bar.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:01:00Z",
        })
        assert result["context_to_inject"] == []


class TestAuditTrail:
    def test_audit_entry_written(self, governor, tmp_audit_dir):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        audit_file = os.path.join(tmp_audit_dir, "test-session.jsonl")
        assert os.path.exists(audit_file)
        with open(audit_file) as f:
            entry = json.loads(f.readline())
        assert entry["machine"] == "TDDCycle"
        assert entry["from_state"] == "red"
        assert entry["tool_name"] == "Edit"


class TestStatePersistence:
    def test_state_persisted_after_transition(self, governor, tmp_state_dir):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        state_file = os.path.join(tmp_state_dir, "testhash.json")
        with open(state_file) as f:
            state = json.load(f)
        assert state["inner_state"] == "green"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_governor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'governor.governor'`

- [ ] **Step 3: Implement governor.py**

Create `governor/governor.py`:
```python
"""Governor process for state machine-governed context injection.

Evaluates tool events against the active state machine. Determines transitions,
applies graduated response based on softness, injects context, and writes audit.

Contract: reads JSON from stdin, writes JSON to stdout.
When used as a library, call Governor.evaluate(event_dict) directly.
"""

import fnmatch
import json
import os
import re
import sys
from datetime import datetime, timezone

from governor.audit import write_audit_entry
from governor.state_io import load_state, save_state


# Graduated response thresholds
SOFTNESS_ALLOW = 0.7
SOFTNESS_REMIND = 0.3


class Governor:
    """Evaluates tool events against a governed state machine."""

    def __init__(
        self,
        machine,
        state_dir: str,
        audit_dir: str,
        context_dir: str,
        project_hash: str,
        session_id: str,
    ):
        self.machine = machine
        self.state_dir = state_dir
        self.audit_dir = audit_dir
        self.context_dir = context_dir
        self.project_hash = project_hash
        self.session_id = session_id

        self._state_file = os.path.join(state_dir, f"{project_hash}.json")
        self._audit_file = os.path.join(audit_dir, f"{session_id}.jsonl")
        self._last_injected_state = None

        # Load persisted state and restore machine position
        persisted = load_state(self._state_file, session_id=session_id)
        saved_state = persisted.get("inner_state")
        if saved_state and saved_state != self.machine.current_state_name:
            self._restore_machine_state(saved_state)
        self._last_injected_state = persisted.get("last_injected_state")

    def _restore_machine_state(self, target_state: str) -> None:
        """Attempt to restore machine to a previously persisted state."""
        # Walk transitions to reach target state (simple BFS for small machines)
        # For now, use direct state setting if available
        for state in self.machine.states:
            if state.id == target_state:
                self.machine._current_state = state
                return

    def evaluate(self, event: dict) -> dict:
        """Evaluate a single event and return the governor response."""
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input", {})
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        from_state = self.machine.current_state_name

        # Check for DeclarePhase pattern
        declaration = self._extract_declaration(tool_name, tool_input)

        transition_name = None
        softness = None
        action = "allow"
        message = None
        context_to_inject = []

        if declaration:
            transition_name, softness, action, message = self._handle_declaration(
                declaration
            )
        else:
            action, message = self._check_tool_against_state(tool_name, tool_input)

        to_state = self.machine.current_state_name
        transitioned = from_state != to_state

        # Context injection: only when state changed or first evaluation
        if transitioned or self._last_injected_state is None:
            context_to_inject = self._resolve_context(to_state)
            self._last_injected_state = to_state
        elif self._last_injected_state != to_state:
            context_to_inject = self._resolve_context(to_state)
            self._last_injected_state = to_state

        # Persist state
        self._persist_state(to_state, timestamp)

        # Build audit entry
        audit_entry = {
            "timestamp": timestamp,
            "session_id": self.session_id,
            "machine": type(self.machine).__name__,
            "from_state": from_state,
            "to_state": to_state if transitioned else None,
            "trigger": "declaration" if declaration else "tool_use",
            "softness": softness,
            "action_taken": action,
            "tool_name": tool_name,
            "tool_input_summary": self._summarize_tool_input(tool_input),
            "declaration": declaration.get("reason") if declaration else None,
            "stack_depth": 0,
            "user_prompt": False,
            "context_injected": context_to_inject,
            "message": message,
        }
        write_audit_entry(self._audit_file, audit_entry)

        transition_str = None
        if transitioned:
            transition_str = f"{from_state} -> {to_state}"

        return {
            "current_state": to_state,
            "transition": transition_str,
            "softness": softness,
            "action": action,
            "context_to_inject": context_to_inject,
            "message": message,
            "audit_entry": audit_entry,
        }

    def _extract_declaration(self, tool_name: str, tool_input: dict) -> dict | None:
        """Extract a DeclarePhase declaration from a Bash echo command."""
        if tool_name != "Bash":
            return None
        command = tool_input.get("command", "")
        match = re.search(r"""echo\s+'(\{"declare_phase".*?\})'""", command)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    def _handle_declaration(self, declaration: dict) -> tuple:
        """Process a phase declaration. Returns (transition_name, softness, action, message)."""
        target_phase = declaration.get("declare_phase", "")

        # Find a transition from current state to the target phase
        for transition in self.machine.current_state.transitions:
            if transition.source != self.machine.current_state:
                continue
            if transition.target.id == target_phase:
                transition_name = transition.event
                softness = self.machine.get_softness(transition_name)
                action, message = self._graduated_response(softness, transition_name, target_phase)

                # Execute the transition if allowed
                if action in ("allow", "remind"):
                    send = getattr(self.machine, transition_name)
                    send()

                return transition_name, softness, action, message

        # No valid transition found
        return (
            None,
            None,
            "challenge",
            f"No valid transition from '{self.machine.current_state_name}' to '{target_phase}'. "
            f"Available transitions: {', '.join(self.machine.available_transition_names)}.",
        )

    def _graduated_response(
        self, softness: float, transition_name: str, target_phase: str
    ) -> tuple[str, str | None]:
        """Apply graduated response bands based on softness."""
        if softness >= SOFTNESS_ALLOW:
            return "allow", None
        elif softness >= SOFTNESS_REMIND:
            return (
                "remind",
                f"Deviation: transitioning to '{target_phase}' via '{transition_name}' "
                f"(softness {softness}). This is outside the expected flow.",
            )
        else:
            return (
                "challenge",
                f"Low-confidence transition to '{target_phase}' via '{transition_name}' "
                f"(softness {softness}). Justify this deviation or return to the expected flow.",
            )

    def _check_tool_against_state(
        self, tool_name: str, tool_input: dict
    ) -> tuple[str, str | None]:
        """Check if a tool use is allowed in the current state."""
        allowed = self.machine.get_allowed_tools(self.machine.current_state_name)
        if allowed is None or allowed == ["*"]:
            return "allow", None

        file_path = tool_input.get("file_path", tool_input.get("command", ""))
        tool_with_target = f"{tool_name}({os.path.basename(file_path)})"

        for pattern in allowed:
            if fnmatch.fnmatch(tool_with_target, pattern):
                return "allow", None
            if fnmatch.fnmatch(tool_name, pattern.split("(")[0] if "(" in pattern else pattern):
                # Tool name matches but target might not — check target pattern
                if "(" in pattern:
                    inner = pattern.split("(", 1)[1].rstrip(")")
                    if fnmatch.fnmatch(os.path.basename(file_path), inner):
                        return "allow", None
                else:
                    return "allow", None

        return (
            "challenge",
            f"Tool '{tool_name}' targeting '{os.path.basename(file_path)}' is not in the "
            f"allowed list for state '{self.machine.current_state_name}': {allowed}. "
            f"Declare a phase transition if you need to do this.",
        )

    def _resolve_context(self, state_name: str) -> list[str]:
        """Resolve context file patterns to actual file paths."""
        patterns = self.machine.get_context(state_name)
        resolved = []
        for pattern in patterns:
            full_pattern = os.path.join(self.context_dir, pattern)
            if "*" in pattern:
                import glob
                resolved.extend(sorted(glob.glob(full_pattern)))
            else:
                full_path = os.path.join(self.context_dir, pattern)
                if os.path.exists(full_path):
                    resolved.append(full_path)
        return resolved

    def _persist_state(self, current_state: str, timestamp: str) -> None:
        """Write the current state to the state file."""
        state = {
            "outer_machine": None,
            "outer_state": None,
            "inner_machine": type(self.machine).__name__,
            "inner_state": current_state,
            "stack": [],
            "last_injected_state": self._last_injected_state,
            "last_injection_timestamp": timestamp,
            "session_id": self.session_id,
        }
        save_state(self._state_file, state)

    def _summarize_tool_input(self, tool_input: dict) -> str:
        """Create a short summary of tool input for the audit log."""
        if "file_path" in tool_input:
            return tool_input["file_path"]
        if "command" in tool_input:
            cmd = tool_input["command"]
            return cmd[:100] + "..." if len(cmd) > 100 else cmd
        return json.dumps(tool_input)[:100]


def main():
    """CLI entry point: read JSON from stdin, write response to stdout."""
    event = json.load(sys.stdin)

    state_dir = os.environ.get("CTX_STATE_DIR", "/tmp/ctx-state")
    audit_dir = os.environ.get("CTX_AUDIT_DIR", os.path.join(os.getcwd(), ".claude", "audit"))
    context_dir = os.environ.get("CTX_CONTEXT_DIR", os.path.join(os.getcwd(), ".claude"))
    project_hash = os.environ.get("CTX_PROJECT_HASH", "default")
    session_id = event.get("session_id", "unknown")
    machine_module = os.environ.get("CTX_MACHINE", "machines.tdd_cycle.TDDCycle")

    # Dynamic machine loading
    module_path, class_name = machine_module.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    machine_cls = getattr(mod, class_name)

    gov = Governor(
        machine=machine_cls(),
        state_dir=state_dir,
        audit_dir=audit_dir,
        context_dir=context_dir,
        project_hash=project_hash,
        session_id=session_id,
    )

    result = gov.evaluate(event)
    json.dump(result, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_governor.py -v`
Expected: 9 passed

If `_restore_machine_state` or `available_transition_names` need adjustment based on `python-statemachine` internals, fix iteratively until all 9 pass.

- [ ] **Step 5: Commit**

```bash
git add governor/governor.py tests/test_governor.py
git commit -m "feat: add governor core logic with graduated response and audit"
```

---

### Task 8: Governor Hook Script (PreToolUse)

**Files:**
- Create: `hooks/governor-hook.sh`

- [ ] **Step 1: Write the hook script**

Create `hooks/governor-hook.sh`:
```bash
#!/bin/sh
# governor-hook.sh — State Machine Governor PreToolUse hook.
# Pipes tool event JSON to the Python governor process.
# Outputs additionalContext based on governor response.
# Exit 0 always — errors are silent no-ops.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
GOVERNOR="$HOME/.claude/plugins/context-injector/governor/governor.py"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Governor not installed — fall back silently
[ -f "$GOVERNOR" ] || exit 0

# Read stdin (tool event JSON from Claude Code)
INPUT=$(cat)

# Set environment for governor
export CTX_STATE_DIR="/tmp/ctx-state"
export CTX_AUDIT_DIR="$PWD/.claude/audit"
export CTX_CONTEXT_DIR="$PWD/.claude"
export CTX_PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
export CTX_MACHINE="${CTX_MACHINE:-machines.tdd_cycle.TDDCycle}"

# Run governor
RESPONSE=$(printf '%s' "$INPUT" | python3 "$GOVERNOR" 2>/dev/null)

# If governor failed, exit silently
[ -z "$RESPONSE" ] && exit 0

# Extract action and message from response
ACTION=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('action',''))" 2>/dev/null)
MESSAGE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('message','') or '')" 2>/dev/null)
STATE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('current_state',''))" 2>/dev/null)

# Extract context files to inject
CONTEXT_FILES=$(printf '%s' "$RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for f in r.get('context_to_inject', []):
    print(f)
" 2>/dev/null)

# Output state indicator
echo "[governor: state=$STATE action=$ACTION]"
echo ""

# Output message if present (remind or challenge)
if [ -n "$MESSAGE" ]; then
    echo "<governor-message>"
    echo "$MESSAGE"
    echo "</governor-message>"
    echo ""
fi

# Inject context files
if [ -n "$CONTEXT_FILES" ]; then
    echo "$CONTEXT_FILES" | while read -r filepath; do
        [ -f "$filepath" ] && cat "$filepath"
    done
fi

exit 0
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x /Users/asgupta/code/context-injector/hooks/governor-hook.sh`

- [ ] **Step 3: Smoke test the hook manually**

Run:
```bash
cd /Users/asgupta/code/context-injector
export CTX_STATE_DIR="/tmp/ctx-state-test"
export CTX_AUDIT_DIR="/tmp/ctx-audit-test"
export CTX_CONTEXT_DIR="$PWD/.claude"
export CTX_PROJECT_HASH="manualtest"
export CTX_MACHINE="machines.tdd_cycle.TDDCycle"
mkdir -p /tmp/ctx-locks
touch "/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
echo '{"event":"pre_tool_use","tool_name":"Edit","tool_input":{"file_path":"tests/test_foo.py"},"session_id":"manual","timestamp":"2026-04-12T12:00:00Z"}' | python3 governor/governor.py
```

Expected: JSON output with `"current_state": "red"` and `"action": "allow"`

- [ ] **Step 4: Commit**

```bash
git add hooks/governor-hook.sh
git commit -m "feat: add governor PreToolUse hook script"
```

---

### Task 9: SessionStart Hook (v2)

**Files:**
- Create: `hooks/session-start-v2.sh`

- [ ] **Step 1: Write the session start hook**

Create `hooks/session-start-v2.sh`:
```bash
#!/bin/sh
# session-start-v2.sh — State Machine Governor SessionStart hook.
# Initializes state machine, injects initial context and DeclarePhase instructions.
# Exit 0 always.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"
STATE_DIR="/tmp/ctx-state"
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_FILE="$STATE_DIR/$PROJECT_HASH.json"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Initialize state directory
mkdir -p "$STATE_DIR"
mkdir -p "$PWD/.claude/audit"

# Reset state file for new session (fresh start)
rm -f "$STATE_FILE"

echo "[ctx: governor mode — state machine initialized]"
echo ""

# Inject core context
if [ -d "$CORE_DIR" ]; then
    for f in "$CORE_DIR"/*.md; do
        [ -f "$f" ] && cat "$f"
    done
    echo ""
fi

# Inject DeclarePhase instructions
cat << 'DECLARE_PHASE_EOF'
## State Machine Governance

You are operating under a state machine governor. The governor tracks your current
workflow phase and injects relevant context automatically.

### Declaring Phase Transitions

When you move to a new phase of work, announce it by running:

```bash
echo '{"declare_phase": "<phase_name>", "reason": "<why you are transitioning>"}'
```

The governor will validate your transition. If it's unexpected, you'll receive
guidance about the expected workflow.

### Current Workflow: TDD Cycle

The default workflow follows Red → Green → Refactor:

- **red**: Write a failing test. Declare `green` when the test is written and confirmed failing.
- **green**: Write minimal code to make the test pass. Declare `refactor` when tests pass.
- **refactor**: Improve the code without changing behavior. Declare `red` when ready for the next test.

### Important

- The governor runs on every tool call — you don't need to do anything special
- If you need to deviate (e.g., fix documentation), declare the deviation phase
- The governor will challenge low-confidence transitions but won't hard-block you
DECLARE_PHASE_EOF

exit 0
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x /Users/asgupta/code/context-injector/hooks/session-start-v2.sh`

- [ ] **Step 3: Commit**

```bash
git add hooks/session-start-v2.sh
git commit -m "feat: add v2 SessionStart hook with state machine init and DeclarePhase instructions"
```

---

### Task 10: PreCompact Hook

**Files:**
- Create: `hooks/pre-compact.sh`

- [ ] **Step 1: Write the pre-compact hook**

Create `hooks/pre-compact.sh`:
```bash
#!/bin/sh
# pre-compact.sh — State Machine Governor PreCompact hook.
# Injects current state context before conversation compaction so invariants
# survive compression. Exit 0 always.

LOCK="/tmp/ctx-locks/$(printf '%s' "$PWD" | md5)"
CORE_DIR="$PWD/.claude/core"
STATE_DIR="/tmp/ctx-state"
PROJECT_HASH="$(printf '%s' "$PWD" | md5)"
STATE_FILE="$STATE_DIR/$PROJECT_HASH.json"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Read current state
if [ -f "$STATE_FILE" ]; then
    INNER_STATE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('inner_state','unknown'))" 2>/dev/null)
    MACHINE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('inner_machine','unknown'))" 2>/dev/null)
else
    INNER_STATE="unknown"
    MACHINE="unknown"
fi

echo "[ctx: pre-compaction context injection — state=$MACHINE.$INNER_STATE]"
echo ""

# Always inject core context before compaction
if [ -d "$CORE_DIR" ]; then
    for f in "$CORE_DIR"/*.md; do
        [ -f "$f" ] && cat "$f"
    done
    echo ""
fi

# Inject state summary
echo "## Current Governor State"
echo "You are in state: $MACHINE.$INNER_STATE"
echo "The conversation is being compacted. Your workflow state is preserved."
echo ""

exit 0
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x /Users/asgupta/code/context-injector/hooks/pre-compact.sh`

- [ ] **Step 3: Commit**

```bash
git add hooks/pre-compact.sh
git commit -m "feat: add PreCompact hook for compaction survival"
```

---

### Task 11: Update Installer

**Files:**
- Modify: `install.sh`

- [ ] **Step 1: Write failing integration test for installer**

Create `tests/test_hooks_integration.py`:
```python
import json
import os
import subprocess
import tempfile

import pytest


@pytest.fixture
def mock_project():
    """Create a temporary project directory with .claude structure."""
    with tempfile.TemporaryDirectory() as d:
        claude_dir = os.path.join(d, ".claude")
        os.makedirs(os.path.join(claude_dir, "core"))
        os.makedirs(os.path.join(claude_dir, "conditional"))
        with open(os.path.join(claude_dir, "core", "project.md"), "w") as f:
            f.write("# Test Project\n")
        with open(os.path.join(claude_dir, "conditional", "testing-patterns.md"), "w") as f:
            f.write("# Testing\n")
        yield d


def test_governor_cli_returns_json(mock_project):
    """Test that governor.py reads stdin JSON and writes stdout JSON."""
    event = {
        "event": "pre_tool_use",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/project/tests/test_foo.py"},
        "session_id": "integration-test",
        "timestamp": "2026-04-12T12:00:00Z",
    }

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", os.path.join(project_root, "governor", "governor.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    response = json.loads(result.stdout)
    assert response["current_state"] == "red"
    assert response["action"] in ("allow", "remind", "challenge", "block")


def test_governor_declaration_transition(mock_project):
    """Test that a DeclarePhase event triggers a state transition."""
    event = {
        "event": "pre_tool_use",
        "tool_name": "Bash",
        "tool_input": {
            "command": """echo '{"declare_phase": "green", "reason": "test confirmed failing"}'""",
        },
        "session_id": "integration-test-2",
        "timestamp": "2026-04-12T12:00:00Z",
    }

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = os.path.join(mock_project, ".ctx-state")
    env["CTX_AUDIT_DIR"] = os.path.join(mock_project, ".ctx-audit")
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "integration2"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        ["python3", os.path.join(project_root, "governor", "governor.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    response = json.loads(result.stdout)
    assert response["current_state"] == "green"
    assert response["transition"] == "red -> green"
```

- [ ] **Step 2: Run integration tests**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/test_hooks_integration.py -v`
Expected: 2 passed

- [ ] **Step 3: Update install.sh to wire v2 hooks**

Add the following to `install.sh` after the existing hook wiring sections (after line 76, before the permissions section):

Add these sections to install.sh:
- Copy governor Python files to `~/.claude/plugins/context-injector/governor/`
- Copy machine definitions to `~/.claude/plugins/context-injector/machines/`
- Wire `PreCompact` hook for `pre-compact.sh`
- Replace `SessionStart` hook entry with `session-start-v2.sh`
- Replace `PreToolUse` hook entry with `governor-hook.sh`
- Add `.claude/audit/` and `.claude/state/` to `.gitignore` if not already present
- Check for `python3` and `python-statemachine` dependency

The install.sh modifications:

After line 13 (`SETTINGS="$PROJECT_DIR/.claude/settings.json"`), add:
```bash
GOVERNOR_DIR="$HOME/.claude/plugins/context-injector/governor"
MACHINES_DIR="$HOME/.claude/plugins/context-injector/machines"
```

After the existing `echo "Installing hooks..."` block (after line 33), add:
```bash
echo "Installing governor..."
mkdir -p "$GOVERNOR_DIR"
cp "$PLUGIN_DIR/governor/__init__.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/state_io.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/audit.py" "$GOVERNOR_DIR/"
cp "$PLUGIN_DIR/governor/governor.py" "$GOVERNOR_DIR/"

echo "Installing machine definitions..."
mkdir -p "$MACHINES_DIR"
cp "$PLUGIN_DIR/machines/__init__.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/base.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/tdd_cycle.py" "$MACHINES_DIR/"
cp "$PLUGIN_DIR/machines/feature_development.py" "$MACHINES_DIR/"
```

Add the new hooks to the copy block:
```bash
cp "$PLUGIN_DIR/hooks/governor-hook.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/session-start-v2.sh" ~/.claude/plugins/context-injector/hooks/
cp "$PLUGIN_DIR/hooks/pre-compact.sh" ~/.claude/plugins/context-injector/hooks/
chmod +x ~/.claude/plugins/context-injector/hooks/governor-hook.sh
chmod +x ~/.claude/plugins/context-injector/hooks/session-start-v2.sh
chmod +x ~/.claude/plugins/context-injector/hooks/pre-compact.sh
```

Add PreCompact hook wiring (same pattern as existing hooks):
```bash
# --- wire PreCompact hook (idempotent) ---
ALREADY_WIRED=$(jq '[.hooks.PreCompact[]?.hooks[]?.command // ""] | any(contains("context-injector"))' "$SETTINGS")
if [ "$ALREADY_WIRED" = "false" ]; then
  echo "Wiring PreCompact hook..."
  HOOK_ENTRY='{"hooks": [{"type": "command", "command": "~/.claude/plugins/context-injector/hooks/pre-compact.sh"}]}'
  jq --argjson entry "$HOOK_ENTRY" \
    '.hooks.PreCompact = ((.hooks.PreCompact // []) + [$entry])' \
    "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
else
  echo "PreCompact hook already wired, skipping."
fi
```

Add gitignore management:
```bash
# --- add audit/state dirs to .gitignore ---
GITIGNORE="$PROJECT_DIR/.gitignore"
if [ -f "$GITIGNORE" ]; then
  grep -q '.claude/audit/' "$GITIGNORE" || echo '.claude/audit/' >> "$GITIGNORE"
  grep -q '.claude/state/' "$GITIGNORE" || echo '.claude/state/' >> "$GITIGNORE"
fi
```

Add Python dependency check at the top validation section:
```bash
if ! python3 -c "import statemachine" 2>/dev/null; then
  echo "Warning: python-statemachine not found. Install with: pip3 install python-statemachine>=3.0.0" >&2
fi
```

- [ ] **Step 4: Commit**

```bash
git add install.sh tests/test_hooks_integration.py
git commit -m "feat: update installer for v2 governor hooks and integration tests"
```

---

### Task 12: Full Integration Test

**Files:**
- Modify: `tests/test_hooks_integration.py`

- [ ] **Step 1: Add end-to-end sequence test**

Append to `tests/test_hooks_integration.py`:
```python
def test_full_tdd_cycle_sequence(mock_project):
    """Test a complete Red → Green → Refactor → Red cycle through the governor CLI."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_dir = os.path.join(mock_project, ".ctx-state")
    audit_dir = os.path.join(mock_project, ".ctx-audit")

    env = os.environ.copy()
    env["CTX_STATE_DIR"] = state_dir
    env["CTX_AUDIT_DIR"] = audit_dir
    env["CTX_CONTEXT_DIR"] = os.path.join(mock_project, ".claude")
    env["CTX_PROJECT_HASH"] = "e2e"
    env["CTX_MACHINE"] = "machines.tdd_cycle.TDDCycle"

    def run_event(event):
        result = subprocess.run(
            ["python3", os.path.join(project_root, "governor", "governor.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return json.loads(result.stdout)

    # 1. Start in red — edit a test file (allowed)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Edit",
        "tool_input": {"file_path": "/p/tests/test_x.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:00:00Z",
    })
    assert r["current_state"] == "red"
    assert r["action"] == "allow"

    # 2. Declare green
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "green", "reason": "test failing"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:01:00Z",
    })
    assert r["current_state"] == "green"
    assert r["transition"] == "red -> green"

    # 3. Edit source file in green (allowed)
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Edit",
        "tool_input": {"file_path": "/p/src/auth.py"},
        "session_id": "e2e", "timestamp": "2026-04-12T12:02:00Z",
    })
    assert r["current_state"] == "green"
    assert r["action"] == "allow"

    # 4. Declare refactor
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "refactor", "reason": "tests pass"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:03:00Z",
    })
    assert r["current_state"] == "refactor"

    # 5. Declare back to red
    r = run_event({
        "event": "pre_tool_use", "tool_name": "Bash",
        "tool_input": {"command": """echo '{"declare_phase": "red", "reason": "refactor done"}'"""},
        "session_id": "e2e", "timestamp": "2026-04-12T12:04:00Z",
    })
    assert r["current_state"] == "red"

    # 6. Verify audit trail
    audit_file = os.path.join(audit_dir, "e2e.jsonl")
    assert os.path.exists(audit_file)
    with open(audit_file) as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert len(entries) == 5
    assert entries[0]["from_state"] == "red"
    assert entries[1]["to_state"] == "green"
    assert entries[4]["to_state"] == "red"
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/ -v`
Expected: All tests pass (approximately 29 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_hooks_integration.py
git commit -m "test: add full TDD cycle end-to-end integration test"
```

---

### Task 13: Final Cleanup and README Update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with v2 documentation**

Add a new section to `README.md` after the existing content, documenting:
- The state machine governor mode (v2)
- How to define custom state machines (Python classes extending GovernedMachine)
- The DeclarePhase convention
- Audit trail location and format
- Environment variables for configuration (`CTX_MACHINE`, `CTX_STATE_DIR`, `CTX_AUDIT_DIR`)
- Migration from v1 (keyword matching) to v2 (state machine)
- Note that v1 hooks are preserved for backward compatibility

- [ ] **Step 2: Run full test suite one final time**

Run: `cd /Users/asgupta/code/context-injector && python3 -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add v2 state machine governor documentation to README"
```
