"""Feature Development state machine: Plan → Implement → Review → Commit.

The outer workflow loop. The 'implementing' state delegates to a TDD cycle
sub-machine managed by the governor.
"""

from statemachine import State

from machines.base import GovernedMachine


class FeatureDevelopment(GovernedMachine):
    """Outer feature development loop."""

    planning = State(initial=True)
    implementing = State()
    reviewing = State()
    committing = State(final=True)

    begin_impl = planning.to(implementing)
    impl_complete = implementing.to(reviewing)
    review_passed = reviewing.to(committing)
    review_failed = reviewing.to(implementing)

    SOFTNESS = {
        "begin_impl": 1.0,
        "impl_complete": 1.0,
        "review_passed": 1.0,
        "review_failed": 0.8,
    }

    CONTEXT = {
        "planning": ["core/*", "conditional/design-principles.md"],
        "implementing": [],
        "reviewing": ["core/*", "conditional/code-review.md"],
        "committing": ["core/*"],
    }

    PRECONDITIONS = {
        "begin_impl": ["Read(*)", "Bash(*)"],
        "impl_complete": ["Edit(*)", "Write(*)"],
        "review_passed": ["Read(*)", "Bash(*)"],
    }

    # Maps state names to dotted-path sub-machine classes.
    # The governor instantiates these when entering the state.
    SUB_MACHINES = {
        "implementing": "machines.tdd.TDD",
    }

    SESSION_INSTRUCTIONS = """\
## Feature Development Governor

You are operating under an enforced feature development governor. The governor
tracks your workflow phase and constrains which tools are available.

### How It Works

Phase transitions are **declaration-based** — you declare transitions via
`echo '{"declare_phase": "<target>"}'`.

**States:**
- **planning** (start): Read code, explore the codebase, plan your approach.
- **implementing**: Write code using TDD. All files are editable.
- **reviewing**: Review the changes. Read files and run tests.
- **committing** (final): Commit the work.

**Cycle:** planning → implementing → reviewing → committing

### Rules

1. **Start by planning.** Read relevant files and understand the codebase.
2. **Declare implementing** when ready to write code.
3. **Write code** following TDD practices.
4. **Declare reviewing** when implementation is complete.
5. **Review** by reading files and running tests. If issues found, declare implementing.
6. **Declare committing** when review passes.

### Important

- Some transitions have **preconditions** — you must use specific tools before declaring.
- Review failures send you back to implementing."""
