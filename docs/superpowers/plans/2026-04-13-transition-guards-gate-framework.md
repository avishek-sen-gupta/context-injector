# Transition Guards & Gate Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a gate framework to the governor that evaluates work quality at transition boundaries, with TestQualityGate as the first implementation, and replace the JSONL audit trail with TinyDB.

**Architecture:** Gates are transition guards — they run after preconditions pass but before the transition fires. Each gate returns PASS/FAIL/REVIEW. FAIL feeds into the graduated response system via per-gate softness. REVIEW injects a self-review prompt and the agent retries. TinyDB replaces JSONL for queryable audit history.

**Tech Stack:** Python 3.10+, python-statemachine>=3.0.0, tinydb>=4.0.0, pytest>=8.0

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `gates/__init__.py` | Package exports: Gate, GateResult, GateVerdict, GateContext |
| Create | `gates/base.py` | Base classes for gate abstraction |
| Create | `gates/test_quality.py` | TestQualityGate with AST-based static analysis |
| Create | `tests/test_gates_base.py` | Tests for gate base classes |
| Create | `tests/test_test_quality_gate.py` | Tests for TestQualityGate |
| Modify | `machines/base.py` | Add GUARDS, GATE_SOFTNESS dicts and accessor methods |
| Modify | `tests/test_base_machine.py` | Tests for new accessors |
| Modify | `governor/audit.py` | Replace JSONL with TinyDB AuditStore |
| Modify | `tests/test_audit.py` | Rewrite for TinyDB API |
| Modify | `governor/state_io.py` | Add gate_attempts field to default_state |
| Modify | `governor/governor.py` | Gate evaluation, transcript refactor, tool signatures, retry tracking |
| Modify | `tests/test_governor.py` | Update audit assertions for TinyDB |
| Create | `tests/test_governor_gates.py` | Tests for gate integration in governor |
| Modify | `machines/tdd.py` | Add GUARDS and GATE_SOFTNESS |
| Modify | `hooks/post-tool-use.sh` | Handle `review` action from governor |
| Modify | `bin/governor` | Add `audit` subcommand |
| Modify | `governor/__main__.py` | Add audit CLI mode |
| Modify | `install-governor.sh` | Copy gates/ package, note tinydb dependency |

---

### Task 1: Gate Base Classes

**Files:**
- Create: `gates/__init__.py`
- Create: `gates/base.py`
- Test: `tests/test_gates_base.py`

- [ ] **Step 1: Write the failing tests for GateVerdict, GateResult, GateContext, Gate**

```python
# tests/test_gates_base.py
import pytest
from gates.base import Gate, GateResult, GateVerdict, GateContext


class TestGateVerdict:
    def test_pass_value(self):
        assert GateVerdict.PASS == "pass"

    def test_fail_value(self):
        assert GateVerdict.FAIL == "fail"

    def test_review_value(self):
        assert GateVerdict.REVIEW == "review"


class TestGateResult:
    def test_pass_result(self):
        r = GateResult(GateVerdict.PASS)
        assert r.verdict == GateVerdict.PASS
        assert r.message is None
        assert r.issues == []

    def test_fail_result_with_message(self):
        r = GateResult(GateVerdict.FAIL, message="bad test", issues=["no_assertions"])
        assert r.verdict == GateVerdict.FAIL
        assert r.message == "bad test"
        assert r.issues == ["no_assertions"]

    def test_review_result(self):
        r = GateResult(GateVerdict.REVIEW, message="check this", issues=["weak"])
        assert r.verdict == GateVerdict.REVIEW


class TestGateContext:
    def test_context_fields(self):
        ctx = GateContext(
            state_name="writing_tests",
            transition_name="pytest_fail",
            recent_tools=["Write(/tmp/tests/test_foo.py)"],
            recent_files=["/tmp/tests/test_foo.py"],
            machine=None,
            project_root="/tmp/project",
        )
        assert ctx.state_name == "writing_tests"
        assert ctx.transition_name == "pytest_fail"
        assert ctx.recent_files == ["/tmp/tests/test_foo.py"]
        assert ctx.project_root == "/tmp/project"


class TestGateBase:
    def test_base_gate_has_name(self):
        g = Gate()
        assert g.name == "unnamed"

    def test_base_gate_evaluate_raises(self):
        g = Gate()
        ctx = GateContext(
            state_name="s", transition_name="t",
            recent_tools=[], recent_files=[],
            machine=None, project_root="/tmp",
        )
        with pytest.raises(NotImplementedError):
            g.evaluate(ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_gates_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gates'`

- [ ] **Step 3: Implement gate base classes**

```python
# gates/__init__.py
"""Gate framework for transition guards."""
from gates.base import Gate, GateContext, GateResult, GateVerdict

__all__ = ["Gate", "GateContext", "GateResult", "GateVerdict"]
```

```python
# gates/base.py
"""Base classes for transition guards.

A Gate is a check that runs when a state machine transition is about to fire.
It inspects the work done during the current state and decides whether the
transition should proceed (PASS), be blocked (FAIL), or require review (REVIEW).
"""

from enum import Enum


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"


class GateResult:
    """Result of a gate evaluation."""

    def __init__(
        self,
        verdict: GateVerdict,
        message: str | None = None,
        issues: list[str] | None = None,
    ):
        self.verdict = verdict
        self.message = message
        self.issues = issues or []


class GateContext:
    """Context passed to gates for evaluation."""

    def __init__(
        self,
        state_name: str,
        transition_name: str,
        recent_tools: list[str],
        recent_files: list[str],
        machine,
        project_root: str,
    ):
        self.state_name = state_name
        self.transition_name = transition_name
        self.recent_tools = recent_tools
        self.recent_files = recent_files
        self.machine = machine
        self.project_root = project_root


class Gate:
    """Base class for transition guards."""

    name: str = "unnamed"

    def evaluate(self, context: GateContext) -> GateResult:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_gates_base.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add gates/__init__.py gates/base.py tests/test_gates_base.py
git commit -m "feat: add gate base classes (GateVerdict, GateResult, GateContext, Gate)"
```

---

### Task 2: GovernedMachine GUARDS and GATE_SOFTNESS

**Files:**
- Modify: `machines/base.py:10-50`
- Test: `tests/test_base_machine.py`

- [ ] **Step 1: Write failing tests for GUARDS and GATE_SOFTNESS accessors**

Append to `tests/test_base_machine.py`:

```python
from gates.base import Gate, GateResult, GateVerdict, GateContext


class StubGate(Gate):
    name = "stub"
    def evaluate(self, ctx):
        return GateResult(GateVerdict.PASS)


class MachineWithGuards(GovernedMachine):
    alpha = State(initial=True)
    beta = State()
    go = alpha.to(beta)

    GUARDS = {
        "go": [StubGate],
    }
    GATE_SOFTNESS = {
        "stub": 0.1,
    }


def test_get_guards_returns_gate_classes():
    sm = MachineWithGuards()
    assert sm.get_guards("go") == [StubGate]


def test_get_guards_returns_empty_for_unknown():
    sm = MachineWithGuards()
    assert sm.get_guards("nonexistent") == []


def test_get_guards_defaults_to_empty():
    sm = SimpleMachine()
    assert sm.get_guards("go") == []


def test_get_gate_softness_returns_value():
    sm = MachineWithGuards()
    assert sm.get_gate_softness("stub") == 0.1


def test_get_gate_softness_defaults_to_zero():
    sm = MachineWithGuards()
    assert sm.get_gate_softness("unknown") == 0.0


def test_get_gate_softness_defaults_when_not_defined():
    sm = SimpleMachine()
    assert sm.get_gate_softness("anything") == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_base_machine.py -v -k "guard or gate_softness"`
