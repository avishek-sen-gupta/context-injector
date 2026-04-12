from statemachine import State

from machines.base import GovernedMachine


class SimpleMachine(GovernedMachine):
    """Minimal machine for testing the base class."""

    alpha = State(initial=True)
    beta = State()

    go = alpha.to(beta)
    back = beta.to(alpha)

    SOFTNESS = {"go": 1.0, "back": 0.3}
    CONTEXT = {
        "alpha": ["core/*"],
        "beta": ["conditional/testing-patterns.md"],
    }
    ALLOWED_TOOLS = {
        "alpha": ["*"],
        "beta": ["Edit(test_*)", "Bash(pytest*)"],
    }


def test_get_softness_returns_value():
    sm = SimpleMachine()
    assert sm.get_softness("go") == 1.0
    assert sm.get_softness("back") == 0.3


def test_get_softness_defaults_to_one():
    sm = SimpleMachine()
    assert sm.get_softness("nonexistent") == 1.0


def test_get_context_for_state():
    sm = SimpleMachine()
    assert sm.get_context("alpha") == ["core/*"]
    assert sm.get_context("beta") == ["conditional/testing-patterns.md"]


def test_get_context_returns_empty_for_unknown():
    sm = SimpleMachine()
    assert sm.get_context("unknown") == []


def test_get_allowed_tools():
    sm = SimpleMachine()
    assert sm.get_allowed_tools("beta") == ["Edit(test_*)", "Bash(pytest*)"]


def test_get_allowed_tools_returns_none_when_unconstrained():
    sm = SimpleMachine()
    # alpha has ["*"] which means everything is allowed
    assert sm.get_allowed_tools("alpha") == ["*"]


def test_get_allowed_tools_returns_none_for_unknown():
    sm = SimpleMachine()
    assert sm.get_allowed_tools("unknown") is None


def test_current_state_name():
    sm = SimpleMachine()
    assert sm.current_state_name == "alpha"
    sm.go()
    assert sm.current_state_name == "beta"


def test_available_transition_names():
    sm = SimpleMachine()
    names = sm.available_transition_names
    assert "go" in names
    assert "back" not in names  # can't go back from alpha
