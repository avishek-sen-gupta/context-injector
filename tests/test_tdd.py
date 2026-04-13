import pytest
from statemachine.exceptions import TransitionNotAllowed

from machines.tdd import TDD
from gates.lint import LintGate
from gates.reassignment import ReassignmentGate
from gates.test_quality import TestQualityGate


class TestStates:
    def test_initial_state_is_writing_tests(self):
        sm = TDD()
        assert sm.current_state_name == "writing_tests"

    def test_six_states_exist(self):
        sm = TDD()
        state_names = {s.id for s in sm.states}
        assert state_names == {
            "writing_tests", "red", "fixing_tests", "green",
            "linting", "fixing_lint",
        }


class TestTransitions:
    def test_writing_tests_to_red_on_pytest_fail(self):
        sm = TDD()
        sm.pytest_fail()
        assert sm.current_state_name == "red"

    def test_writing_tests_to_green_on_pytest_pass(self):
        sm = TDD()
        sm.pytest_pass()
        assert sm.current_state_name == "green"

    def test_red_to_fixing_tests(self):
        sm = TDD()
        sm.pytest_fail()  # → red
        sm.start_fixing()
        assert sm.current_state_name == "fixing_tests"

    def test_fixing_tests_to_red_on_pytest_fail(self):
        sm = TDD()
        sm.pytest_fail()  # → red
        sm.start_fixing()  # → fixing_tests
        sm.pytest_fail()
        assert sm.current_state_name == "red"

    def test_fixing_tests_to_green_on_pytest_pass(self):
        sm = TDD()
        sm.pytest_fail()  # → red
        sm.start_fixing()  # → fixing_tests
        sm.pytest_pass()
        assert sm.current_state_name == "green"

    def test_green_to_linting(self):
        sm = TDD()
        sm.pytest_pass()  # → green
        sm.start_linting()
        assert sm.current_state_name == "linting"

    def test_linting_to_writing_tests_on_lint_pass(self):
        sm = TDD()
        sm.pytest_pass()  # → green
        sm.start_linting()  # → linting
        sm.lint_pass()
        assert sm.current_state_name == "writing_tests"

    def test_linting_to_fixing_lint_on_lint_fail(self):
        sm = TDD()
        sm.pytest_pass()  # → green
        sm.start_linting()  # → linting
        sm.lint_fail()
        assert sm.current_state_name == "fixing_lint"

    def test_fixing_lint_to_writing_tests_on_lint_pass(self):
        sm = TDD()
        sm.pytest_pass()  # → green
        sm.start_linting()  # → linting
        sm.lint_fail()  # → fixing_lint
        sm.lint_pass()
        assert sm.current_state_name == "writing_tests"

    def test_full_cycle(self):
        """WritingTests → RED → FixingTests → GREEN → Linting → WritingTests"""
        sm = TDD()
        sm.pytest_fail()       # writing_tests → red
        sm.start_fixing()      # red → fixing_tests
        sm.pytest_fail()       # fixing_tests → red (still failing)
        sm.start_fixing()      # red → fixing_tests (try again)
        sm.pytest_pass()       # fixing_tests → green
        sm.start_linting()     # green → linting
        sm.lint_pass()         # linting → writing_tests
        assert sm.current_state_name == "writing_tests"

    def test_full_cycle_with_lint_failure(self):
        """Full cycle where lint fails and must be fixed."""
        sm = TDD()
        sm.pytest_fail()       # writing_tests → red
        sm.start_fixing()      # red → fixing_tests
        sm.pytest_pass()       # fixing_tests → green
        sm.start_linting()     # green → linting
        sm.lint_fail()         # linting → fixing_lint
        sm.lint_pass()         # fixing_lint → writing_tests
        assert sm.current_state_name == "writing_tests"

    def test_cannot_go_from_writing_tests_to_fixing_tests(self):
        sm = TDD()
        with pytest.raises(TransitionNotAllowed):
            sm.start_fixing()

    def test_cannot_go_from_red_to_green(self):
        sm = TDD()
        sm.pytest_fail()  # → red
        with pytest.raises(TransitionNotAllowed):
            sm.pytest_pass()

    def test_cannot_go_from_fixing_tests_to_linting(self):
        sm = TDD()
        sm.pytest_fail()
        sm.start_fixing()
        with pytest.raises(TransitionNotAllowed):
            sm.start_linting()