Expected: FAIL — `AttributeError: 'SimpleMachine' object has no attribute 'get_guards'`

- [ ] **Step 3: Add GUARDS, GATE_SOFTNESS, and accessors to GovernedMachine**

In `machines/base.py`, add after the `SESSION_INSTRUCTIONS` field (line 18):

```python
    GUARDS: dict[str, list] = {}
    GATE_SOFTNESS: dict[str, float] = {}
```

Add after `get_preconditions` method (after line 38):

```python
    def get_guards(self, transition_name: str) -> list:
        """Return gate classes registered for a transition. Defaults to []."""
        return self.GUARDS.get(transition_name, [])

    def get_gate_softness(self, gate_name: str) -> float:
        """Return the softness override for a gate. Defaults to 0.0 (strict)."""
        return self.GATE_SOFTNESS.get(gate_name, 0.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_base_machine.py -v`
Expected: PASS (all tests including new ones)

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add machines/base.py tests/test_base_machine.py
git commit -m "feat: add GUARDS and GATE_SOFTNESS to GovernedMachine base class"
```

---

### Task 3: TinyDB Audit Trail

**Files:**
- Modify: `governor/audit.py`
- Modify: `tests/test_audit.py`

- [ ] **Step 1: Install tinydb**

Run: `pip3 install tinydb>=4.0.0`

- [ ] **Step 2: Write failing tests for AuditStore**

Replace the contents of `tests/test_audit.py`:

```python
import os
import pytest

from governor.audit import AuditStore, write_audit_entry, read_audit_log


class TestAuditStore:
    def test_write_returns_doc_id(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        doc_id = store.write({"timestamp": "2026-04-13T12:00:00Z", "type": "transition"})
        assert isinstance(doc_id, int)

    def test_write_and_query_all(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "transition", "from_state": "red"})
        store.write({"type": "transition", "from_state": "green"})
        results = store.query()
        assert len(results) == 2

    def test_query_with_filter(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "transition", "from_state": "red"})
        store.write({"type": "gate_eval", "gate": "test_quality"})
        results = store.query(type="gate_eval")
        assert len(results) == 1
        assert results[0]["gate"] == "test_quality"

    def test_gate_failures_filters_non_pass(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "pass"})
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "fail"})
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "review"})
        results = store.gate_failures()
        assert len(results) == 2

    def test_gate_failures_filters_by_gate_name(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "gate_eval", "gate": "test_quality", "verdict": "fail"})
        store.write({"type": "gate_eval", "gate": "diff_size", "verdict": "fail"})
        results = store.gate_failures(gate_name="test_quality")
        assert len(results) == 1

    def test_gate_failures_filters_by_since(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "test.audit.json")
        store = AuditStore(db_path)
        store.write({"type": "gate_eval", "gate": "tq", "verdict": "fail", "timestamp": "2026-04-12T10:00:00Z"})
        store.write({"type": "gate_eval", "gate": "tq", "verdict": "fail", "timestamp": "2026-04-13T10:00:00Z"})
        results = store.gate_failures(since="2026-04-13T00:00:00Z")
        assert len(results) == 1


