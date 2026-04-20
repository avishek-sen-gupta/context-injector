import pytest
from governor_v3.engine import GovernorV3
from governor_v3.config import MachineConfig, NodeConfig, EdgeConfig, GateConfig


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


class TestTrigger:
    def test_simple_transition(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        result = gov.trigger("pytest_fail")
        assert result["to_state"] == "fixing_tests"
        assert gov.current_phase == "fixing_tests"

    def test_auto_advance(self):
        """Transient state (red) auto-advances to fixing_tests."""
        machine = MachineConfig(
            name="tdd", description="",
            nodes=[
                NodeConfig(name="writing_tests", initial=True),
                NodeConfig(name="red", auto_transition="start_fixing"),
                NodeConfig(name="fixing_tests"),
            ],
            edges=[
                EdgeConfig(from_state="writing_tests", to_state="red", trigger="pytest_fail"),
                EdgeConfig(from_state="red", to_state="fixing_tests", trigger="start_fixing"),
            ],
        )
        gov = GovernorV3(config=machine, session_id="t")
        result = gov.trigger("pytest_fail")
        assert gov.current_phase == "fixing_tests"
        assert result["auto_advanced"] is True

    def test_chained_auto_advance(self):
        """Two transient states auto-advance in sequence."""
        machine = MachineConfig(
            name="test", description="",
            nodes=[
                NodeConfig(name="a", initial=True),
                NodeConfig(name="b", auto_transition="go_c"),
                NodeConfig(name="c", auto_transition="go_d"),
                NodeConfig(name="d"),
            ],
            edges=[
                EdgeConfig(from_state="a", to_state="b", trigger="start"),
                EdgeConfig(from_state="b", to_state="c", trigger="go_c"),
                EdgeConfig(from_state="c", to_state="d", trigger="go_d"),
            ],
        )
        gov = GovernorV3(config=machine, session_id="t")
        result = gov.trigger("start")
        assert gov.current_phase == "d"

    def test_invalid_trigger_raises(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        with pytest.raises(ValueError, match="No transition"):
            gov.trigger("nonexistent")

    def test_trigger_from_wrong_state_raises(self):
        gov = GovernorV3(config=make_simple_machine(), session_id="t")
        gov.trigger("pytest_fail")  # -> fixing_tests
        with pytest.raises(ValueError, match="No transition"):
            gov.trigger("pytest_fail")  # no edge from fixing_tests with this trigger


class TestExitGates:
    def test_exit_gate_runs_and_allows_transition(self, tmp_path):
        """Exit gate infrastructure works and allows transition when gate returns PASS."""
        machine = MachineConfig(
            name="test", description="",
            nodes=[
                NodeConfig(name="writing_tests", initial=True),
                NodeConfig(name="red"),
            ],
            edges=[
                EdgeConfig(from_state="writing_tests", to_state="red", trigger="pytest_fail"),
            ],
            gates=[
                GateConfig(
                    name="test_quality",
                    applies_to=["writing_tests"],
                    trigger="on_exit",
                    gate_names=["test_quality"],
                    policy="strict",
                ),
            ],
        )
        gov = GovernorV3(config=machine, project_root=str(tmp_path), session_id="t")
        result = gov.trigger("pytest_fail")
        # test_quality returns PASS when there are no test files in recent_files
        assert result["to_state"] == "red"
        assert gov.current_phase == "red"


class TestEnterGates:
    def test_enter_gate_routes_on_pass(self):
        """on_enter gate routes to pass_event transition when gate passes."""
        machine = MachineConfig(
            name="test", description="",
            nodes=[
                NodeConfig(name="fixing_tests", initial=True),
                NodeConfig(name="green", auto_transition="start_linting"),
                NodeConfig(name="linting"),
                NodeConfig(name="writing_tests"),
                NodeConfig(name="fixing_lint"),
            ],
            edges=[
                EdgeConfig(from_state="fixing_tests", to_state="green", trigger="pytest_pass"),
                EdgeConfig(from_state="green", to_state="linting", trigger="start_linting"),
                EdgeConfig(from_state="linting", to_state="writing_tests", trigger="lint_pass"),
                EdgeConfig(from_state="linting", to_state="fixing_lint", trigger="lint_fail"),
            ],
            gates=[
                GateConfig(
                    name="lint_check",
                    applies_to=["linting"],
                    trigger="on_enter",
                    gate_names=["lint", "reassignment"],
                    policy="strict",
                    routes={"pass": "lint_pass", "fail": "lint_fail"},
                ),
            ],
        )
        gov = GovernorV3(config=machine, project_root=".", session_id="t")
        result = gov.trigger("pytest_pass")
        # Lint and reassignment gates pass with empty recent_files -> routes to lint_pass
        # Then auto_advance triggers start_linting from green -> linting, which enters linting
        # Gates route to lint_pass, auto_advance takes that route -> writing_tests
        assert gov.current_phase == "writing_tests"
