import os
import pytest
from governor_v3.loader import load_machine_from_json
from governor_v3.engine import GovernorV3

TDD_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd.json")


@pytest.fixture
def tdd_gov():
    config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
    return GovernorV3(config=config, project_root=".", session_id="tdd-test")


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

    def test_pytest_fail_goes_to_fixing_tests(self, tdd_gov):
        tdd_gov.trigger("pytest_fail")
        assert tdd_gov.current_phase == "fixing_tests"

    def test_fixing_tests_allows_all_writes(self, tdd_gov):
        tdd_gov.trigger("pytest_fail")
        result = tdd_gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"

    def test_pytest_pass_goes_to_linting(self, tdd_gov):
        tdd_gov.trigger("pytest_fail")  # → fixing_tests
        tdd_gov.trigger("pytest_pass")  # → green → linting (or writing_tests via lint_pass)
        assert tdd_gov.current_phase in ("linting", "writing_tests", "fixing_lint")

    def test_add_tests_returns_to_writing_tests(self, tdd_gov):
        tdd_gov.trigger("pytest_fail")  # → fixing_tests
        tdd_gov.trigger("add_tests")   # → writing_tests
        assert tdd_gov.current_phase == "writing_tests"

    def test_linting_blocks_write(self, tdd_gov):
        tdd_gov._current_phase = "linting"
        result = tdd_gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "block"

    def test_fixing_lint_allows_write(self, tdd_gov):
        tdd_gov._current_phase = "fixing_lint"
        result = tdd_gov.evaluate(tool_name="Write", tool_input={"file_path": "main.py"})
        assert result["action"] == "allow"


class TestTDDErrors:
    def test_invalid_trigger_raises(self, tdd_gov):
        with pytest.raises(ValueError, match="No transition"):
            tdd_gov.trigger("nonexistent")

    def test_cannot_pytest_fail_from_green(self, tdd_gov):
        tdd_gov._current_phase = "green"
        with pytest.raises(ValueError, match="No transition"):
            tdd_gov.trigger("pytest_fail")

    def test_cannot_add_tests_from_writing_tests(self, tdd_gov):
        with pytest.raises(ValueError, match="No transition"):
            tdd_gov.trigger("add_tests")
