# Evidence-Based Transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the trigger-based governor (v3) with an evidence-based transition engine where the agent decides when to transition and the governor validates evidence from a tamper-proof locker.

**Architecture:** Agent runs tools → PostToolUse hook captures output into evidence locker → agent requests `/transition <target> <evidence_key>` → engine retrieves evidence, passes key + locker to gate → gate validates → transition allowed or denied. Built from scratch as `governor_v4/` package; `governor_v3/` is deleted.

**Tech Stack:** Python 3.10+, pytest, fnmatch for pattern matching, JSON for persistence

---

## Context

The v3 governor forces transitions automatically when hooks detect events in tool output. This removes agent agency. The evidence-based model inverts control: the agent decides when to transition and provides a reference to tamper-proof evidence captured by the hook system.

**Design spec:** `docs/superpowers/specs/2026-04-21-evidence-based-transitions-design.md`

---

## File Structure

**New files (governor_v4 package):**
- `governor_v4/__init__.py` — package version
- `governor_v4/config.py` — CaptureRule, EvidenceContract, NodeConfig, EdgeConfig, MachineConfig dataclasses
- `governor_v4/locker.py` — EvidenceLocker class (store, retrieve, key generation, persistence)
- `governor_v4/primitives.py` — check_tool_allowed(), match_capture_rule()
- `governor_v4/gates.py` — EvidenceGate base + PytestFailGate, PytestPassGate, LintFailGate, LintPassGate
- `governor_v4/engine.py` — GovernorV4 class: evaluate(), want_to_transition()
- `governor_v4/loader.py` — JSON → MachineConfig parser with validation

**New files (machine definitions):**
- `machines/tdd_v4.json` — TDD machine with evidence contracts

**New test files:**
- `tests/test_v4_config.py` — dataclass unit tests
- `tests/test_v4_locker.py` — evidence locker unit tests
- `tests/test_v4_primitives.py` — tool blocking + capture matching unit tests
- `tests/test_v4_gates.py` — evidence gate unit tests
- `tests/test_v4_engine.py` — engine evaluate + want_to_transition unit tests
- `tests/test_v4_loader.py` — JSON loader unit tests
- `tests/test_v4_integration.py` — full TDD cycle integration tests

**Deleted files:**
- `governor_v3/__init__.py`
- `governor_v3/config.py`
- `governor_v3/primitives.py`
- `governor_v3/loader.py`
- `governor_v3/engine.py`
- `tests/test_v3_setup.py`
- `tests/test_v3_config.py`
- `tests/test_v3_primitives.py`
- `tests/test_v3_loader.py`
- `tests/test_v3_engine.py`
- `tests/test_v3_tdd_config.py`
- `tests/test_v3_persistence.py`
- `tests/test_v3_tdd_integration.py`
- `machines/tdd.json`

**Modified files:**
- `pyproject.toml` — replace `governor_v3` with `governor_v4` in packages list

**Untouched (reused as-is):**
- `gates/base.py`, `gates/lint.py`, `gates/reassignment.py`, `gates/test_quality.py` (old gates, not used by v4 but kept for v2 compatibility)
- All v2 code (`governor/`, `machines/*.py`, existing v2 tests)

---

## Task 1: Cleanup v3 and Scaffold v4 Package

**Files:**
- Delete: `governor_v3/` (all files), `tests/test_v3_*.py` (all 8 files), `machines/tdd.json`
- Modify: `pyproject.toml`
- Create: `governor_v4/__init__.py`
- Test: `tests/test_v4_setup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_setup.py

def test_governor_v4_package_importable():
    from governor_v4 import __version__
    assert __version__ is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_setup.py -xvs`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Delete v3 package, tests, and machine definition**

```bash
rm -rf governor_v3/
rm -f tests/test_v3_setup.py tests/test_v3_config.py tests/test_v3_primitives.py tests/test_v3_loader.py tests/test_v3_engine.py tests/test_v3_tdd_config.py tests/test_v3_persistence.py tests/test_v3_tdd_integration.py
rm -f machines/tdd.json
```

- [ ] **Step 4: Create governor_v4 package and update pyproject.toml**

```python
# governor_v4/__init__.py
"""Governor v4: Evidence-based transition engine."""

__version__ = "4.0.0"
```

Update `pyproject.toml`: replace `governor_v3` with `governor_v4` in packages list, and remove LangGraph dependencies (unused):

```toml
[tool.setuptools]
packages = ["governor", "governor_v4", "gates", "hooks", "machines"]
```

Remove from dependencies:
```toml
    "langgraph>=0.3.0",
    "langgraph-checkpoint-sqlite>=2.0.0",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_v4_setup.py -xvs`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(v4): scaffold governor_v4 package, remove governor_v3"
```

---

## Task 2: Config Dataclasses

**Files:**
- Create: `governor_v4/config.py`
- Test: `tests/test_v4_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_config.py
import pytest
from governor_v4.config import (
    CaptureRule, EvidenceContract, NodeConfig, EdgeConfig, MachineConfig,
)


class TestCaptureRule:
    def test_creation(self):
        rule = CaptureRule(tool_pattern="Bash(pytest*)", evidence_type="pytest_output")
        assert rule.tool_pattern == "Bash(pytest*)"
        assert rule.evidence_type == "pytest_output"


class TestEvidenceContract:
    def test_creation(self):
        contract = EvidenceContract(required_type="pytest_output", gate="pytest_fail_gate")
        assert contract.required_type == "pytest_output"
        assert contract.gate == "pytest_fail_gate"