class TestBackwardCompatFunctions:
    def test_write_audit_entry_creates_file(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "session.audit.json")
        entry = {"timestamp": "2026-04-13T12:00:00Z", "type": "transition"}
        write_audit_entry(db_path, entry)
        assert os.path.exists(db_path)

    def test_write_and_read_audit_log(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "session.audit.json")
        write_audit_entry(db_path, {"type": "transition", "from_state": "red"})
        write_audit_entry(db_path, {"type": "transition", "from_state": "green"})
        entries = read_audit_log(db_path)
        assert len(entries) == 2
        assert entries[0]["from_state"] == "red"

    def test_read_returns_empty_for_missing_file(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "nonexistent.audit.json")
        entries = read_audit_log(db_path)
        assert entries == []

    def test_write_creates_parent_directories(self, tmp_audit_dir):
        db_path = os.path.join(tmp_audit_dir, "nested", "session.audit.json")
        write_audit_entry(db_path, {"timestamp": "2026-04-13T12:00:00Z"})
        assert os.path.exists(db_path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit.py -v`
Expected: FAIL — `ImportError: cannot import name 'AuditStore' from 'governor.audit'`

- [ ] **Step 4: Rewrite governor/audit.py with TinyDB**

```python
# governor/audit.py
"""Audit trail for governor evaluations.

Uses TinyDB as a queryable document store. One database file per session.
"""

import os

from tinydb import TinyDB, where


class AuditStore:
    """Queryable audit trail backed by TinyDB."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = TinyDB(db_path)

    def write(self, entry: dict) -> int:
        """Append an audit document. Returns the document ID."""
        return self.db.insert(entry)

    def query(self, **filters) -> list[dict]:
        """Query audit entries by field values."""
        q = None
        for key, value in filters.items():
            condition = where(key) == value
            q = condition if q is None else q & condition
        return self.db.search(q) if q else self.db.all()

    def gate_failures(self, gate_name: str | None = None, since: str | None = None) -> list[dict]:
        """Query gate evaluations with non-pass verdicts."""
        q = (where("type") == "gate_eval") & (where("verdict") != "pass")
        if gate_name:
            q = q & (where("gate") == gate_name)
        if since:
            q = q & (where("timestamp") >= since)
        return self.db.search(q)


def write_audit_entry(path: str, entry: dict) -> None:
    """Append an audit entry. Backward-compatible function signature."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = TinyDB(path)
    db.insert(entry)


def read_audit_log(path: str) -> list[dict]:
    """Read all entries from an audit log. Return [] if file missing."""
    if not os.path.exists(path):
        return []
    db = TinyDB(path)
    return db.all()
```

- [ ] **Step 5: Run audit tests to verify they pass**

Run: `python3 -m pytest tests/test_audit.py -v`
Expected: PASS (all 10 tests)

- [ ] **Step 6: Update audit file path in governor.py**

In `governor/governor.py` line 46, change the audit file extension from `.jsonl` to `.audit.json`:

```python
# Before:
self._audit_file = os.path.join(audit_dir, f"{session_id}.jsonl")
# After:
self._audit_file = os.path.join(audit_dir, f"{session_id}.audit.json")
```

- [ ] **Step 7: Update test_governor.py audit assertion**

In `tests/test_governor.py` line 183, change:
```python
# Before:
audit_file = os.path.join(tmp_audit_dir, "test-session.jsonl")
# After:
audit_file = os.path.join(tmp_audit_dir, "test-session.audit.json")
```

And change lines 184-189 to use TinyDB:
```python
        assert os.path.exists(audit_file)
        from governor.audit import read_audit_log
        entries = read_audit_log(audit_file)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry["machine"] == "TDDCycle"
        assert entry["from_state"] == "red"
        assert entry["tool_name"] == "Edit"
```

- [ ] **Step 8: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add governor/audit.py tests/test_audit.py governor/governor.py tests/test_governor.py
git commit -m "feat: replace JSONL audit trail with TinyDB document store"
```

---

### Task 4: Tool Signature Enhancement — Full Paths

**Files:**
- Modify: `governor/governor.py:96-102`
- Modify: `tests/test_governor.py` (or create targeted test)

- [ ] **Step 1: Write failing test for full-path tool signatures**

Append to `tests/test_governor.py` (or add new test class):

```python
class TestToolSignatures:
    def test_write_tool_records_full_path(self, governor):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert any("/project/tests/test_foo.py" in t for t in governor._recent_tools)

    def test_edit_tool_records_full_path(self, governor):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/src/widget.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert any("/project/src/widget.py" in t for t in governor._recent_tools)

    def test_bash_tool_records_command(self, governor):
        governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/ -v"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert any("pytest tests/ -v" in t for t in governor._recent_tools)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_governor.py::TestToolSignatures -v`
Expected: FAIL — `test_write_tool_records_full_path` fails because current code stores `Write(test_foo.py)` not `Write(/project/tests/test_foo.py)`

- [ ] **Step 3: Change tool signature storage to use full paths**

In `governor/governor.py`, replace lines 96-101:

```python
            # Before:
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                tool_sig = f"Bash({command})"
            else:
                file_path = tool_input.get("file_path", "")
                tool_sig = f"{tool_name}({os.path.basename(file_path)})"
```

With:

```python
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                tool_sig = f"Bash({command})"
            else:
                file_path = tool_input.get("file_path", "")
                tool_sig = f"{tool_name}({file_path})"
```

- [ ] **Step 4: Update _check_tool_against_state to extract basename for pattern matching**

In `governor/governor.py`, the `_check_tool_against_state` method (line 456) already extracts `target = os.path.basename(file_path)` from `tool_input` directly, so blocklist/allowlist pattern matching is unaffected. Verify no other code depends on `_recent_tools` having basenames.

Check `_check_preconditions` (line 429): it uses `fnmatch.fnmatch(tool_sig, pattern)` against patterns like `Write(test_*)` and `Bash(pytest*)`. With full paths, `Write(/project/tests/test_foo.py)` would NOT match `Write(test_*)`.

Fix `_check_preconditions` to also try matching against the basename form:

```python
    def _check_preconditions(self, required_patterns: list[str]) -> bool:
        """Check if any recent tool use matches at least one required pattern."""
        for tool_sig in self._recent_tools:
            # Create basename version for pattern matching
            # e.g. Write(/project/tests/test_foo.py) -> Write(test_foo.py)
            basename_sig = tool_sig
            if "(" in tool_sig and not tool_sig.startswith("Bash("):
                name, inner = tool_sig.split("(", 1)
                inner = inner.rstrip(")")
                basename_sig = f"{name}({os.path.basename(inner)})"
            for pattern in required_patterns:
                if fnmatch.fnmatch(tool_sig, pattern) or fnmatch.fnmatch(basename_sig, pattern):
                    return True
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass including new signature tests and existing precondition tests.

- [ ] **Step 6: Commit**

```bash
git add governor/governor.py tests/test_governor.py
git commit -m "feat: store full file paths in tool signatures for gate file access"
```

---

### Task 5: gate_attempts in State Persistence

**Files:**
- Modify: `governor/state_io.py:12-23`
- Modify: `tests/test_state_io.py`

- [ ] **Step 1: Write failing test for gate_attempts field**

Add to `tests/test_state_io.py`:

```python
def test_default_state_includes_gate_attempts():
    state = default_state(session_id="test")
    assert "gate_attempts" in state
    assert state["gate_attempts"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_state_io.py::test_default_state_includes_gate_attempts -v`
Expected: FAIL — `KeyError: 'gate_attempts'`

- [ ] **Step 3: Add gate_attempts to default_state**

In `governor/state_io.py`, add `"gate_attempts": {},` to the `default_state()` return dict (after `"session_id"`):

```python
def default_state(session_id: str = "") -> dict:
    return {
        "outer_machine": None,
        "outer_state": None,
        "inner_machine": None,
        "inner_state": None,
        "stack": [],
        "last_injected_state": None,
        "last_injection_timestamp": None,
        "session_id": session_id,
        "gate_attempts": {},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_state_io.py -v`
Expected: All pass.

- [ ] **Step 5: Update Governor._persist_state to include gate_attempts**

In `governor/governor.py`, update `_persist_state` (line 537) to include gate_attempts:

```python
    def _persist_state(self, current_state: str, timestamp: str) -> None:
        state = {
            "outer_machine": None,
            "outer_state": None,
            "inner_machine": type(self.machine).__name__,
            "inner_state": current_state,
            "stack": [],
            "last_injected_state": self._last_injected_state,
            "last_injection_timestamp": timestamp,
            "session_id": self.session_id,
            "recent_tools": self._recent_tools,
            "gate_attempts": self._gate_attempts,
        }
        save_state(self._state_file, state)
```

Also initialize `self._gate_attempts` in `__init__` (after line 55):

```python
        self._gate_attempts: dict = persisted.get("gate_attempts", {})
```

- [ ] **Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add governor/state_io.py governor/governor.py tests/test_state_io.py
git commit -m "feat: add gate_attempts to state persistence for review retry tracking"
```

---

### Task 6: Governor Gate Evaluation in trigger_transition

**Files:**
- Modify: `governor/governor.py:151-252`
- Create: `tests/test_governor_gates.py`

- [ ] **Step 1: Write failing tests for gate evaluation in trigger_transition**

```python
# tests/test_governor_gates.py
import os
import pytest

from gates.base import Gate, GateContext, GateResult, GateVerdict
from governor.governor import Governor
from machines.tdd import TDD
from statemachine import State
from machines.base import GovernedMachine


class AlwaysPassGate(Gate):
    name = "always_pass"
    def evaluate(self, ctx):
        return GateResult(GateVerdict.PASS)


class AlwaysFailGate(Gate):
    name = "always_fail"
    def evaluate(self, ctx):
        return GateResult(GateVerdict.FAIL, message="blocked by gate", issues=["test_issue"])


class AlwaysReviewGate(Gate):
    name = "always_review"
    def evaluate(self, ctx):
        return GateResult(GateVerdict.REVIEW, message="review needed", issues=["weak_test"])


class GatedTDD(TDD):
    GUARDS = {
        "pytest_fail": [AlwaysPassGate],
    }
    GATE_SOFTNESS = {
        "always_pass": 0.1,
    }


class FailGatedTDD(TDD):
    GUARDS = {
        "pytest_fail": [AlwaysFailGate],
    }
    GATE_SOFTNESS = {
        "always_fail": 0.1,
    }


class ReviewGatedTDD(TDD):
    GUARDS = {
        "pytest_fail": [AlwaysReviewGate],
    }
    GATE_SOFTNESS = {
        "always_review": 0.1,
    }


@pytest.fixture
def gated_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=GatedTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


@pytest.fixture
def fail_gated_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=FailGatedTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


@pytest.fixture
def review_gated_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=ReviewGatedTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


class TestGatePassInTriggerTransition:
    def test_passing_gate_allows_transition(self, gated_governor):
        result = gated_governor.trigger_transition("pytest_fail")
        assert result["action"] == "allow"
        assert "writing_tests -> fixing_tests" in result["transition"]

    def test_passing_gate_updates_state(self, gated_governor):
        gated_governor.trigger_transition("pytest_fail")
        assert gated_governor.machine.current_state_name == "fixing_tests"


class TestGateFailInTriggerTransition:
    def test_failing_gate_blocks_transition(self, fail_gated_governor):
        result = fail_gated_governor.trigger_transition("pytest_fail")
        assert result["action"] == "challenge"
        assert "blocked by gate" in result["message"]

    def test_failing_gate_does_not_change_state(self, fail_gated_governor):
        fail_gated_governor.trigger_transition("pytest_fail")
        assert fail_gated_governor.machine.current_state_name == "writing_tests"


class TestGateReviewInTriggerTransition:
    def test_review_gate_returns_review_action(self, review_gated_governor):
        result = review_gated_governor.trigger_transition("pytest_fail")
        assert result["action"] == "review"
        assert "review needed" in result["message"]

    def test_review_gate_does_not_change_state(self, review_gated_governor):
        review_gated_governor.trigger_transition("pytest_fail")
        assert review_gated_governor.machine.current_state_name == "writing_tests"

    def test_review_gate_tracks_attempt(self, review_gated_governor):
        review_gated_governor.trigger_transition("pytest_fail")
        assert review_gated_governor._gate_attempts.get("always_review", {}).get("count", 0) == 1

    def test_review_gate_escalates_after_max_attempts(self, review_gated_governor):
        review_gated_governor.trigger_transition("pytest_fail")
        review_gated_governor.trigger_transition("pytest_fail")
        result = review_gated_governor.trigger_transition("pytest_fail")
        # Third attempt: override to allow
        assert result["action"] == "allow"


class TestGateContextConstruction:
    def test_gate_receives_recent_files(self, tmp_state_dir, tmp_audit_dir, tmp_context_dir):
        """Gate context includes files derived from recent_tools."""
        class CapturingGate(Gate):
            name = "capturing"
            captured_ctx = None
            def evaluate(self, ctx):
                CapturingGate.captured_ctx = ctx
                return GateResult(GateVerdict.PASS)

        class CapturingTDD(TDD):
            GUARDS = {"pytest_fail": [CapturingGate]}

        gov = Governor(
            machine=CapturingTDD(),
            state_dir=tmp_state_dir,
            audit_dir=tmp_audit_dir,
            context_dir=tmp_context_dir,
            project_hash="testhash",
            session_id="test-session",
        )
        # Record a tool use first
        gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        gov.trigger_transition("pytest_fail")
        assert CapturingGate.captured_ctx is not None
        assert "/project/tests/test_foo.py" in CapturingGate.captured_ctx.recent_files
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_governor_gates.py -v`
Expected: FAIL — gates not evaluated in trigger_transition

- [ ] **Step 3: Add gate evaluation to trigger_transition**

In `governor/governor.py`, add a new import at the top:

```python
from gates.base import Gate, GateContext, GateResult, GateVerdict
```

Add helper methods to the Governor class (before `_extract_declaration`):

```python
    def _build_gate_context(self, event_name: str) -> "GateContext":
        """Build a GateContext from current governor state."""
        recent_files = []
        for sig in self._recent_tools:
            if "(" in sig and not sig.startswith("Bash("):
                inner = sig.split("(", 1)[1].rstrip(")")
                if inner:
                    recent_files.append(inner)
        return GateContext(
            state_name=self.machine.current_state_name,
            transition_name=event_name,
            recent_tools=list(self._recent_tools),
            recent_files=recent_files,
            machine=self.machine,
            project_root=os.getcwd(),
        )

    def _evaluate_gates(self, event_name: str, timestamp: str) -> dict | None:
        """Run gates for a transition. Returns a response dict if blocked, else None."""
        guards = self.machine.get_guards(event_name)
        if not guards:
            return None

        ctx = self._build_gate_context(event_name)
        for gate_cls in guards:
            gate = gate_cls()
            result = gate.evaluate(ctx)

            # Audit the gate evaluation
            gate_audit = {
                "timestamp": timestamp,
                "session_id": self.session_id,
                "machine": type(self.machine).__name__,
                "type": "gate_eval",
                "from_state": self.machine.current_state_name,
                "to_state": None,
                "trigger": event_name,
                "gate": gate.name,
                "verdict": result.verdict.value,
                "issues": result.issues,
                "attempt": self._gate_attempts.get(gate.name, {}).get("count", 0) + 1,
            }
            write_audit_entry(self._audit_file, gate_audit)

            if result.verdict == GateVerdict.FAIL:
                softness = self.machine.get_gate_softness(gate.name)
                if softness >= SOFTNESS_ALLOW:
                    return None  # Soft enough to pass
                elif softness >= SOFTNESS_REMIND:
                    return {
                        "current_state": self.machine.current_state_name,
                        "transition": None,
                        "action": "remind",
                        "message": result.message,
                        "context_to_inject": [],
                        "gate_results": {gate.name: {"verdict": "fail", "issues": result.issues}},
                    }
                else:
                    return {
                        "current_state": self.machine.current_state_name,
                        "transition": None,
                        "action": "challenge",
                        "message": result.message,
                        "context_to_inject": [],
                        "gate_results": {gate.name: {"verdict": "fail", "issues": result.issues}},
                    }

            if result.verdict == GateVerdict.REVIEW:
                attempts = self._gate_attempts.get(gate.name, {})
                count = attempts.get("count", 0) + 1
                self._gate_attempts[gate.name] = {
                    "count": count,
                    "last_issues": result.issues,
                }
                self._persist_state(self.machine.current_state_name, timestamp)

                if count >= 3:
                    # Escalation: override to allow after max attempts
                    self._gate_attempts.pop(gate.name, None)
                    return None

                msg = result.message
                if count == 2:
                    msg = (
                        f"This is the second time this gate flagged the same issue. "
                        f"{result.message}"
                    )

                return {
                    "current_state": self.machine.current_state_name,
                    "transition": None,
                    "action": "review",
                    "message": msg,
                    "context_to_inject": [],
                    "gate_results": {gate.name: {"verdict": "review", "issues": result.issues, "attempt": count}},
                }

        return None  # All gates passed
```

Modify `trigger_transition` to call `_evaluate_gates` before firing the transition. Insert gate evaluation after the `send = getattr(...)` check but BEFORE calling `send()` (between current lines 163 and 173):

```python
    def trigger_transition(self, event_name: str, timestamp: str | None = None) -> dict:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        from_state = self.machine.current_state_name

        send = getattr(self.machine, event_name, None)
        if send is None:
            return {
                "current_state": from_state,
                "transition": None,
                "action": "challenge",
                "message": f"Unknown transition '{event_name}'.",
                "context_to_inject": [],
            }

        # Run gates before firing the transition
        gate_response = self._evaluate_gates(event_name, timestamp)
        if gate_response is not None:
            return gate_response

        try:
            send()
        except Exception:
            return {
                "current_state": from_state,
                "transition": None,
                "action": "challenge",
                "message": f"Transition '{event_name}' not valid from state '{from_state}'.",
                "context_to_inject": [],
            }

        # ... rest unchanged (auto-advance, context, persist) ...
```

Also: after a successful transition, reset gate_attempts for gates that were on this transition:

After `self._recent_tools = []` (line 244), add:

```python
        # Reset gate attempts on successful transition
        guards = self.machine.get_guards(event_name)
        for gate_cls in guards:
            self._gate_attempts.pop(gate_cls().name, None)
```

- [ ] **Step 4: Run gate tests to verify they pass**

Run: `python3 -m pytest tests/test_governor_gates.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add governor/governor.py tests/test_governor_gates.py
git commit -m "feat: add gate evaluation to trigger_transition with retry tracking"
```

---

### Task 7: Gate Evaluation in _handle_declaration

**Files:**
- Modify: `governor/governor.py:267-314`
- Add tests to: `tests/test_governor_gates.py`

- [ ] **Step 1: Write failing test for gates in declaration path**

Append to `tests/test_governor_gates.py`:

```python
from machines.tdd_cycle import TDDCycle


class FailGatedTDDCycle(TDDCycle):
    GUARDS = {
        "test_written": [AlwaysFailGate],
    }
    GATE_SOFTNESS = {
        "always_fail": 0.1,
    }


class TestGateInDeclaration:
    def test_failing_gate_blocks_declaration(self, tmp_state_dir, tmp_audit_dir, tmp_context_dir):
        gov = Governor(
            machine=FailGatedTDDCycle(),
            state_dir=tmp_state_dir,
            audit_dir=tmp_audit_dir,
            context_dir=tmp_context_dir,
            project_hash="testhash",
            session_id="test-session",
        )
        # Satisfy precondition
        gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/tests/test_foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T11:59:00Z",
        })
        # Declare transition — gate should block
        result = gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Bash",
            "tool_input": {
                "command": """echo '{"declare_phase": "green", "reason": "test failing"}'""",
            },
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
        })
        assert result["action"] == "challenge"
        assert "blocked by gate" in result["message"]
        assert result["current_state"] == "red"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_governor_gates.py::TestGateInDeclaration -v`
Expected: FAIL — declaration path doesn't evaluate gates

- [ ] **Step 3: Add gate evaluation to _handle_declaration**

In `_handle_declaration`, after the precondition check succeeds (around line 296) but before firing the transition (line 300), insert:

```python
                # Run gates before firing
                gate_response = self._evaluate_gates(transition_name, 
                    datetime.now(timezone.utc).isoformat())
                if gate_response is not None:
                    return (
                        transition_name,
                        softness,
                        gate_response["action"],
                        gate_response["message"],
                    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_governor_gates.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add governor/governor.py tests/test_governor_gates.py
git commit -m "feat: add gate evaluation to declaration-based transitions"
```

---

### Task 8: Transcript Scanning Refactor

**Files:**
- Modify: `governor/governor.py:316-427`
- Add tests to: `tests/test_governor_gates.py`

- [ ] **Step 1: Write failing test for gates on transcript-detected transitions**

Append to `tests/test_governor_gates.py`:

```python
import json
import tempfile


class TestGatesOnTranscriptDetection:
    def _write_transcript(self, path, command, output, fail=True):
        """Write a minimal transcript with a pytest result."""
        tool_use_id = "tu_001"
        assistant_line = json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "id": tool_use_id, "name": "Bash",
                 "input": {"command": command}}
            ]},
        })
        result_text = "FAILED" if fail else "passed"
        user_line = json.dumps({
            "type": "user",
            "message": {"content": [
                {"type": "tool_result", "tool_use_id": tool_use_id,
                 "content": f"tests/test_foo.py {result_text}"}
            ]},
        })
        with open(path, "w") as f:
            f.write(assistant_line + "\n")
            f.write(user_line + "\n")

    def test_transcript_detected_fail_runs_gates(self, tmp_state_dir, tmp_audit_dir, tmp_context_dir):
        """When transcript scanning detects pytest_fail, gates should run."""
        gov = Governor(
            machine=FailGatedTDD(),
            state_dir=tmp_state_dir,
            audit_dir=tmp_audit_dir,
            context_dir=tmp_context_dir,
            project_hash="testhash",
            session_id="test-session",
        )
        transcript = os.path.join(tmp_state_dir, "transcript.jsonl")
        self._write_transcript(transcript, "pytest tests/ -v", "FAILED", fail=True)

        # Evaluate with transcript — should detect pytest_fail but gate should block
        result = gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Read",
            "tool_input": {"file_path": "/project/foo.py"},
            "session_id": "test-session",
            "timestamp": "2026-04-12T12:00:00Z",
            "transcript_path": transcript,
        })
        # State should NOT have changed because gate blocks
        assert gov.machine.current_state_name == "writing_tests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_governor_gates.py::TestGatesOnTranscriptDetection -v`
Expected: FAIL — transcript scanning calls `send()` directly, bypassing gates

- [ ] **Step 3: Refactor _check_transcript_for_pytest to use trigger_transition**

Replace lines 411-426 in `governor/governor.py` (the `send()` + auto-advance block inside `_check_transcript_for_pytest`) with a call to `self.trigger_transition()`:

```python
                if event_name:
                    # Mark as processed
                    try:
                        with open(marker_file, "w") as f:
                            f.write(str(line_num))
                    except OSError:
                        pass

                    # Route through trigger_transition so gates are evaluated
                    self.trigger_transition(event_name, timestamp)
                return
```

This replaces the direct `send()` call, manual auto-advance loop, `_persist_state()`, and `_recent_tools = []` with a single `trigger_transition()` call that handles all of those plus gate evaluation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_governor_gates.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass (including transcript detection tests in test_hooks_integration.py if any).

- [ ] **Step 6: Commit**

```bash
git add governor/governor.py tests/test_governor_gates.py
git commit -m "refactor: route transcript-detected pytest results through trigger_transition"
```

---

### Task 9: TestQualityGate — Hard Violations

**Files:**
- Create: `gates/test_quality.py`
- Create: `tests/test_test_quality_gate.py`

- [ ] **Step 1: Write failing tests for hard violation detection**

```python
# tests/test_test_quality_gate.py
import os
import tempfile
import pytest

from gates.base import GateContext, GateVerdict
from gates.test_quality import TestQualityGate


def _make_test_file(tmp_path, filename, content):
    """Write a Python test file and return its path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_context(tmp_path, files):
    """Build a GateContext with the given recent_files."""
    return GateContext(
        state_name="writing_tests",
        transition_name="pytest_fail",
        recent_tools=[f"Write({f})" for f in files],
        recent_files=files,
        machine=None,
        project_root=tmp_path,
    )


class TestHardViolations:
    def test_no_assertions_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = 1 + 1
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("no_assertions" in i for i in result.issues)

    def test_assert_true_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    assert True
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("trivial_assertion" in i for i in result.issues)

    def test_assert_literal_number_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    assert 1
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL

    def test_pytest_skip_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
import pytest
def test_something():
    pytest.skip("not ready")
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("skip_abuse" in i for i in result.issues)

    def test_pytest_xfail_decorator_is_hard_fail(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
import pytest
@pytest.mark.xfail
def test_something():
    assert 1 == 2
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.FAIL
        assert any("xfail_abuse" in i for i in result.issues)

    def test_valid_test_passes(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_addition():
    assert 1 + 1 == 2
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_no_test_files_passes(self, tmp_path):
        path = _make_test_file(tmp_path, "widget.py", """\
def compute():
    return 42
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_pytest_raises_counts_as_assertion(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
import pytest
def test_raises():
    with pytest.raises(ValueError):
        int("not a number")
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_test_quality_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gates.test_quality'`

- [ ] **Step 3: Implement TestQualityGate with hard violation detection**

```python
# gates/test_quality.py
"""TestQualityGate — AST-based test quality analysis.

Detects structurally invalid and weak tests at transition boundaries.
"""

import ast
import os
from dataclasses import dataclass

from gates.base import Gate, GateContext, GateResult, GateVerdict


@dataclass
class Issue:
    """A detected test quality issue."""
    category: str     # e.g. "no_assertions", "trivial_assertion"
    severity: str     # "hard" or "soft"
    file: str
    function: str
    line: int
    detail: str

    def __str__(self):
        return f"{self.category}:{self.file}:{self.line}"


class TestQualityGate(Gate):
    """Gate that evaluates test quality via AST analysis."""

    name = "test_quality"

    def evaluate(self, ctx: GateContext) -> GateResult:
        test_files = [f for f in ctx.recent_files if self._is_test_file(f)]
        if not test_files:
            return GateResult(GateVerdict.PASS)

        issues: list[Issue] = []
        for path in test_files:
            if not os.path.exists(path):
                continue
            source = open(path).read()
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError:
                continue
            for func in self._extract_test_functions(tree):
                issues.extend(self._analyze_function(func, path))

        hard = [i for i in issues if i.severity == "hard"]
        soft = [i for i in issues if i.severity == "soft"]

        if hard:
            return GateResult(
                GateVerdict.FAIL,
                message=self._format_issues(hard),
                issues=[str(i) for i in hard],
            )
        if soft:
            return GateResult(
                GateVerdict.REVIEW,
                message=self._format_review_prompt(soft),
                issues=[str(i) for i in soft],
            )
        return GateResult(GateVerdict.PASS)

    @staticmethod
    def _is_test_file(path: str) -> bool:
        return os.path.basename(path).startswith("test_") and path.endswith(".py")

    def _extract_test_functions(self, tree: ast.Module) -> list[ast.FunctionDef]:
        funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    funcs.append(node)
        return funcs

    def _analyze_function(self, func: ast.FunctionDef, path: str) -> list[Issue]:
        issues = []
        basename = os.path.basename(path)

        # Check for xfail decorator
        for decorator in func.decorator_list:
            if self._is_xfail(decorator):
                issues.append(Issue(
                    "xfail_abuse", "hard", basename, func.name, func.lineno,
                    "@pytest.mark.xfail decorator",
                ))

        # Check for skip/xfail calls in body
        for node in ast.walk(func):
            if self._is_skip_call(node):
                issues.append(Issue(
                    "skip_abuse", "hard", basename, func.name, node.lineno,
                    "pytest.skip() call",
                ))
            if self._is_xfail_call(node):
                issues.append(Issue(
                    "xfail_abuse", "hard", basename, func.name, node.lineno,
                    "pytest.xfail() call",
                ))

        # Extract assertions
        asserts = self._find_assertions(func)
        has_pytest_raises = self._has_pytest_raises(func)

        if not asserts and not has_pytest_raises:
            issues.append(Issue(
                "no_assertions", "hard", basename, func.name, func.lineno,
                "No assert statements found",
            ))
            return issues  # No point checking further

        # Check for trivial assertions
        for assert_node in asserts:
            if self._is_trivial_assertion(assert_node):
                issues.append(Issue(
                    "trivial_assertion", "hard", basename, func.name, assert_node.lineno,
                    "Trivial assertion (assert True/literal)",
                ))

        return issues

    def _find_assertions(self, func: ast.FunctionDef) -> list[ast.Assert]:
        return [n for n in ast.walk(func) if isinstance(n, ast.Assert)]

    def _has_pytest_raises(self, func: ast.FunctionDef) -> bool:
        """Check if function uses pytest.raises context manager."""
        for node in ast.walk(func):
            if isinstance(node, ast.With):
                for item in node.items:
                    if self._is_pytest_raises_call(item.context_expr):
                        return True
        return False

    @staticmethod
    def _is_pytest_raises_call(node: ast.expr) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "raises":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                return True
        return False

    @staticmethod
    def _is_trivial_assertion(node: ast.Assert) -> bool:
        test = node.test
        if isinstance(test, ast.Constant):
            return bool(test.value)  # assert True, assert 1, assert "literal"
        return False

    @staticmethod
    def _is_xfail(decorator) -> bool:
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "xfail"
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            return decorator.func.attr == "xfail"
        return False

    @staticmethod
    def _is_skip_call(node) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "skip":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                return True
        return False

    @staticmethod
    def _is_xfail_call(node) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "xfail":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                return True
        return False

    @staticmethod
    def _format_issues(issues: list[Issue]) -> str:
        lines = ["GATE: test_quality — blocked:"]
        for i in issues:
            lines.append(f"  - {i.file}::{i.function}:{i.line} — {i.detail}")
        return "\n".join(lines)

    @staticmethod
    def _format_review_prompt(issues: list[Issue]) -> str:
        lines = ["GATE: test_quality flagged potential issues:"]
        for i in issues:
            lines.append(f"  - {i.file}::{i.function}:{i.line} — {i.detail}")
        lines.append("")
        lines.append(
            "Review these tests — do they actually constrain the behavior you're "
            "implementing? If intentional, run pytest again to retry. "
            "Otherwise, strengthen the assertions first."
        )
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_test_quality_gate.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add gates/test_quality.py tests/test_test_quality_gate.py
git commit -m "feat: add TestQualityGate with hard violation detection (AST-based)"
```

---

### Task 10: TestQualityGate — Soft Violations

**Files:**
- Modify: `gates/test_quality.py`
- Add tests to: `tests/test_test_quality_gate.py`

- [ ] **Step 1: Write failing tests for soft violation detection**

Append to `tests/test_test_quality_gate.py`:

```python
class TestSoftViolations:
    def test_none_only_checks_trigger_review(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = get_widget()
    assert result is not None
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.REVIEW
        assert any("none_only" in i for i in result.issues)

    def test_membership_only_checks_trigger_review(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = get_data()
    assert "key" in result
    assert "other" in result
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.REVIEW
        assert any("membership_only" in i for i in result.issues)

    def test_type_only_checks_trigger_review(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = create_widget()
    assert isinstance(result, dict)
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.REVIEW
        assert any("type_only" in i for i in result.issues)

    def test_mixed_assertions_with_value_check_passes(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = get_data()
    assert "key" in result
    assert result["key"] == "expected_value"
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_none_check_plus_value_check_passes(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
def test_something():
    result = get_widget()
    assert result is not None
    assert result.name == "expected"
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.PASS

    def test_import_overlap_triggers_review(self, tmp_path):
        path = _make_test_file(tmp_path, "test_foo.py", """\
from app import compute
def test_tautology():
    assert compute(1) == compute(1)
""")
        ctx = _make_context(str(tmp_path), [path])
        result = TestQualityGate().evaluate(ctx)
        assert result.verdict == GateVerdict.REVIEW
        assert any("import_overlap" in i for i in result.issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_test_quality_gate.py::TestSoftViolations -v`
Expected: FAIL — soft violation checks not implemented yet

- [ ] **Step 3: Add soft violation detection to TestQualityGate**

Add the following methods to the `TestQualityGate` class in `gates/test_quality.py`. Also update `_analyze_function` to call soft checks after hard checks:

Add to the end of `_analyze_function`, before `return issues`:

```python
        # Soft violations: only flag if no hard issues found and there are assertions
        if not issues and asserts:
            soft = self._check_soft_violations(asserts, func, path)
            issues.extend(soft)

        return issues
```

Add new methods:

```python
    def _check_soft_violations(self, asserts: list[ast.Assert], func: ast.FunctionDef, path: str) -> list[Issue]:
        basename = os.path.basename(path)
        issues = []

        has_value_comparison = False
        all_none_checks = True
        all_membership_checks = True
        all_type_checks = True

        for a in asserts:
            kind = self._classify_assertion(a)
            if kind == "value_comparison":
                has_value_comparison = True
                all_none_checks = False
                all_membership_checks = False
                all_type_checks = False
            elif kind == "none_check":
                all_membership_checks = False
                all_type_checks = False
            elif kind == "membership_check":
                all_none_checks = False
                all_type_checks = False
            elif kind == "type_check":
                all_none_checks = False
                all_membership_checks = False
            else:
                all_none_checks = False
                all_membership_checks = False
                all_type_checks = False

        if not has_value_comparison and len(asserts) > 0:
            if all_none_checks:
                issues.append(Issue(
                    "none_only", "soft", basename, func.name, asserts[0].lineno,
                    "All assertions only check None/not None",
                ))
            elif all_membership_checks:
                issues.append(Issue(
                    "membership_only", "soft", basename, func.name, asserts[0].lineno,
                    "All assertions only check membership (in/not in) without verifying values",
                ))
            elif all_type_checks:
                issues.append(Issue(
                    "type_only", "soft", basename, func.name, asserts[0].lineno,
                    "All assertions only check types (isinstance) without verifying values",
                ))

        # Import overlap: same callable on both sides of ==
        overlap = self._check_import_overlap(asserts, func)
        if overlap:
            issues.append(Issue(
                "import_overlap", "soft", basename, func.name, overlap.lineno,
                "Same production function called on both sides of assertion",
            ))

        return issues

    def _classify_assertion(self, node: ast.Assert) -> str:
        """Classify an assertion into a category."""
        test = node.test

        # assert x is None / assert x is not None
        if isinstance(test, ast.Compare):
            if len(test.ops) == 1:
                op = test.ops[0]
                comparator = test.comparators[0]
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comparator, ast.Constant) and comparator.value is None:
                    return "none_check"
                if isinstance(op, (ast.In, ast.NotIn)):
                    return "membership_check"
                if isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
                    return "value_comparison"

        # assert isinstance(x, Y)
        if isinstance(test, ast.Call):
            if isinstance(test.func, ast.Name) and test.func.id == "isinstance":
                return "type_check"

        # Anything else with a comparison operator
        if isinstance(test, ast.Compare):
            return "value_comparison"

        return "other"

    def _check_import_overlap(self, asserts: list[ast.Assert], func: ast.FunctionDef) -> ast.Assert | None:
        """Detect if the same function call appears on both sides of an assertion comparison."""
        for a in asserts:
            test = a.test
            if not isinstance(test, ast.Compare) or len(test.ops) != 1:
                continue
            if not isinstance(test.ops[0], ast.Eq):
                continue
            left = test.left
            right = test.comparators[0]
            if isinstance(left, ast.Call) and isinstance(right, ast.Call):
                left_name = self._call_name(left)
                right_name = self._call_name(right)
                if left_name and left_name == right_name:
                    return a
        return None

    @staticmethod
    def _call_name(node: ast.Call) -> str | None:
        """Extract the callable name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_test_quality_gate.py -v`
Expected: All pass (both hard and soft violation tests).

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add gates/test_quality.py tests/test_test_quality_gate.py
git commit -m "feat: add soft violation detection to TestQualityGate (none-only, membership-only, type-only, import-overlap)"
```

---

### Task 11: Wire TestQualityGate to TDD Machine

**Files:**
- Modify: `machines/tdd.py`
- Add test to: `tests/test_tdd.py`

- [ ] **Step 1: Write failing test for TDD GUARDS**

Add to `tests/test_tdd.py`:

```python
from gates.test_quality import TestQualityGate


def test_tdd_has_guards_for_pytest_fail():
    m = TDD()
    guards = m.get_guards("pytest_fail")
    assert TestQualityGate in guards


def test_tdd_has_gate_softness_for_test_quality():
    m = TDD()
    softness = m.get_gate_softness("test_quality")
    assert softness == 0.1


def test_tdd_no_guards_for_pytest_pass():
    m = TDD()
    guards = m.get_guards("pytest_pass")
    assert guards == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tdd.py -v -k "guards or gate_softness"`
Expected: FAIL

- [ ] **Step 3: Add GUARDS and GATE_SOFTNESS to TDD machine**

In `machines/tdd.py`, add import at top:

```python
from gates.test_quality import TestQualityGate
```

Add after `AUTO_TRANSITIONS` dict (after line 56):

```python
    GUARDS = {
        "pytest_fail": [TestQualityGate],
        "pytest_pass": [],
    }

    GATE_SOFTNESS = {
        "test_quality": 0.1,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tdd.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add machines/tdd.py tests/test_tdd.py
git commit -m "feat: register TestQualityGate on TDD machine pytest_fail transition"
```

---

### Task 12: PostToolUse Hook — Handle Review Action

**Files:**
- Modify: `hooks/post-tool-use.sh`

- [ ] **Step 1: Read current hook behavior**

The current hook (line 84-116) fires `trigger_transition`, extracts state and context, and outputs transition info. It does not check for `action: "review"` in the response. When a gate returns REVIEW, the governor returns `{"action": "review", "message": "..."}` — the hook needs to emit the review message.

- [ ] **Step 2: Add review action handling to post-tool-use.sh**

After the `RESPONSE` extraction (line 85) and before the state extraction (line 91), add action extraction and handling:

```bash
# Extract action from governor response
ACTION=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('action',''))" 2>/dev/null)

# Extract message
MESSAGE=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('message','') or '')" 2>/dev/null)

# If gate returned review or challenge, emit the message
if [ "$ACTION" = "review" ] || [ "$ACTION" = "challenge" ]; then
    if [ -n "$MESSAGE" ]; then
        echo ""
        echo "$MESSAGE"
        echo ""
    fi
fi
```

- [ ] **Step 3: Test manually**

Run a governor trigger manually to verify the hook output:
```bash
echo '{"session_id":"test"}' | CTX_STATE_DIR=/tmp/ctx-state CTX_AUDIT_DIR=/tmp/test-audit CTX_CONTEXT_DIR="$PWD/.claude" CTX_PROJECT_HASH=test PYTHONPATH=. python3 -m governor trigger pytest_fail
```
Verify the output includes gate results when applicable.

- [ ] **Step 4: Commit**

```bash
git add hooks/post-tool-use.sh
git commit -m "feat: handle review and challenge actions in PostToolUse hook"
```

---

### Task 13: Audit Query CLI

**Files:**
- Modify: `governor/__main__.py`
- Modify: `bin/governor`
- Modify: `governor/governor.py` (add `_print_audit` function)

- [ ] **Step 1: Write failing test for audit CLI mode**

Add to `tests/test_hooks_integration.py` (or create `tests/test_audit_cli.py`):

```python
import json
import os
import subprocess

def test_audit_cli_returns_entries(tmp_path):
    """governor audit --all returns audit entries."""
    audit_dir = str(tmp_path)
    # Pre-populate an audit file
    from governor.audit import AuditStore
    store = AuditStore(os.path.join(audit_dir, "test-session.audit.json"))
    store.write({"type": "transition", "from_state": "writing_tests", "to_state": "red",
                 "timestamp": "2026-04-13T12:00:00Z", "session_id": "test-session"})

    result = subprocess.run(
        ["python3", "-m", "governor", "audit", "--all"],
        capture_output=True, text=True,
        env={**os.environ, "CTX_AUDIT_DIR": audit_dir, "PYTHONPATH": "."},
    )
    assert result.returncode == 0
    entries = json.loads(result.stdout)
    assert len(entries) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_audit_cli.py -v`
Expected: FAIL — `governor audit` not recognized

- [ ] **Step 3: Add audit CLI mode to governor/__main__.py and governor.py**

In `governor/governor.py`, add a `_print_audit` function (after `_print_context`):

```python
def _print_audit():
    """Query and print audit entries as JSON."""
    import argparse
    import glob as globmod

    audit_dir = os.environ.get("CTX_AUDIT_DIR", os.path.join(os.getcwd(), ".claude", "audit"))

    parser = argparse.ArgumentParser(prog="governor audit")
    parser.add_argument("--all", action="store_true", help="Show all entries")
    parser.add_argument("--type", help="Filter by entry type (transition, gate_eval, tool_eval)")
    parser.add_argument("--gate", help="Filter by gate name")
    parser.add_argument("--verdict", help="Filter by verdict (pass, fail, review)")
    parser.add_argument("--session", help="Filter by session ID (use 'current' for latest)")
    parser.add_argument("--since", help="ISO timestamp or relative (e.g. 7d)")
    parser.add_argument("--limit", type=int, default=50, help="Max entries to return")
    args = parser.parse_args(sys.argv[2:])

    from governor.audit import AuditStore

    # Find all audit files
    all_entries = []
    pattern = os.path.join(audit_dir, "*.audit.json")
    for db_path in globmod.glob(pattern):
        store = AuditStore(db_path)
        all_entries.extend(store.query())

    # Apply filters
    if args.type:
        all_entries = [e for e in all_entries if e.get("type") == args.type]
    if args.gate:
        all_entries = [e for e in all_entries if e.get("gate") == args.gate]
    if args.verdict:
        all_entries = [e for e in all_entries if e.get("verdict") == args.verdict]
    if args.session:
        all_entries = [e for e in all_entries if e.get("session_id") == args.session]
    if args.since:
        all_entries = [e for e in all_entries if e.get("timestamp", "") >= args.since]

    # Sort by timestamp descending, apply limit
    all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    all_entries = all_entries[:args.limit]

    json.dump(all_entries, sys.stdout, indent=2)
    print()
```

In the `main()` function, add a new branch before the existing `elif` chain:

```python
    if len(sys.argv) >= 2 and sys.argv[1] == "audit":
        _print_audit()
        return
```

- [ ] **Step 4: Add audit subcommand to bin/governor**

In `bin/governor`, add a case for `audit` before the `status` case:

```bash
  audit)
    CTX_AUDIT_DIR="${CTX_AUDIT_DIR:-$PWD/.claude/audit}" \
      PYTHONPATH="$PLUGIN_DIR" python3 -m governor audit "$@"
    ;;
```

And update the case statement to pass remaining args:

```bash
case "$ARG" in
  audit)
    shift  # remove 'audit'
    CTX_AUDIT_DIR="${CTX_AUDIT_DIR:-$PWD/.claude/audit}" \
      PYTHONPATH="$PLUGIN_DIR" python3 -m governor audit "$@"
    ;;
  status)
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_cli.py -v`
Expected: All pass.

- [ ] **Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add governor/governor.py bin/governor tests/test_audit_cli.py
git commit -m "feat: add governor audit CLI for querying gate evaluations and transitions"
```

