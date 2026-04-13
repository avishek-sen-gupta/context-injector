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

    SESSION_INSTRUCTIONS = """\
## TDD Cycle Governor — Red/Green/Refactor

You are operating under an enforced TDD cycle governor. The governor tracks your
workflow phase and constrains which tools are available.

### How It Works

Phase transitions are **declaration-based** — you declare transitions via
`echo '{"declare_phase": "<target>"}'`.

**States:**
- **red** (start): Write a failing test. Only test files can be created/edited.
- **green**: Make the test pass. Production code is editable.
- **refactor**: Clean up. All code is editable.
- **docs_detour**: Deviation for documentation work.

**Cycle:** red → green → refactor → red

### Rules

1. **Start in red.** Write a failing test using `Write(test_*)` or `Edit(test_*)`.
2. **Declare green** when your test is written and pytest confirms it fails.
3. **Write minimal code** to make the test pass.
4. **Declare refactor** once pytest passes.
5. **Refactor**, then declare red to start the next cycle.

### Important

- Some transitions have **preconditions** — you must use specific tools before declaring.
- Low-softness transitions (docs_detour) will be **challenged** — justify the deviation."""