class TestNodeConfig:
    def test_creation_with_capture(self):
        node = NodeConfig(
            name="writing_tests",
            initial=True,
            blocked_tools=["Write", "Edit"],
            allowed_exceptions=["Write(test_*)", "Edit(test_*)"],
            capture=[CaptureRule(tool_pattern="Bash(pytest*)", evidence_type="pytest_output")],
        )
        assert node.name == "writing_tests"
        assert node.initial is True
        assert len(node.capture) == 1
        assert node.capture[0].evidence_type == "pytest_output"

    def test_defaults(self):
        node = NodeConfig(name="idle")
        assert node.initial is False
        assert node.blocked_tools == []
        assert node.allowed_exceptions == []
        assert node.capture == []


class TestEdgeConfig:
    def test_with_contract(self):
        edge = EdgeConfig(
            from_state="writing_tests",
            to_state="fixing_tests",
            evidence_contract=EvidenceContract(required_type="pytest_output", gate="pytest_fail_gate"),
        )
        assert edge.from_state == "writing_tests"
        assert edge.to_state == "fixing_tests"
        assert edge.evidence_contract.gate == "pytest_fail_gate"

    def test_without_contract(self):
        edge = EdgeConfig(from_state="fixing_tests", to_state="writing_tests")
        assert edge.evidence_contract is None


class TestMachineConfig:
    def test_creation(self):
        machine = MachineConfig(
            name="tdd",
            description="TDD cycle",
            nodes=[
                NodeConfig(name="writing_tests", initial=True),
                NodeConfig(name="fixing_tests"),
            ],
            edges=[
                EdgeConfig(from_state="writing_tests", to_state="fixing_tests"),
            ],
        )
        assert machine.name == "tdd"
        assert len(machine.nodes) == 2
        assert len(machine.edges) == 1

    def test_find_initial_node(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="start", initial=True)],
            edges=[],
        )
        assert machine.find_initial_node().name == "start"

    def test_find_initial_node_missing_raises(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="start")],
            edges=[],
        )
        with pytest.raises(ValueError, match="no initial node"):
            machine.find_initial_node()

    def test_find_edge(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="a", initial=True), NodeConfig(name="b")],
            edges=[EdgeConfig(from_state="a", to_state="b")],
        )
        edge = machine.find_edge("a", "b")
        assert edge is not None
        assert edge.to_state == "b"

    def test_find_edge_missing_returns_none(self):
        machine = MachineConfig(
            name="test", description="",
            nodes=[NodeConfig(name="a", initial=True), NodeConfig(name="b")],
            edges=[],
        )
        assert machine.find_edge("a", "b") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_config.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/config.py
"""Configuration dataclasses for v4 machines."""

from dataclasses import dataclass, field


@dataclass
class CaptureRule:
    """Defines which tool outputs to capture as evidence."""
    tool_pattern: str      # e.g. "Bash(pytest*)"
    evidence_type: str     # e.g. "pytest_output"


@dataclass
class EvidenceContract:
    """Defines what evidence an edge requires for transition."""
    required_type: str     # must match CaptureRule.evidence_type
    gate: str              # gate name from GATE_REGISTRY


@dataclass
class NodeConfig:
    """A state node in the machine."""
    name: str
    initial: bool = False
    blocked_tools: list[str] = field(default_factory=list)
    allowed_exceptions: list[str] = field(default_factory=list)
    capture: list[CaptureRule] = field(default_factory=list)


@dataclass
class EdgeConfig:
    """A transition edge identified by from/to states."""
    from_state: str
    to_state: str
    evidence_contract: EvidenceContract | None = None


@dataclass
class MachineConfig:
    """Complete machine definition."""
    name: str
    description: str
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]

    def find_initial_node(self) -> NodeConfig:
        for node in self.nodes:
            if node.initial:
                return node
        raise ValueError(f"Machine {self.name} has no initial node")

    def find_edge(self, from_state: str, to_state: str) -> EdgeConfig | None:
        for edge in self.edges:
            if edge.from_state == from_state and edge.to_state == to_state:
                return edge
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_config.py -xvs`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/config.py tests/test_v4_config.py
git commit -m "feat(v4): add config dataclasses with CaptureRule and EvidenceContract"
```

---

## Task 3: Evidence Locker