---

### Task 14: Update Installers and CI

**Files:**
- Modify: `install-governor.sh`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Update install-governor.sh to copy gates package**

After the machines installation block (line 65), add:

```bash
# --- install gates ---
echo "Installing gates..."
GATES_DIR="$HOME/.claude/plugins/context-injector/gates"
mkdir -p "$GATES_DIR"
cp "$PLUGIN_DIR/gates/__init__.py" "$GATES_DIR/"
cp "$PLUGIN_DIR/gates/base.py" "$GATES_DIR/"
cp "$PLUGIN_DIR/gates/test_quality.py" "$GATES_DIR/"
```

- [ ] **Step 2: Update CI to install tinydb**

In `.github/workflows/ci.yml`, update the Install dependencies step:

```yaml
      - name: Install dependencies
        run: pip install python-statemachine>=3.0.0 pytest>=8.0 tinydb>=4.0.0
```

- [ ] **Step 3: Update the python-statemachine warning in install-governor.sh**

After the existing python-statemachine check (line 20-22), add a tinydb check:

```bash
if ! python3 -c "import tinydb" 2>/dev/null; then
  echo "Warning: tinydb not found. Install with: pip3 install tinydb>=4.0.0" >&2
fi
```

- [ ] **Step 4: Run full test suite locally**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add install-governor.sh .github/workflows/ci.yml
git commit -m "feat: update installer and CI for gates package and tinydb dependency"
```

---

### Task 15: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add gate framework documentation to README**

Add a new section after "### Graduated response" and before "### TDD cycle":

```markdown
### Transition guards (gates)

