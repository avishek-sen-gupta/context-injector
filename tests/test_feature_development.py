import pytest
from statemachine.exceptions import TransitionNotAllowed

from machines.feature_development import FeatureDevelopment


def test_initial_state_is_planning():
    sm = FeatureDevelopment()
    assert sm.current_state_name == "planning"


def test_happy_path_plan_to_commit():
    sm = FeatureDevelopment()
    sm.begin_impl()
    assert sm.current_state_name == "implementing"
    sm.impl_complete()
    assert sm.current_state_name == "reviewing"
    sm.review_passed()
    assert sm.current_state_name == "committing"


def test_review_fail_returns_to_implementing():
    sm = FeatureDevelopment()
    sm.begin_impl()
    sm.impl_complete()
    sm.review_failed()
    assert sm.current_state_name == "implementing"


def test_review_failed_softness():
    sm = FeatureDevelopment()
    assert sm.get_softness("review_failed") == 0.8


def test_context_for_planning():
    sm = FeatureDevelopment()
    ctx = sm.get_context("planning")
    assert "core/*" in ctx
    assert "conditional/design-principles.md" in ctx


def test_context_for_reviewing():
    sm = FeatureDevelopment()
    ctx = sm.get_context("reviewing")
    assert "conditional/code-review.md" in ctx


def test_cannot_review_from_planning():
    sm = FeatureDevelopment()
    with pytest.raises(TransitionNotAllowed):
        sm.review_passed()


def test_sub_machine_reference():
    sm = FeatureDevelopment()
    assert sm.SUB_MACHINES.get("implementing") == "machines.tdd_cycle.TDDCycle"


def test_session_instructions_present():
    sm = FeatureDevelopment()
    assert len(sm.SESSION_INSTRUCTIONS) > 0
    assert "Feature Development" in sm.SESSION_INSTRUCTIONS
