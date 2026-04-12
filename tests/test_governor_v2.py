"""Tests for governor with TDDv2 machine (auto-transitions, pytest-driven)."""

import json
import os

import pytest

from governor.governor import Governor
from machines.tdd_v2 import TDDv2


@pytest.fixture
def governor_v2(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=TDDv2(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="v2test",
        session_id="v2-session",
    )


class TestWritingTestsState:
    def test_starts_in_writing_tests(self, governor_v2):
        result = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Read",
            "tool_input": {"file_path": "/project/README.md"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:00:00Z",
        })
        assert result["current_state"] == "writing_tests"

    def test_allows_writing_test_files(self, governor_v2):
        result = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/test_math.py"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:00:00Z",
        })
        assert result["action"] == "allow"

    def test_blocks_writing_production_code(self, governor_v2):
        result = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/math_utils.py"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:00:00Z",
        })
        assert result["action"] == "challenge"


class TestPytestTransitions:
    def test_pytest_fail_transitions_to_fixing_tests(self, governor_v2):
        """pytest fail in writing_tests → red → auto → fixing_tests."""
        result = governor_v2.trigger_transition("pytest_fail")
        # Should auto-advance through red to fixing_tests
        assert result["current_state"] == "fixing_tests"

    def test_pytest_pass_transitions_to_writing_tests(self, governor_v2):
        """pytest pass in writing_tests → green → auto → writing_tests."""
        result = governor_v2.trigger_transition("pytest_pass")
        # Should auto-advance through green back to writing_tests
        assert result["current_state"] == "writing_tests"

    def test_fixing_tests_pytest_fail_goes_to_red_then_fixing(self, governor_v2):
        """In fixing_tests, pytest fail → red → auto → fixing_tests."""
        governor_v2.trigger_transition("pytest_fail")  # → fixing_tests
        result = governor_v2.trigger_transition("pytest_fail")  # → red → fixing_tests
        assert result["current_state"] == "fixing_tests"

    def test_fixing_tests_pytest_pass_goes_to_green_then_writing(self, governor_v2):
        """In fixing_tests, pytest pass → green → auto → writing_tests."""
        governor_v2.trigger_transition("pytest_fail")  # → fixing_tests
        result = governor_v2.trigger_transition("pytest_pass")  # → green → writing_tests
        assert result["current_state"] == "writing_tests"


class TestFullCycle:
    def test_complete_tdd_cycle(self, governor_v2):
        """Write test → fail → fix → fail → fix → pass → back to writing tests."""
        # 1. Write a test file (allowed in writing_tests)
        r = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/test_calc.py"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:00:00Z",
        })
        assert r["action"] == "allow"
        assert r["current_state"] == "writing_tests"

        # 2. pytest fails → red → fixing_tests
        r = governor_v2.trigger_transition("pytest_fail")
        assert r["current_state"] == "fixing_tests"

        # 3. Write production code (allowed in fixing_tests)
        r = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/calc.py"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:01:00Z",
        })
        assert r["action"] == "allow"

        # 4. pytest still fails → red → fixing_tests
        r = governor_v2.trigger_transition("pytest_fail")
        assert r["current_state"] == "fixing_tests"

        # 5. Edit production code again
        r = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/project/calc.py"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:02:00Z",
        })
        assert r["action"] == "allow"

        # 6. pytest passes → green → writing_tests
        r = governor_v2.trigger_transition("pytest_pass")
        assert r["current_state"] == "writing_tests"

        # 7. Back to writing tests — production code blocked again
        r = governor_v2.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/calc.py"},
            "session_id": "v2-session",
            "timestamp": "2026-04-13T12:03:00Z",
        })
        assert r["action"] == "challenge"


class TestAutoTransitionContext:
    def test_context_injected_on_transition_to_fixing_tests(self, governor_v2):
        """Transitioning to fixing_tests should inject core/* context."""
        result = governor_v2.trigger_transition("pytest_fail")
        assert result["current_state"] == "fixing_tests"
        assert len(result["context_to_inject"]) > 0

    def test_context_injected_on_return_to_writing_tests(self, governor_v2):
        """Returning to writing_tests should inject testing-patterns context."""
        # Go through a full cycle
        governor_v2.trigger_transition("pytest_fail")  # → fixing_tests
        result = governor_v2.trigger_transition("pytest_pass")  # → writing_tests
        assert result["current_state"] == "writing_tests"
        assert len(result["context_to_inject"]) > 0


class TestStatePersistence:
    def test_state_persisted_after_auto_transition(self, governor_v2, tmp_state_dir):
        """State file should show the final state after auto-transition."""
        governor_v2.trigger_transition("pytest_fail")  # → fixing_tests
        state_file = os.path.join(tmp_state_dir, "v2test.json")
        with open(state_file) as f:
            state = json.load(f)
        assert state["inner_state"] == "fixing_tests"


class TestAuditTrail:
    def test_auto_transition_creates_audit_entries(self, governor_v2, tmp_audit_dir):
        """Auto-transition should write audit entries for both transitions."""
        governor_v2.trigger_transition("pytest_fail")  # writing_tests → red → fixing_tests
        audit_file = os.path.join(tmp_audit_dir, "v2-session.jsonl")
        with open(audit_file) as f:
            entries = [json.loads(line) for line in f if line.strip()]
        # Should have entries for: writing_tests→red and red→fixing_tests
        assert len(entries) >= 2
        assert entries[0]["from_state"] == "writing_tests"
        assert entries[-1]["to_state"] == "fixing_tests"
