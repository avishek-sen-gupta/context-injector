"""Evidence gates: validate transition claims against locker evidence."""

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