Gates are transition guards — they run when a transition is about to fire, after preconditions pass but before the transition executes. Each gate inspects the work done during the current state and returns a verdict:

| Verdict | Behavior |
|---|---|
| `PASS` | Transition proceeds |
| `FAIL` | Blocked per gate softness (graduated response) |
| `REVIEW` | Injects a review prompt — agent must self-review, then retry |

**Built-in gate: TestQualityGate** — runs on `pytest_fail` in the TDD machine. Uses AST analysis to detect structurally invalid tests (no assertions, `assert True`, `pytest.skip`) and weak patterns (none-only, membership-only, type-only checks).

Machines register gates via `GUARDS` and `GATE_SOFTNESS`:

```python
GUARDS = {
    "pytest_fail": [TestQualityGate],
}
GATE_SOFTNESS = {
    "test_quality": 0.1,   # Strict — override per project
}
```

**Audit queries:**

```bash
governor audit --gate test_quality --verdict fail
governor audit --type gate_eval --limit 20
governor audit --all
```
```

Also update the "### Audit trail" section to mention TinyDB:

```markdown
### Audit trail

Each governor evaluation is stored in a TinyDB document database at `$CTX_AUDIT_DIR/<session_id>.audit.json`. Documents include: timestamp, from/to state, trigger type, softness, action taken, tool name, and gate evaluation results.

