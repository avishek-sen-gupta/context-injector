"""TDD Cycle state machine: Red → Green → Refactor.

The inner loop of test-driven development. Each state specifies which context
files to inject and which tools are expected.
"""

from statemachine import State

from machines.base import GovernedMachine


class TDDCycle(GovernedMachine):
    """Red → Green → Refactor cycle with deviation support."""

    red = State(initial=True)
    green = State()
    refactor = State()
    docs_detour = State()

    # Happy path
    test_written = red.to(green)
    test_passes = green.to(refactor)
    refactor_done = refactor.to(red)

    # Less expected
    test_was_wrong = green.to(red)
    skip_refactor = green.to(red)

    # Deviations
    need_docs = red.to(docs_detour)
    need_docs_g = green.to(docs_detour)
    docs_done = docs_detour.to(red)

    SOFTNESS = {
        "test_written": 1.0,
        "test_passes": 1.0,
        "refactor_done": 1.0,
        "test_was_wrong": 0.5,
        "skip_refactor": 0.4,
        "need_docs": 0.2,
        "need_docs_g": 0.2,
        "docs_done": 1.0,
    }

    CONTEXT = {
        "red": ["conditional/testing-patterns.md"],
        "green": ["core/*"],
        "refactor": ["conditional/refactoring.md"],
        "docs_detour": ["core/*"],
    }

    ALLOWED_TOOLS = {
        "red": ["Edit(test_*)", "Write(test_*)", "Bash(pytest*)"],
        "green": ["Edit", "Write", "Bash(pytest*)"],
        "refactor": ["Edit", "Write", "Bash(pytest*)"],
        "docs_detour": ["Edit(*.md)", "Write(*.md)"],
    }

    PRECONDITIONS = {
        "test_written": ["Write(test_*)", "Edit(test_*)"],
        "test_passes": ["Bash(pytest*)"],
        "refactor_done": ["Edit(*)", "Write(*)"],
    }