**Files:**
- Create: `governor_v4/locker.py`
- Test: `tests/test_v4_locker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_locker.py
import json
import pytest
from governor_v4.locker import EvidenceLocker


class TestStore:
    def test_store_returns_key(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/",
            output="FAILED test_foo.py",
            exit_code=1,
        )
        assert key.startswith("evt_")
        assert len(key) == 10  # evt_ + 6 hex chars

    def test_store_creates_file(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/",
            output="FAILED",
            exit_code=1,
        )
        path = tmp_path / "s1_evidence.json"
        assert path.exists()

    def test_stored_entry_has_correct_fields(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_auth.py",
            output="FAILED test_auth.py::test_login",
            exit_code=1,
        )
        entry = locker.retrieve(key)
        assert entry["type"] == "pytest_output"
        assert entry["tool_name"] == "Bash"
        assert entry["command"] == "pytest tests/test_auth.py"
        assert entry["output"] == "FAILED test_auth.py::test_login"
        assert entry["exit_code"] == 1
        assert "timestamp" in entry


class TestRetrieve:
    def test_retrieve_existing(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="PASSED",
        )
        entry = locker.retrieve(key)
        assert entry is not None
        assert entry["type"] == "pytest_output"

    def test_retrieve_missing_returns_none(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        assert locker.retrieve("evt_nonexistent") is None


class TestPersistence:
    def test_new_locker_reads_existing_file(self, tmp_path):
        locker1 = EvidenceLocker(str(tmp_path), "s1")
        key = locker1.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        # New locker instance loads from file
        locker2 = EvidenceLocker(str(tmp_path), "s1")
        entry = locker2.retrieve(key)
        assert entry is not None
        assert entry["type"] == "pytest_output"

    def test_different_sessions_isolated(self, tmp_path):
        locker1 = EvidenceLocker(str(tmp_path), "s1")
        key = locker1.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
        )
        locker2 = EvidenceLocker(str(tmp_path), "s2")
        assert locker2.retrieve(key) is None


class TestMultipleEntries:
    def test_multiple_stores_produce_unique_keys(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        key1 = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_a.py",
            output="FAILED",
        )
        key2 = locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_b.py",
            output="PASSED",
        )
        assert key1 != key2

    def test_keys_lists_all_stored(self, tmp_path):
        locker = EvidenceLocker(str(tmp_path), "s1")
        k1 = locker.store(evidence_type="a", tool_name="Bash", command="cmd1", output="out1")
        k2 = locker.store(evidence_type="b", tool_name="Bash", command="cmd2", output="out2")
        assert set(locker.keys()) == {k1, k2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_locker.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/locker.py
"""Evidence locker: tamper-proof store of captured tool outputs."""

import hashlib
import json
import os
import time


class EvidenceLocker:
    """Per-session key-value store of captured tool outputs.

    Populated by PostToolUse hook. Read by gates during transition validation.
    The agent receives keys via additionalContext but cannot modify entries.
    """

    def __init__(self, state_dir: str, session_id: str):
        self._state_dir = state_dir
        self._session_id = session_id
        self._entries: dict[str, dict] = self._load()

    def _file_path(self) -> str:
        return os.path.join(self._state_dir, f"{self._session_id}_evidence.json")

    def _load(self) -> dict:
        path = self._file_path()
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    def _save(self):
        dir_path = os.path.dirname(self._file_path()) or "."
        os.makedirs(dir_path, exist_ok=True)
        with open(self._file_path(), "w") as f:
            json.dump(self._entries, f)

    def _generate_key(self, command: str) -> str:
        raw = f"{time.time()}:{command}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:6]
        return f"evt_{h}"

    def store(
        self,
        evidence_type: str,
        tool_name: str,
        command: str,
        output: str,
        exit_code: int | None = None,
    ) -> str:
        """Store a captured tool output. Returns the evidence key."""
        key = self._generate_key(command)
        self._entries[key] = {
            "type": evidence_type,
            "tool_name": tool_name,
            "command": command,
            "output": output,
            "exit_code": exit_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._save()
        return key

    def retrieve(self, key: str) -> dict | None:
        """Retrieve an evidence entry by key. Returns None if not found."""
        return self._entries.get(key)

    def keys(self) -> list[str]:
        """List all stored evidence keys."""
        return list(self._entries.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_locker.py -xvs`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/locker.py tests/test_v4_locker.py
git commit -m "feat(v4): add EvidenceLocker with store, retrieve, persistence"
```

---

## Task 4: Tool Blocking and Capture Matching

**Files:**
- Create: `governor_v4/primitives.py`
- Test: `tests/test_v4_primitives.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_primitives.py
import pytest
from governor_v4.primitives import check_tool_allowed, match_capture_rule


class TestCheckToolAllowed:
    def test_no_blocklist_allows(self):
        assert check_tool_allowed("Edit", "/test.py", blocked=None, exceptions=None)

    def test_empty_blocklist_allows(self):
        assert check_tool_allowed("Bash", "ls", blocked=[], exceptions=None)

    def test_exact_name_blocks(self):
        assert not check_tool_allowed("Write", "/main.py", blocked=["Write", "Edit"], exceptions=None)

    def test_exception_overrides_block(self):
        assert check_tool_allowed("Write", "test_foo.py", blocked=["Write"], exceptions=["Write(test_*)"])

    def test_non_matching_exception_stays_blocked(self):
        assert not check_tool_allowed("Write", "main.py", blocked=["Write"], exceptions=["Write(test_*)"])

    def test_non_blocked_tool_allowed(self):
        assert check_tool_allowed("Read", "/test.py", blocked=["Write", "Edit"], exceptions=None)

    def test_edit_exception_with_path(self):
        assert check_tool_allowed("Edit", "test_bar.py", blocked=["Edit"], exceptions=["Edit(test_*)"])

    def test_edit_blocked_without_matching_exception(self):
        assert not check_tool_allowed("Edit", "src/auth.py", blocked=["Edit"], exceptions=["Edit(test_*)"])


class TestMatchCaptureRule:
    def test_bash_pytest_matches(self):
        assert match_capture_rule("Bash", "pytest tests/", "Bash(pytest*)")

    def test_bash_pytest_verbose_matches(self):
        assert match_capture_rule("Bash", "pytest tests/ -xvs", "Bash(pytest*)")

    def test_bash_non_pytest_no_match(self):
        assert not match_capture_rule("Bash", "ls -la", "Bash(pytest*)")

    def test_wrong_tool_no_match(self):
        assert not match_capture_rule("Write", "test_foo.py", "Bash(pytest*)")

    def test_bash_ruff_matches(self):
        assert match_capture_rule("Bash", "ruff check src/", "Bash(ruff*)")

    def test_bare_tool_pattern(self):
        assert match_capture_rule("Bash", "anything", "Bash")

    def test_bare_tool_pattern_no_match(self):
        assert not match_capture_rule("Write", "test.py", "Bash")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_primitives.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/primitives.py
"""Tool blocking and capture rule matching."""

import fnmatch


def check_tool_allowed(
    tool_name: str,
    tool_arg: str | None = None,
    blocked: list[str] | None = None,
    exceptions: list[str] | None = None,
) -> bool:
    """Check if a tool call is allowed given blocklist and exception patterns.

    Exception patterns use "ToolName(arg_glob)" syntax, e.g. "Write(test_*)".
    """
    if not blocked:
        return True

    tool_blocked = any(fnmatch.fnmatch(tool_name, p) for p in blocked)
    if not tool_blocked:
        return True

    if exceptions and tool_arg:
        for exc in exceptions:
            if "(" in exc and exc.endswith(")"):
                exc_name, exc_pattern = exc.rstrip(")").split("(", 1)
                if exc_name == tool_name and fnmatch.fnmatch(tool_arg, exc_pattern):
                    return True

    return False


