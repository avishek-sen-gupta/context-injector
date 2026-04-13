"""TDD state machine: WritingTests → RED → FixingTests → GREEN → WritingTests.

Transitions are driven by pytest results, not voluntary declarations.
RED and GREEN are transient states that auto-advance.
"""

from statemachine import State

from machines.base import GovernedMachine


class TDD(GovernedMachine):
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

    # Blocklist: block file-modifying tools where inappropriate.
    # Everything not listed is allowed (Read, Grep, Glob, Agent, etc.).
    # Prefix with ! to create exceptions (e.g. !Write(test_*) = allow Write on test files).
    BLOCKED_TOOLS = {
        "writing_tests": ["Write", "Edit", "!Write(test_*)", "!Edit(test_*)"],
        "red": ["Write", "Edit"],
        "fixing_tests": [],
        "green": ["Write", "Edit"],
    }

    # Transient states auto-advance via these transitions
    AUTO_TRANSITIONS = {
        "red": "start_fixing",
        "green": "start_next_test",
    }

    SESSION_INSTRUCTIONS = """\
## TDD Governor — Enforced Workflow

You are operating under an enforced TDD governor. The governor tracks your workflow
phase and **blocks** tool calls that don't match the current phase.

### How It Works

Phase transitions are **automatic** — driven by pytest results, not manual declarations.

**States:**
- **writing_tests** (start): Write failing tests. Only test files can be created/edited.
- **red**: Transient — auto-advances to fixing_tests after pytest fails.
- **fixing_tests**: Write production code to make tests pass. All files editable.
- **green**: Transient — auto-advances to writing_tests after pytest passes.

**Cycle:** writing_tests → (pytest fails) → fixing_tests → (pytest passes) → writing_tests

### Rules

1. **Start by writing a test.** You can only create/edit `test_*` files in writing_tests.
2. **Run pytest** to see your test fail. This transitions you to fixing_tests.
3. **Write minimal code** to make the test pass in fixing_tests.
4. **Run pytest** again. When tests pass, you return to writing_tests.
5. **Production code is blocked** in writing_tests — the governor will reject Write/Edit on non-test files.

### Important

- The governor **blocks** disallowed tools (not just warns)
- You do NOT need to declare phase transitions — pytest results drive them automatically
- If blocked, check which state you're in and follow the TDD cycle"""
