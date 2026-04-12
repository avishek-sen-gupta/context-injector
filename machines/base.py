"""Base class for state machines governed by the context-injector governor.

Subclasses define SOFTNESS, CONTEXT, and ALLOWED_TOOLS as class-level dicts.
The governor uses these to decide what action to take and which context to inject.
"""

from statemachine import StateMachine


class GovernedMachine(StateMachine):
    """Base class adding softness, context, and allowed-tools metadata."""

    SOFTNESS: dict[str, float] = {}
    CONTEXT: dict[str, list[str]] = {}
    ALLOWED_TOOLS: dict[str, list[str]] = {}

    def get_softness(self, transition_name: str) -> float:
        """Return the softness value for a transition. Defaults to 1.0."""
        return self.SOFTNESS.get(transition_name, 1.0)

    def get_context(self, state_name: str) -> list[str]:
        """Return context file patterns for a state. Defaults to []."""
        return self.CONTEXT.get(state_name, [])

    def get_allowed_tools(self, state_name: str) -> list[str] | None:
        """Return allowed tool patterns for a state. None if unconstrained."""
        return self.ALLOWED_TOOLS.get(state_name)

    @property
    def current_state_name(self) -> str:
        """Return the name of the current state."""
        return self.current_state.id

    @property
    def available_transition_names(self) -> list[str]:
        """Return names of transitions available from the current state."""
        state = self.current_state
        return [t.event for t in state.transitions if t.source.id == state.id]
