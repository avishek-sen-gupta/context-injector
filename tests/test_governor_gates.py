# tests/test_governor_gates.py
import json
import os
import pytest

from gates.base import Gate, GateContext, GateResult, GateVerdict
from governor.governor import Governor
from machines.tdd import TDD
from machines.tdd_cycle import TDDCycle
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


class ToggleGate(Gate):
    """Gate whose verdict can be toggled between PASS and FAIL."""
    name = "toggle"
    _verdict = GateVerdict.FAIL

    def evaluate(self, ctx):
        if self._verdict == GateVerdict.PASS:
            return GateResult(GateVerdict.PASS)
        return GateResult(GateVerdict.FAIL, message="lint violations", issues=["violation_1"])

    @classmethod
    def set_pass(cls):
        cls._verdict = GateVerdict.PASS

    @classmethod
    def set_fail(cls):
        cls._verdict = GateVerdict.FAIL


class CheckStateTDD(TDD):
    """TDD subclass that uses ToggleGate for CHECK_STATES."""
    CHECK_STATES = {
        "linting": {
            "gate": ToggleGate,
            "pass_event": "lint_pass",
            "fail_event": "lint_fail",
        },
    }


@pytest.fixture(autouse=False)
def reset_toggle_gate():
    """Reset ToggleGate to FAIL before each test."""
    ToggleGate.set_fail()
    yield
    ToggleGate.set_fail()


@pytest.fixture
def check_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir, reset_toggle_gate):
    return Governor(
        machine=CheckStateTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="checktest",
        session_id="check-session",
    )


class TestCheckStatesLintPass:
    """When lint gate passes in CHECK_STATES, should advance to writing_tests."""

    def _setup_with_files(self, gov):
        """Get to fixing_tests and record a file write so recent_files is populated."""
        gov.trigger_transition("pytest_fail")
        gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/widget.py"},
            "session_id": "check-session",
            "timestamp": "2026-04-13T11:59:00Z",
        })

    def test_lint_pass_goes_to_writing_tests(self, check_governor):
        self._setup_with_files(check_governor)
        ToggleGate.set_pass()
        result = check_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "writing_tests"



class TestCheckStatesLintFail:
    """When lint gate fails in CHECK_STATES, should advance to fixing_lint."""

    def _setup_with_files(self, gov):
        """Get to fixing_tests and record a file write so recent_files is populated."""
        gov.trigger_transition("pytest_fail")
        gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/widget.py"},
            "session_id": "check-session",
            "timestamp": "2026-04-13T11:59:00Z",
        })

    def test_lint_fail_goes_to_fixing_lint(self, check_governor):
        self._setup_with_files(check_governor)
        ToggleGate.set_fail()
        result = check_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "fixing_lint"


    def test_lint_fail_message_in_result(self, check_governor):
        self._setup_with_files(check_governor)
        ToggleGate.set_fail()
        result = check_governor.trigger_transition("pytest_pass")
        assert "lint violations" in result.get("message", "")


class TestCheckStateAuditTrail:
    """Audit entries are written for CHECK_STATES and RECHECK_STATES gate evaluations."""

    def test_check_state_writes_gate_audit(self, check_governor, tmp_audit_dir):
        check_governor.trigger_transition("pytest_fail")
        check_governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/widget.py"},
            "session_id": "check-session",
            "timestamp": "2026-04-13T11:59:00Z",
        })
        ToggleGate.set_fail()
        check_governor.trigger_transition("pytest_pass")
        from governor.audit import read_audit_log
        audit_file = os.path.join(tmp_audit_dir, "check-session.audit.json")
        entries = read_audit_log(audit_file)
        gate_entries = [e for e in entries if e.get("type") == "check_state_gate"]
        assert len(gate_entries) >= 1
        assert gate_entries[0]["gate"] == "toggle"
        assert gate_entries[0]["verdict"] == "fail"

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


class ExitGuardFailTDD(TDD):
    """TDD with a failing exit guard on writing_tests."""
    GUARDS = {}  # Remove event-based guard
    EXIT_GUARDS = {
        "writing_tests": [AlwaysFailGate],
    }
    GATE_SOFTNESS = {
        "always_fail": 0.1,
    }


class ExitGuardPassTDD(TDD):
    """TDD with a passing exit guard on writing_tests."""
    GUARDS = {}
    EXIT_GUARDS = {
        "writing_tests": [AlwaysPassGate],
    }
    GATE_SOFTNESS = {
        "always_pass": 0.1,
    }


class ExitGuardReviewTDD(TDD):
    """TDD with a review exit guard on writing_tests."""
    GUARDS = {}
    EXIT_GUARDS = {
        "writing_tests": [AlwaysReviewGate],
    }
    GATE_SOFTNESS = {
        "always_review": 0.1,
    }


@pytest.fixture
def exit_guard_fail_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=ExitGuardFailTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


@pytest.fixture
def exit_guard_pass_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=ExitGuardPassTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


@pytest.fixture
def exit_guard_review_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir):
    return Governor(
        machine=ExitGuardReviewTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="testhash",
        session_id="test-session",
    )


class TestExitGuardPassInTriggerTransition:
    def test_passing_exit_guard_allows_transition(self, exit_guard_pass_governor):
        result = exit_guard_pass_governor.trigger_transition("pytest_fail")
        assert result["action"] == "allow"
        assert "writing_tests -> fixing_tests" in result["transition"]

    def test_passing_exit_guard_updates_state(self, exit_guard_pass_governor):
        exit_guard_pass_governor.trigger_transition("pytest_fail")
        assert exit_guard_pass_governor.machine.current_state_name == "fixing_tests"


