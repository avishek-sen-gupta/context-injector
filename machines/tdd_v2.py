"""TDD v2 state machine: WritingTests → RED → FixingTests → GREEN → WritingTests.

Transitions are driven by pytest results, not voluntary declarations.
RED and GREEN are transient states that auto-advance.
"""

from statemachine import State

from machines.base import GovernedMachine


class TDDv2(GovernedMachine):
    """Pytest-driven TDD cycle with automatic transitions."""

    writing_tests = State(initial=True)
    red = State()
    fixing_tests = State()
    green = State()

    # pytest result transitions (fired by PostToolUse hook)
    pytest_fail = writing_tests.to(red) | fixing_tests.to(red)
    pytest_pass = writing_tests.to(green) | fixing_tests.to(green)

    # Auto-transitions from transient states (fired by governor)
    start_fixing = red.to(fixing_tests)
    start_next_test = green.to(writing_tests)

    SOFTNESS = {
        "pytest_fail": 1.0,
        "pytest_pass": 1.0,
        "start_fixing": 1.0,
        "start_next_test": 1.0,
    }

    CONTEXT = {
        "writing_tests": ["conditional/testing-patterns.md"],
        "red": [],
        "fixing_tests": ["core/*"],
        "green": [],
    }

    ALLOWED_TOOLS = {
        "writing_tests": ["Write(test_*)", "Edit(test_*)", "Read", "Bash(pytest*)"],
        "red": ["Read", "Bash(pytest*)"],
        "fixing_tests": ["Edit", "Write", "Read", "Bash(pytest*)"],
        "green": ["Read"],
    }

    # Transient states auto-advance via these transitions
    AUTO_TRANSITIONS = {
        "red": "start_fixing",
        "green": "start_next_test",
    }
