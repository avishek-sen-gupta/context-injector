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
        result = tdd_gov.evaluate(
            tool_name="Write", tool_input={"file_path": "main.py"}
        )
        assert result["action"] == "block"

    def test_allows_test_write(self, tdd_gov):
        result = tdd_gov.evaluate(
            tool_name="Write", tool_input={"file_path": "test_auth.py"}
        )
        assert result["action"] == "allow"

    def test_allows_read_always(self, tdd_gov):
        result = tdd_gov.evaluate(tool_name="Read", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"

    def test_full_red_green_refactor_cycle(self, tdd_gov):
        # Red: writing_tests -> fixing_tests (pytest fails)
        key1 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_auth.py",
            output="FAILED test_auth.py::test_login",
            exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_tests", key1)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "fixing_tests"

        # Green: fixing_tests -> refactoring (pytest passes)
        key2 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/test_auth.py",
            output="1 passed",
            exit_code=0,
        )
        result = tdd_gov.want_to_transition("refactoring", key2)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "refactoring"

        # Refactor: refactoring -> writing_tests (pytest still passes)
        key3 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest tests/",
            output="5 passed",
            exit_code=0,
        )
        result = tdd_gov.want_to_transition("writing_tests", key3)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "writing_tests"

    def test_refactor_breaks_tests_goes_back(self, tdd_gov):
        # Get to refactoring
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)
        k2 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="1 passed",
            exit_code=0,
        )
        tdd_gov.want_to_transition("refactoring", k2)

        # Refactoring breaks tests -> back to fixing
        k3 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_tests", k3)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "fixing_tests"

    def test_lint_fail_during_refactor(self, tdd_gov):
        # Get to refactoring
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)
        k2 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="passed",
            exit_code=0,
        )
        tdd_gov.want_to_transition("refactoring", k2)

        # Lint fails -> fixing_lint
        k3 = tdd_gov.locker.store(
            evidence_type="lint_output",
            tool_name="Bash",
            command="ruff check src/",
            output="Found 3 errors",
            exit_code=1,
        )
        result = tdd_gov.want_to_transition("fixing_lint", k3)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "fixing_lint"

        # Lint fixed -> back to refactoring
        k4 = tdd_gov.locker.store(
            evidence_type="lint_output",
            tool_name="Bash",
            command="ruff check src/",
            output="All checks passed",
            exit_code=0,
        )
        result = tdd_gov.want_to_transition("refactoring", k4)
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "refactoring"

    def test_fixing_tests_back_to_writing(self, tdd_gov):
        # Get to fixing_tests
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)

        # Agent decides to write more tests (no evidence needed)
        result = tdd_gov.want_to_transition("writing_tests")
        assert result["action"] == "allow"
        assert tdd_gov.current_phase == "writing_tests"

    def test_fixing_tests_allows_all_writes(self, tdd_gov):
        k1 = tdd_gov.locker.store(
            evidence_type="pytest_output",
            tool_name="Bash",
            command="pytest",
            output="FAILED",
            exit_code=1,
        )
        tdd_gov.want_to_transition("fixing_tests", k1)
        result = tdd_gov.evaluate(
            tool_name="Write", tool_input={"file_path": "main.py"}
        )
        assert result["action"] == "allow"


class TestTDDDenials:
    def test_no_edge_from_writing_to_refactoring(self, tdd_gov):
        result = tdd_gov.want_to_transition("refactoring")
        assert result["action"] == "deny"
        assert "No edge" in result["message"]

    def test_wrong_evidence_type_denied(self, tdd_gov):
        key = tdd_gov.locker.store(
            evidence_type="lint_output",
            tool_name="Bash",
            command="ruff check",
            output="errors",
            exit_code=1,
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
