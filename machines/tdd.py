"""TDD state machine: WritingTests → RED → FixingTests → GREEN → WritingTests.

Transitions are driven by pytest results, not voluntary declarations.
RED and GREEN are transient states that auto-advance.
"""

from statemachine import State

from machines.base import GovernedMachine
from gates.lint import LintGate
from gates.test_quality import TestQualityGate


class TDD(GovernedMachine):
    """Pytest-driven TDD cycle with automatic transitions."""

    writing_tests = State(initial=True)
    red = State()
    fixing_tests = State()
    green = State()
    linting = State()
    fixing_lint = State()

    # pytest result transitions (fired by PostToolUse hook)
    pytest_fail = writing_tests.to(red) | fixing_tests.to(red)
    pytest_pass = writing_tests.to(green) | fixing_tests.to(green)

    # Auto-transitions from transient states (fired by governor)
    start_fixing = red.to(fixing_tests)
    start_linting = green.to(linting)

    # Lint transitions (fired by governor CHECK_STATES / RECHECK_STATES)
    lint_pass = linting.to(writing_tests) | fixing_lint.to(writing_tests)
    lint_fail = linting.to(fixing_lint)

    SOFTNESS = {
        "pytest_fail": 1.0,
        "pytest_pass": 1.0,
        "start_fixing": 1.0,
        "start_linting": 1.0,
        "lint_pass": 1.0,
        "lint_fail": 1.0,
    }

    CONTEXT = {
        "writing_tests": ["conditional/testing-patterns.md"],
        "red": [],
        "fixing_tests": ["core/*"],
        "green": [],
        "linting": [],
        "fixing_lint": [],
    }

    # Blocklist: block file-modifying tools where inappropriate.
    # Everything not listed is allowed (Read, Grep, Glob, Agent, etc.).
    # Prefix with ! to create exceptions (e.g. !Write(test_*) = allow Write on test files).
    BLOCKED_TOOLS = {
        "writing_tests": ["Write", "Edit", "!Write(test_*)", "!Edit(test_*)"],
        "red": ["Write", "Edit"],
        "fixing_tests": [],
        "green": ["Write", "Edit"],
        "linting": ["Write", "Edit"],
        "fixing_lint": [],
    }

    # Transient states auto-advance via these transitions
    AUTO_TRANSITIONS = {
        "red": "start_fixing",
        "green": "start_linting",
    }

    GUARDS = {
        "pytest_fail": [TestQualityGate],
    }

    GATE_SOFTNESS = {
        "test_quality": 0.1,
    }

    # Conditional auto-advance: gate runs on entry, result picks transition
    CHECK_STATES = {
        "linting": {
            "gate": LintGate,
            "pass_event": "lint_pass",
            "fail_event": "lint_fail",
        },
    }

    SESSION_INSTRUCTIONS = """\
## TDD Governor — Enforced Workflow

You are operating under an enforced TDD governor. The governor tracks your workflow
phase and **blocks** tool calls that don't match the current phase.

### How It Works

Phase transitions are **automatic** — driven by pytest results and lint checks.

**States:**
- **writing_tests** (start): Write failing tests. Only test files can be created/edited.
- **red**: Transient — auto-advances to fixing_tests after pytest fails.
- **fixing_tests**: Write production code to make tests pass. All files editable.
- **green**: Transient — auto-advances to linting after pytest passes.
- **linting**: Transient — runs ast-grep lint on modified files. Auto-advances to writing_tests (clean) or fixing_lint (violations).
- **fixing_lint**: Fix lint violations. All files editable. Auto-advances to writing_tests when lint passes.

**Cycle:** writing_tests → (pytest fails) → fixing_tests → (pytest passes) → linting → writing_tests
**Lint violations:** linting → fixing_lint → (fix code) → writing_tests

### Rules

1. **Start by writing a test.** You can only create/edit `test_*` files in writing_tests.
2. **Run pytest** to see your test fail. This transitions you to fixing_tests.
3. **Write minimal code** to make the test pass in fixing_tests.
4. **Run pytest** again. When tests pass, lint runs automatically on your modified files.
5. **If lint passes**, you return to writing_tests.
6. **If lint fails**, you enter fixing_lint. Fix the violations — lint re-runs automatically on each tool call.
7. **Production code is blocked** in writing_tests — the governor will reject Write/Edit on non-test files.

### Important

- The governor **blocks** disallowed tools (not just warns)
- Transitions are automatic — pytest results and lint checks drive them
- Lint violations must be fixed before starting the next test cycle"""
