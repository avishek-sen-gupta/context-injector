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

    # Maps state names to dotted-path sub-machine classes.
    # The governor instantiates these when entering the state.
    SUB_MACHINES = {
        "implementing": "machines.tdd_cycle.TDDCycle",
    }