class TestExitGuardFailInTriggerTransition:
    def test_failing_exit_guard_blocks_transition(self, exit_guard_fail_governor):
        result = exit_guard_fail_governor.trigger_transition("pytest_fail")
        assert result["action"] == "challenge"
        assert "blocked by gate" in result["message"]

    def test_failing_exit_guard_does_not_change_state(self, exit_guard_fail_governor):
        exit_guard_fail_governor.trigger_transition("pytest_fail")
        assert exit_guard_fail_governor.machine.current_state_name == "writing_tests"

    def test_exit_guard_only_runs_for_guarded_state(self, tmp_state_dir, tmp_audit_dir, tmp_context_dir):
        """Exit guard on writing_tests should NOT fire when leaving fixing_tests."""
        gov = Governor(
            machine=ExitGuardFailTDD(),
            state_dir=tmp_state_dir,
            audit_dir=tmp_audit_dir,
            context_dir=tmp_context_dir,
            project_hash="testhash",
            session_id="test-session",
        )
        # Bypass exit guard by passing it first
        AlwaysFailGate_orig = AlwaysFailGate.evaluate
        AlwaysFailGate.evaluate = lambda self, ctx: GateResult(GateVerdict.PASS)
        gov.trigger_transition("pytest_fail")  # writing_tests -> fixing_tests
        AlwaysFailGate.evaluate = AlwaysFailGate_orig
        # Now from fixing_tests, exit guard on writing_tests should NOT fire
        result = gov.trigger_transition("pytest_pass")
        assert result["action"] == "allow"


class TestExitGuardReviewInTriggerTransition:
    def test_review_exit_guard_returns_review(self, exit_guard_review_governor):
        result = exit_guard_review_governor.trigger_transition("pytest_fail")
        assert result["action"] == "review"
        assert "review needed" in result["message"]

    def test_review_exit_guard_does_not_change_state(self, exit_guard_review_governor):
        exit_guard_review_governor.trigger_transition("pytest_fail")
        assert exit_guard_review_governor.machine.current_state_name == "writing_tests"

    def test_review_exit_guard_escalates_after_max_attempts(self, exit_guard_review_governor):
        exit_guard_review_governor.trigger_transition("pytest_fail")
        exit_guard_review_governor.trigger_transition("pytest_fail")
        result = exit_guard_review_governor.trigger_transition("pytest_fail")
        assert result["action"] == "allow"


class ToggleGate2(Gate):
    """Second toggleable gate for multi-gate tests."""
    name = "toggle2"
    _verdict = GateVerdict.FAIL

    def evaluate(self, ctx):
        if self._verdict == GateVerdict.PASS:
            return GateResult(GateVerdict.PASS)
        return GateResult(GateVerdict.FAIL, message="reassignment violations", issues=["reassign_1"])

    @classmethod
    def set_pass(cls):
        cls._verdict = GateVerdict.PASS

    @classmethod
    def set_fail(cls):
        cls._verdict = GateVerdict.FAIL


class MultiGateCheckTDD(TDD):
    """TDD subclass with multiple gates in CHECK_STATES."""
    CHECK_STATES = {
        "linting": {
            "gate": [ToggleGate, ToggleGate2],
            "pass_event": "lint_pass",
            "fail_event": "lint_fail",
        },
    }


@pytest.fixture
def multi_gate_governor(tmp_state_dir, tmp_audit_dir, tmp_context_dir, reset_toggle_gate):
    ToggleGate2.set_fail()
    gov = Governor(
        machine=MultiGateCheckTDD(),
        state_dir=tmp_state_dir,
        audit_dir=tmp_audit_dir,
        context_dir=tmp_context_dir,
        project_hash="multitest",
        session_id="multi-session",
    )
    yield gov
    ToggleGate2.set_fail()


class TestMultiGateCheckStates:
    """Multiple gates in CHECK_STATES must all pass for lint_pass."""

    def _setup_with_files(self, gov):
        gov.trigger_transition("pytest_fail")
        gov.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/widget.py"},
            "session_id": "multi-session",
            "timestamp": "2026-04-13T11:59:00Z",
        })

    def test_both_pass_goes_to_writing_tests(self, multi_gate_governor):
        self._setup_with_files(multi_gate_governor)
        ToggleGate.set_pass()
        ToggleGate2.set_pass()
        result = multi_gate_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "writing_tests"

    def test_first_fails_goes_to_fixing_lint(self, multi_gate_governor):
        self._setup_with_files(multi_gate_governor)
        ToggleGate.set_fail()
        ToggleGate2.set_pass()
        result = multi_gate_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "fixing_lint"

    def test_second_fails_goes_to_fixing_lint(self, multi_gate_governor):
        self._setup_with_files(multi_gate_governor)
        ToggleGate.set_pass()
        ToggleGate2.set_fail()
        result = multi_gate_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "fixing_lint"

    def test_both_fail_merges_issues(self, multi_gate_governor):
        self._setup_with_files(multi_gate_governor)
        ToggleGate.set_fail()
        ToggleGate2.set_fail()
        result = multi_gate_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "fixing_lint"
        msg = result.get("message", "")
        assert "lint violations" in msg
        assert "reassignment violations" in msg

    def test_single_gate_backward_compatible(self, check_governor):
        """Single gate (not a list) still works as before."""
        check_governor.trigger_transition("pytest_fail")
        check_governor.evaluate({
            "event": "pre_tool_use",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/widget.py"},
            "session_id": "check-session",
            "timestamp": "2026-04-13T11:59:00Z",
        })
        ToggleGate.set_pass()
        result = check_governor.trigger_transition("pytest_pass")
        assert result["current_state"] == "writing_tests"