def match_capture_rule(tool_name: str, tool_arg: str, tool_pattern: str) -> bool:
    """Check if a tool call matches a capture rule pattern like 'Bash(pytest*)'.

    Uses the same ToolName(arg_glob) syntax as exception patterns.
    """
    if "(" not in tool_pattern or not tool_pattern.endswith(")"):
        return fnmatch.fnmatch(tool_name, tool_pattern)
    pat_name, pat_arg = tool_pattern.rstrip(")").split("(", 1)
    return fnmatch.fnmatch(tool_name, pat_name) and fnmatch.fnmatch(tool_arg, pat_arg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_primitives.py -xvs`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/primitives.py tests/test_v4_primitives.py
git commit -m "feat(v4): add tool blocking and capture rule matching"
```

---

## Task 5: Evidence Gates

**Files:**
- Create: `governor_v4/gates.py`
- Test: `tests/test_v4_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_gates.py
import pytest
from governor_v4.gates import (
    GateVerdict, EvidenceGate, GATE_REGISTRY,
    PytestFailGate, PytestPassGate, LintFailGate, LintPassGate,
)
from governor_v4.locker import EvidenceLocker


@pytest.fixture
def locker(tmp_path):
    return EvidenceLocker(str(tmp_path), "test")


class TestPytestFailGate:
    def test_pass_with_matching_evidence(self, locker):
        key = locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED test_foo.py", exit_code=1,
        )
        gate = PytestFailGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.PASS

    def test_fail_with_wrong_evidence_type(self, locker):
        key = locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check", output="error", exit_code=1,
        )
        gate = PytestFailGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.FAIL

    def test_fail_with_missing_key(self, locker):
        gate = PytestFailGate()
        result = gate.validate(["evt_nonexistent"], locker)
        assert result.verdict == GateVerdict.FAIL


class TestPytestPassGate:
    def test_pass_with_matching_evidence(self, locker):
        key = locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="3 passed", exit_code=0,
        )
        gate = PytestPassGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.PASS

    def test_fail_with_wrong_evidence_type(self, locker):
        key = locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff", output="ok", exit_code=0,
        )
        gate = PytestPassGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.FAIL


class TestLintFailGate:
    def test_pass_with_matching_evidence(self, locker):
        key = locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check src/", output="Found 3 errors", exit_code=1,
        )
        gate = LintFailGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.PASS

    def test_fail_with_wrong_evidence_type(self, locker):
        key = locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        gate = LintFailGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.FAIL


class TestLintPassGate:
    def test_pass_with_matching_evidence(self, locker):
        key = locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check src/", output="All checks passed", exit_code=0,
        )
        gate = LintPassGate()
        result = gate.validate([key], locker)
        assert result.verdict == GateVerdict.PASS

    def test_fail_with_missing_key(self, locker):
        gate = LintPassGate()
        result = gate.validate(["evt_nonexistent"], locker)
        assert result.verdict == GateVerdict.FAIL


class TestGateRegistry:
    def test_all_gates_registered(self):
        assert "pytest_fail_gate" in GATE_REGISTRY
        assert "pytest_pass_gate" in GATE_REGISTRY
        assert "lint_fail_gate" in GATE_REGISTRY
        assert "lint_pass_gate" in GATE_REGISTRY

    def test_registry_returns_correct_classes(self):
        assert GATE_REGISTRY["pytest_fail_gate"] is PytestFailGate
        assert GATE_REGISTRY["pytest_pass_gate"] is PytestPassGate
        assert GATE_REGISTRY["lint_fail_gate"] is LintFailGate
        assert GATE_REGISTRY["lint_pass_gate"] is LintPassGate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_gates.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/gates.py
"""Evidence gates: validate transition claims against locker evidence."""

from enum import Enum

from governor_v4.locker import EvidenceLocker


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class GateResult:
    """Result of a gate validation."""

    def __init__(self, verdict: GateVerdict, message: str | None = None):
        self.verdict = verdict
        self.message = message


class EvidenceGate:
    """Base class for evidence gates. Receives key(s) + locker access."""

    name: str = "unnamed"
    required_type: str = ""

    def validate(self, evidence_keys: list[str], locker: EvidenceLocker) -> GateResult:
        raise NotImplementedError


class _TypeCheckGate(EvidenceGate):
    """Trust-mode gate: checks evidence exists and type matches."""

    def validate(self, evidence_keys: list[str], locker: EvidenceLocker) -> GateResult:
        for key in evidence_keys:
            entry = locker.retrieve(key)
            if entry and entry.get("type") == self.required_type:
                return GateResult(GateVerdict.PASS)
        return GateResult(
            GateVerdict.FAIL,
            f"No {self.required_type} evidence found for keys: {evidence_keys}",
        )


class PytestFailGate(_TypeCheckGate):
    name = "pytest_fail_gate"
    required_type = "pytest_output"


class PytestPassGate(_TypeCheckGate):
    name = "pytest_pass_gate"
    required_type = "pytest_output"


class LintFailGate(_TypeCheckGate):
    name = "lint_fail_gate"
    required_type = "lint_output"


class LintPassGate(_TypeCheckGate):
    name = "lint_pass_gate"
    required_type = "lint_output"


GATE_REGISTRY: dict[str, type[EvidenceGate]] = {
    "pytest_fail_gate": PytestFailGate,
    "pytest_pass_gate": PytestPassGate,
    "lint_fail_gate": LintFailGate,
    "lint_pass_gate": LintPassGate,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_gates.py -xvs`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/gates.py tests/test_v4_gates.py
git commit -m "feat(v4): add evidence gates with trust-mode validation"
```

---

## Task 6: GovernorV4 Engine

**Files:**
- Create: `governor_v4/engine.py`
- Test: `tests/test_v4_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_engine.py
import pytest
from governor_v4.engine import GovernorV4
from governor_v4.config import (
    MachineConfig, NodeConfig, EdgeConfig, EvidenceContract, CaptureRule,
)


def make_simple_machine():
    """Two-state machine: writing_tests (blocks Write except test_*) -> fixing_tests."""
    return MachineConfig(
        name="tdd",
        description="TDD cycle",
        nodes=[
            NodeConfig(
                name="writing_tests",
                initial=True,
                blocked_tools=["Write", "Edit"],
                allowed_exceptions=["Write(test_*)", "Edit(test_*)"],
                capture=[CaptureRule(tool_pattern="Bash(pytest*)", evidence_type="pytest_output")],
            ),
            NodeConfig(name="fixing_tests"),
        ],
        edges=[
            EdgeConfig(
                from_state="writing_tests",
                to_state="fixing_tests",
                evidence_contract=EvidenceContract(required_type="pytest_output", gate="pytest_fail_gate"),
            ),
            EdgeConfig(
                from_state="fixing_tests",
                to_state="writing_tests",
            ),
        ],
    )


class TestEvaluate:
    def test_creation(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        assert gov.current_phase == "writing_tests"

    def test_allowed_tool(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        result = gov.evaluate(tool_name="Read", tool_input={"file_path": "/project/test.py"})
        assert result["action"] == "allow"

    def test_blocked_tool(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        result = gov.evaluate(tool_name="Write", tool_input={"file_path": "/project/main.py"})
        assert result["action"] == "block"

    def test_exception_allows(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        result = gov.evaluate(tool_name="Write", tool_input={"file_path": "test_auth.py"})
        assert result["action"] == "allow"


class TestWantToTransition:
    def test_transition_with_valid_evidence(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        key = gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest tests/", output="FAILED test_auth.py", exit_code=1,
        )
        result = gov.want_to_transition("fixing_tests", key)
        assert result["action"] == "allow"
        assert result["from_state"] == "writing_tests"
        assert result["to_state"] == "fixing_tests"
        assert gov.current_phase == "fixing_tests"

    def test_deny_no_edge(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        result = gov.want_to_transition("nonexistent")
        assert result["action"] == "deny"
        assert "No edge" in result["message"]

    def test_deny_missing_evidence_key(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        result = gov.want_to_transition("fixing_tests", "evt_nonexistent")
        assert result["action"] == "deny"
        assert "not found" in result["message"]

    def test_deny_evidence_required_but_not_provided(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        result = gov.want_to_transition("fixing_tests")
        assert result["action"] == "deny"
        assert "requires evidence" in result["message"]

    def test_deny_wrong_evidence_type(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        key = gov.locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check", output="error", exit_code=1,
        )
        result = gov.want_to_transition("fixing_tests", key)
        assert result["action"] == "deny"
        assert "does not match" in result["message"]

    def test_transition_without_contract(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        # First move to fixing_tests with valid evidence
        key = gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        gov.want_to_transition("fixing_tests", key)
        # Now transition back without evidence (no contract on this edge)
        result = gov.want_to_transition("writing_tests")
        assert result["action"] == "allow"
        assert gov.current_phase == "writing_tests"

    def test_evaluate_after_transition(self, tmp_path):
        gov = GovernorV4(config=make_simple_machine(), state_dir=str(tmp_path), session_id="t")
        key = gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        gov.want_to_transition("fixing_tests", key)
        result = gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"  # fixing_tests has no blocklist


class TestPersistence:
    def test_state_survives_new_instance(self, tmp_path):
        config = make_simple_machine()
        gov1 = GovernorV4(config=config, state_dir=str(tmp_path), session_id="s1")
        key = gov1.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        gov1.want_to_transition("fixing_tests", key)
        assert gov1.current_phase == "fixing_tests"

        gov2 = GovernorV4(config=config, state_dir=str(tmp_path), session_id="s1")
        assert gov2.current_phase == "fixing_tests"

    def test_different_sessions_isolated(self, tmp_path):
        config = make_simple_machine()
        gov1 = GovernorV4(config=config, state_dir=str(tmp_path), session_id="s1")
        key = gov1.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        gov1.want_to_transition("fixing_tests", key)

        gov2 = GovernorV4(config=config, state_dir=str(tmp_path), session_id="s2")
        assert gov2.current_phase == "writing_tests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_engine.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/engine.py
"""GovernorV4 engine: evaluate() and want_to_transition()."""

import json
import os

from governor_v4.config import MachineConfig, NodeConfig
from governor_v4.locker import EvidenceLocker
from governor_v4.primitives import check_tool_allowed
from governor_v4.gates import GATE_REGISTRY, GateVerdict


class GovernorV4:
    """Evidence-based workflow engine.

    The agent decides when to transition and provides evidence.
    The governor validates evidence against edge contracts via gates.
    """

    def __init__(
        self,
        config: MachineConfig,
        project_root: str = ".",
        session_id: str = "default",
        state_dir: str | None = None,
    ):
        self.config = config
        self.project_root = project_root
        self.session_id = session_id
        self._state_dir = state_dir
        self._locker = EvidenceLocker(state_dir, session_id) if state_dir else None
        self._current_phase = self._load_phase() or config.find_initial_node().name

    @property
    def current_phase(self) -> str:
        return self._current_phase

    @property
    def locker(self) -> EvidenceLocker | None:
        return self._locker

    def _get_node(self, name: str | None = None) -> NodeConfig:
        target = name or self._current_phase
        for node in self.config.nodes:
            if node.name == target:
                return node
        raise ValueError(f"Node {target} not found in {self.config.name}")

    def _state_file(self) -> str | None:
        if not self._state_dir:
            return None
        return os.path.join(self._state_dir, f"{self.session_id}.json")

    def _load_phase(self) -> str | None:
        path = self._state_file()
        if not path or not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        return data.get("current_phase")

    def _save_phase(self):
        path = self._state_file()
        if not path:
            return
        dir_path = os.path.dirname(path) or "."
        os.makedirs(dir_path, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"current_phase": self._current_phase, "machine": self.config.name}, f)

    def evaluate(self, tool_name: str, tool_input: dict) -> dict:
        """Evaluate a tool call against current state. Returns action dict."""
        node = self._get_node()

        tool_arg = None
        if tool_name in ("Write", "Edit"):
            tool_arg = tool_input.get("file_path", "")
        elif tool_name == "Bash":
            tool_arg = tool_input.get("command", "")

        allowed = check_tool_allowed(
            tool_name,
            tool_arg,
            blocked=node.blocked_tools or None,
            exceptions=node.allowed_exceptions or None,
        )

        if allowed:
            return {"action": "allow", "current_phase": self._current_phase, "message": None}
        return {
            "action": "block",
            "current_phase": self._current_phase,
            "message": f"{tool_name} is blocked in {self._current_phase}",
        }

    def want_to_transition(self, target_state: str, evidence_key: str | None = None) -> dict:
        """Request a state transition with optional evidence.

        1. Find edge from current_state to target_state
        2. If edge has evidence_contract: validate evidence via gate
        3. Transition or deny
        """
        # 1. Find edge
        edge = self.config.find_edge(self._current_phase, target_state)
        if not edge:
            return {
                "action": "deny",
                "current_phase": self._current_phase,
                "message": f"No edge from {self._current_phase} to {target_state}",
            }

        # 2. Check evidence contract
        if edge.evidence_contract:
            if not evidence_key:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": f"Transition to {target_state} requires evidence",
                }

            if not self._locker:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": "No evidence locker configured",
                }

            entry = self._locker.retrieve(evidence_key)
            if not entry:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": f"Evidence key {evidence_key} not found in locker",
                }

            if entry.get("type") != edge.evidence_contract.required_type:
                return {
                    "action": "deny",
                    "current_phase": self._current_phase,
                    "message": (
                        f"Evidence type {entry.get('type')} does not match "
                        f"required {edge.evidence_contract.required_type}"
                    ),
                }

            # 3. Run gate
            gate_cls = GATE_REGISTRY.get(edge.evidence_contract.gate)
            if gate_cls:
                gate = gate_cls()
                result = gate.validate([evidence_key], self._locker)
                if result.verdict == GateVerdict.FAIL:
                    return {
                        "action": "deny",
                        "current_phase": self._current_phase,
                        "message": result.message or f"Gate {edge.evidence_contract.gate} denied transition",
                    }

        # 4. Transition
        from_state = self._current_phase
        self._current_phase = target_state
        self._save_phase()

        return {
            "action": "allow",
            "from_state": from_state,
            "to_state": target_state,
            "current_phase": self._current_phase,
            "message": None,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_engine.py -xvs`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/engine.py tests/test_v4_engine.py
git commit -m "feat(v4): add GovernorV4 engine with want_to_transition()"
```

---

## Task 7: JSON Machine Loader

**Files:**
- Create: `governor_v4/loader.py`
- Test: `tests/test_v4_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_loader.py
import json
import tempfile
import pytest
from governor_v4.loader import load_machine_from_json
from governor_v4.config import MachineConfig

SIMPLE_MACHINE = json.dumps({
    "name": "tdd",
    "description": "TDD cycle",
    "nodes": [
        {
            "name": "writing_tests",
            "initial": True,
            "blocked_tools": ["Write", "Edit"],
            "allowed_exceptions": ["Write(test_*)", "Edit(test_*)"],
            "capture": [
                {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"}
            ],
        },
        {"name": "fixing_tests"},
    ],
    "edges": [
        {
            "from": "writing_tests", "to": "fixing_tests",
            "evidence_contract": {"required_type": "pytest_output", "gate": "pytest_fail_gate"},
        },
        {"from": "fixing_tests", "to": "writing_tests"},
    ],
})


class TestLoadFromString:
    def test_load_basic(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        assert isinstance(config, MachineConfig)
        assert config.name == "tdd"
        assert len(config.nodes) == 2
        assert len(config.edges) == 2

    def test_node_capture_rules(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        wt = next(n for n in config.nodes if n.name == "writing_tests")
        assert len(wt.capture) == 1
        assert wt.capture[0].tool_pattern == "Bash(pytest*)"
        assert wt.capture[0].evidence_type == "pytest_output"

    def test_edge_with_contract(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        edge = config.find_edge("writing_tests", "fixing_tests")
        assert edge.evidence_contract is not None
        assert edge.evidence_contract.required_type == "pytest_output"
        assert edge.evidence_contract.gate == "pytest_fail_gate"

    def test_edge_without_contract(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        edge = config.find_edge("fixing_tests", "writing_tests")
        assert edge.evidence_contract is None

    def test_node_defaults(self):
        config = load_machine_from_json(SIMPLE_MACHINE)
        ft = next(n for n in config.nodes if n.name == "fixing_tests")
        assert ft.blocked_tools == []
        assert ft.allowed_exceptions == []
        assert ft.capture == []


class TestLoadFromFile:
    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(SIMPLE_MACHINE)
            f.flush()
            config = load_machine_from_json(f.name, from_file=True)
            assert config.name == "tdd"


class TestValidation:
    def test_duplicate_nodes(self):
        bad = json.dumps({
            "name": "bad", "description": "",
            "nodes": [{"name": "a", "initial": True}, {"name": "a"}],
            "edges": [],
        })
        with pytest.raises(ValueError, match="duplicate node"):
            load_machine_from_json(bad)

    def test_edge_references_nonexistent_node(self):
        bad = json.dumps({
            "name": "bad", "description": "",
            "nodes": [{"name": "a", "initial": True}],
            "edges": [{"from": "a", "to": "nonexistent"}],
        })
        with pytest.raises(ValueError, match="nonexistent"):
            load_machine_from_json(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_loader.py -xvs`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# governor_v4/loader.py
"""Load machines from JSON."""

import json

from governor_v4.config import (
    NodeConfig, EdgeConfig, EvidenceContract, CaptureRule, MachineConfig,
)


def load_machine_from_json(source: str, from_file: bool = False) -> MachineConfig:
    """Parse JSON string or file into MachineConfig. Validates structure."""
    if from_file:
        with open(source) as f:
            data = json.load(f)
    else:
        data = json.loads(source)

    nodes = _parse_nodes(data.get("nodes", []))
    node_names = {n.name for n in nodes}
    edges = _parse_edges(data.get("edges", []), node_names)

    return MachineConfig(
        name=data["name"],
        description=data.get("description", ""),
        nodes=nodes,
        edges=edges,
    )


def _parse_nodes(raw: list[dict]) -> list[NodeConfig]:
    nodes = []
    seen = set()
    for d in raw:
        name = d["name"]
        if name in seen:
            raise ValueError(f"duplicate node: {name}")
        seen.add(name)
        capture = [
            CaptureRule(tool_pattern=c["tool_pattern"], evidence_type=c["evidence_type"])
            for c in d.get("capture", [])
        ]
        nodes.append(NodeConfig(
            name=name,
            initial=d.get("initial", False),
            blocked_tools=d.get("blocked_tools", []),
            allowed_exceptions=d.get("allowed_exceptions", []),
            capture=capture,
        ))
    return nodes


def _parse_edges(raw: list[dict], node_names: set[str]) -> list[EdgeConfig]:
    edges = []
    for d in raw:
        from_s, to_s = d["from"], d["to"]
        if from_s not in node_names:
            raise ValueError(f"edge references nonexistent node: from {from_s}")
        if to_s not in node_names:
            raise ValueError(f"edge references nonexistent node: to {to_s}")

        contract_raw = d.get("evidence_contract")
        contract = None
        if contract_raw:
            contract = EvidenceContract(
                required_type=contract_raw["required_type"],
                gate=contract_raw["gate"],
            )

        edges.append(EdgeConfig(from_state=from_s, to_state=to_s, evidence_contract=contract))
    return edges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_loader.py -xvs`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add governor_v4/loader.py tests/test_v4_loader.py
git commit -m "feat(v4): add JSON machine loader with evidence contract parsing"
```

---

## Task 8: TDD Machine JSON Definition

**Files:**
- Create: `machines/tdd_v4.json`
- Test: `tests/test_v4_tdd_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v4_tdd_config.py
import os
import pytest
from governor_v4.loader import load_machine_from_json

TDD_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")


def test_load_tdd_machine():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert config.name == "tdd"


def test_tdd_has_four_states():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    names = {n.name for n in config.nodes}
    assert names == {"writing_tests", "fixing_tests", "refactoring", "fixing_lint"}


def test_tdd_initial_is_writing_tests():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert config.find_initial_node().name == "writing_tests"


def test_tdd_has_seven_edges():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    assert len(config.edges) == 7


def test_tdd_writing_tests_blocks_write():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "writing_tests")
    assert "Write" in node.blocked_tools
    assert "Edit" in node.blocked_tools
    assert "Write(test_*)" in node.allowed_exceptions


def test_tdd_writing_tests_captures_pytest():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "writing_tests")
    assert len(node.capture) == 1
    assert node.capture[0].tool_pattern == "Bash(pytest*)"
    assert node.capture[0].evidence_type == "pytest_output"


def test_tdd_fixing_tests_captures_pytest_and_lint():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    node = next(n for n in config.nodes if n.name == "fixing_tests")
    types = {c.evidence_type for c in node.capture}
    assert types == {"pytest_output", "lint_output"}


def test_tdd_edge_writing_to_fixing_has_contract():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    edge = config.find_edge("writing_tests", "fixing_tests")
    assert edge is not None
    assert edge.evidence_contract.required_type == "pytest_output"
    assert edge.evidence_contract.gate == "pytest_fail_gate"


def test_tdd_edge_fixing_to_writing_no_contract():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    edge = config.find_edge("fixing_tests", "writing_tests")
    assert edge is not None
    assert edge.evidence_contract is None


def test_tdd_edge_refactoring_to_fixing_lint_has_contract():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    edge = config.find_edge("refactoring", "fixing_lint")
    assert edge is not None
    assert edge.evidence_contract.required_type == "lint_output"
    assert edge.evidence_contract.gate == "lint_fail_gate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_v4_tdd_config.py -xvs`
Expected: FAIL with FileNotFoundError

- [ ] **Step 3: Create machines/tdd_v4.json**

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
            "capture": [
                {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"},
                {"tool_pattern": "Bash(ruff*)", "evidence_type": "lint_output"}
            ]
        },
        {
            "name": "refactoring",
            "capture": [
                {"tool_pattern": "Bash(pytest*)", "evidence_type": "pytest_output"},
                {"tool_pattern": "Bash(ruff*)", "evidence_type": "lint_output"}
            ]
        },
        {
            "name": "fixing_lint",
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_v4_tdd_config.py -xvs`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add machines/tdd_v4.json tests/test_v4_tdd_config.py
git commit -m "feat(v4): add TDD machine JSON with evidence contracts"
```

---

## Task 9: TDD End-to-End Integration Tests

**Files:**
- Create: `tests/test_v4_integration.py`

- [ ] **Step 1: Write the integration tests**

```python
# tests/test_v4_integration.py
import os
import pytest
from governor_v4.loader import load_machine_from_json
from governor_v4.engine import GovernorV4

TDD_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd_v4.json")


@pytest.fixture
def tdd_gov(tmp_path):
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    return GovernorV4(config=config, state_dir=str(tmp_path), session_id="integration")


class TestTDDCycle:
    def test_starts_at_writing_tests(self, tdd_gov):
        assert tdd_gov.current_phase == "writing_tests"

    def test_blocks_production_write(self, tdd_gov):
        result = tdd_gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "block"

    def test_allows_test_write(self, tdd_gov):
        result = tdd_gov.evaluate(tool_name="Write", tool_input={"file_path": "test_auth.py"})
        assert result["action"] == "allow"

    def test_allows_read_always(self, tdd_gov):
        result = tdd_gov.evaluate(tool_name="Read", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"

    def test_full_red_green_refactor_cycle(self, tdd_gov):
        # Red: writing_tests -> fixing_tests (pytest fails)
        key1 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest tests/test_auth.py", output="FAILED test_auth.py::test_login", exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_tests", key1)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "fixing_tests"

        # Green: fixing_tests -> refactoring (pytest passes)
        key2 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest tests/test_auth.py", output="1 passed", exit_code=0,
        )
        result = tdd_gov.want_to_transition("refactoring", key2)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "refactoring"

        # Refactor: refactoring -> writing_tests (pytest still passes)
        key3 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest tests/", output="5 passed", exit_code=0,
        )
        result = tdd_gov.want_to_transition("writing_tests", key3)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "writing_tests"

    def test_refactor_breaks_tests_goes_back(self, tdd_gov):
        # Get to refactoring
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)
        k2 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="1 passed", exit_code=0,
        )
        tdd_gov.want_to_transition("refactoring", k2)

        # Refactoring breaks tests -> back to fixing
        k3 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_tests", k3)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "fixing_tests"

    def test_lint_fail_during_refactor(self, tdd_gov):
        # Get to refactoring
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)
        k2 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="passed", exit_code=0,
        )
        tdd_gov.want_to_transition("refactoring", k2)

        # Lint fails -> fixing_lint
        k3 = tdd_gov.locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check src/", output="Found 3 errors", exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_lint", k3)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "fixing_lint"

        # Lint fixed -> back to refactoring
        k4 = tdd_gov.locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check src/", output="All checks passed", exit_code=0,
        )
        result = tdd_gov.want_to_transition("refactoring", k4)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "refactoring"

    def test_fixing_tests_back_to_writing(self, tdd_gov):
        # Get to fixing_tests
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)

        # Agent decides to write more tests (no evidence needed)
        result = tdd_gov.want_to_transition("writing_tests")
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "writing_tests"

    def test_fixing_tests_allows_all_writes(self, tdd_gov):
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output", tool_name="Bash",
            command="pytest", output="FAILED", exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)
        result = tdd_gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"


class TestTDDDenials:
    def test_no_edge_from_writing_to_refactoring(self, tdd_gov):
        result = tdd_gov.want_to_transition("refactoring")
        assert result["action"] == "deny"
        assert "No edge" in result["message"]

    def test_wrong_evidence_type_denied(self, tdd_gov):
        key = tdd_gov.locker.store(
            evidence_type="lint_output", tool_name="Bash",
            command="ruff check", output="errors", exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_tests", key)
        assert result["action"] == "deny"
        assert "does not match" in result["message"]

    def test_missing_evidence_denied(self, tdd_gov):
        result = tdd_gov.want_to_transition("fixing_tests")
        assert result["action"] == "deny"
        assert "requires evidence" in result["message"]

    def test_nonexistent_key_denied(self, tdd_gov):
        result = tdd_gov.want_to_transition("fixing_tests", "evt_fake")
        assert result["action"] == "deny"
        assert "not found" in result["message"]
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_v4_integration.py -xvs`
Expected: PASS (12 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_v4_integration.py
git commit -m "test(v4): add TDD end-to-end integration tests"
```

---

## Task 10: Final Verification

**Files:** none (verification only)

- [ ] **Step 1: Run all v4 tests**

```bash
pytest tests/test_v4_*.py -xvs
```

Expected: all PASS

- [ ] **Step 2: Run all v2 tests (backward compatibility)**

```bash
pytest tests/test_tdd.py tests/test_governor.py tests/test_gates_base.py tests/test_governor_tdd.py -xvs
```

Expected: all PASS (v2 code is untouched)

- [ ] **Step 3: Run full test suite**

```bash
pytest -xvs
```

Expected: all tests pass, no v3 test files remain, no import errors

- [ ] **Step 4: Verify imports**

```bash
python3 -c "from governor_v4.engine import GovernorV4; print('OK')"
python3 -c "from governor_v4.loader import load_machine_from_json; c = load_machine_from_json('machines/tdd_v4.json', from_file=True); print(c.name, len(c.nodes), len(c.edges))"
```

Expected: prints `OK` then `tdd 4 7`

---

## Verification

After all tasks:

1. `pytest tests/test_v4_*.py -v` — all v4 tests pass
2. `pytest tests/ -v` — full suite passes, no v2 regressions, no v3 leftovers
3. `governor_v3/` directory does not exist
4. `machines/tdd_v4.json` has 4 nodes and 7 edges with evidence contracts
5. Evidence locker stores and retrieves entries correctly
6. `want_to_transition()` validates evidence against edge contracts via gates

## Future Work (not in this plan)

- **Verification-mode gates** — Gates parse actual tool output (e.g., check for FAILED/PASSED in pytest output) instead of just checking type match
- **PostToolUse hook rewrite** — Replace event detection with evidence capture using node capture rules
- **UserPromptSubmit hook** — Parse `/transition` slash command and call engine
- **Evidence locker cleanup** — Garbage collection of old entries
- **Additional machines** — Port feature_development and other machines to v4 format
