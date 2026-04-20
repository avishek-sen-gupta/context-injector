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
