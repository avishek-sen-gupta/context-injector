import pytest
from governor_v3.engine import GovernorV3
from governor_v3.config import MachineConfig, NodeConfig, EdgeConfig


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
            ),
            NodeConfig(name="fixing_tests"),
        ],
        edges=[
            EdgeConfig(from_state="writing_tests", to_state="fixing_tests", trigger="pytest_fail"),
        ],
    )


class TestEvaluate:
    def test_creation(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        assert gov.current_phase == "writing_tests"

    def test_allowed_tool(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        result = gov.evaluate(tool_name="Read", tool_input={"file_path": "/project/test.py"})
        assert result["action"] == "allow"
        assert result["current_phase"] == "writing_tests"

    def test_blocked_tool(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        result = gov.evaluate(tool_name="Write", tool_input={"file_path": "/project/main.py"})
        assert result["action"] == "block"
        assert "blocked" in result["message"].lower()

    def test_exception_allows(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        result = gov.evaluate(tool_name="Write", tool_input={"file_path": "test_auth.py"})
        assert result["action"] == "allow"

    def test_evaluate_after_trigger(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        gov.trigger("pytest_fail")
        result = gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"  # fixing_tests has no blocklist