class TestBlockedTools:
    def test_writing_tests_blocks_production_writes(self):
        sm = TDD()
        blocked = sm.get_blocked_tools("writing_tests")
        assert "Write" in blocked
        assert "Edit" in blocked

    def test_writing_tests_excepts_test_files(self):
        sm = TDD()
        blocked = sm.get_blocked_tools("writing_tests")
        assert "!Write(test_*)" in blocked
        assert "!Edit(test_*)" in blocked

    def test_red_blocks_writes(self):
        sm = TDD()
        blocked = sm.get_blocked_tools("red")
        assert "Write" in blocked
        assert "Edit" in blocked

    def test_fixing_tests_blocks_nothing(self):
        sm = TDD()
        blocked = sm.get_blocked_tools("fixing_tests")
        assert blocked == []

    def test_green_blocks_writes(self):
        sm = TDD()
        blocked = sm.get_blocked_tools("green")
        assert "Write" in blocked
        assert "Edit" in blocked


class TestContext:
    def test_writing_tests_injects_testing_patterns(self):
        sm = TDD()
        ctx = sm.get_context("writing_tests")
        assert "conditional/testing-patterns.md" in ctx

    def test_fixing_tests_injects_core(self):
        sm = TDD()
        ctx = sm.get_context("fixing_tests")
        assert "core/*" in ctx

    def test_green_injects_nothing(self):
        sm = TDD()
        ctx = sm.get_context("green")
        assert ctx == []


class TestAutoTransitions:
    def test_red_is_marked_transient(self):
        sm = TDD()
        assert "red" in sm.AUTO_TRANSITIONS

    def test_green_is_marked_transient(self):
        sm = TDD()
        assert "green" in sm.AUTO_TRANSITIONS

    def test_auto_transition_from_red(self):
        sm = TDD()
        assert sm.AUTO_TRANSITIONS["red"] == "start_fixing"

    def test_auto_transition_from_green(self):
        sm = TDD()
        assert sm.AUTO_TRANSITIONS["green"] == "start_linting"


class TestSoftness:
    def test_happy_path_softness_is_high(self):
        sm = TDD()
        assert sm.get_softness("pytest_fail") == 1.0
        assert sm.get_softness("pytest_pass") == 1.0
        assert sm.get_softness("start_fixing") == 1.0
        assert sm.get_softness("start_linting") == 1.0
        assert sm.get_softness("lint_pass") == 1.0
        assert sm.get_softness("lint_fail") == 1.0


class TestSessionInstructions:
    def test_has_session_instructions(self):
        sm = TDD()
        assert len(sm.SESSION_INSTRUCTIONS) > 0

    def test_instructions_mention_tdd(self):
        sm = TDD()
        assert "TDD" in sm.SESSION_INSTRUCTIONS

    def test_instructions_mention_writing_tests(self):
        sm = TDD()
        assert "writing_tests" in sm.SESSION_INSTRUCTIONS

    def test_instructions_mention_pytest(self):
        sm = TDD()
        assert "pytest" in sm.SESSION_INSTRUCTIONS


class TestGuards:
    def test_tdd_has_guards_for_pytest_fail(self):
        m = TDD()
        guards = m.get_guards("pytest_fail")
        assert TestQualityGate in guards

    def test_tdd_has_gate_softness_for_test_quality(self):
        m = TDD()
        softness = m.get_gate_softness("test_quality")
        assert softness == 0.1

    def test_lint_gate_in_check_states(self):
        m = TDD()
        assert "linting" in m.CHECK_STATES
        assert m.CHECK_STATES["linting"]["gate"] == [LintGate, ReassignmentGate]
        assert m.CHECK_STATES["linting"]["pass_event"] == "lint_pass"
        assert m.CHECK_STATES["linting"]["fail_event"] == "lint_fail"

