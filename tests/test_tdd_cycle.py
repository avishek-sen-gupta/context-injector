import pytest
from statemachine.exceptions import TransitionNotAllowed

from machines.tdd_cycle import TDDCycle


def test_initial_state_is_red():
    sm = TDDCycle()
    assert sm.current_state_name == "red"


def test_happy_path_red_green_refactor():
    sm = TDDCycle()
    sm.test_written()
    assert sm.current_state_name == "green"
    sm.test_passes()
    assert sm.current_state_name == "refactor"
    sm.refactor_done()
    assert sm.current_state_name == "red"


def test_softness_happy_path_is_high():
    sm = TDDCycle()
    assert sm.get_softness("test_written") == 1.0
    assert sm.get_softness("test_passes") == 1.0
    assert sm.get_softness("refactor_done") == 1.0


def test_test_was_wrong_goes_back_to_red():
    sm = TDDCycle()
    sm.test_written()
    assert sm.current_state_name == "green"
    sm.test_was_wrong()
    assert sm.current_state_name == "red"


def test_test_was_wrong_softness_is_medium():
    sm = TDDCycle()
    assert sm.get_softness("test_was_wrong") == 0.5


def test_docs_detour_from_red():
    sm = TDDCycle()
    sm.need_docs()
    assert sm.current_state_name == "docs_detour"
    assert sm.get_softness("need_docs") == 0.2


def test_docs_detour_returns_to_red():
    sm = TDDCycle()
    sm.need_docs()
    sm.docs_done()
    assert sm.current_state_name == "red"


def test_cannot_refactor_from_red():
    sm = TDDCycle()
    with pytest.raises(TransitionNotAllowed):
        sm.refactor_done()


def test_context_for_states():
    sm = TDDCycle()
    assert sm.get_context("red") == ["conditional/testing-patterns.md"]
    assert sm.get_context("refactor") == ["conditional/refactoring.md"]


def test_allowed_tools_for_red():
    sm = TDDCycle()
    allowed = sm.get_allowed_tools("red")
    assert allowed is not None
    assert "Edit(test_*)" in allowed
