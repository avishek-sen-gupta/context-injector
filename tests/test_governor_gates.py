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