Query the audit trail via `governor audit` — see Transition guards section above.
```

Update the Dependencies section to include tinydb:

```markdown
## Requirements

- [Claude Code](https://claude.ai/code) with a project that has a `.claude/` directory
- `jq` (for the automated installers)
- Python 3 with `python-statemachine>=3.0.0` and `tinydb>=4.0.0` (governor only)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add gate framework, TestQualityGate, and TinyDB audit to README"
```

---

### Task 16: Deploy to Plugin Directory

**Files:**
- Deploy all changed files to `~/.claude/plugins/context-injector/`

- [ ] **Step 1: Copy gate framework files**

```bash
mkdir -p ~/.claude/plugins/context-injector/gates
cp gates/__init__.py ~/.claude/plugins/context-injector/gates/
cp gates/base.py ~/.claude/plugins/context-injector/gates/
cp gates/test_quality.py ~/.claude/plugins/context-injector/gates/
```

- [ ] **Step 2: Copy updated governor files**

```bash
cp governor/audit.py ~/.claude/plugins/context-injector/governor/
cp governor/state_io.py ~/.claude/plugins/context-injector/governor/
cp governor/governor.py ~/.claude/plugins/context-injector/governor/
```

- [ ] **Step 3: Copy updated machine files**

```bash
cp machines/base.py ~/.claude/plugins/context-injector/machines/
cp machines/tdd.py ~/.claude/plugins/context-injector/machines/
```

- [ ] **Step 4: Copy updated hooks and CLI**

```bash
cp hooks/post-tool-use.sh ~/.claude/plugins/context-injector/hooks/
cp bin/governor ~/.claude/plugins/context-injector/bin/
chmod +x ~/.claude/plugins/context-injector/hooks/post-tool-use.sh
chmod +x ~/.claude/plugins/context-injector/bin/governor
```

- [ ] **Step 5: Verify installation**

```bash
PYTHONPATH=~/.claude/plugins/context-injector python3 -c "from gates import Gate, GateVerdict; print('gates OK')"
PYTHONPATH=~/.claude/plugins/context-injector python3 -c "from governor.audit import AuditStore; print('audit OK')"
```

- [ ] **Step 6: Commit any remaining changes**

```bash
git status  # Should be clean
```
